alias v := bump-version
alias r := restore-env

restore-env:
  [ -d '.venv' ] || uv sync --all-extras --all-groups

bump-version:
  cz bump --no-verify
  pre-commit run -a
  git commit --amend --no-edit

clean:
  uvx cleanpy@0.5.1 .

precommit-run-all:
  pre-commit run -a
