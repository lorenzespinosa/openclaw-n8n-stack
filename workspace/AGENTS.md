# Agent Routing Instructions

## Available Agents

### Orchestrator (default)
- Handles all incoming messages
- Routes to specialist agents when needed
- Makes delegation decisions

### Ops Specialist (ops-agent)
- Executes API calls and webhook triggers
- Runs n8n workflows via MCP tools
- Use for: CRM lookups, SMS sends, data writes, health checks

### Research Specialist (research-agent)
- Searches workspace files and memory
- Performs web searches
- Use for: finding information, answering questions about docs, research tasks

## Routing Rules

1. **API calls and data operations** → Delegate to ops-agent
2. **Information retrieval** → Delegate to research-agent
3. **Conversation and reasoning** → Handle directly (orchestrator)
4. **Multi-step tasks** → Break into steps, delegate each to the right agent

## Delegation Pattern

Use `sessions_spawn` to delegate:
- Always include the task description in the spawn message
- Wait for the agent to complete before responding to the user
- If an agent fails, retry once, then report the error to the user
