# Available Tools & Endpoints

## n8n Workflows (via MCP)

These n8n workflows are available as MCP tools. They replace LLM calls with deterministic API calls to save tokens.

| Workflow | MCP Path | Purpose | Tokens Saved |
|----------|----------|---------|-------------|
| CRM Lookup | /mcp/crm-lookup | Fetch contact/client data | ~5K/call |
| SMS Send | /mcp/sms-send | Send SMS via OpenPhone (TCPA checked) | ~3K/call |
| Airtable Write | /mcp/staging-write | Write records to Airtable staging | ~4K/call |
| Calendar Check | /mcp/calendar-check | Check availability | ~3K/call |
| Audit Log | /mcp/audit-log | Write PII-masked audit record | ~2K/call |
| Health Check | /mcp/health-check | Ping all connected services | ~1K/call |

## When to Use n8n vs AI

| Task Type | Route To | Why |
|-----------|----------|-----|
| API call (GET/POST) | n8n | Deterministic, 0 tokens |
| Data lookup | n8n | Structured query, 0 tokens |
| Send message (SMS/email) | n8n | Template-based, 0 tokens |
| Write to database | n8n | Validated schema, 0 tokens |
| Analyze text | AI | Requires reasoning |
| Draft document | AI | Requires creativity |
| Make a decision | AI | Requires judgment |
| Classify/categorize | AI | Requires understanding |

## Estimated Monthly Savings

| Scenario | Without n8n | With n8n | Savings |
|----------|------------|----------|---------|
| 100 CRM lookups/day | $30/mo | $0 | $30/mo |
| 50 SMS sends/day | $15/mo | $0 | $15/mo |
| 200 audit logs/day | $12/mo | $0 | $12/mo |
| **Total** | **$115/mo** | **$50/mo** | **$65/mo (57%)** |
