---
id: ADR-018
title: "Introduced-Delta Enforcement at the Edit Gate"
status: accepted
priority: foundational
date: 2026-08-08
scope: enforcement.change_scope
---

# ADR-018: Introduced-Delta Enforcement at the Edit Gate

**Status:** Accepted
**Date:** 2026-08-08
**Deciders:** Theo Valmis

---

## Context

ADR-017 settled *which decisions* are enforced against an edit. It did not
settle *which text* they are enforced against. The Claude Code hook
materialized the entire resulting file and checked all of it, and no ADR
recorded that as a decision — it was the incidental consequence of
`materialize_proposed_content` returning a whole file.

Two problems follow, and both surface on first contact with a real repository.

### Pre-existing violations block unrelated edits

If a forbidden literal already sits anywhere in a file, every later edit to
that file is blocked: edits to a different function, edits that change nothing
relevant, and — worst — the edit that removes the violation. Installing Mneme
on an existing codebase converts pre-existing debt into an immediate wall
rather than a gradual tightening. That is adoption friction precisely at the
moment a design partner forms their opinion of the tool.

### Self-reference

A file that *describes* a rule is subject to it. The ADR defining a forbidden
string, tests carrying it as a fixture, documentation explaining why it is
wrong, and migration guides showing before/after all fail legitimately.

This is observable in this repository: after ADR-017 landed, ADR-017 itself and
its own regression test both report FAIL, on the bare words `main` and
`enforcement`. The hand-built ADR-005 gate (`scripts/check_install_command.py`)
needed an explicit allowlist for the same reason, in two repositories.

## Decision

1. **The edit gate enforces on introduced content.** The Claude Code hook
   checks the lines an edit *adds*, not the whole file that results from it.

2. **Audit paths keep whole-file semantics.** `mneme check --input <file>`
   is unchanged and continues to answer "is this file compliant?" over the
   complete file. An edit gate and an audit ask different questions, and both
   are legitimate; conflating them is what produced the defect.

3. **"Introduced" is the inserted or replaced lines of a deterministic diff**
   from one snapshot of the file's current content to the content the tool is
   about to write. The implementation uses `difflib.SequenceMatcher` with
   `autojunk=False` and checks proposed lines from `insert` and `replace`
   opcodes. One definition covers `Edit`, `MultiEdit`, and `Write`: a new file
   diffs against nothing, so all of its content is introduced; a `Write` over
   an existing file checks only its inserted or replaced lines.

4. **Movement attribution follows the deterministic diff.** A moved line that
   the diff represents as an insertion is checked. A block aligned as unchanged
   is not, even if its absolute line number moved. Two text snapshots cannot
   establish semantic author intent, so this gate does not claim universal move
   detection. Whole-file audit remains the standing-compliance backstop.

5. **An edit with no inserted or replaced non-blank lines is not checked.** A
   pure deletion cannot introduce a non-blank mechanical rule value. A
   whitespace edit that replaces a non-blank line is still checked as a
   replacement; it is not silently classified as deletion-only.

6. **This does not resolve self-reference.** Introducing an ADR that names a
   forbidden string *is* introducing that string, so the document explaining a
   rule still trips it on the commit that creates it. Solving that needs
   per-rule exemptions or path applicability. ADR-019 deliberately provides
   only canonical policy-source exemptions for `FORBID_LITERAL`; broader
   applicability remains open under #150 and the unresolved half of #259. It
   is not papered over here with a global allowlist, because an allowlist not
   recorded in the decision recreates the invisible governance this project
   exists to remove.

## Consequences

- Installing on a repository with existing violations no longer blocks work in
  the affected files. Adoption becomes "clean as you code" rather than
  "remediate before you can edit".
- Remediation edits are never blocked by the violation they remove, which was
  previously a genuine deadlock: the only way out was to disable the hook.
- This resolves the pre-existing-violation half of #259. The issue remains open
  for rule self-reference and applicability; this ADR does not claim otherwise.
- A file can remain non-compliant indefinitely if nobody edits the offending
  lines. That is the accepted trade: the gate's job is to stop new violations,
  and the audit path exists to report standing ones. A repo-wide audit mode
  (#251) is the right surface for the second question.
- A rule can only match within introduced lines. A violation split across an
  introduced line and an untouched one is not caught at the gate. Rules today
  are literal tokens rather than multi-line patterns, so the exposure is
  narrow, and the whole-file audit still sees it.
- The hook reads the file's current content once and derives both current and
  proposed snapshots from that read. A missing, unreadable, or non-UTF-8 target
  of `Write` is conservatively treated as new, so its proposed content is
  enforced in full rather than skipped.
- This ADR asserts no change to the CLI's behaviour, exit codes, or JSON
  verdict schema.

## Alternatives considered

**Final-state compliance (the previous behaviour).** Stronger guarantee: after
any accepted edit the file is fully compliant. Rejected because it is
unachievable on an existing codebase without a remediation project first, and
because it blocks its own remediation. It does not solve self-reference either;
new rule documentation can still introduce the literal it describes.

**Baseline/suppression file.** Record existing violations and ignore them until
touched. Rejected for now as a second source of truth that drifts from the
decision record — the same failure mode as the hand-built ADR-005 gate.

## Related

- ADR-017: Enforcement Scope Is Independent of Retrieval Scope — settles which
  decisions apply; this ADR settles which text they apply to
- ADR-019: Typed Literal Rule Contract — defines the current typed vocabulary
  and its canonical policy-source exemptions
- Issue #259 (partially resolved here; self-reference remains), #150 (rule
  applicability), #251 (repo-wide audit mode), #250 (completed typed-rule
  capability)
