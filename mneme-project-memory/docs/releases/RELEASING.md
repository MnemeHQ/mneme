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

Create it **outside the repository** — a venv inside the working tree is not
ignored and would make the later clean-tree check (`git status --short`) fail.
Do not add a `.gitignore` rule just for the release environment; keep it out of
the tree entirely and clean it up explicitly in step 17.

```powershell
$releaseVenv = Join-Path $env:TEMP "mneme-hq-release-0.5.0"

Remove-Item -Recurse -Force $releaseVenv -ErrorAction SilentlyContinue
py -3.11 -m venv $releaseVenv
& "$releaseVenv\Scripts\Activate.ps1"

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

## 9. Verify package name, version, and console scripts from the artifacts

**The packaging contract test is the authoritative check.** With `dist/`
populated (step 6), run it against the built wheel and sdist:

```powershell
python -m pytest tests/test_packaging_contract.py -v
```

It asserts, directly from the artifacts:

- exactly one `mneme_hq-0.5.0-*.whl` and exactly one `mneme_hq-0.5.0.tar.gz`;
- the wheel `*.dist-info/METADATA` declares `Name: mneme-hq` and
  `Version: 0.5.0`;
- the sdist `PKG-INFO` declares the same name and version;
- the wheel `entry_points.txt` `[console_scripts]` is *exactly*:
  ```
  mneme = mneme.cli:main
  mneme-hook = mneme.integrations.claude_code.hook:cli_main
  ```

The declared version comes from `pyproject.toml`, so the test also proves the
artifacts match the version you intend to ship. Do not proceed unless it passes.

> `python -m pip show mneme-hq` (`Name: mneme-hq`, `Version: 0.5.0`) is only a
> **source-environment sanity check** — it reports whatever is installed in the
> active venv (the editable source from step 3), **not** the contents of the
> built artifacts. It is not artifact inspection; the contract test above is.

## 10. Tag the exact commit used for the build

Tag the commit you just built and tested — not a later one.

```powershell
git tag -a v0.5.0 -m "mneme-hq 0.5.0"
git push origin v0.5.0
```

## 11. Upload only the verified wheel and sdist

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

## 12. Clean the token from the environment

Remove the token from the session immediately after upload:

```powershell
Remove-Item Env:TWINE_USERNAME, Env:TWINE_PASSWORD
```

Then close the elevated/publish shell. If the token was ever echoed or logged,
revoke it in the PyPI project settings and issue a new one.

## 13. Validate the public package from a clean `pipx` environment

Verify what PyPI actually serves — from a *fresh*, isolated environment, not the
build venv (which already has the local source package installed). Uninstall
first so you cannot accidentally validate a stale install, then pin the exact
published version.

```powershell
deactivate
pipx uninstall mneme-hq
pipx install "mneme-hq==0.5.0"

Get-Command mneme
Get-Command mneme-hook
mneme --help
```

Notes:

- It is fine if `pipx uninstall` reports the package was not installed — the
  point is to guarantee a clean starting state.
- Confirm both console scripts resolve with `Get-Command` (they must point into
  the `pipx` environment, not your source checkout).
- Only `mneme` has a `--help`. **Do not run `mneme-hook --help`** — `mneme-hook`
  is the Claude Code hook entrypoint: it reads a hook event from **stdin**, so
  invoking it interactively (with or without `--help`) blocks waiting for EOF.
  Its real validation is the Claude Code smoke test in steps 14–15.

> The pytest end-to-end tests in
> `tests/integrations/claude_code/test_hook_e2e.py` are **source-level
> regression tests**, not public-package validation. They import the hook
> adapter directly from the source checkout, and the adapter launches
> `[sys.executable, "-m", "mneme", ...]`; run from `mneme-project-memory/` that
> can execute the **local source** package rather than the `pipx`-installed
> public one. Keep running them (step 5) as regression coverage, but validate
> the *published* package only through the real plugin path below.

## 14. Validate the plugin with Claude Code strict validation

This and the next step are the **real** public-package validation: they exercise
the `pipx`-installed `mneme` / `mneme-hook` commands through the actual Claude
Code plugin, not through the source checkout.

From the **repository root**, resolve the plugin directory once and run strict
validation and a plugin-dir load with enforcement forced to `strict`:

```powershell
$env:MNEME_HOOK_MODE = "strict"
$pluginPath = (
  Resolve-Path `
    ".\mneme-project-memory\integrations\claude-code-plugin"
).Path

claude.cmd plugin validate $pluginPath --strict
claude.cmd --plugin-dir $pluginPath
```

`claude.cmd plugin validate ... --strict` must pass (valid manifest, semver
version `0.1.0`, exec-form hook). `claude.cmd --plugin-dir $pluginPath` loads the
plugin into a Claude Code session so you can run the smoke tests below.

## 15. Run the compliant-Write and blocked-Write smoke tests through Claude Code

Inside the Claude Code session started in step 14, issue the two prompts below
verbatim. These drive the real `PreToolUse` hook (published `mneme-hook` →
published `mneme check`), which is what actually validates the public package.

**Compliant Write — must succeed.** Request this exact prompt:

```text
This is specifically a PreToolUse hook allow test.

Attempt the Write tool, not Bash or Edit, to create:

scripts/encoding_smoke_clean.py

with exactly this content:

open("out.txt", "w", encoding="utf-8").write("x")

Do not change any other file.
```

The Write must succeed (the content pins `encoding="utf-8"`, so it does not
violate ADR-009).

**Blocked Write — must be blocked.** Request this exact prompt:

```text
This is specifically a PreToolUse hook-blocking test.

Attempt the Write tool, not Bash or Edit, to create:

scripts/encoding_smoke_block.py

with exactly this content:

open("out.txt", "w").write("x")

Do not rewrite the content to comply. The purpose is to attempt this exact Write and verify that the hook blocks it. Do not change any other file.
```

The Write must be blocked by the `PreToolUse` hook (the content omits
`encoding=`, violating ADR-009).

**Clean up** the smoke-test artifacts and the forced mode, then confirm a clean
tree:

```powershell
Remove-Item .\scripts\encoding_smoke_clean.py -ErrorAction SilentlyContinue
Remove-Item .\scripts\encoding_smoke_block.py -ErrorAction SilentlyContinue
Remove-Item Env:MNEME_HOOK_MODE -ErrorAction SilentlyContinue
git status --short
```

`git status --short` must report nothing (the clean Write is removed and the
blocked Write was never created).

## 16. Create the GitHub release — only after public validation succeeds

Only now, once the public package validates end to end, publish the GitHub
release for the `v0.5.0` tag. Run this from the **repository root** (the same
place as the smoke tests), so the notes path is repository-root-relative:

```powershell
gh release create v0.5.0 `
  --title "mneme-hq 0.5.0" `
  --notes-file .\mneme-project-memory\docs\releases\v0.5.0.md
```

## 17. Remove the temporary release environment

Tear down the external release venv created in step 2 and confirm the working
tree is clean (the venv lived outside the repo, so nothing should remain):

```powershell
deactivate
Remove-Item -Recurse -Force $releaseVenv -ErrorAction SilentlyContinue
git status --short
```

`git status --short` must report nothing.

---

## Post-merge publication checklist

Run in order. Do not advance past a failing step.

- [ ] `main` is clean and at the release-alignment squash commit.
- [ ] Isolated release venv created **outside the repo** (`$env:TEMP`); Python >= 3.11 confirmed.
- [ ] `build`, `twine`, and `.[dev]` installed.
- [ ] `build/`, `dist/`, `*.egg-info` removed.
- [ ] Full test suite passes (with the package installed, e2e hook tests run).
- [ ] Wheel + sdist built.
- [ ] `twine check dist/*` → both PASSED.
- [ ] `dist/` inspected — exactly the two expected artifacts.
- [ ] **Artifact contract** (`test_packaging_contract.py` with `dist/` present): exactly one `mneme_hq-0.5.0-*.whl` + one `mneme_hq-0.5.0.tar.gz`; wheel METADATA and sdist PKG-INFO both declare `Name: mneme-hq` / `Version: 0.5.0`; wheel `entry_points.txt` is exactly the two console scripts. (`pip show` is only a source-env sanity check, not artifact inspection.)
- [ ] `v0.5.0` tag pushed on the exact built commit.
- [ ] Uploaded only the named wheel + sdist with a project-scoped token.
- [ ] Token removed from the environment.
- [ ] Clean `pipx`: `pipx uninstall mneme-hq` then `pipx install "mneme-hq==0.5.0"`; `Get-Command mneme` and `Get-Command mneme-hook` both resolve into the pipx env; `mneme --help` works (do **not** run `mneme-hook --help`).
- [ ] `claude.cmd plugin validate $pluginPath --strict` passes; `claude.cmd --plugin-dir $pluginPath` loads the plugin (with `MNEME_HOOK_MODE=strict`).
- [ ] Claude Code smoke tests: compliant Write (`encoding="utf-8"`) succeeds; blocked Write (no `encoding=`) is blocked by the `PreToolUse` hook.
- [ ] Smoke artifacts removed, `MNEME_HOOK_MODE` cleared, `git status --short` clean.
- [ ] GitHub release created for `v0.5.0` (`--notes-file .\mneme-project-memory\docs\releases\v0.5.0.md`, from repo root).
- [ ] Temporary release venv removed; `git status --short` clean.
- [ ] **Only then:** update the plugin README to drop the install workaround and
      advertise `pipx install "mneme-hq>=0.5.0"` (a separate, follow-up change —
      the README is intentionally left unchanged in the alignment PR).
