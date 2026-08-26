# Makefile for the GO Project Databricks Asset Bundle.
# Override the target env on any command, e.g. `make deploy TARGET=prod`.
TARGET ?= dev
# App resource key(s) to start after deploy. Set once we define an app, e.g. APP=go_opps_app
APP ?=

.PHONY: help install deploy deploy-all

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create the venv and install deps with uv
	uv sync --extra dev


deploy: ## Deploy the bundle to the target env (default: dev)
	databricks bundle deploy -t $(TARGET)

deploy-all: deploy ## Deploy, then start the app(s) via `bundle run`
	@if [ -z "$(APP)" ]; then \
		echo "No APP set — deployed only. Start an app with: make deploy-all APP=<app_key>"; \
	else \
		databricks bundle run -t $(TARGET) $(APP); \
	fi
