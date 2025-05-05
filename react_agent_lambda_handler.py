"""
Re-act Agent Lambda Implementation - Core agent execution patterns
"""
import json
import time
import os
from typing import Dict, List, Any, Callable, Optional, Union
from core_dependencies import lc, react, get_remaining_time_ms, DEBUG
from aws_service_layer import Lambda, S3, DynamoDB, Secrets
from protocol_interfaces import MCPClient, get_mcp_client, AgentCard, AgentRegistry, A2AProtocol

# Get environment variables
MODEL_NAME = os.environ.get("MODEL_NAME", "gpt-4")
AGENT_STATE_BUCKET = os.environ.get("AGENT_STATE_BUCKET")
AGENT_REGISTRY_TABLE = os.environ.get("AGENT_REGISTRY_TABLE")
SECRETS_ID = os.environ.get("AGENT_SECRETS_ID")

# Get API keys from secrets
def get_api_keys():
    try:
        secrets = Secrets.get_secret(SECRETS_ID)
        return {
            "openai_api_key": secrets.get("OPENAI_API_KEY"),
            "anthropic_api_key": secrets.get("ANTHROPIC_API_KEY")
        }
    except Exception as e:
        if DEBUG:
            print(f"Error getting secrets: {e}")
        return {}

# Initialize tools registry
_tools_registry = {}

def register_tool(name: str, description: str):
    """Decorator to register a tool"""
    def decorator(func):
        _tools_registry[name] = {
            "name": name,
            "description": description,
            "func": func
        }
        return func
    return decorator

# Base Re-act Agent
class ReActAgent:
    """Re-act Agent base implementation"""
    def __init__(self, agent_id: str, system_prompt: str = None):
        self.agent_id = agent_id
        self.system_prompt = system_prompt or "You're a helpful AI assistant."
        self.tools = []
        self.api_keys = get_api_keys()
        self.state = self._load_state()
        self.registry = AgentRegistry(AGENT_REGISTRY_TABLE)
        
        # Register this agent
        self._register_agent()
        
    def _register_agent(self):
        """Register agent in the registry"""
        capabilities = list(self._get_capabilities())
        agent_card = AgentCard(
            agent_id=self.agent_id,
            name=self.state.get("name", f"Agent-{self.agent_id}"),
            description=self.state.get("description", "A ReAct agent"),
            version=self.state.get("version", "1.0.0"),
            capabilities=capabilities
        )
        self.registry.register_agent(agent_card)
        
    def _get_capabilities(self):
        """Get agent capabilities based on tools"""
        for tool_name in _tools_registry:
            yield tool_name
    
    def _load_state(self) -> Dict:
        """Load agent state from S3"""
        if not AGENT_STATE_BUCKET:
            return {}
        
        try:
            state = S3.get_object(AGENT_STATE_BUCKET, f"agents/{self.agent_id}/state.json")
            return state or {}
        except Exception:
            return {}
    
    def _save_state(self):
        """Save agent state to S3"""
        if not AGENT_STATE_BUCKET:
            return
        
        try:
            S3.put_object(AGENT_STATE_BUCKET, f"agents/{self.agent_id}/state.json", self.state)
        except Exception as e:
            if DEBUG:
                print(f"Failed to save state: {e}")
    
    def add_tool(self, name: str):
        """Add a registered tool to this agent"""
        if name in _tools_registry:
            tool_info = _tools_registry[name]
            tool_func = tool_info["func"]
            
            @react()["tools"]["tool"](name=name, description=tool_info["description"])
            def wrapped_tool(*args, **kwargs):
                return tool_func(self, *args, **kwargs)
            
            self.tools.append(wrapped_tool)
        
    def add_mcp_tool(self, mcp_url: str, tool_name: str, description: str, auth_token: str = None):
        """Add a tool from an MCP server"""
        mcp_client = get_mcp_client(mcp_url, auth_token)
        
        @react()["tools"]["tool"](name=tool_name, description=description)
        def mcp_tool(*args, **kwargs):
            return mcp_client.run_tool(tool_name, kwargs)
        
        self.tools.append(mcp_tool)
    
    def _create_react_chain(self):
        """Create the ReAct agent chain"""
        model = lc()["models"]["ChatOpenAI"](
            model=MODEL_NAME,
            temperature=0.2,
            api_key=self.api_keys.get("openai_api_key"),
            streaming=True
        )
        
        prompt = lc()["prompts"]["ChatPromptTemplate"].from_messages([
            ("system", self.system_prompt),
            lc()["prompts"]["MessagesPlaceholder"](variable_name="chat_history"),
            ("human", "{input}"),
            lc()["prompts"]["MessagesPlaceholder"](variable_name="agent_scratchpad")
        ])
        
        agent = react()["create_react_agent"](model, self.tools, prompt)
        return react()["AgentExecutor"](
            agent=agent, 
            tools=self.tools,
            return_intermediate_steps=True,
            verbose=DEBUG
        )
    
    def process(self, input_text: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Process input with ReAct reasoning"""
        chat_history = self.state.get("chat_history", [])
        
        # Create agent chain
        react_chain = self._create_react_chain()
        
        # Execute ReAct loop
        result = react_chain.invoke({
            "input": input_text,
            "chat_history": chat_history,
            "context": context or {}
        })
        
        # Update chat history
        if len(chat_history) > 10:
            chat_history = chat_history[-10:]
        chat_history.append(lc()["messages"]["HumanMessage"](content=input_text))
        chat_history.append(lc()["messages"]["AIMessage"](content=result["output"]))
        
        # Update state
        self.state["chat_history"] = chat_history
        self._save_state()
        
        return {
            "agent_id": self.agent_id,
            "output": result["output"],
            "intermediate_steps": [
                {"tool": step[0].tool, "input": step[0].tool_input, "output": step[1]}
                for step in result.get("intermediate_steps", [])
            ],
            "context": context
        }

# Lambda handler
def handler(event, context):
    """Lambda handler for ReAct agent"""
    start_time = time.time()
    
    try:
        # Extract agent ID and input from event
        agent_id = event.get("agent_id")
        if not agent_id:
            return {"error": "Missing agent_id"}
        
        input_text = event.get("input")
        if not input_text:
            return {"error": "Missing input"}
        
        # Load agent configuration
        agent_config = event.get("agent_config", {})
        system_prompt = agent_config.get("system_prompt")
        
        # Create agent
        agent = ReActAgent(agent_id, system_prompt)
        
        # Add tools specified in event
        for tool_name in event.get("tools", []):
            agent.add_tool(tool_name)
        
        # Add MCP tools
        for mcp_tool in event.get("mcp_tools", []):
            agent.add_mcp_tool(
                mcp_tool["url"],
                mcp_tool["name"],
                mcp_tool["description"],
                mcp_tool.get("auth_token")
            )
        
        # Process input
        result = agent.process(input_text, event.get("context"))
        
        # Add execution time
        result["execution_time"] = time.time() - start_time
        result["remaining_time"] = get_remaining_time_ms(context)
        
        return result
        
    except Exception as e:
        if DEBUG:
            import traceback
            return {
                "error": str(e),
                "traceback": traceback.format_exc(),
                "execution_time": time.time() - start_time
            }
        return {
            "error": str(e),
            "execution_time": time.time() - start_time
        }
