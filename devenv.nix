{
  pkgs,
  lib,
  config,
  inputs,
  ...
}:

{

  languages.python.enable = true;
  languages.python.uv.enable = true;
  languages.python.uv.package = pkgs.uv;
  languages.python.uv.sync.enable = true;
  languages.python.uv.sync.allExtras = true;
  languages.python.venv.enable = true;
  languages.python.version = "3.11";

  git-hooks.hooks = {
    black.enable = true;
    typos.enable = true;
    yamllint.enable = true;
    yamlfmt.enable = true;
    check-toml.enable = true;
    commitizen.enable = true;
    nixfmt-rfc-style.enable = true;
  };

  scripts.format.exec = ''
    pre-commit run --all-files
  '';

  scripts.test-all.exec = ''
    pytest -s -vv "$@"
  '';

  scripts.test-coverage.exec = ''
    set -euo pipefail
    pytest --cov=.
    coverage html
    open htmlcov/index.html
  '';

  scripts.test-one.exec = ''
    test-all -k "$@"
  '';

  scripts.test-watch.exec = ''
    ptw .
  '';

  scripts.test-update-snapshots.exec = ''
    pytest --snapshot-update
  '';

  enterTest = ''
    test-all
  '';

  # See full reference at https://devenv.sh/reference/options/
}
