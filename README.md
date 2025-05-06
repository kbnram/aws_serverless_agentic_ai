# Serverless Agentic AI Platform on AWS
<img src="logo.png" align="right" width="200" height="200" alt="Logo">

Most of this code is generated using Vibe Coding.
#### **Model:** Claude
#### **URL:** https://claude.ai/

#### **Version:** 3.7 Sonnet
#### **Prompt:**
```
I'm building a serverless Agentic AI platform on AWS Lambda for Re-act agents in python. I want the code to be minified (less lines). 
 1. Implementation plan for each layer:
   - Core dependencies layer with specific libraries and their purposes (langchain, boto3 etc as needed)
   - AWS service abstraction layer with patterns for common operations (authentication, queueing, storage, database operations etc)
   - Protocol & Client Interfaces layer with:
     a. Agent-to-Agent (A2A) Protocol:
        - Agent Card specification
        - Discovery mechanism
        - Communication patterns
     b. Model Context Protocol (MCP) Client:
        - Given a URL of an MCP server, bring the capabilities of the MCP server to the agent to use.
 2. Lambda function implementations:
   - Re-act loop pattern
   - Tool selection and integration approach
   - Agent reasoning implementation
   - Cross-agent coordination
   - MCP server interactions
```

