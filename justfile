alias v := bump-version
alias p := precommit-run-all
alias re := restore-env
alias rde := restore-dev-env

restore-env:
  [ -d '.venv' ] || uv sync --no-dev --frozen

restore-dev-env:
  [ -d '.venv' ] || (uv sync --all-groups --frozen && uv run pre-commit install)

bump-version: restore-dev-env
  uv run cz bump

clean: restore-dev-env
  uvx cleanpy@0.5.1 .

precommit-run-all: restore-dev-env
  uv run --frozen pre-commit run -a
