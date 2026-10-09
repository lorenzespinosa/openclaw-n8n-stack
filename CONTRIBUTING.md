# Contributing to openclaw-n8n-stack

Thank you for contributing. This repository provides example Docker Compose configuration and n8n workflows for review and adaptation; deployment safety has not been verified.

## How to Contribute

### Adding n8n Workflows
1. Create your workflow in n8n
2. Export as JSON
3. Strip any credentials or instance-specific data
4. Add to `workflows/` directory
5. Document the workflow's MCP path in `workspace/TOOLS.md`
6. Open a PR

### Improving Configuration
1. Test changes with `docker compose up -d`
2. Verify all 3 services start and pass health checks
3. Document any new environment variables in `.env.example`

### Reporting Issues
Use the issue templates in `.github/ISSUE_TEMPLATE/`.

## Pre-Submit Checklist
- [ ] No real API keys, tokens, or credentials in any file
- [ ] `docker compose up -d` starts all services
- [ ] Health checks pass for all 3 services
- [ ] Changes documented in CHANGELOG.md
