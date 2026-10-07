# Protection Activation

Mneme can turn a classified Mneme-ready architectural decision into a real,
mechanically enforced guardrail. This page describes the activation workflow
and the exact guarantees behind it.

## Mneme-ready is not Protected

`mneme audit` classifies every active decision:

| Tier | Meaning |
| --- | --- |
| Protected | Deterministic intent **with** verified enforcement evidence |
| Mneme-ready | Deterministic intent with a concrete safe guardrail identified — an opportunity |
| Requires modelling | Deterministic intent that needs modelling before it can be a guardrail |
| Guidance | Not appropriate for deterministic enforcement |

Mneme-ready means "Mneme knows exactly which deterministic rule would protect
this, and none exists yet". It does not mean the decision is protected.

## The workflow

```bash
mneme protect list --memory .mneme/project_memory.json
```

Lists decisions that are active, currently unprotected, and canonically
Mneme-ready. Already-Protected, Requires-modelling, Guidance, and
superseded decisions are never candidates, and no model decides eligibility —
the audit's frozen classification decides it.

```bash
mneme protect validate <decision-id> --memory .mneme/project_memory.json
```

Runs four deterministic checks through the existing enforcement engine —
without writing anything and without enabling protection:

1. a prohibited input containing the forbidden token is detected as a FAIL;
2. a permitted input is not blocked by the proposed rule;
3. applicability is respected: ordinary artifact paths are enforced and the
   canonical policy sources (the memory file carrying the rule) stay exempt;
4. unrelated paths are unaffected.

**Validation is not activation.** A VALID result changes nothing in the
repository and moves no audit metric.

```bash
mneme protect activate <decision-id> --memory .mneme/project_memory.json
```

**Activation is an explicit user action.** Audit, setup, rule generation and
validation never enable protection; only this command installs enforcement.
It installs the typed `FORBID_LITERAL` rule for that one decision in project
memory, the same artifact `mneme check` and the agent hooks enforce, and
refuses on any unsafe or unsupported state. Activation is idempotent:
rerunning does not create duplicate rules.

How the rule is stored depends on the memory file:

- **Canonical memory** (one with a `decision_index` section: memory created
  by `mneme init` or `mneme setup`, or older memory converted with
  `mneme decision-index migrate`). The rule becomes a `protection` rule
  binding on the decision's active version. The version record and existing
  rules are never modified. If the same rule is already bound, nothing
  changes. The binding, the derived `decisions[]` snapshot, and the activation
  record are written together, and the write is refused if the file changed
  after it was read.
- **Section-less memory.** The rule is appended to the decision's
  `decisions[]` entry, as before.

A protection binding survives ADR evolution. If an edited ADR re-imported
with `--update-existing` no longer derives the rule, the import refuses until
you pass `--preserve-protection` or `--release-protection` for it. See ADR
import, "Protection continuity".

```bash
mneme protect status <decision-id> --memory .mneme/project_memory.json
```

Shows the decision's canonical tier, guardrail, evidence, and whether the
activation rule is installed — all derived from the repository, never stored.

## Activation is not verified protection

After activation Mneme does not simply mark the decision Protected. It
re-loads project memory from disk and re-runs the same canonical assessment
`mneme audit` uses. Only when that independent assessment observes real
enforcement evidence is the activation reported as verified:

```text
Protection activated and verified: [config-format] (rule installed)
  rule: FORBID_LITERAL "yaml"
  verification: canonical assessment reports protected
```

If activation is requested but no enforcement evidence is observable, the
decision remains NOT Protected, Current Protection does not increase, and the
command says so. The audit score is always a consequence of canonical
classification — never edited directly.

## Walkthrough

```bash
# What can be activated?
$ mneme protect list --memory .mneme/project_memory.json
Protection activation candidates
============================================================
Protected: 1  Mneme-ready: 2  Requires modelling: 1  Guidance: 1
Candidates: 1

[1] config-format: Use JSON for configuration files
    guardrail: FORBID_LITERAL: yaml
    rule to install: FORBID_LITERAL "yaml"
    applies to: global applicability (canonical policy sources exempt)
    enforcement: FORBID_LITERAL fails on an exact case-sensitive match, ...

# Prove the rule behaves correctly before touching anything
$ mneme protect validate config-format --memory .mneme/project_memory.json
Validating proposed protection for [config-format]
  proposal:  FORBID_LITERAL "yaml"
  checks:
    PASS prohibited_detected: input containing 'yaml' is a typed FAIL
    PASS permitted_allowed: permitted input without 'yaml' is not blocked
    PASS path_scope_respected: artifact path enforced=True, canonical policy source exempt=True
    PASS unrelated_paths_unaffected: unrelated artifact path enforced=True, permitted content blocked=False
Result: VALID
Validation never activates protection.

# Activate (explicit) — verified by a fresh canonical assessment
$ mneme protect activate config-format --memory .mneme/project_memory.json
Protection activated and verified: [config-format] (rule installed)
  rule: FORBID_LITERAL "yaml"
  verification: canonical assessment reports protected
Re-run `mneme audit` to observe the new Protected decision.

# The audit now independently observes the protection
$ mneme audit --memory .mneme/project_memory.json --repo-root .
```

## Boundaries

- One decision per activation; there is no "protect everything".
- Activation never overwrites user-authored rules or unrelated configuration.
- No network, cloud, or model involvement anywhere in the path.
- Requires-modelling and Guidance decisions are not activatable; converting
  them is a separate modelling task.
- Legacy-migrated decisions (from `items[]` rather than `decisions[]`) cannot
  be activated; the command fails closed.
