.DEFAULT_GOAL := help

help: ## Show available targets.
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  %-18s %s\n", $$1, $$2}'

validate: ## Validate the marketplace, every plugin, and every SKILL.md.
	@python3 tools/validate.gpt.py

catalogue: ## Regenerate catalogue.json and INDEX.md from meta/*.skill.yml.
	@python3 tools/build_catalogue.gpt.py

catalogue-check: ## Fail if the committed catalogue differs from a fresh build.
	@python3 tools/build_catalogue.gpt.py --check

sync: ## Refresh vendored SKILL.md copies from their pinned upstream refs.
	@python3 tools/sync_skills.gpt.py

test: ## Prove the tooling's guards fire, on a throwaway copy.
	@python3 tools/test_guards.gpt.py

check: validate catalogue-check test ## Everything CI runs.

.PHONY: help validate catalogue catalogue-check sync test check
