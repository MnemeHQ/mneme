# BPMN, DMN, and bounded decision operations

Status: research note  
Scope: Open Architecture / O1 research only  
Date: 2026-10-02

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

The unexplored area is the mutation side:

> What bounded operations should an agent use when creating or modifying structured engineering decisions?

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

**O1B — External decision and process representations**

This label is provisional and should not be treated as a committed milestone.

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

Do not write to `.mneme/`, `MemoryStore`, `DecisionIndex`, or canonical authority services.

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

## Explicit non-goals

This research note does not authorize:

- adding BPMN Assistant as a dependency,
- adding BPMN or DMN parsers to the Mneme runtime,
- changing canonical Decision schemas,
- changing `.mneme/project_memory.json`,
- creating a new product integration,
- claiming BPMN/DMN interoperability,
- or promoting O1 research data into authoritative decisions.

## Recommended next review

Before implementation, perform an adversarial architecture review focused on:

1. whether "bounded decision operations" is a real domain abstraction or an attractive restatement of CRUD;
2. whether operation semantics belong in O1 research, the canonical Decision model, or a separate command layer;
3. whether ADR-023, ADR-028, ADR-029, and ADR-030 already constrain the answer;
4. whether precedence, lifecycle, authority, and provenance make mutations transaction-like;
5. whether the proposed research accidentally conflates inference, authorization, mutation, and enforcement;
6. which DMN semantics would make a Mneme-specific abstraction redundant;
7. what evidence would falsify the hypothesis.

No production implementation should begin until that review is complete.
