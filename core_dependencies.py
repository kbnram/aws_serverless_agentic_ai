"""
Core Dependencies Layer - efficiently expose critical libraries
"""
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Union, Callable

# Lazy imports to minimize cold start times
def _import_langchain():
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    from langchain_core.output_parsers import JsonOutputParser
    from langchain_core.runnables import RunnablePassthrough
    from langchain_openai import ChatOpenAI
    return {
        "prompts": {"ChatPromptTemplate": ChatPromptTemplate, "MessagesPlaceholder": MessagesPlaceholder},
        "messages": {"HumanMessage": HumanMessage, "AIMessage": AIMessage, "SystemMessage": SystemMessage},
        "parsers": {"JsonOutputParser": JsonOutputParser},
        "runnables": {"RunnablePassthrough": RunnablePassthrough},
        "models": {"ChatOpenAI": ChatOpenAI}
    }

def _import_aws():
    import boto3
    from botocore.exceptions import ClientError
    return {
        "boto3": boto3,
        "exceptions": {"ClientError": ClientError}
    }

def _import_react():
    from langchain.agents import create_react_agent, AgentExecutor
    from langchain_core.tools import BaseTool, StructuredTool, tool
    return {
        "create_react_agent": create_react_agent,
        "AgentExecutor": AgentExecutor,
        "tools": {"BaseTool": BaseTool, "StructuredTool": StructuredTool, "tool": tool}
    }

def _import_anthropic():
    import anthropic
    return {"client": anthropic}

# Cached imports to prevent redundant imports
@lru_cache(maxsize=None)
def lc():
    """LangChain components with lazy loading"""
    return _import_langchain()

@lru_cache(maxsize=None)
def aws():
    """AWS services with lazy loading"""
    return _import_aws()

@lru_cache(maxsize=None)
def react():
    """ReAct agent components with lazy loading"""
    return _import_react()

@lru_cache(maxsize=None)
def anthropic_client():
    """Anthropic client with lazy loading"""
    return _import_anthropic()

# Environment configuration
ENV = os.environ.get("ENVIRONMENT", "dev")
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

# Lambda context helper
def get_remaining_time_ms(context):
    """Get remaining execution time in ms for Lambda"""
    try:
        return context.get_remaining_time_in_millis()
    except:
        return 60000  # Default 60s for local testing
