alias v := bump-version
alias r := restore-env

restore-env:
  [ -d '.venv' ] || uv sync --all-extras --no-dev --frozen

bump-version: restore-env
  uv run cz bump --no-verify
  uv run pre-commit run -a
  git commit --amend --no-edit

clean: restore-env
  uvx cleanpy@0.5.1 .

precommit-run-all: restore-env
  uv run pre-commit run -a
