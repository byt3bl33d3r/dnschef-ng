.PHONY: tests

default: build

clean:
	rm -f -r build/
	rm -f -r bin/
	rm -f -r dist/
	rm -f -r *.egg-info
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f  {} +
	find . -name '__pycache__' -exec rm -rf {} +
	find . -name '.pytest_cache' -exec rm -rf {} +

tests:
	ruff --select=E9,F63,F7,F82 --show-source .
	python -m pytest

requirements:
	poetry export -f requirements.txt > requirements.txt
	poetry export -f requirements.txt --extras=api > requirements-api.txt
	poetry export -f requirements.txt --with=dev > requirements-dev.txt