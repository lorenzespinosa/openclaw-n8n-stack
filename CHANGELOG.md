# Changelog

## [1.0.0] - 2025-08-01

### Added
- Docker Compose stack: OpenClaw + n8n + PostgreSQL
- Pre-configured multi-agent setup (orchestrator, ops-agent, research-agent)
- MCP integration between OpenClaw and n8n
- Identity stack templates (SOUL.md, AGENTS.md, USER.md, TOOLS.md)
- Workflow-routing examples; earlier cost-savings figures were illustrative, not measured
- Health checks on all 3 services
- Security hardening (no hardcoded tokens, .env-based config)
- One-command deploy: `docker compose up -d`
