STACK_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ENV_FILE := $(STACK_DIR)/.env
COMPOSE := docker compose --project-directory "$(STACK_DIR)" --env-file "$(ENV_FILE)" -f "$(STACK_DIR)/docker-compose.yml"

.DEFAULT_GOAL := help

.PHONY: help setup init download-model build up down restart rebuild status config logs logs-ninfer logs-hermes logs-sandbox shell-hermes shell-ninfer shell-sandbox setup-hermes configure-hermes verify benchmark validate clean

help:
	@echo "Hermes + NInfer stack"
	@echo "  setup             run the complete interactive first-run workflow"
	@echo "  download-model    download and verify the pinned ~20 GiB artifact"
	@echo "  build/up/down      build or manage the Compose stack"
	@echo "  restart/status     restart services or show effective status"
	@echo "  setup-hermes       rerun only the Hermes wizard (advanced recovery)"
	@echo "  configure-hermes   reapply the reviewed NInfer/sandbox configuration"
	@echo "  verify/benchmark   run local GPU integration checks or measurements"
	@echo "  validate           run hardware-independent repository checks"
	@echo "  clean              stop containers and remove local images only; preserve all data"

setup:
	cd "$(STACK_DIR)" && python3 stack.py setup

init:
	@echo "'make init' is retained as an alias for 'make setup'."
	$(MAKE) setup

download-model:
	cd "$(STACK_DIR)" && python3 stack.py download-model

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

rebuild:
	$(COMPOSE) build --pull
	$(COMPOSE) up -d --force-recreate

status:
	$(COMPOSE) ps

config:
	$(COMPOSE) config --quiet
	@echo "Docker Compose configuration is valid."

logs:
	$(COMPOSE) logs -f

logs-ninfer:
	$(COMPOSE) logs -f ninfer

logs-hermes:
	$(COMPOSE) logs -f hermes

logs-sandbox:
	$(COMPOSE) logs -f sandbox

shell-hermes:
	$(COMPOSE) exec hermes bash

shell-ninfer:
	$(COMPOSE) exec ninfer bash

shell-sandbox:
	$(COMPOSE) exec --user agent sandbox bash

setup-hermes:
	$(COMPOSE) run --rm --no-deps hermes setup

configure-hermes:
	cd "$(STACK_DIR)" && python3 stack.py configure-hermes

verify:
	cd "$(STACK_DIR)" && python3 stack.py verify

benchmark:
	cd "$(STACK_DIR)" && python3 stack.py benchmark

validate:
	cd "$(STACK_DIR)" && python3 ./scripts/validate.py

clean:
	$(COMPOSE) down --remove-orphans --rmi local
	@echo "Preserved models/, hermes-data/, workspace/, benchmarks/, and all named volumes."
