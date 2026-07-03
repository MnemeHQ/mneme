# Releasing `mneme-hq` to PyPI

The exact, manual procedure for publishing the `mneme-hq` package. It is
intentionally **not** automated — there is no PyPI GitHub Actions workflow, and
adding one is out of scope for a release-alignment PR. Every publish is a
deliberate, operator-run sequence.

All commands assume:

- You are in the **package directory** `mneme-project-memory/` (this is the
  build root; `pyproject.toml` lives here).
- Windows 11 with **PowerShell** is the reference environment (this is where the
  hook is exercised in CI). Windows-specific steps below are written in
  PowerShell; the build, `twine`, and `pytest` invocations are cross-platform
  and run as shown under PowerShell.

> **PyPI artifacts are immutable.** Once a version is uploaded to PyPI it can
> never be replaced — only *yanked*. A yanked release still occupies its version
> number forever; you cannot re-upload `0.5.0` with different bytes. Do every
> verification step below **before** `twine upload`, because upload is the point
> of no return. If something is wrong after upload, the only remedy is to yank
> and publish a new patch version.

---

## 1. Start from a clean `main`

```powershell
git checkout main
git pull --ff-only
git status               # must report a clean working tree
```

Confirm the release commit is exactly what you intend to ship. Do not build from
a feature branch, a dirty tree, or a detached checkout.

## 2. Create an isolated Python environment

Never build or publish from your day-to-day interpreter. Use a throwaway venv so
build/publish tooling can never leak into (or be contaminated by) other work.

```powershell
py -3.11 -m venv .release-venv
.\.release-venv\Scripts\Activate.ps1
python --version          # confirm >= 3.11 (the package requires-python)
```

> If PowerShell blocks the activation script, allow it for this process only:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`.

## 3. Install build, twine, and test dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install build twine
python -m pip install -e ".[dev]"     # pytest + the package itself
```

## 4. Remove previous build output

Stale `build/`, `dist/`, or egg-info directories can smuggle old artifacts into
a fresh upload. Delete them first.

```powershell
Remove-Item -Recurse -Force build, dist, *.egg-info -ErrorAction SilentlyContinue
```

## 5. Run the full test suite

```powershell
python -m pytest
```

All tests must pass. Because the package is installed (step 3), the
`mneme` CLI is on `PATH`, so the Claude Code end-to-end tests
(`tests/integrations/claude_code/test_hook_e2e.py`) run instead of skipping —
including the compliant-Write / blocked-Write cases.

## 6. Build both wheel and sdist

```powershell
python -m build
```

This produces two artifacts under `dist/`:

- `mneme_hq-0.5.0-py3-none-any.whl` (wheel)
- `mneme_hq-0.5.0.tar.gz` (sdist)

## 7. Run `twine check`

```powershell
python -m twine check dist/*
```

Both artifacts must report `PASSED` (valid metadata, renderable README).

## 8. Inspect the built artifacts

Confirm exactly the two expected files exist and nothing stale remains:

```powershell
Get-ChildItem dist
```

## 9. Confirm package name and version

```powershell
python -m pip show mneme-hq        # Name: mneme-hq   Version: 0.5.0
```

The filenames in `dist/` must also carry `0.5.0`. If they do not, the version in
`pyproject.toml` was not bumped — stop and fix it.

## 10. Confirm the wheel contains both console scripts

The wheel's `entry_points.txt` must declare **both** console scripts:

```
mneme = mneme.cli:main
mneme-hook = mneme.integrations.claude_code.hook:cli_main
```

The packaging contract test verifies this automatically against the wheel you
just built:

```powershell
python -m pytest tests/test_packaging_contract.py -v
```

`test_built_wheel_contains_both_console_scripts` runs (rather than skipping)
because `dist/` now holds a wheel. For a manual cross-check:

```powershell
python -c "import zipfile,glob; w=glob.glob('dist/mneme_hq-*.whl')[0]; z=zipfile.ZipFile(w); print(next(z.read(n).decode('utf-8') for n in z.namelist() if n.endswith('entry_points.txt')))"
```

Do not proceed unless both scripts are present.

## 11. Tag the exact commit used for the build

Tag the commit you just built and tested — not a later one.

```powershell
git tag -a v0.5.0 -m "mneme-hq 0.5.0"
git push origin v0.5.0
```

## 12. Upload only the verified wheel and sdist

Use a **project-scoped** PyPI API token (scoped to the `mneme-hq` project, not an
account-wide token). Provide it via environment variables so it never lands in
shell history or a config file:

```powershell
$env:TWINE_USERNAME = "__token__"
$env:TWINE_PASSWORD = "pypi-...your-project-scoped-token..."

python -m twine upload dist/mneme_hq-0.5.0-py3-none-any.whl dist/mneme_hq-0.5.0.tar.gz
```

Upload the two named artifacts explicitly — not `dist/*` — so nothing unexpected
in `dist/` can be published by accident.

## 13. Clean the token from the environment

Remove the token from the session immediately after upload:

```powershell
Remove-Item Env:TWINE_USERNAME, Env:TWINE_PASSWORD
```

Then close the elevated/publish shell. If the token was ever echoed or logged,
revoke it in the PyPI project settings and issue a new one.

## 14. Validate the public package from a clean `pipx` environment

Verify what PyPI actually serves — from a *fresh* environment, not the build
venv (which already has the local package installed).

```powershell
deactivate
pipx install "mneme-hq==0.5.0"
mneme --help
mneme-hook --help          # both console scripts resolve on PATH
```

`pipx` installs into an isolated environment, so this proves the published
wheel — not your local checkout — provides both entry points.

## 15. Repeat Claude Code plugin strict validation

```powershell
claude plugin validate .\integrations\claude-code-plugin --strict
```

Must pass `--strict` (valid manifest, semver version `0.1.0`, exec-form hook).

## 16. Repeat the compliant-Write and blocked-Write tests

With the published package on `PATH` (via `pipx`), re-run the end-to-end hook
tests against the real binary to confirm enforcement works from the public
install:

```powershell
python -m pytest tests/integrations/claude_code/test_hook_e2e.py -v
```

A compliant Write is allowed (exit `0`); a violating Write is blocked (exit `2`)
in strict mode.

## 17. Create the GitHub release — only after public validation succeeds

Only now, once the public package validates end to end, publish the GitHub
release for the `v0.5.0` tag:

```powershell
gh release create v0.5.0 --title "mneme-hq 0.5.0" --notes-file docs/releases/v0.5.0.md
```

---

## Post-merge publication checklist

Run in order. Do not advance past a failing step.

- [ ] `main` is clean and at the release-alignment squash commit.
- [ ] Isolated release venv created; Python >= 3.11 confirmed.
- [ ] `build`, `twine`, and `.[dev]` installed.
- [ ] `build/`, `dist/`, `*.egg-info` removed.
- [ ] Full test suite passes (with the package installed, e2e hook tests run).
- [ ] Wheel + sdist built.
- [ ] `twine check dist/*` → both PASSED.
- [ ] `dist/` inspected — exactly the two expected artifacts.
- [ ] `pip show mneme-hq` → name `mneme-hq`, version `0.5.0`.
- [ ] Wheel declares both console scripts (`test_packaging_contract.py`).
- [ ] `v0.5.0` tag pushed on the exact built commit.
- [ ] Uploaded only the named wheel + sdist with a project-scoped token.
- [ ] Token removed from the environment.
- [ ] `pipx install "mneme-hq==0.5.0"` → `mneme` and `mneme-hook` both resolve.
- [ ] `claude plugin validate ... --strict` passes.
- [ ] Compliant-Write allowed / violating-Write blocked, from the public install.
- [ ] GitHub release created for `v0.5.0`.
- [ ] **Only then:** update the plugin README to drop the install workaround and
      advertise `pipx install "mneme-hq>=0.5.0"` (a separate, follow-up change —
      the README is intentionally left unchanged in the alignment PR).
