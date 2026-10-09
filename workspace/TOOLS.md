# Available Tools & Endpoints

## n8n Workflows (via MCP)

These files describe example n8n endpoints. MCP exposure requires separate configuration and activation. Token impact has not been measured for a complete task.

| Workflow | File | Webhook Path | Example purpose |
|----------|------|-------------|-----------------|
| CRM Lookup | `crm-contact-lookup.json` | POST /webhook/mcp/crm-lookup | Fetch a record from a configured CRM endpoint |
| SMS Send | `sms-send-openphone.json` | POST /webhook/mcp/sms-send | Submit an SMS request; no independent consent or opt-out lookup in this JSON |
| Airtable Write | `airtable-staging-write.json` | POST /webhook/mcp/staging-write | Write an example record to Airtable staging |
| Calendar Check | `calendar-availability-check.json` | POST /webhook/mcp/calendar-check | Check availability in a configured calendar |
| Audit Log | `audit-log-writer.json` | POST /webhook/mcp/audit-log | Write an example record; validate masking against your data |
| Health Check | `service-health-check.json` | *(scheduled, no webhook)* | Example service check and notification |

**Note:** These production paths combine n8n's default `/webhook` endpoint with the `mcp/…` path in each committed Webhook node. Confirm the displayed Production URL after configuration; test URLs and custom endpoint settings can differ. Whether MCP exposes a workflow as a tool depends on your actual server configuration and permissions.

## When to Use n8n vs AI

| Task Type | Route To | Why |
|-----------|----------|-----|
| API call (GET/POST) | n8n | Deterministic step; end-to-end model use may differ |
| Data lookup | n8n | Structured step; measure full request path |
| Send message (SMS/email) | n8n | Template step; verify approval before send |
| Write to database | n8n | Schema validation must be configured and tested |
| Analyze text | AI | Requires reasoning |
| Draft document | AI | Requires creativity |
| Make a decision | AI | Requires judgment |
| Classify/categorize | AI | Requires understanding |

## Why Route to n8n

A defined workflow can handle an API step without a model call at that step, but the full task may still use a model, retries, hosting, and external services. Measure the complete task before claiming cost or token savings.
