# Pipeline Strict Enforcement Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `warn` (default, unchanged) and `strict` (raise on conflict) `enforcement_mode` to `Pipeline`, so callers can choose between observe-and-continue and fail-fast behavior after conflict detection.

**Architecture:** Post-response enforcement only. After `ConflictDetector.detect()` runs in `Pipeline.run()`, branch on `self.enforcement_mode`. `warn` returns the existing `PipelineResult`. `strict` raises a new `MnemeConflictError` carrying both the conflicts and the partial `PipelineResult` so callers can inspect what happened. No retry, no remediation loop, no pre-generation blocking, no severity model.

**Tech Stack:** Python 3.11+, pytest, no new dependencies. Library lives at `mneme-project-memory/mneme/`.

**Versioning note:** v0.3.0 already tagged. This is a small library patch on top of v0.3.0 — tag as `v0.3.1` after merge if desired, but tagging is out of scope for this plan.

**Working directory:** `mneme-project-memory/` (run all `pytest`/`git` commands from here unless noted). Same git repo as the marketing site at `C:/dev/mneme/`. Working main directly is safe — current uncommitted changes are isolated to `scripts/` (marketing site) and don't touch the library.

---

## Task 1: Add `MnemeConflictError` exception

**Files:**
- Modify: `mneme/schemas.py` (append at end of file, after `AlignmentResult`)
- Test: `tests/test_schemas.py` (append new test)

**Why this first:** The exception is referenced by `Pipeline` and by tests. Defining it first means each subsequent task imports a real class, not a stub.

**Step 1: Write the failing test**

Append to `tests/test_schemas.py`:

```python
def test_mneme_conflict_error_carries_conflicts_and_result():
    from mneme.schemas import MnemeConflictError

    err = MnemeConflictError(conflicts=["c1", "c2"], result="r")
    assert err.conflicts == ["c1", "c2"]
    assert err.result == "r"
    # The exception message should mention how many conflicts were found
    # so it is informative when raised without being caught.
    assert "2" in str(err)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_schemas.py::test_mneme_conflict_error_carries_conflicts_and_result -v`

Expected: `FAIL` with `ImportError: cannot import name 'MnemeConflictError' from 'mneme.schemas'`.

**Step 3: Write the minimal implementation**

Append at the end of `mneme/schemas.py`:

```python
# ── Errors ────────────────────────────────────────────────────────────────────

class MnemeConflictError(Exception):
    """Raised by Pipeline.run() in strict mode when conflicts are detected.

    Carries both the list of Conflict records and the (partial) PipelineResult
    so callers in a try/except can still inspect the LLM response, the
    injected decisions, and the system prompt that produced the violation.

    Attributes:
        conflicts: List of Conflict records produced by ConflictDetector.
        result:    The PipelineResult that would have been returned in
                   warn mode. Typed as Any to avoid a circular import.
    """

    def __init__(self, conflicts: list, result: object) -> None:
        self.conflicts = conflicts
        self.result = result
        super().__init__(
            f"Strict enforcement: {len(conflicts)} conflict(s) detected"
        )
```

Note: typing `conflicts` as `list` (not `list[Conflict]`) and `result` as `object` keeps `schemas.py` free of the `pipeline`/`conflict_detector` imports that would create a circular reference. The Conflict shape is documented in the docstring; runtime is unchanged.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_schemas.py::test_mneme_conflict_error_carries_conflicts_and_result -v`

Expected: `PASS`. Then run the full schemas suite: `pytest tests/test_schemas.py -v` → all PASS.

**Step 5: Commit**

```bash
git add mneme-project-memory/mneme/schemas.py mneme-project-memory/tests/test_schemas.py
git commit -m "feat(schemas): add MnemeConflictError for strict enforcement"
```

---

## Task 2: Add `enforcement_mode` parameter to `Pipeline` (warn-only branch first)

**Files:**
- Modify: `mneme-project-memory/mneme/pipeline.py:50-122` (`Pipeline` class)
- Test: `mneme-project-memory/tests/test_pipeline.py` (append new test)

**Why this is one task and not two:** We're adding the parameter and validating its value, but the runtime behavior in this task is identical to today (warn). This proves the parameter doesn't regress existing behavior before we introduce branching logic in Task 3.

**Step 1: Write the failing tests**

Append to `tests/test_pipeline.py`:

```python
import pytest


def test_pipeline_default_enforcement_mode_is_warn():
    p = Pipeline(memory_path=EXAMPLE, dry_run=True)
    assert p.enforcement_mode == "warn"


def test_pipeline_explicit_strict_mode_construction():
    """Explicit valid 'strict' must round-trip onto the instance unchanged."""
    p = Pipeline(memory_path=EXAMPLE, dry_run=True, enforcement_mode="strict")
    assert p.enforcement_mode == "strict"


def test_pipeline_invalid_enforcement_mode_raises_at_construction():
    with pytest.raises(ValueError, match="enforcement_mode"):
        Pipeline(memory_path=EXAMPLE, dry_run=True, enforcement_mode="bogus")


def test_pipeline_warn_mode_returns_result_even_with_conflicts():
    """warn mode is the existing behavior — surface conflicts, do not raise."""
    p = Pipeline(memory_path=EXAMPLE, dry_run=True, enforcement_mode="warn")
    result = p.run(
        "Should I switch storage to Postgres?",
        _override_response="We recommend introducing Postgres next quarter.",
    )
    assert len(result.conflicts) >= 1
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline.py -v -k "enforcement or warn_mode or strict_mode_construction"`

Expected: 4 FAIL — `Pipeline.__init__()` does not accept `enforcement_mode`, and the attribute does not exist.

**Step 3: Write the minimal implementation**

In `mneme/pipeline.py`, replace the `__init__` (currently at lines 59-70) with:

```python
def __init__(
    self,
    memory_path: str | Path,
    dry_run: bool = False,
    max_decisions: int = DEFAULT_MAX_DECISIONS,
    enforcement_mode: str = "warn",
) -> None:
    if enforcement_mode not in ("warn", "strict"):
        raise ValueError(
            f"enforcement_mode must be 'warn' or 'strict', "
            f"got {enforcement_mode!r}"
        )
    self.store = MemoryStore(memory_path)
    self.store.load()
    self.retriever = DecisionRetriever(self.store.decisions())
    self.adapter = LLMAdapter(dry_run=dry_run)
    self.detector = ConflictDetector()
    self.max_decisions = max_decisions
    self.enforcement_mode = enforcement_mode
```

Also update the `Pipeline` class docstring (currently lines 50-58) to mention the new arg:

```python
"""Composes MemoryStore + DecisionRetriever + ContextBuilder + LLMAdapter + ConflictDetector.

Args:
    memory_path:      Path to project_memory.json.
    dry_run:          Pass-through to LLMAdapter; if True, no API call.
    max_decisions:    Top-N cap on decisions injected per call.
    enforcement_mode: "warn" (default) returns conflicts on PipelineResult.
                      "strict" raises MnemeConflictError when any conflict
                      is detected. Future modes (e.g. "retry") are deferred.
"""
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline.py -v`

Expected: all PASS, including the four pre-existing pipeline tests (no regression).

**Step 5: Commit**

```bash
git add mneme-project-memory/mneme/pipeline.py mneme-project-memory/tests/test_pipeline.py
git commit -m "feat(pipeline): add enforcement_mode arg (warn default, validated)"
```

---

## Task 3: Implement strict mode (raise `MnemeConflictError` on conflicts)

**Files:**
- Modify: `mneme-project-memory/mneme/pipeline.py` (`run()` method, end of method)
- Test: `mneme-project-memory/tests/test_pipeline.py` (append two new tests)

**Step 1: Write the failing tests**

Append to `tests/test_pipeline.py`:

```python
def test_pipeline_strict_mode_raises_when_conflicts_detected():
    from mneme.schemas import MnemeConflictError

    p = Pipeline(memory_path=EXAMPLE, dry_run=True, enforcement_mode="strict")
    with pytest.raises(MnemeConflictError) as excinfo:
        p.run(
            "Should I switch storage to Postgres?",
            _override_response="We recommend introducing Postgres next quarter.",
        )
    err = excinfo.value
    # Exception carries the conflict list...
    assert len(err.conflicts) >= 1
    assert any("postgres" in c.snippet.lower() for c in err.conflicts)
    # ...and the partial result, so callers can inspect what was sent.
    assert err.result is not None
    assert err.result.query.startswith("Should I switch storage")
    assert err.result.system_prompt  # non-empty
    assert err.result.response.content.startswith("We recommend")


def test_pipeline_strict_mode_returns_result_when_no_conflicts():
    """strict mode only raises on conflicts; clean responses still return."""
    p = Pipeline(memory_path=EXAMPLE, dry_run=True, enforcement_mode="strict")
    result = p.run(
        "Should I switch storage to Postgres?",
        # A bland response that does not trigger any constraint match.
        _override_response="Stay with the current local store and revisit later.",
    )
    assert result.conflicts == []
    assert result.response.content.startswith("Stay with")
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline.py -v -k strict`

Expected: `test_pipeline_strict_mode_raises_when_conflicts_detected` FAILs because no exception is raised. The "no conflicts" test should already pass even before the change.

**Step 3: Write the minimal implementation**

In `mneme/pipeline.py`, modify the end of `run()` (currently lines 113-122) — build the `PipelineResult` first, then branch on enforcement mode before returning:

```python
        conflicts = self.detector.detect(response.content, injected)

        result = PipelineResult(
            query=query,
            scored=scored,
            injected_decisions=injected,
            system_prompt=system_prompt,
            response=response,
            conflicts=conflicts,
        )

        if self.enforcement_mode == "strict" and conflicts:
            from mneme.schemas import MnemeConflictError
            raise MnemeConflictError(conflicts=conflicts, result=result)

        return result
```

The local import inside the branch keeps the hot path (warn mode) free of any extra import cost and makes the dependency obvious — strict mode is the only caller.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline.py -v`

Expected: all 9 tests pass (4 pre-existing + 5 new across Tasks 2 and 3).

Then run the full library suite: `pytest -q`

Expected: 142 → 147 tests, all PASS.

**Step 5: Commit**

```bash
git add mneme-project-memory/mneme/pipeline.py mneme-project-memory/tests/test_pipeline.py
git commit -m "feat(pipeline): implement strict enforcement_mode (raises on conflict)"
```

---

## Task 4: Document strict mode in the library README

**Files:**
- Modify: `mneme-project-memory/README.md` (insert after the existing Pipeline example around line 240)

**Why a separate task:** Code is verified before docs. If the docs commit needs to be reverted, the feature still ships. Doc changes don't need their own tests.

**Step 1: Locate insertion point**

Run: `grep -n "result.injected_decisions" mneme-project-memory/README.md`

Expected: one match around line 240 (just after the existing `Pipeline("examples/...").run(query)` example block ends).

**Step 2: Write the docs change**

After the existing Pipeline example block (the one ending with `print(result.injected_decisions)`), insert this new subsection:

````markdown
### Strict enforcement mode

By default `Pipeline` runs in `warn` mode: conflicts are surfaced on
`PipelineResult.conflicts` and the caller decides what to do. For pipelines
that should fail fast on any detected violation — e.g. a CI gate or a
scripted workflow — pass `enforcement_mode="strict"`:

```python
from mneme.pipeline import Pipeline
from mneme.schemas import MnemeConflictError

p = Pipeline(
    "examples/project_memory.json",
    dry_run=True,
    enforcement_mode="strict",
)

try:
    result = p.run("Should I switch storage to Postgres?")
except MnemeConflictError as err:
    # err.conflicts: list[Conflict] from ConflictDetector
    # err.result:    the partial PipelineResult, so you can still inspect
    #                the LLM response, the system prompt, and the injected
    #                decisions that produced the violation.
    for c in err.conflicts:
        print(c.violated_decision_id, "->", c.reason)
```

Strict mode runs the conflict detector on the response and raises if any
conflict is found. It does **not** retry, regenerate, or block the LLM call
upstream — that's a deliberate non-goal for this iteration.
````

**Step 3: Verify the markdown renders cleanly**

Run: `grep -n "Strict enforcement mode" mneme-project-memory/README.md`

Expected: exactly one match.

Open the README and skim the new section — confirm fenced code blocks open and close, and that the section heading sits at the right level (`###`, matching neighboring subsections).

**Step 4: Commit**

```bash
git add mneme-project-memory/README.md
git commit -m "docs(readme): document Pipeline strict enforcement_mode"
```

---

## Task 5: Final verification

**Step 1: Run the full test suite**

Run: `pytest -q` (from `mneme-project-memory/`)

Expected: 148 tests pass, 0 fail. (142 prior + 6 new: 1 in test_schemas, 5 in test_pipeline.)

**Step 2: Verify the public surface**

Run: `python -c "from mneme.pipeline import Pipeline; from mneme.schemas import MnemeConflictError; print('imports OK')"`

Expected: prints `imports OK` with no traceback.

**Step 3: Smoke-test strict mode by hand**

Run from `mneme-project-memory/`:

```bash
python -c "
from mneme.pipeline import Pipeline
from mneme.schemas import MnemeConflictError
p = Pipeline('examples/project_memory.json', dry_run=True, enforcement_mode='strict')
try:
    p.run('Should I switch storage to Postgres?',
          _override_response='We recommend introducing Postgres next quarter.')
    print('FAIL: should have raised')
except MnemeConflictError as e:
    print(f'OK: raised with {len(e.conflicts)} conflict(s); result.query={e.result.query!r}')
"
```

Expected: `OK: raised with 1 conflict(s); result.query='Should I switch storage to Postgres?'` (or similar — exact conflict count depends on the example memory).

**Step 4: Verify git history is clean**

Run: `git log --oneline -5`

Expected: four new commits in order — schemas, pipeline (warn-only param), pipeline (strict), readme.

---

## Out of scope (deferred — do not implement)

These items are listed so a future executor doesn't accidentally expand the change:

- `retry` enforcement mode and any regeneration / reflection loop
- `severity` field on `Decision` and per-decision enforcement overrides
- Pre-generation blocking (modifying the system prompt to forbid violations upfront)
- A CLI flag for `--enforcement-mode` (Pipeline isn't currently a CLI surface — `mneme check` uses `enforcer.py`, a different code path)
- Mocking `LLMAdapter` for tests — the existing `_override_response` hook is sufficient
- Bumping `pyproject.toml` version (currently `0.1.0`, already out of sync with the `v0.3.0` git tag — that's a pre-existing inconsistency, separate concern)

If feedback from current testers warrants any of the above, plan it as a follow-up after the validation gate clears.
