# Releasing `mneme-hq` to PyPI

How `mneme-hq` releases are actually published. The build and upload are
automated: after the release tag exists, publishing the GitHub release for
that tag triggers the **Publish to PyPI** workflow
([`.github/workflows/release.yml`](../../.github/workflows/release.yml)),
which builds both artifacts and uploads them to PyPI through **Trusted
Publishing** (OIDC, `pypa/gh-action-pypi-publish`, `pypi` environment
approval). There is no manual `twine upload` step.

What stays deliberately manual is the decision to release: an operator
validates the release candidate against the exact SHA, tags it, and publishes
the GitHub release. Publication never bypasses that validation.

All commands assume:

- You are in the **repository root** (the build root; `pyproject.toml` lives
  here).
- Windows 11 with **PowerShell** is the reference environment. The
  `gh`, `git`, and `python` invocations below are cross-platform.

> **PyPI artifacts are immutable.** Once a version is uploaded to PyPI it can
> never be replaced — only *yanked*. A yanked release still occupies its
> version number forever; you cannot re-upload `0.7.0` with different bytes.
> Do every validation step below **before** creating the GitHub release,
> because that is the point of no return. If something is wrong after upload,
> the only remedy is to yank and publish a new patch version.

---

## Test batteries used in this procedure

Defined in [`scripts/run_test_battery.py`](../../scripts/run_test_battery.py);
see [CONTRIBUTING.md](../../CONTRIBUTING.md) for the full table.

| Battery    | What it is |
| ---------- | ---------- |
| `gate`     | Critical paths; runs on every pull request. |
| `main`     | Complete canonical suite; runs on push/merge to `main` (plus the langchain-extra job). |
| `release`  | Canonical suite **plus** the langchain-extra integration suite — the complete source validation. |
| `artifact-smoke` | Validates the published package bytes from a clean install (automated after publication). |
| `benchmark`| Charter instrument for retrieval/enforcement behavioural semantics; separate from all pytest batteries. |

## 1. Start from a clean `main`

```powershell
git checkout main
git pull --ff-only
git status               # must report a clean working tree
```

## 2. Prepare the release commit (the release-candidate SHA)

Open a release-prep PR that:

- bumps the package version in `pyproject.toml` (`[project].version`) **and**
  `mneme/__init__.py` (`__version__`);
- adds the `CHANGELOG.md` entry for the new version;
- adds the release notes file `docs/releases/vX.Y.Z.md`.

Squash-merge it into `main`. The resulting squash commit is the
**release-candidate SHA** — the exact commit the tag must point at.

Because the prep commit changes package metadata (the version), it requires
its own complete validation on that exact SHA (step 3) — a full-suite pass on
an earlier commit does not carry over.

## 3. Run the release battery once on the exact release-candidate SHA

> **Invariant: a successful full release-suite result belongs to an exact Git
> SHA.** One complete pass per release-candidate SHA is mandatory before
> tagging and publishing.

Dispatch the release battery on the release-candidate ref:

```powershell
# If the release candidate is the tip of main (usual case):
gh workflow run tests.yml --ref main -f battery=release

# If the release candidate is a tag (e.g. an RC tag):
gh workflow run tests.yml --ref vX.Y.Z -f battery=release
```

The run must be green (canonical suite plus the langchain-extra suite, in the
`release (complete source validation)` job). **Acceptable alternative:** the
push-to-`main` run for that exact SHA (the `main` job plus the
`pytest (langchain extra)` job) — it is the same content as the release
battery and equally binds to the SHA.

Record the run URL and the exact SHA in
`docs/releases/vX.Y.Z-validation.md` (see
[`v0.7.0-validation.md`](v0.7.0-validation.md) for the established format).

### When a changed SHA invalidates a full-suite result

Re-run the release battery (step 3) on the new SHA if any of the following
changed since the validated result:

| Change on the SHA                                                       | Full release battery |
| ----------------------------------------------------------------------- | -------------------- |
| Runtime/application code (`mneme/`, packaging-affecting repo files)      | **required again**   |
| Tests                                                                    | **required again**   |
| Dependencies or package metadata capable of affecting runtime/install    | **required again**   |
| Docs or release notes only                                               | not required         |
| Release-workflow-only changes (`.github/workflows/*`)                    | validate the workflow appropriately; the source test suite is **not** rerun unless the shipped package source changed |

## 4. Pre-tag artifact validation (isolated venv)

Run this on the exact release-candidate SHA, from a throwaway venv created
**outside the repository** (a venv inside the working tree would make the
clean-tree check fail). Python >= 3.11:

```powershell
$releaseVenv = Join-Path $env:TEMP "mneme-hq-release-X.Y.Z"
Remove-Item -Recurse -Force $releaseVenv -ErrorAction SilentlyContinue
py -3.11 -m venv $releaseVenv
& "$releaseVenv\Scripts\Activate.ps1"

python -m pip install --upgrade pip
python -m pip install build twine
python -m pip install -e ".[dev]"
```

Remove stale build output, then build both artifacts:

```powershell
Remove-Item -Recurse -Force build, dist, *.egg-info -ErrorAction SilentlyContinue
python -m build
```

Check metadata renders, inspect the artifacts, and run the packaging
contract — the authoritative pre-publish check of name, version, and entry
points, read directly from the artifacts:

```powershell
python -m twine check dist/*      # both artifacts must report PASSED
Get-ChildItem dist                # exactly the two expected artifacts
python -m pytest tests/test_packaging_contract.py -v
```

The contract test asserts exactly one `mneme_hq-X.Y.Z-*.whl` and one
`mneme_hq-X.Y.Z.tar.gz`, the declared name/version in wheel METADATA and
sdist PKG-INFO, and the exact three console scripts
(`mneme`, `mneme-hook`, `mneme-kiro-hook`) in the wheel's `entry_points.txt`.
Do not proceed unless it passes. (`pip show mneme-hq` only reports what is
installed in the active venv — it is not artifact inspection.)

## 5. Tag the exact release-candidate SHA

Tag the commit you validated in steps 3–4 — never a different commit:

```powershell
git tag -a vX.Y.Z -m "mneme-hq X.Y.Z" <release-candidate-sha>
git push origin vX.Y.Z
```

Tags in this repo mark durable milestones only (see `CLAUDE.md`): `v0.x.y`
product releases — not site deployments or CI housekeeping.

## 6. Publish: create the GitHub release

Only after steps 3–4 pass, publish the GitHub release for the tag — from the
repository root, so the notes path is repository-root-relative:

```powershell
gh release create vX.Y.Z `
  --title "mneme-hq X.Y.Z" `
  --notes-file .\docs\releases\vX.Y.Z.md
```

Publishing the release automatically starts the **Publish to PyPI** workflow:
`build` (`python -m build`, artifact upload) then `publish` (Trusted
Publishing to PyPI). The `pypi` environment requires a reviewer approval
before the upload proceeds. Monitor the workflow run to success.

There is no token handling for the operator: Trusted Publishing issues
short-lived OIDC credentials to the workflow. The former manual-upload
procedure (project-scoped PyPI token at Twine's hidden prompt) is retired —
do not upload manually.

## 7. Post-publication artifact smoke

After a successful **Publish to PyPI** run for a `v*` tag, the
**release smoke** workflow
([`.github/workflows/release-smoke.yml`](../../.github/workflows/release-smoke.yml))
runs automatically:

- waits until PyPI serves the published version;
- installs it with `pipx` (a clean install of the published artifact — never
  the source checkout);
- verifies the installed version and CLI surface (`mneme --help` shows
  `setup` / `audit` / `protect`; `mneme setup --help` shows `--audit-ref`;
  `mneme protect --help` shows the subcommands);
- runs a disposable-repo clean-setup check against the installed package
  (`state: setup`, `enforcement: not_enabled`).

This is the `artifact-smoke` battery: it validates the package bytes PyPI
actually serves and never re-runs the source test suite. To re-verify any
published version manually:

```powershell
gh workflow run release-smoke.yml -f version=X.Y.Z
```

Notes:

- **Do not run `mneme-hook` interactively.** It is a Claude Code hook
  entrypoint that reads a hook event from stdin; invoking it with or without
  `--help` blocks waiting for EOF. Its enforcement path is exercised in the
  pytest source batteries and through the real plugin path in operator smoke
  tests.
- The pytest end-to-end hook tests (`tests/integrations/claude_code/`) are
  source-level regression coverage inside the canonical suite — not
  public-package validation. The published package is validated only by the
  artifact smoke above.

## 8. Clean up

Remove the temporary release venv created in step 4 and confirm a clean
working tree:

```powershell
Remove-Item -Recurse -Force $releaseVenv -ErrorAction SilentlyContinue
git status --short
```

`git status --short` must report nothing. Only then is it safe to close the
shell.

---

## Post-merge publication checklist

Run in order. Do not advance past a failing step.

- [ ] `main` is clean and at the release-candidate squash commit.
- [ ] Release-prep PR squash-merged: version bump in `pyproject.toml` **and**
      `mneme/__init__.py`, `CHANGELOG.md` entry, `docs/releases/vX.Y.Z.md`.
- [ ] **Release battery passed once on the exact release-candidate SHA**
      (`gh workflow run tests.yml --ref <rc-ref> -f battery=release`, or the
      push-to-`main` run for that exact SHA); run URL + SHA recorded in
      `docs/releases/vX.Y.Z-validation.md`.
- [ ] Benchmark battery run if `decision_retriever.py`, `enforcer.py`,
      `benchmark.py`, or any benchmark fixture changed since the last
      benchmarked point (see CONTRIBUTING.md).
- [ ] Isolated release venv created **outside the repo** (`$env:TEMP`);
      Python >= 3.11 confirmed; `build`, `twine`, and `.[dev]` installed.
- [ ] `build/`, `dist/`, `*.egg-info` removed; wheel + sdist built.
- [ ] `twine check dist/*` — both PASSED; `dist/` inspected (exactly the two
      expected artifacts).
- [ ] **Artifact contract** (`tests/test_packaging_contract.py -v` with
      `dist/` present): exactly one wheel + one sdist; METADATA and PKG-INFO
      declare `Name: mneme-hq` / the intended version; wheel
      `entry_points.txt` is exactly `mneme`, `mneme-hook`,
      `mneme-kiro-hook`. (`pip show` is only a source-env sanity check.)
- [ ] `vX.Y.Z` tag pushed on the exact validated release-candidate SHA.
- [ ] GitHub release created (`--notes-file .\docs\releases\vX.Y.Z.md`,
      from repo root); **Publish to PyPI** workflow succeeded (`build` +
      `publish`); `pypi` environment approval completed.
- [ ] **Release smoke** (`release-smoke.yml`) passed for the published
      version: PyPI serves it, clean `pipx` install, CLI surface, and the
      disposable-repo clean-setup check (`state: setup`,
      `enforcement: not_enabled`).
- [ ] Temporary release venv removed; `git status --short` clean.
