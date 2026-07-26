.DEFAULT_GOAL := help

help: ## Show available targets.
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  %-18s %s\n", $$1, $$2}'

validate: ## Validate the marketplace, every plugin, and every SKILL.md.
	@python3 tools/validate.gpt.py

catalogue: ## Regenerate catalogue.json and INDEX.md from meta/*.skill.yml.
	@python3 tools/build_catalogue.gpt.py

catalogue-check: ## Fail if the committed catalogue differs from a fresh build.
	@python3 tools/build_catalogue.gpt.py >/dev/null
	@git diff --quiet -- catalogue.json INDEX.md \
	  || { echo "catalogue.json or INDEX.md is stale; run 'make catalogue'"; exit 1; }
	@echo "OK    catalogue is current"

sync: ## Refresh vendored SKILL.md copies from their pinned upstream refs.
	@python3 tools/sync_skills.gpt.py

check: validate catalogue-check ## Everything CI runs.

.PHONY: help validate catalogue catalogue-check sync check
