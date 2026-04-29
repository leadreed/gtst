# Agent Notes

## Testing

- Use the ComfyUI venv for this plugin:
  `..\..\venv\Scripts\python.exe -m pytest -p no:cacheprovider`
- To run pytest inside the Codex sandbox on Windows, point temp paths inside the
  repo and enable the local pytest plugin that relaxes pytest's restrictive
  temp directory modes. Use a fresh basetemp because sandboxed Python may not
  be able to delete temp files after the run:
  `$env:TMP="$PWD\.tmp"; $env:TEMP="$PWD\.tmp"; $env:TMPDIR="$PWD\.tmp"; $run="pytest-sandbox-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"; ..\..\venv\Scripts\python.exe -m pytest --basetemp "$PWD\.tmp\$run" -p no:cacheprovider -p pytest_sandbox_windows`
- Without `pytest_sandbox_windows`, sandboxed pytest can fail with
  `PermissionError` while creating or cleaning temporary directories.
- Sandbox test runs can leave `.tmp` behind; clean it with escalation when
  needed.
- Current Windows baseline: the suite runs in the ComfyUI venv, but some tests
  may fail because they assert POSIX-style `/` path suffixes while Windows
  returns backslash paths.
