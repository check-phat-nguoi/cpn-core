alias v := bump-version
alias r := restore-env

restore-env:
  [ -d '.venv' ] || uv sync --all-extras --all-groups

bump-verison:
  uv run cz bump

clean:
  uvx cleanpy@0.5.1 .

precommit-run-all:
  uv run pre-commit run -a
