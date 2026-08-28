# Makefile for the GO Project Databricks Asset Bundle.
# Override the target env on any command, e.g. `make deploy TARGET=prod`.
TARGET ?= dev
# CLI auth profile for the target workspace.
PROFILE ?= fe-vm-ai-fde-hackathon
# App resource key started after deploy by `deploy-all`.
APP ?= go_outreach_app

.PHONY: help install app-build deploy deploy-all

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create the venv and install deps with uv
	uv sync --extra dev

app-build: ## Install frontend deps and build the React app (app/frontend/dist)
	cd app/frontend && npm install && npm run build

deploy: app-build ## Build the frontend, then deploy the bundle to the target env (default: dev)
	databricks bundle deploy -t $(TARGET) -p $(PROFILE)

deploy-all: deploy ## Deploy, then start the app via `bundle run`
	@if [ -z "$(APP)" ]; then \
		echo "No APP set — deployed only. Start an app with: make deploy-all APP=<app_key>"; \
	else \
		databricks bundle run -t $(TARGET) -p $(PROFILE) $(APP); \
	fi
