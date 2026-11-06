# BPMN, DMN, and bounded decision operations

Status: research note  
Scope: Open Architecture / O1 research only  
Date: 2026-10-02  
Review: adversarial architecture review completed 2026-10-02 (see "Adversarial review record"); the hypothesis is narrowed, not confirmed

## Purpose

This note records a bounded research finding from reviewing BPMN Assistant and DMN in relation to Mneme's Open Architecture work.

It does **not** propose BPMN support, a BPMN dependency, a DMN implementation, or a change to Mneme's canonical runtime.

The question under investigation is narrower:

> Can the architectural pattern used by BPMN Assistant — an LLM operating through a constrained semantic representation and bounded operations, with deterministic validation around the state transition — help define how agents should safely create and modify Mneme decision data?

A second question is:

> What can BPMN and DMN teach us about the boundary between process models, executable business-decision models, and Mneme's engineering-decision model?

## Sources reviewed

Primary external sources:

- BPMN Assistant paper: https://arxiv.org/html/2509.24592v1
- BPMN Assistant implementation: https://github.com/jtlicardo/bpmn-assistant
- OMG DMN 1.6 specification page: https://www.omg.org/spec/DMN/1.6

Mneme sources inspected:

- `mneme/open_architecture/orchestrator.py`
- `mneme/open_architecture/classification.py`
- `mneme/open_architecture/schemas.py`
- `mneme/open_architecture/store.py`

Added by the adversarial review (the original draft inspected only the O1 research package, which is why it described mutation as unexplored):

- `mneme/decision_authority.py` (`DecisionAuthorityService.accept` / `reject`)
- `mneme/protection.py` (`activate_protection`, `_install_rule`)
- `mneme/decision_index.py`, `mneme/decision_proposal_store.py`, `mneme/adr_import.py`
- ADR-017, ADR-019, ADR-020, ADR-023, ADR-027, ADR-028, ADR-029, ADR-030
- `docs/research/open-architecture/program.md`

## Finding 1: BPMN Assistant is an intermediate-representation and state-transition architecture

BPMN Assistant does not rely only on prompting an LLM to emit BPMN XML.

The paper defines a JSON representation of the process and a set of process-editing functions. The current implementation represents an edit proposal as a structured function plus arguments and dispatches it to explicit editing functions such as:

- `add_element`
- `delete_element`
- `move_element`
- `update_element`
- `redirect_branch`

The editing service validates:

1. the proposal shape,
2. function-specific arguments,
3. affected elements,
4. and the resulting complete process.

Invalid changes are rejected and the validation error is returned to the model for another proposal.

The useful abstraction is therefore:

```text
natural-language intent
        |
        v
model proposes structured operation
        |
        v
deterministic operation validation
        |
        v
deterministic state transition
        |
        v
whole-model validation
        |
        v
serialized native artifact
```

The research value is not JSON itself. The value is reducing the model's action space and placing deterministic validation around state transitions.

### Evidence from the paper

The paper reports similar structural generation quality for JSON and XML, but greater reliability for the JSON representation and higher editing success. For BPMN editing, it reports average latency of 21.46 seconds for JSON versus 46.98 seconds for direct XML, and average output tokens of 364.14 versus 2,665.32.

These results are specific to the authors' benchmark and model setup. They are evidence for the pattern, not evidence that the same quantitative improvement will transfer to Mneme.

Two qualifications from the paper's own editing table (40 editing tasks per model, eight models) limit how far the result transfers:

- Absolute editing success is low even with the constrained representation: 0.38 to 0.68 for JSON, 0.05 to 0.65 for XML. Roughly a third or more of bounded edits still fail.
- The reliability gap shrinks as model strength rises. The strongest model tested scored 0.68 (JSON) against 0.65 (XML); the large gaps belong to weaker models (0.45 against 0.05, 0.50 against 0.08). The pattern mostly rescues weak models from a verbose target format.

The latency and token savings come from BPMN XML being verbose (2,665 output tokens per edit). A Mneme decision record is a few hundred tokens in full, so the cost argument does not carry over, and the reliability argument has to be re-earned against a frontier-model baseline.

### Important qualification

The current implementation does not express every complex edit as a sequence of small atomic functions.

For processes containing pools, subprocesses, or boundary handlers, the editing service can require `replace_process`, where the model proposes the complete replacement process and the application validates it atomically.

So the stronger general principle is not:

> All agent changes should be decomposed into tiny operations.

It is:

> Agents should operate through the smallest semantically meaningful action space that preserves the invariants needed by the domain, and proposed state transitions should be validated outside the model.

That principle is directly testable for Mneme.

## Finding 2: O1 already follows half of this pattern

O1 already separates probabilistic interpretation from deterministic representation.

The current pipeline is approximately:

```text
repository evidence
      |
      v
candidate extraction
      |
      v
semantic classification
      |
      v
fail-closed normalization
      |
      v
DecisionCandidate
      |
      v
ResearchStore
```

The `DecisionCandidate` research model already represents dimensions including:

- normalized decision,
- classification,
- domain,
- purpose,
- authority,
- scope,
- lifecycle,
- relationships,
- enforcement potential,
- candidate rule,
- confidence,
- human validation.

The classifier contract is backend-neutral, and the normalizers fail closed when model output does not belong to the declared vocabulary.

This means Mneme does **not** need to copy BPMN Assistant's architecture. O1 already embodies a related principle on the interpretation side.

The original draft called the mutation side unexplored. That is true only inside the O1 research package. `ResearchStore` is run-scoped insert/upsert of inferred data and has no mutation semantics worth bounding.

In the canonical layer, bounded, validated-before-write, verified-after-write operations already exist:

| Existing operation | Where | Shape |
| --- | --- | --- |
| `decision.propose` / `decision.propose_batch` | ADR-027 §4-§5, `mneme/decision_index_service.py` | producer-callable, never authoritative, idempotent |
| `accept` / `reject` | `mneme/decision_authority.py` | human authority only; validate, transition, materialize, reload, verify; fail-closed recovery |
| `activate_protection` | `mneme/protection.py` | eligibility precheck, deterministic rule validation, install, independent re-assessment |
| ADR import | `mneme/adr_import.py` | compile, collision detection, preview, apply |

This is the BPMN Assistant pattern already (operation validation, state transition, whole-state verification), minus the LLM as proposer of the operation. So the open question is narrower than the draft stated:

> Beyond `propose`, is there any operation an agent should be allowed to *propose* against an existing canonical decision, and does naming those operations add integrity over proposing a complete new decision version?

## Hypothesis: a bounded operation vocabulary for decision data

A candidate operation vocabulary could include:

```text
create_decision
update_statement
change_scope
change_authority
change_lifecycle
supersede_decision
add_relationship
remove_relationship
add_exception
attach_rule
detach_rule
attach_evidence_requirement
```

This list is intentionally provisional.

### What the accepted and proposed ADRs already say about each operation

The review mapped the list onto ADR-030's content tiers and ADR-027's authority boundary. ADR-030 is `proposed` and not implemented (no `decision_index` section, `version_id`, or `active_version_id` exists in `mneme/` today), so this mapping is against a design contract, not running code.

| Draft operation | Existing semantics | Review verdict |
| --- | --- | --- |
| `create_decision` | `decision.propose` then human `accept` (ADR-027) | already exists; not new |
| `update_statement`, `change_scope` | ADR-030 §6 Tier 1: any change to statement, rationale, scope, constraints, or anti-patterns creates a new immutable version occurrence and moves the active pointer | one operation ("new version occurrence"), not two; splitting by field is field-level CRUD |
| `attach_rule` | `activate_protection` today; ADR-030 §9 rule binding later. ADR-019 forbids rules by assertion | exists; must stay deterministic and human-triggered |
| `detach_rule` | no defined semantics. ADR-030 never mutates or removes a binding; a rule set changes only through a new binding or a new version | undefined; needs an ADR before any experiment encodes it |
| `change_lifecycle` | ADR-030 Tier 3, authority-gated; version state derives from the active pointer, with no second state machine (§11) | exists as a concept; no writer yet (D1E) |
| `supersede_decision` | ADR-030 §11: a relationship record that drives the *target's* lifecycle transition, distinct from same-decision version replacement | the one clearly compound, cross-record operation |
| `add_relationship`, `remove_relationship` | ADR-030 §11 permits only `supersedes`; new relationship kinds are a non-goal. ADR-023 §9: representable relationships gain no operational semantics | generic form is barred; reduces to `supersede_decision` |
| `change_authority` | no canonical field. Authority is the proposal-to-acceptance path. O1 `authority_status` is an inferred research label | category error; remove |
| `add_exception` | ADR-023 §16, ADR-027 §3/§7, ADR-030 non-goals: no exception runtime behavior. O1 `exception_to` / `create_exception` are research labels | barred pending a dedicated ADR |
| `attach_evidence_requirement` | no such concept. ADR-024 declared test evidence is Tier 3 metadata; ADR-029 evidence is observed and bound, never attached by a caller | undefined; do not invent in an experiment |

Net result: of twelve draft operations, the ones with stable semantics are already built or already specified, and they reduce to roughly four: propose a decision, propose a new version of a decision, supersede a decision, and bind a rule. The rest are either field-level splits of "new version", or have no canonical semantics.

That is the CRUD risk in concrete form. What is *not* CRUD is the machinery around the write (immutable occurrences, occurrence-key idempotency, predecessor-bound identity, fail-closed half-state handling, independent post-write verification). That machinery is ADR-030's contribution and does not depend on an operation vocabulary.

### Where the semantics belong

- Not O1. Research candidates are inferred, run-scoped, and never authoritative (`mneme/open_architecture/projection.py`, `docs/research/open-architecture/decision-research-store.md`).
- Not the canonical Decision model. ADR-030 makes version records immutable; operations are not properties of records.
- In the Mneme-owned authority/write layer. ADR-027 (D2C amendment) assigns lifecycle, persistence, collision, provenance, and recovery rules to a dedicated authority service; ADR-030 §1 allows only Mneme-owned validated canonical write paths to write `decision_index`, and its slices D1C to D1E are where those writers get built.

So any finding from this research is an input to D1C-D1E design review. It is not an O1 deliverable and should not produce a parallel operation schema.

The operation set should not be promoted into runtime code until research establishes:

- which operations correspond to stable domain semantics,
- which invariants each operation must preserve,
- which operations need human authorization,
- which transitions should be impossible,
- whether compound operations are required,
- how provenance is attached,
- how conflicts and precedence interact with mutation,
- and how operations map to the canonical persistence and authority model.

A useful target shape for later experimentation is:

```json
{
  "operation": "supersede_decision",
  "target_decision_id": "ADR-017",
  "arguments": {
    "replacement_decision_id": "ADR-031"
  },
  "actor": {
    "type": "agent",
    "authority_context": "..."
  },
  "provenance": {
    "source": "...",
    "request_id": "..."
  }
}
```

The example is illustrative only and is not a proposed schema.

Review correction: the envelope as drawn violates the authority boundary and must not be used as an experiment target in this form.

- An `actor` block with an `authority_context` supplied by the caller is a producer asserting authority. ADR-027 §3 and ADR-030 §1 forbid that, and ADR-029 §5 states the same rule for evidence (no caller-supplied field may manufacture trust).
- `supersede_decision` issued by an agent is one of the operations ADR-027 names as never producer-callable (`accept`, `activate`, `supersede`, `create_exception`, and any alias).
- Caller-supplied `provenance` is informational only (ADR-027 §9, ADR-030 §10).

The only shape consistent with the ADRs is a *proposal of an operation*: it enters the proposal store as `proposed`, carries producer provenance, has no effect until a human authority action applies it, and is applied by a Mneme-owned writer. ADR-027 currently defers "proposal amend/update operations", so even that shape needs an ADR-027 amendment before it is more than a research fixture.

## Finding 3: BPMN, DMN, and Mneme occupy different semantic layers

### BPMN

BPMN primarily represents process flow:

> What work happens, in what order, through which activities, events, and gateways?

BPMN can identify where a decision or control occurs in a workflow, but a process model is not by itself an authoritative engineering-decision model.

### DMN

DMN provides a formal representation for decisions and decision logic. It includes decisions, input data, business knowledge, knowledge sources, dependencies, and executable decision logic such as decision tables and FEEL expressions.

DMN 1.6 is the current formal OMG version as of September 2026.

The relevant research question is not whether Mneme can reproduce DMN. It is where their semantics differ.

A simplified distinction to test is:

```text
DMN
inputs -> decision logic -> output

Mneme
change/task
    -> applicable engineering decisions
    -> authority/lifecycle/precedence resolution
    -> constraints/guidance/exceptions
    -> enforcement
    -> evidence
```

There is real overlap around explicit decision representation. The expected distinction is that Mneme is centered on durable engineering intent, applicability to work, authority, lifecycle, precedence, enforcement, provenance, and evidence rather than primarily evaluating business rules to produce a result.

This distinction should be tested against the DMN specification rather than treated as settled positioning.

Review corrections to the diagram and the distinction:

1. The Mneme pipeline above is not the current architecture. It draws one chain from applicability through "precedence resolution" to enforcement. In the runtime these are separate by decision: retrieval is relevance only and never gates enforcement (ADR-017, ADR-023 §13); decision scope is not rule applicability (ADR-023 §5, ADR-020); precedence is resolved once at ADR compile time (`adr_compiler.resolve_precedence`, consumed in `mneme/decision_index.py`), not per change; exceptions do not exist; enforcement evidence is specified (ADR-029) but not persisted. Treat the diagram as a target sketch.
2. Mneme's own evaluation step *is* DMN-shaped. "Change context in, governing decision set out" is inputs, logic, output. ADR-020 include/exclude selectors are expressible as a decision table with a Collect hit policy. The difference from DMN is therefore not at evaluation; it is in what surrounds the decision record.
3. Two items listed as Mneme-specific have DMN constructs that must be compared before any claim is made:
   - authority: DMN Knowledge Source plus Authority Requirement record who or what is the authority for a decision;
   - precedence: DMN hit policies (Unique, Any, Priority, First, Collect, Rule order, Output order) are a specified conflict-resolution vocabulary among rules.

   Likewise `depends_on` / `requires` relationships overlap DMN information and knowledge requirements in the decision requirements graph.
4. What DMN does not specify, as far as this review could establish from general knowledge of the standard (Experiment C must confirm against the 1.6 text): decision lifecycle states, immutable version identity, supersession, source provenance chains, exceptions or waivers, enforcement evidence, and mutation semantics. DMN is an interchange and execution model; it says nothing about how a model may be edited. So DMN cannot make a Mneme mutation layer redundant, and equally cannot validate one.

## Process IR and Decision IR should remain separate in the experiment

A process representation and a decision representation can reference each other without becoming one schema.

Example experimental process:

```text
Change proposed
      |
      v
Identify change context
      |
      v
Retrieve governing decisions
      |
      v
AI agent implements change
      |
      v
Run deterministic controls
      |
      v
   pass? ---------------- no ----------------> exception request
      |                                          |
     yes                                         v
      |                                    authority review
      v                                          |
   evidence                              approve / reject
      |                                   |          |
      v                                   v          v
    merge                              evidence     revise
```

Possible bindings:

- "Retrieve governing decisions" -> Mneme applicability query
- "Run deterministic controls" -> Mneme enforcement
- "Exception request" -> exception relationship / waiver semantics
- "Authority review" -> authority semantics
- "Evidence" -> enforcement evidence

The experiment should test whether the process can carry stable references to Mneme decision identities while Mneme remains authoritative for decision semantics.

## Proposed research track

Working label:

**O1-EXT (unassigned) — External decision and process representations**

This label is provisional and should not be treated as a committed milestone. The draft used "O1B", which is already assigned in `docs/research/open-architecture/program.md` to "Maintainer-verified Decision Index". This track is not part of that milestone and has no slot in the O1A to O1D sequence.

Study three representations:

| Representation | Primary concern | Research relevance |
| --- | --- | --- |
| BPMN | process / workflow | how agents safely manipulate structured process models |
| DMN | executable decision logic | how established standards represent decisions and dependencies |
| Mneme | engineering decisions | applicability, authority, lifecycle, precedence, enforcement, evidence, provenance |

The output should initially be comparative evidence, fixtures, and schemas. It should not add BPMN or DMN dependencies to the runtime.

## Minimal experiment

### Experiment A: bounded decision operations

Create an isolated research fixture containing a small decision graph and implement a non-runtime validator for a provisional operation envelope.

Test operations such as:

1. change scope,
2. add an exception,
3. supersede a decision,
4. attach an enforcement rule,
5. attach an evidence requirement.

Measure:

- invalid-operation rejection,
- invariant preservation,
- ability to explain rejection,
- provenance preservation,
- whether compound edits require a transaction-like operation.

Do not write to `.mneme/`, `MemoryStore`, `DecisionIndex`, `DecisionProposalStore`, or canonical authority services.

Review changes to the design. As drafted, the experiment cannot fail: its authors write both the invariants and the validator, so "invalid-operation rejection" and "invariant preservation" measure whether the validator implements its own spec. Required changes before it is run:

1. **Baseline arm.** Compare the operation vocabulary against a single generic operation, "propose a complete new version of decision X", checked by a whole-state validator. This is BPMN Assistant's own `replace_process` path. If the generic arm rejects the same invalid transitions, the vocabulary adds nothing.
2. **Invariants come from the ADRs, not from the experiment.** Use only invariants already stated in ADR-023, ADR-027, ADR-029, and ADR-030 (for example: Tier 1 change implies a new version occurrence; no silent rule carry-over across versions; supersession moves the target's lifecycle; no positional rule identity; reverse half-states fail closed). An invariant invented for the experiment is a design proposal and must be labelled as one.
3. **Fixture from real history.** Replay actual changes rather than synthetic ones: this repository's ADR corpus, including ADR-016 superseding seven site ADRs in one decision (a one-to-many supersession the draft vocabulary cannot express as a single operation), and the `rules[]` enrichment that `activate_protection` performs after acceptance.
4. **Frontier-model control.** Include a strong model emitting full records. The paper's gap is 0.03 at the top of its model range.
5. **Reuse, do not reimplement.** Any check on statement intent must call `mneme.enforcer.assess_decision_intent` (ADR-028). A research validator that re-derives intent semantics is the divergence ADR-028 prohibits. Note that a statement edit can flip intent between prescriptive and advisory and so change an Audit tier with no rule change; that is a real cross-surface invariant worth testing.
6. **Operations excluded from the fixture** until an ADR defines them: `add_exception`, `change_authority`, `attach_evidence_requirement`, `detach_rule`, and any relationship kind other than `supersedes`.
7. **Pre-registration.** Fix the task set, the invariants, and the thresholds in "Falsification criteria" below before running.

### Experiment B: BPMN-to-Mneme references

Create one BPMN fixture for a software-change workflow.

Attach stable Mneme decision references to a small number of tasks or gateways without embedding the full Mneme decision model inside BPMN.

Test:

- whether a process task supplies enough context for applicability lookup,
- whether decision identity survives process editing,
- whether BPMN changes can invalidate a decision reference,
- and whether enforcement/evidence remain external to the BPMN model.

No BPMN runtime integration is required.

### Experiment C: DMN comparison

Produce a source-backed comparison across:

- decision identity,
- inputs/context,
- scope/applicability,
- authority,
- lifecycle,
- precedence,
- relationships,
- exceptions,
- executable logic,
- enforcement,
- evidence,
- provenance,
- mutation semantics.

The result should identify both overlap and non-overlap. Avoid positioning language until the comparison is complete.

## Decision gates

Continue this research only if at least one of the following is demonstrated:

1. a bounded operation model materially strengthens safe mutation of Mneme decision data;
2. external process context improves applicability evaluation without coupling Mneme to BPMN;
3. DMN exposes reusable semantics or interoperability opportunities that reduce invention in Mneme;
4. the comparison identifies a clear standards boundary useful for the Decision Data Engine.

Stop or archive the track if:

- the operation vocabulary simply mirrors CRUD with no meaningful domain invariants;
- process bindings require BPMN-specific concepts inside canonical Mneme decisions;
- DMN already covers the proposed semantics with no material Mneme-specific requirement;
- or the experiment creates runtime complexity without improving decision integrity.

Review note: the continue gates are disjunctive and qualitative ("materially strengthens", "exposes reusable semantics"), so almost any outcome satisfies one of them, and the stop conditions have no measurable test. The criteria below replace them for the bounded-operation hypothesis. Experiments B and C keep the gates above.

## Falsification criteria for the bounded-operation hypothesis

The hypothesis is: *a named operation vocabulary gives agents a safer way to change Mneme decision data than proposing complete decision versions through the existing propose/accept path.* It is falsified if any of the following holds on the pre-registered fixture:

1. **Reduction to field writes.** Every operation's invariants can be checked by looking only at the target record's new field values. Operationally: fewer than three operations have an invariant that references another record, the version history, or the active pointer. (On the review's mapping, only supersession and rule binding clearly qualify today.)
2. **No advantage over the generic arm.** Whole-version proposal plus whole-state validation rejects at least as many invalid transitions and accepts at least as many valid ones as the operation-specific arm.
3. **Vocabulary is not closed.** More than a small pre-registered share of real historical changes (suggested: 10%) needs a compound or free-form operation. One-to-many supersession already counts against closure.
4. **Authorization does not vary by operation.** If every operation needs the same human authority step that ADR-027 already requires for acceptance, the operation name carries no authorization information and the action space is no smaller in any way that matters for safety.
5. **No reliability gain for a strong model.** A frontier model proposing full records produces invalid proposals at a rate statistically indistinguishable from the bounded arm.
6. **Semantics already specified.** Every surviving operation maps one-to-one onto a writer ADR-030 already schedules (D1C to D1E). Then the research has produced a restatement of ADR-030 and should be closed with a pointer to it.

Evidence that would *support* the hypothesis: an invalid transition, drawn from real history or constructed from ADR-stated invariants, that the generic arm accepts and the operation arm rejects, where the difference is due to the operation's declared intent (for example, distinguishing a version replacement from a supersession that have identical resulting content).

## Explicit non-goals

This research note does not authorize:

- adding BPMN Assistant as a dependency,
- adding BPMN or DMN parsers to the Mneme runtime,
- changing canonical Decision schemas,
- changing `.mneme/project_memory.json`,
- creating a new product integration,
- claiming BPMN/DMN interoperability,
- or promoting O1 research data into authoritative decisions.

## Adversarial review record

The review requested below was performed on 2026-10-02 against `origin/main` at `134fbae5`. Its findings are folded into the sections above and marked as review corrections. Summary by question:

1. **Abstraction or CRUD?** Mostly CRUD as drafted. About four operations have domain semantics, and all four are already built or specified.
2. **Where do the semantics belong?** The Mneme-owned authority/write layer (ADR-027 D2C amendment, ADR-030 §1). Not O1, not the Decision model.
3. **ADR constraints.** ADR-027 (omitted from the draft's list, and the most binding) bars agent-issued accept, activate, supersede, exception, and rule creation. ADR-023 separates scope from applicability and retrieval from enforcement. ADR-029 bars caller-manufactured trust and defers identity to D1. ADR-030 fixes mutation as immutable occurrences plus an active pointer. ADR-028 requires intent checks to go through the public API.
4. **Transactional?** Yes, and already treated that way: acceptance is an ordered two-file write with explicit recovery; `_install_rule` changes a rule and the activation state in one atomic file replace; ADR-030 chose a single file to keep single-writer atomicity and defines occurrence-key idempotency. Supersession spans two decisions. One gap worth recording: `atomic_write_json` is an atomic replace with no lock or compare-and-swap, so two concurrent read-modify-write callers can lose an update. That matters more once agents are proposers, and it belongs to D1C, not to this track.
5. **Conflation?** Yes, in three places: the envelope mixes authorization into an operation payload; the Mneme pipeline diagram chains retrieval, precedence, and enforcement; and the BPMN bindings treat `decision.applicable_to` (retrieval/context only, ADR-027 §6) as an enforcement applicability query. O1's LLM-inferred `classification` and `authority_status` labels are also a second vocabulary beside ADR-028 intent and canonical lifecycle and must not be read as either.
6. **DMN redundancy?** Not for mutation (DMN has none). Possibly for relationship vocabulary, authority-as-source, and rule precedence. Mneme's applicability evaluation is itself DMN-shaped.
7. **Falsifiers.** See "Falsification criteria" above.

Recommendation: do not run Experiment A as originally drafted. Either run the revised design, or close the bounded-operation question by reference to ADR-030 and keep only Experiment C (DMN comparison), which is the part with new information.

## Original review request

The draft asked for an adversarial architecture review focused on:

1. whether "bounded decision operations" is a real domain abstraction or an attractive restatement of CRUD;
2. whether operation semantics belong in O1 research, the canonical Decision model, or a separate command layer;
3. whether ADR-023, ADR-028, ADR-029, and ADR-030 already constrain the answer;
4. whether precedence, lifecycle, authority, and provenance make mutations transaction-like;
5. whether the proposed research accidentally conflates inference, authorization, mutation, and enforcement;
6. which DMN semantics would make a Mneme-specific abstraction redundant;
7. what evidence would falsify the hypothesis.

No production implementation should begin until that review is complete. The review is recorded above; it does not authorize implementation.
