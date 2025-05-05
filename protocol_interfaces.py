"""
Protocol & Client Interfaces Layer - Agent-to-Agent (A2A) Protocol and Model Context Protocol (MCP) Client
"""
import uuid
import json
import requests
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field, asdict
from core_dependencies import lru_cache
from aws_service_layer import DynamoDB, S3, retry

# --- Agent-to-Agent (A2A) Protocol ---

@dataclass
class AgentCard:
    """Agent Card specification for agent discovery and capability description"""
    agent_id: str
    name: str
    description: str
    version: str
    capabilities: List[str]
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    auth_required: bool = False
    rate_limit: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self):
        """Convert agent card to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data):
        """Create agent card from dictionary"""
        return cls(**data)

class AgentRegistry:
    """Agent discovery and registration mechanism"""
    def __init__(self, table_name: str, index_name: str = "capabilities-index"):
        self.table_name = table_name
        self.index_name = index_name
    
    def register_agent(self, agent_card: AgentCard) -> bool:
        """Register agent with the registry"""
        try:
            DynamoDB.put(self.table_name, agent_card.to_dict())
            return True
        except Exception as e:
            print(f"Error registering agent: {e}")
            return False
    
    def get_agent(self, agent_id: str) -> Optional[AgentCard]:
        """Get agent by ID"""
        result = DynamoDB.get(self.table_name, {"agent_id": agent_id})
        return AgentCard.from_dict(result) if result else None
    
    def find_agents_by_capability(self, capability: str) -> List[AgentCard]:
        """Find agents with specific capability"""
        results = DynamoDB.query(
            self.table_name,
            "contains(capabilities, :cap)",
            self.index_name,
            expression_values={":cap": capability}
        )
        return [AgentCard.from_dict(item) for item in results]

@dataclass
class AgentMessage:
    """Message format for agent-to-agent communication"""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = ""
    recipient_id: str = ""  
    content: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    timestamp: float = field(default_factory=lambda: import time; return time.time())
    ttl: Optional[int] = None
    
    def to_dict(self):
        """Convert message to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data):
        """Create message from dictionary"""
        return cls(**data)

class A2AProtocol:
    """Agent-to-Agent communication protocol implementation"""
    def __init__(self, agent_id: str, message_bucket: str, registry: AgentRegistry):
        self.agent_id = agent_id
        self.message_bucket = message_bucket
        self.registry = registry
    
    def send_message(self, recipient_id: str, content: Dict[str, Any], 
                     correlation_id: Optional[str] = None) -> str:
        """Send message to another agent"""
        message = AgentMessage(
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            content=content,
            correlation_id=correlation_id
        )
        
        key = f"messages/{recipient_id}/{message.message_id}.json"
        S3.put_object(self.message_bucket, key, message.to_dict())
        return message.message_id
    
    def get_messages(self, limit: int = 10) -> List[AgentMessage]:
        """Get messages for this agent"""
        prefix = f"messages/{self.agent_id}/"
        response = S3.list_objects(self.message_bucket, prefix)
        
        messages = []
        for obj in response.get('Contents', [])[:limit]:
            message_data = S3.get_object(self.message_bucket, obj['Key'])
            if message_data:
                messages.append(AgentMessage.from_dict(message_data))
                # Move to processed folder
                new_key = obj['Key'].replace("messages/", "messages/processed/")
                S3.copy_object(self.message_bucket, obj['Key'], self.message_bucket, new_key)
                S3.delete_object(self.message_bucket, obj['Key'])
                
        return messages

# --- Model Context Protocol (MCP) Client ---

@dataclass
class MCPRequest:
    """Model Context Protocol request"""
    operation: str
    context: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

@dataclass
class MCPResponse:
    """Model Context Protocol response"""
    status: str
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    request_id: str = ""
    
    @property
    def success(self) -> bool:
        return self.status == "success"

class MCPClient:
    """Client for Model Context Protocol servers"""
    def __init__(self, base_url: str, auth_token: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.headers = {"Content-Type": "application/json"}
        if auth_token:
            self.headers["Authorization"] = f"Bearer {auth_token}"
    
    @retry(max_attempts=3)
    def call(self, operation: str, context: Dict[str, Any] = None, 
             parameters: Dict[str, Any] = None) -> MCPResponse:
        """Call MCP server operation"""
        request = MCPRequest(
            operation=operation,
            context=context or {},
            parameters=parameters or {}
        )
        
        response = requests.post(
            f"{self.base_url}/invoke",
            headers=self.headers,
            json=asdict(request),
            timeout=30
        )
        
        response.raise_for_status()
        result = response.json()
        return MCPResponse(
            status=result.get("status", "error"),
            data=result.get("data", {}),
            errors=result.get("errors", []),
            request_id=result.get("request_id", request.request_id)
        )
    
    def get_capabilities(self) -> List[str]:
        """Get MCP server capabilities"""
        response = self.call("get_capabilities")
        return response.data.get("capabilities", []) if response.success else []
    
    def expand_context(self, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Expand context with relevant information"""
        response = self.call(
            "expand_context", 
            context=context or {},
            parameters={"query": query}
        )
        return response.data.get("expanded_context", {}) if response.success else {}
    
    def run_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Run a tool on the MCP server"""
        response = self.call(
            "run_tool",
            parameters={"tool_name": tool_name, "parameters": parameters}
        )
        return response.data if response.success else {"error": response.errors}

# Cached MCP client factory
@lru_cache(maxsize=32)
def get_mcp_client(base_url: str, auth_token: Optional[str] = None) -> MCPClient:
    """Get cached MCP client for URL"""
    return MCPClient(base_url, auth_token)
