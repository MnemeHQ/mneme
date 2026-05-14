# Governance Incident Log

> **Scope boundary.** This public log records governance incidents observed
> during Mneme's own development (dogfooding) only. Design-partner and
> customer incidents must **not** be recorded here. Those belong in the
> private `mneme-growth-ops` repo.

## Purpose

Capture real governance behavior from Mneme's own development so roadmap
and benchmark decisions stay grounded in actual usage rather than
speculative design. Entries should cover:

- prevented drift (governance correctly blocked a change)
- missed drift (governance failed to block a change that violated a decision)
- false positives (governance blocked a change that was actually fine)
- noisy enforcement (correct outcome, but signal was hard to read)
- missing decisions (governance had nothing to say but should have)
- retrieval surprises (the wrong decisions ranked, or the right ones did not)
- lessons for the benchmark or the roadmap

Failures are more valuable than successes here. Do not curate only the
clean wins.

## Operating rules

- Lightweight and manual. No automated capture for now.
- One incident per entry. Number sequentially.
- Record the outcome plainly, including when the human reviewer overrode
  governance.
- No partner, customer, or private-repo material.

## Status labels

- `prevented-drift` — governance correctly blocked or flagged a violation
- `missed-drift` — governance failed to flag a real violation
- `false-positive` — governance flagged something that was actually fine
- `noisy` — outcome was correct but the signal was unclear or over-broad
- `missing-decision` — no governance covered the change but should have
- `retrieval-surprise` — top-K did not contain the relevant decision(s)

A single incident may carry more than one label.

## Entry template

```md
## Incident NNN — <short title>

**Date:**
**Repo:**
**Agent / runtime:**
**Session context:**
**Status:** <label(s) from above>

### Proposed change

<what was about to happen>

### Relevant decision(s)

- <ADR or memory key>

### Retrieval result

Top-K:
1.
2.
3.

### Enforcement result

<PASS / FAIL / WARN, with the matched signal if any>

### Outcome

<what actually happened, including human override if any>

### Notes / lesson

<what this implies for the benchmark, roadmap, or future governance>
```

---

## Incident 001 — Layer 1 freeze doc self-triggered `mneme check`

**Date:** 2026-05-10
**Repo:** mneme (public)
**Agent / runtime:** Claude Code
**Session context:** Adding `docs/architecture/layer1-freeze-e73ff7d.md` (PR #23, merged as `1d5e2a1`)
**Status:** `false-positive`, `noisy`

### Proposed change

A docs-only PR adding the Layer 1 freeze artifact at `e73ff7d`. The file
describes governance and enforcement concepts in prose, including
references to anti-patterns and constraint phrasing.

### Relevant decision(s)

None — the change was documentation describing governance, not a code or
architecture change subject to governance.

### Retrieval result

Not the interesting axis here. The trigger was keyword-based enforcement
matching governance vocabulary inside a doc *about* governance.

### Enforcement result

`mneme check` flagged the change because the freeze doc's prose contains
the same vocabulary that anti-pattern matching looks for. The flag was on
the doc's text, not on any change in behavior, code, or architecture.

### Outcome

Human PR review confirmed the change was docs-only and appropriate, and
the PR merged as `1d5e2a1`. No governance concern was real; no override
of a real violation occurred.

### Notes / lesson

Keyword-based enforcement can self-trigger on governance documentation —
documents that describe what to forbid will lexically resemble the things
they forbid. This is a known limitation of the current Layer 1 enforcer,
not a defect.

Implications, recorded for future consideration only (not action items
under the Layer 1 freeze):

- Future event capture or parser improvements should distinguish
  "describes a constraint" from "violates a constraint" while preserving
  deterministic auditability — the determinism property must not be
  traded away for noise reduction.
- This incident is a candidate signal source if scope-aware enforcement
  is ever scoped into Layer 2; it is not a reason to relax Layer 1.
- Not a benchmark change. The benchmark surface is intentionally frozen.

---

## Incident 002 — Silent UTF-8 corruption from implicit PowerShell encoding

**Date:** 2026-05-12  
**Repo:** mneme (public)  
**Agent / runtime:** Claude Code (claude-sonnet-4-6)  
**Session context:** Site-wide footer centre-alignment — bulk HTML rewrite via PowerShell `Set-Content`  
**Status:** `missing-decision`

### Proposed change

A PowerShell one-liner rewrote 49 HTML files in `site/` to change `text-align: left` to
`text-align: center` on footer elements. The operation used `Set-Content` without `-Encoding utf8`.

### Relevant decision(s)

None at the time — no governance rule covered encoding requirements for automation file writes.
The gap is what allowed the incident.

### Retrieval result

No relevant decision was retrieved because none existed. This is a `missing-decision` case,
not a retrieval failure.

### Enforcement result

`PASS` (no relevant rule). Corruption proceeded silently.

### Outcome

49 files written as Windows-1252. Em dashes stored as `0xE2 0x80 0x94` (UTF-8) were
re-encoded as `0x97` (Windows-1252 em dash byte), which is invalid UTF-8. `sync_shared.py`
crashed with `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97 in position 162`
when processing the affected files.

Recovery required a Python re-encoding pass (read as `windows-1252`, write as `utf-8`).
Three additional commits were required before the deploy could proceed clean. Total
remediation time: approximately 30 minutes.

### Notes / lesson

This incident triggered ADR-009 (Automation file writes must specify explicit text encodings).

Key observations:

- **Silent corruption is undetectable at write time.** Git diffs show changed lines; the
  byte-level encoding change is invisible unless raw bytes are inspected.
- **Pre-execution enforcement is the correct surface.** If Mneme had flagged `Set-Content`
  without `-Encoding` before the script ran, the incident would not have occurred.
- **The pattern is reliably matchable.** `Set-Content without -Encoding` and
  `open() without encoding=` are syntactically specific and do not require semantic analysis.
- **Scope is broader than PowerShell.** The same silent-corruption risk exists in any runtime
  that defaults to system locale encoding. ADR-009 captures the cross-language pattern.
- **This is a strong dogfooding signal.** Real production incident, deterministic root cause,
  enforceable pre-execution condition, clear consequence chain. Candidate for a benchmark
  scenario demonstrating governance-from-incident.
