# DG1F — G3: missing-memory eligibility assessment (bounded recommendation)

**Status:** architecture **assessment and recommendation**, not a charter,
approval, or implementation plan. It authorizes **no** runtime change, no new
authority store, no ADR-033 acceptance, and no Layer 1 unfreeze.
**Source anchor:** `MnemeHQ/mneme` `main` at
`ff23c780429bb4461cd5df0612f9192402228018` (G1 evidence, PR #510).
**Governing contracts:** [ADR-030](../adr/ADR-030-canonical-decision-persistence-version-identity-and-stable-rule-lineage.md),
[ADR-021](../adr/ADR-021-shell-preflight-and-stop-session-delta.md), the
[blocking-semantics matrix](2026-10-14-dg1f-adversarial-blocking-semantics-matrix.md)
(S1), and the [G2 CI-consumer audit](2026-10-14-dg1f-g2-ci-consumer-coverage.md).

## 1. The question

> How can Mneme distinguish a repository that was **never protected** from one
> whose **authoritative decision memory has disappeared**?

Today both look identical to a consumer: `find_memory` returns `None`, and the
hooks **silently skip** (`return 0`) — the S1 behavior in the blocking-semantics
matrix. If ADR-033 later introduces fail-closed behavior, treating *every*
missing memory as a failure would block legitimate unprotected work; treating it
as a silent skip would keep silently disabling protection. A trustworthy
**eligibility witness** is therefore a prerequisite for fail-closed enforcement.

## 2. What the existing contracts actually provide

### 2.1 Activation lifecycle (`mneme/setup_state.py`)

- Activation is an optional top-level `activation` key **inside**
  `.mneme/project_memory.json` (schema `mneme.setup/v1`); the module states
  "No parallel state file is created."
- States: `not_installed | setup | active`; setup always writes
  `enforcement: "not_enabled"`; `active` is reachable only through an explicit
  future action. `mneme init` scaffolds memory **without** an activation record;
  `mneme setup` adds it.

**Consequence:** the activation record is **in-band**. Deleting the memory file
deletes the only activation witness with it.

### 2.2 Canonical persistence (ADR-030)

- `.mneme/project_memory.json`'s `decision_index` section is the **sole durable
  authority**; the switch is **section presence alone**; there is no second
  canonical store. Writers never migrate implicitly.

**Consequence:** there is no out-of-band authority marker to consult when the
file is gone.

### 2.3 Memory discovery and consumer behavior

- `mneme/integrations/claude_code/hook.py:find_memory` returns the path from
  `MNEME_MEMORY`, else walks up from `cwd` for `.mneme/project_memory.json`,
  else `None`.
- On `None`, the Claude Code gate and `stop_event` **`return 0` silently**;
  Codex gate → `SKIP`; Kiro → quiet zero (matrix S1, `Si`/`St`).

**Consequence:** "never protected" and "memory disappeared" are
indistinguishable in-band, and the default is a silent permit.

## 3. Candidate eligibility witnesses

A usable witness must be (i) **durable** — survive deletion of the memory file;
(ii) **trustworthy** — not silently forgeable by the governed agent; and
(iii) **not a new authority store**.

| # | Witness | Survives file deletion? | Trust boundary | Failure modes |
|---|---|---|---|---|
| W1 | `activation` record inside `project_memory.json` | **No** (in-band) | the memory file itself | cannot distinguish; unusable alone |
| W2 | **Git tracking** of `.mneme/project_memory.json` (a committed file) | **Yes**, if committed | git (durable, reviewable; `git rm` is a visible diff) | FP: repo commits memory but never intended blocking; FN: memory never committed, or history rewritten |
| W3 | Committed `decision_index`/`activation` snapshot in a **committed** memory file | Same as W2 | git | same as W2 |
| W4 | Hook/plugin **registration** (`.claude/settings.json`, installed plugin) | Yes | transport config, **agent-editable**, not authority | FP: hook installed for observation only; FN: hook removed with memory |
| W5 | `MNEME_MEMORY` environment variable | No (per-invocation) | caller environment | not durable |
| W6 | A **new** durable marker (e.g. `.mneme/active` or a git ref) | Yes | would be a **new authority store** | out of scope here (needs its own decision) |

## 4. Recommendation (bounded)

1. **The only existing durable witness is W2/W3 — git tracking of a *committed*
   memory file.** For a repository that commits `.mneme/project_memory.json`,
   git can establish that the file *was* present and is now absent, which is a
   positive "protected repo whose memory disappeared" signal.
2. **The `activation` record (W1) cannot be the witness**, because it lives in
   the file whose disappearance is the question.
3. **Hook/plugin registration (W4) is not sufficient authority** — it is
   agent-editable transport configuration, so it may corroborate but must not
   gate.
4. **Repositories that do not commit memory have no durable witness.** For
   them, fail-closed cannot be made safe by reusing existing artifacts; it would
   require a **new durable marker (W6)**, which is explicitly out of scope and
   needs its own architectural decision.
5. **Recommended eligibility rule (for a future, separately-authorized
   change):** treat missing memory as an operational *unavailable* state — not a
   silent permit — **only** when git positively witnesses that the repository
   committed an authoritative memory file. Otherwise, keep today's
   inactive/skip behavior and surface it as *inactive*, never as *pass*.

**Trust boundary:** the witness is git history/state for a committed path — the
same durable, reviewable boundary ADR-030 already relies on for the memory file
— never an agent-supplied argument or in-band field.

**Failure modes to carry forward:** W2 false positives (a repo commits memory
for retrieval context but never intends blocking) must not be forced into
fail-closed without an explicit opt-in; W2 false negatives (memory never
committed, shallow clones, history rewrite) must fall back to the *inactive*
state, never to a fabricated *pass*.

## 5. Explicit non-authorization

This assessment authorizes **no** runtime, hook, CLI, schema, or benchmark
change; **no** new authority store or marker file; **no** ADR-033 acceptance or
implementation; and **no** Layer 1 unfreeze. It also does not change DG1F-C1b
(still locked) or DG1B2 (evidence-gated). Any eligibility/activation-witness
change requires its own charter and the matching `[layer1-freeze]` amendment
before implementation.
