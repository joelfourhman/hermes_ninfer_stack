STACK_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ENV_FILE := $(STACK_DIR)/.env
COMPOSE := docker compose --project-directory "$(STACK_DIR)" --env-file "$(ENV_FILE)" -f "$(STACK_DIR)/docker-compose.yml"

.DEFAULT_GOAL := help

.PHONY: help setup init install-hermes prepare-model select-model download-model build up down restart rebuild status config logs logs-ninfer shell-ninfer verify benchmark validate clean

help:
	@echo "NInfer local runtime"
	@echo "  setup             set up NInfer, then offer stock Hermes Desktop installation"
	@echo "  install-hermes    install/configure stock Hermes Desktop for local NInfer"
	@echo "  prepare-model     prepare the configured stock or uncensored model profile"
	@echo "  select-model      interactively prepare, verify, and switch model profiles"
	@echo "  download-model    compatibility alias for prepare-model"
	@echo "  build/up/down      build or manage the NInfer Compose service"
	@echo "  restart/status     restart NInfer or show effective status"
	@echo "  verify/benchmark   run local GPU integration checks or measurements"
	@echo "  validate           run hardware-independent repository checks"
	@echo "  clean              stop containers and remove local images; preserve model data"

setup:
	cd "$(STACK_DIR)" && python3 ninfer.py setup

init:
	@echo "'make init' is retained as an alias for 'make setup'."
	$(MAKE) setup

install-hermes:
	cd "$(STACK_DIR)" && python3 ninfer.py install-hermes

prepare-model:
	cd "$(STACK_DIR)" && python3 ninfer.py prepare-model

select-model:
	cd "$(STACK_DIR)" && python3 ninfer.py select-model

download-model:
	cd "$(STACK_DIR)" && python3 ninfer.py download-model

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d --remove-orphans

down:
	$(COMPOSE) down --remove-orphans

restart:
	$(COMPOSE) restart ninfer

rebuild:
	$(COMPOSE) build --pull ninfer
	$(COMPOSE) up -d --remove-orphans --force-recreate ninfer

status:
	$(COMPOSE) ps

config:
	$(COMPOSE) config --quiet
	@echo "Docker Compose configuration is valid."

logs:
	$(COMPOSE) logs -f ninfer

logs-ninfer:
	$(COMPOSE) logs -f ninfer

shell-ninfer:
	$(COMPOSE) exec ninfer bash

verify:
	cd "$(STACK_DIR)" && python3 ninfer.py verify

benchmark:
	cd "$(STACK_DIR)" && python3 ninfer.py benchmark

validate:
	cd "$(STACK_DIR)" && python3 ./scripts/validate.py

clean:
	$(COMPOSE) down --remove-orphans --rmi local
	@echo "Preserved models/ and benchmarks/."
