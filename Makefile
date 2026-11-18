.PHONY: fmt
fmt:
	poetry run black custom_components
	poetry run isort --profile black custom_components

.PHONY: lint
lint: fmt
	poetry run pylint custom_components
.PHONY: test
# Same packages as the Tests workflow, without touching poetry.lock
test:
	uv run --no-project --python 3.13 --with pytest-homeassistant-custom-component \
		--with "$$(jq -r '.requirements[]' custom_components/honeygain/manifest.json)" python -m pytest -q
