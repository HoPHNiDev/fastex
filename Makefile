.PHONY: lint
lint:
	pre-commit run --all-files

.PHONY: check-lint
check-lint:
	pre-commit run --all-files --hook-stage push --verbose
