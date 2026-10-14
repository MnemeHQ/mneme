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

The assessment separates two questions: whether authoritative memory **once
existed** here (**Question A**) and whether the repository was **explicitly
protected** and should now fail closed (**Question B**). §4 shows only Question
A is answerable from existing evidence.

## 2. What the existing contracts actually provide

### 2.1 Activation lifecycle (`mneme/setup_state.py`)

- Activation is an optional top-level `activation` key **inside**
  `.mneme/project_memory.json` (schema `mneme.setup/v1`); the module states
  "No parallel state file is created."
- States: `not_installed | setup | active`; setup writes
  `enforcement: "not_enabled"`. **`active` is reachable today**: the explicit
  `mneme protect activate` action (M1.4) installs a typed protection rule and
  transitions the record to `active` with `activated_at` set
  (`mneme/protection.py`). `mneme init` scaffolds memory **without** an
  activation record; `mneme setup` adds it.

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
(iii) **not a new authority store**. Durability and trustworthiness are
**separate** properties (see §4.1): surviving deletion does not make a witness
trustworthy.

| # | Witness | Survives file deletion? | Trust boundary | Failure modes |
|---|---|---|---|---|
| W1 | `activation` record inside `project_memory.json` | **No** (in-band) | the memory file itself | cannot distinguish; unusable alone |
| W2 | **Git tracking** of `.mneme/project_memory.json` (a committed file) | **Yes**, if committed | **Durable but not automatically trustworthy** — the local index, refs and history are agent-modifiable; needs a trusted revision + independent verification | FP: repo commits memory but never intended blocking; FN: memory never committed, history rewritten, or a `MNEME_MEMORY` override |
| W3 | Committed `decision_index`/`activation` snapshot in a **committed** memory file | Same as W2 | same as W2 | same as W2 |
| W4 | Hook/plugin **registration** (`.claude/settings.json`, installed plugin) | Yes | transport config, **agent-editable**, not authority | FP: hook installed for observation only; FN: hook removed with memory |
| W5 | `MNEME_MEMORY` environment variable | No (per-invocation) | caller environment | not durable |
| W6 | A **new** durable marker (e.g. `.mneme/active` or a git ref) | Yes | would be a **new authority store** | out of scope here (needs its own decision) |

## 4. Recommendation (bounded)

Two questions must be kept separate:

- **Question A — did authoritative memory previously exist here?** Potentially
  yes, using *sufficiently trustworthy* git evidence for a committed memory
  path.
- **Question B — was this repository explicitly protected, and should it now
  fail closed?** **Not yet answerable** from existing git evidence.

Mneme currently conflates several distinct states, which must not be merged:

1. a repository **with decision memory** (it may be retrieval context only);
2. a repository where protection was **explicitly activated**
   (`activation.state == "active"`, reached via `mneme protect activate`);
3. a repository **explicitly configured** for a future fail-closed availability
   policy (no such flag exists yet).

Git can, at best, speak to (1)'s history. It cannot establish (2) or (3).

### 4.1 Git is a candidate *historical witness*, not an authorization

- **Durability is not trustworthiness.** Git tracking survives file deletion,
  but the local index, refs and history are **modifiable by an agent with
  repository access**. A witness that authorizes a protective action must name a
  **trusted revision** and an **independent verification** of it (for example a
  reviewed commit on a protected ref), not merely "the local clone says so."
- A **trusted revision** can potentially establish that protection **was
  activated at that revision**, provided the activation record and its
  protection binding are verified. It **cannot** establish that protection
  **remains active today**, nor that a future **fail-closed** policy was
  authorized.
- Therefore git is recorded as a **candidate historical witness** (Question A),
  **not** as an independently sufficient authorization mechanism (Question B).

### 4.2 The witness must be bound to the repository and the effective memory path

Memory discovery is ambiguous (`mneme/integrations/claude_code/hook.py:find_memory`):

- `MNEME_MEMORY` wins if set; if it points at a **non-existent** file, discovery
  returns `None` **even when the repository's own memory exists**;
- otherwise discovery **walks up parent directories**, so a child repo whose
  memory disappeared could resolve a **parent directory's** memory.

An eligibility witness must therefore be bound to the **intended repository
root** *and* the **effective memory path** it expects — not to "some memory file
was found or absent somewhere up the tree."

### 4.3 Bounded recommendation

1. Record git tracking of a committed memory file as a **candidate historical
   witness** for Question A only.
2. Do **not** treat it as authorization for fail-closed behavior: Question B
   needs an explicit, durable, independently verifiable **protection/eligibility
   declaration** that does not exist yet.
3. The `activation` record (W1) cannot serve — it lives in the file whose
   disappearance is the question.
4. Hook/plugin registration (W4) is agent-editable transport config, not
   authority.
5. Any future eligibility change must (i) bind the witness to the intended repo
   root and effective memory path, (ii) name the trusted revision and its
   independent verification, and (iii) preserve the distinction between "memory
   once existed", "protection was activated", and "fail-closed was configured".
   It requires its own charter + `[layer1-freeze]` amendment.

**Trust boundary:** a trusted, independently verified revision for a committed
path — never an agent-supplied argument, an in-band field, or an unverified
local clone state.

**Failure modes to carry forward:** false positives (memory committed for
context, never intended blocking) must not be forced into fail-closed without
explicit opt-in; false negatives (memory never committed, shallow clone, history
rewrite, or a `MNEME_MEMORY` override) must fall back to the *inactive* state,
never a fabricated *pass*.

## 5. Explicit non-authorization

This assessment authorizes **no** runtime, hook, CLI, schema, or benchmark
change; **no** new authority store or marker file; **no** ADR-033 acceptance or
implementation; and **no** Layer 1 unfreeze. It also does not change DG1F-C1b
(still locked) or DG1B2 (evidence-gated). Any eligibility/activation-witness
change requires its own charter and the matching `[layer1-freeze]` amendment
before implementation.
