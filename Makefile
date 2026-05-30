# openclaw-n8n-stack — helper commands
# Thin wrappers around `docker compose`. Run `make help` for the list.

.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down restart logs ps health import reset config

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Start all services in the background
	$(COMPOSE) up -d

down: ## Stop and remove containers (volumes kept)
	$(COMPOSE) down

restart: ## Restart all services
	$(COMPOSE) restart

logs: ## Tail logs from all services (Ctrl-C to exit)
	$(COMPOSE) logs -f

ps: ## Show service status
	$(COMPOSE) ps

health: ## Curl the n8n and OpenClaw health endpoints
	@curl -fsS http://localhost:5678/healthz  && echo "  n8n OK"      || echo "n8n DOWN"
	@curl -fsS http://localhost:18789/healthz && echo "  OpenClaw OK" || echo "OpenClaw DOWN"

import: ## Import bundled workflows into n8n (needs N8N_API_KEY in .env)
	./scripts/init-workflows.sh

config: ## Validate the compose file
	$(COMPOSE) config

reset: ## Stop and DELETE all data (containers + volumes), then start fresh
	$(COMPOSE) down -v
	$(COMPOSE) up -d
