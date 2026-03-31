# Available Tools & Endpoints

## n8n Workflows (via MCP)

These n8n workflows are available as MCP tools. They replace LLM calls with deterministic API calls to save tokens.

| Workflow | File | Webhook Path | Purpose | Tokens Saved |
|----------|------|-------------|---------|-------------|
| CRM Lookup | `crm-contact-lookup.json` | POST /webhook/crm-lookup | Fetch contact/client data | ~5K/call |
| SMS Send | `sms-send-openphone.json` | POST /webhook/sms-send | Send SMS via OpenPhone (TCPA checked) | ~3K/call |
| Airtable Write | `airtable-staging-write.json` | POST /webhook/staging-write | Write records to Airtable staging | ~4K/call |
| Calendar Check | `calendar-availability-check.json` | POST /webhook/calendar-check | Check availability | ~3K/call |
| Audit Log | `audit-log-writer.json` | POST /webhook/audit-log | Write PII-masked audit record | ~2K/call |
| Health Check | `service-health-check.json` | *(scheduled, no webhook)* | Ping all services, Slack alert on failure | N/A |

**Note:** Webhook paths are configured in n8n when you activate each workflow. The paths above are the defaults set in the workflow JSON files. MCP exposes these as tools once the n8n MCP server is connected.

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
