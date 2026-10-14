# DMN 1.6 and the Mneme decision model: a source-backed comparison

Status: research note  
Scope: Open Architecture research only; no runtime, schema, or project-memory change  
Date: 2026-10-02

## Purpose

The bounded-operation review (`bpmn-dmn-bounded-operations.md`, PR #418) left one open question: where does Mneme overlap with an established decision standard, and is any Mneme concept reinventing a DMN semantic?

This note answers that by reading the DMN 1.6 specification text against Mneme's accepted ADRs, its one proposed persistence ADR, and the current implementation. It makes no product positioning claims.

## Sources and method

DMN:

- OMG Decision Model and Notation, version 1.6, formal/25-12-02 (260 pages), read directly. Clause numbers below refer to this document.
- The normative DMN 1.6 XML Schema (`DMN16.xsd`, dtc/24-05-20), used to confirm which attributes exist.

Clauses read in full: 1, 2, 5, 6.2.1 to 6.2.3, 6.3 (all of the requirements metamodel), 7.3.8, 8.1, 8.2.10 to 8.2.12, 8.3, 10.4, 13.1, 13.3, Annex A. The remaining text (mostly FEEL syntax, built-in functions, diagram interchange, worked examples) was keyword-searched rather than read line by line. Where a finding rests on an absence, the search terms are stated so it can be re-checked.

Mneme:

- ADR-017, ADR-019, ADR-020, ADR-023, ADR-024, ADR-026, ADR-027, ADR-028, ADR-029 (accepted); ADR-030 (proposed).
- `mneme/schemas.py`, `mneme/decision_index.py`, `mneme/adr_compiler.py`, `mneme/path_selectors.py`, `mneme/decision_authority.py`, `mneme/protection.py`, `mneme/enforcer.py`.

Two Mneme states are distinguished throughout:

- **current**: what runs on `main` at `134fbae5`;
- **target**: ADR-030, which `docs/architecture/README.md` lists as proposed target architecture. No `decision_index` section, `version_id`, or `active_version_id` exists in `mneme/` today.

Classification labels used per dimension: *semantic overlap*; *superficially similar but materially different*; *Mneme-specific*; *DMN-specific*; *unresolved*.

## The framing difference that drives everything else

DMN defines a decision as the act of determining an output value from input values using logic (clause 5.3.1). It explicitly adopts that sense over the other common sense of the word, the option that was chosen.

Mneme uses the other sense. A Mneme decision is a recorded choice: a statement of organizational intent with a rationale, which may have zero, one, or many machine-operational rules derived from it (ADR-023 §4).

So the two models attach the word "decision" to different things:

| | DMN | Mneme |
| --- | --- | --- |
| What a "decision" is | a repeatable determination, evaluated each time inputs arrive | a standing choice, made once and then applied to later work |
| What is evaluated at run time | the decision itself | a rule derived from the decision, against a proposed change |
| Typical scope stated by the spec | operational decisions in day-to-day business processes (5.2) | architectural decisions governing a codebase (ADR-023 context) |

The closest DMN analogue to a Mneme decision is therefore not a DMN Decision. It is a **Knowledge Source**: an authority such as a policy document that governs how determinations are made (5.2.1, 6.3.12). The closest DMN analogue to Mneme's enforcement check is a DMN **Decision** with a decision table. Several "overlaps" below are real only after this re-mapping, and several apparent overlaps (both have a thing called `decision` with an `id`) are superficial.

## Dimension-by-dimension comparison

### 1. Decision identity

- **DMN.** Every element has an optional `id`, constrained to XML ID syntax and unique within its containing `Definitions` (6.3.1, Table 3). `Definitions` carries a required `namespace` URI (6.3.2). Cross-file references use an href whose fragment is the element id (13.3.2). Names must be unique among decisions, input data, invocables, and imports in a model (6.3.7). Identity is therefore model-scoped and location-relative: namespace plus id.
- **Mneme.** `decision_id` is stable and independent of source file location; moving or renaming a source does not create a new decision (ADR-023 §3). Ids are human-assigned or deterministic hashes (`ddec-`, ADR-027 D2C amendment). Target: immutable version occurrences with content digests (ADR-030 §4).
- **Classification: superficially similar but materially different.** Both give a decision an identifier. DMN's is optional and scoped to a file's namespace, with no version component. Mneme's is mandatory, source-independent, and (target) versioned.

### 2. Input and context

- **DMN.** Inputs are typed and declared. `InputData` defines a variable whose type references an `ItemDefinition` (6.3.11). A Decision declares what it needs through Information Requirements (6.3.13), and the requirement graph must be acyclic (6.3.7). A decision service has an explicit interface of input data, input decisions, and output decisions (5.3.3, 6.3.10).
- **Mneme.** Enforcement input is an artifact path plus the text being evaluated (ADR-020, ADR-018). Retrieval input is a free-text query. The research package has an untyped `ChangeContext` (path, component, change type, dependencies, api, technology) in `mneme/open_architecture/schemas.py`, used only for benchmarking. No decision or rule declares the inputs it needs.
- **Classification: DMN-specific.** Declared, typed inputs and an explicit service interface have no Mneme counterpart. This is the largest capability gap in DMN's favour and the most relevant to `decision.applicable_to` (ADR-027 §6), whose input shape is currently informal.

### 3. Applicability

- **DMN.** Applicability is a rule-level concept inside a decision table: a rule is applicable when every input expression satisfies the corresponding input entry, and a rule with no input entries always applies (8.3.3). There is no notion of a decision being applicable or not applicable to a piece of work. The nearest construct is the informational `usingProcess` / `usingTask` association to BPMN (6.3.7, Annex A.5), which has no execution semantics.
- **Mneme.** Two separate things, deliberately kept apart: decision scope (retrieval and organizational relevance) and rule applicability (`include_paths` / `exclude_paths`), with `decision scope != typed-rule applicability` (ADR-023 §5, ADR-020). Rule applicability yields `APPLIED`, `EXCLUDED`, or `UNKNOWN` (`mneme/path_selectors.py`).
- **Classification: semantic overlap at rule level; Mneme-specific at decision level.** ADR-020 path selectors are structurally a single-input decision table: input expression "artifact path", input entries the glob patterns, and "no selector means global" matches DMN's "no input entries means always applicable". The decision-level scope concept, and the rule that it must not leak into enforcement, have no DMN equivalent. One real difference at rule level: Mneme has a third outcome, `UNKNOWN`, treated as an operational failure (ADR-029 §2). DMN's nearest behaviour is returning null on error (7.3.8), with strict or lenient mode chosen at evaluation time, not in the model.

### 4. Authority, Knowledge Sources, and Authority Requirements

- **DMN.** A Knowledge Source models an authority for a decision or business knowledge model. The spec's examples are domain experts, source documents, bodies of legislation, and sets of test cases the decision must be consistent with (5.3.1, 5.2.1). It has `type`, `owner`, and `locationURI` (6.3.12). An Authority Requirement links a governed element to its source of authority, and sources can chain (6.2.2.3, 6.3.15). The spec states plainly that Knowledge Sources and Authority Requirements have no execution semantics and that their interpretation is left to implementers (6.2.2.3).
- **Mneme.** Authority is a state transition, not an annotation. A proposal becomes a canonical decision only through an explicit human or Mneme authority action; producers can never assert it (ADR-027 §3, §7). The chain is: evidence exists, decision discovered, decision verified, decision authoritative (ADR-023 §8). Provenance never grants authority (ADR-030 §10).
- **Classification: superficially similar but materially different.** Both use the word authority. DMN's is descriptive: it records which source a decision's logic answers to, and nothing in the standard acts on it. Mneme's is operative: it gates whether a decision governs anything. The DMN construct does overlap with something else in Mneme, covered under provenance (dimension 12).

### 5. Dependencies and relationships

- **DMN.** Three typed requirement relations with strict connection rules (6.2.3, Table 2): information (data flow between decisions and input data, 6.3.13), knowledge (invocation of reusable logic, 6.3.14), and authority (6.3.15). Information and knowledge requirements carry execution semantics; the requirement graph is a DAG.
- **Mneme.** Current canonical relationships are `(type, target)` pairs, with only `supersedes` and `derived_from` required to be representable (ADR-023 §9). ADR-030 §11 restricts authoritative relationships to `supersedes` plus internal version lineage and bars new kinds. The research taxonomy has `requires`, `prohibits`, `depends_on`, `refines`, `conflicts_with`, `supersedes`, `exception_to` as inferred labels only.
- **Classification: superficially similar but materially different.** DMN relationships are about how one evaluation feeds another. Mneme relationships are about how one recorded choice stands relative to another over time. `depends_on` in the research taxonomy sounds like an Information Requirement but is not one: no Mneme decision consumes another decision's output. The only exact structural match is acyclicity: DMN requires an acyclic requirement graph, and `mneme/adr_compiler.py` rejects circular supersession.

### 6. Precedence and DMN hit policies

- **DMN.** Hit policies resolve overlap among rules inside one decision table (8.2.11). Single-hit policies: Unique (no overlap allowed, the default), Any (overlap allowed only if outputs agree), Priority (highest output priority wins, independent of rule order), First (rule order wins). Multiple-hit policies: Output order, Rule order, Collect with optional sum, min, max, count. The spec notes hit policy can be used to check correctness at design time, and warns that First tables are hard to validate.
- **Mneme, decision level.** `resolve_precedence` in `mneme/adr_compiler.py` resolves conflicts among accepted ADRs once, at compile time: status filter, explicit supersession, then within a scope group higher priority wins and a tie falls to the newer date; an unbreakable tie raises an error and no winner is picked. Losers become `inactive` and are never projected (`mneme/decision_index.py`).
- **Mneme, rule level.** No precedence at all. Every applicable typed rule is evaluated and any match is a violation (ADR-017, ADR-019). There is no allow-rule that could override a forbid-rule.
- **Classification: semantic overlap, at two different levels.**
  - Rule level: Mneme's evaluation is a Collect table. All applicable rules fire and the verdict aggregates them. Because every rule has the same output kind (a violation), rules cannot conflict, so no conflict-resolving policy is needed. That holds only while `FORBID_LITERAL` is the sole rule type.
  - Decision level: Mneme's same-scope resolution is the same *kind* of semantic as a single-hit policy (Priority, with a date tiebreak and fail-closed ambiguity). It differs in object and timing: it selects among decisions, not rules, and runs at compile time, not per evaluation. DMN has no equivalent of "ambiguity is an error and nothing wins"; its nearest is Unique, which forbids overlap outright.

### 7. Lifecycle and supersession

- **DMN.** None. The schema has no status, version, validity, or supersession attribute on any element (confirmed against `DMN16.xsd`). The specification text contains no occurrence of "supersed", and "deprecated" appears only for the standard's own retired features. The single use of "life-cycle" (6.3.2) concerns element containment: elements in a `Definitions` are not deleted when other elements are. The only version fields are `exporter` and `exporterVersion`, which name the tool that wrote the file.
- **Mneme.** Canonical lifecycle `active | superseded | deprecated | inactive` (`mneme/decision_index.py`); ADR status and `supersedes` in the source corpus; proposal lifecycle kept separate (ADR-027 §2). Target: immutable version occurrences, an explicit active pointer, and decision-to-decision supersession distinct from same-decision version replacement (ADR-030 §4, §11).
- **Classification: Mneme-specific.**

### 8. Exceptions

- **DMN.** No exception, waiver, or override concept. The word appears only in FEEL contexts (a thrown exception in an external function yields null, 10.3.2). Within a table, a more specific rule plus a First or Priority policy can express "except when", and `defaultOutputEntry` covers the no-match case (8.3.2), but these are logic, not governed deviations from a decision.
- **Mneme.** Not implemented. ADR-023 §16 says future exceptions may attach to the identity chain and introduces no behaviour; ADR-027 bars producer-created exceptions; ADR-030 lists exception and bypass lifecycle as a non-goal. `exclude_paths` is the only present mechanism that narrows a rule, and it is applicability, not a waiver. `exception_to` and `create_exception` exist only as research labels.
- **Classification: unresolved.** Neither side has the semantic. DMN will not supply it. If Mneme ever defines exceptions, the DMN-shaped option (a more specific overriding rule) is exactly what Mneme should avoid, because it hides a governed deviation inside rule logic with no authority record.

### 9. Executable decision logic

- **DMN.** The core of the standard. FEEL is a side-effect-free expression language with formal semantics (clause 10); decision tables, contexts, invocations, and function definitions are boxed expressions (7, 8, 10.2); business knowledge models are reusable functions (6.3.9); decision services are stateless and semantically equivalent to a FEEL function (10.4). Three conformance levels separate modelling from execution (2.1).
- **Mneme.** One typed rule, `FORBID_LITERAL`: an exact case-sensitive literal match with path applicability (ADR-019, ADR-020). Legacy `anti_patterns` and `"no X"` constraint matching remain under the Layer 1 freeze. No expression language; a higher-level policy DSL is explicitly deferred (`docs/architecture/current-phase.md`). Decisions with no rule are valid and common (ADR-023 §4).
- **Classification: DMN-specific.** Shared design values are real (deterministic, side-effect free, no inference from prose), but Mneme has no general logic layer and has decided not to build one now.

### 10. Enforcement

- **DMN.** None. A decision produces a value; what a caller does with it is outside the standard. The word "enforce" does not occur in the specification. Annex A notes that linking decisions to BPMN tasks allows validation of the association but does not by itself make processes execute the decisions (A.5).
- **Mneme.** The purpose of the runtime: checks at the edit gate and in CI that block or warn on a proposed change, evaluated independently of retrieval (ADR-017, ADR-018, ADR-021), plus Audit tiers that classify whether a decision is protected at all (ADR-026).
- **Classification: Mneme-specific.**

### 11. Evidence

- **DMN.** No evidence model. Two nearby constructs exist. Rule annotations are free text on a rule that implementations may use for auditing or logging, with no standard way to read them at execution time (8.2.11.1). A decision service may return additional information such as log records or rule annotations in an unspecified format (10.4). Separately, the spec lists "sets of test cases with which the decisions must be consistent" as one kind of Knowledge Source (5.3.1), again with no semantics.
- **Mneme.** Three defined channels: declared test evidence with exact selector binding (ADR-024), deferred trusted attestation (ADR-025), and enforcement observation that requires control, subject, decision, rule, applicability, and outcome bound to the same evaluation, failing closed otherwise (ADR-029). Not yet persisted.
- **Classification: Mneme-specific.** The test-cases Knowledge Source is a superficial match to ADR-024: same idea in one sentence, no binding, no trust boundary.

### 12. Provenance

- **DMN.** No provenance chain. Searches for "provenance" return nothing. What exists is the Knowledge Source with `locationURI`, `type`, and `owner`, the Authority Requirement linking it to what it governs, and per-file `exporter` metadata.
- **Mneme.** `CanonicalSourceEvidence` carries `source_type` and `source_locator` today (`mneme/decision_index.py`); ADR-023 §8 specifies `source_id`, `source_type`, `source_locator`, `source_revision`, `observed_at`, `evidence_hash`, `verification_status`; ADR-030 §10 freezes a provenance snapshot per version.
- **Classification: semantic overlap, partial.** This is the one place a Mneme structure and a DMN structure describe the same thing: *this decision derives from that source document*. A DMN Knowledge Source with `type` and `locationURI`, linked by an Authority Requirement, corresponds to Mneme's `source_type` and `source_locator` on a decision. Mneme adds what DMN lacks (revision, hash, observation time, verification status); DMN adds what Mneme lacks (sources as first-class shared elements that many decisions can reference, and chains of sources). In current Mneme, source evidence is embedded per decision, so two decisions from one ADR or policy document do not share a source record.

### 13. Human authority

- **DMN.** `decisionMaker` and `decisionOwner` associate a Decision with organisational units, and a Knowledge Source has an `owner` (6.3.7, 6.3.12). The spec calls `OrganisationalUnit` and `PerformanceIndicator` placeholders pending adoption from another OMG metamodel (6.3.8). These are informational; nothing depends on them. The spec also covers mixed human and automated decision-making as a modelling concern (5.2.2).
- **Mneme.** A hard boundary with running code: only an explicit human authority action moves a proposal to a canonical decision; six MCP tools and no accept, activate, supersede, or exception tool exists (ADR-027). `CanonicalDecisionRecord.owner` exists in `mneme/decision_index.py` but no adapter populates it; ADRs carry a free-text "Deciders" line that is not parsed into the canonical record.
- **Classification: superficially similar but materially different**, with one overlap. Who-owns-this is the same informational concept on both sides (DMN `decisionOwner`, Mneme `owner`), and Mneme's is currently empty. The acceptance boundary is Mneme-specific.

### 14. Mutation and version semantics

- **DMN.** None. DMN is an interchange and execution model. It defines how a model is serialized, including explicit support for interchanging incomplete models during iterative work (13.1), and nothing about how a model may be changed, by whom, or how versions relate. The introduction mentions "knowledge maintenance interfaces" for personnel who maintain logic over time (5.2.3) as a use of the model, not a specified mechanism. The one phrase "alternative versions of decision logic" (5.3.1) refers to multiple business knowledge models chosen by situation, not to versioning.
- **Mneme.** Current: validated, verified write paths with fail-closed recovery (`mneme/decision_authority.py`, `mneme/protection.py`). Target: immutable occurrences, occurrence-key idempotency, explicit active pointer (ADR-030 §4 to §6).
- **Classification: Mneme-specific.** This confirms the PR #418 review's provisional statement, now against the text: DMN cannot make a Mneme mutation layer redundant and cannot validate one.

### Summary table

| # | Dimension | Classification |
| --- | --- | --- |
| 1 | Decision identity | superficially similar but materially different |
| 2 | Input / context | DMN-specific |
| 3 | Applicability | semantic overlap (rule level); Mneme-specific (decision level) |
| 4 | Authority / Knowledge Sources / Authority Requirements | superficially similar but materially different |
| 5 | Dependencies and relationships | superficially similar but materially different |
| 6 | Precedence / hit policies | semantic overlap (at two different levels) |
| 7 | Lifecycle and supersession | Mneme-specific |
| 8 | Exceptions | unresolved |
| 9 | Executable decision logic | DMN-specific |
| 10 | Enforcement | Mneme-specific |
| 11 | Evidence | Mneme-specific |
| 12 | Provenance | semantic overlap (partial) |
| 13 | Human authority | superficially similar but materially different |
| 14 | Mutation / version semantics | Mneme-specific |

## Is Mneme reinventing a DMN semantic?

Mostly no, and the reason is the framing difference: the bulk of Mneme (lifecycle, authority gating, versioning, enforcement, evidence) sits in territory DMN does not enter. Three places deserve a direct answer.

1. **Rule applicability and evaluation (ADR-019, ADR-020).** Structurally a single-input Collect decision table. This is convergence on a decades-old form, not harmful reinvention: the Mneme version is a few dozen lines with a fail-closed `UNKNOWN` outcome DMN lacks, and adopting DMN here would import an expression language to match one glob. It becomes real reinvention the moment Mneme adds a second input dimension or a rule type whose outputs can conflict. At that point the questions DMN already answers (which rule wins, is the table complete, may rules overlap) arrive together.
2. **Same-scope precedence (`resolve_precedence`).** The same kind of semantic as a Priority single-hit policy. It is not a reinvention to worry about: it operates on decisions rather than rules, at compile time, with fail-closed ambiguity, which DMN does not offer.
3. **Source provenance (ADR-023 §8, ADR-030 §10).** The closest thing to duplication. Mneme models "decision derives from source" as embedded evidence; DMN models it as a shared, typed, linkable element. Mneme's content is richer; DMN's structure is better normalized.

One correction to the PR #418 note: it suggested DMN authority constructs and hit policies might make parts of a Mneme model redundant. Read against the text, authority does not (no execution semantics, by the spec's own statement), and hit policies overlap only in kind. The note also said DMN `depends_on`-style relationships overlap Mneme relationships; they do not, because DMN requirements describe evaluation data flow.

## 1. Semantics Mneme should reuse or align with

- **Hit policy vocabulary, as vocabulary.** If a rule type is ever added whose outcomes can disagree (an allow or require rule alongside forbid), name the combination semantics using the DMN terms (Unique, Any, Priority, First, Collect) in the ADR that introduces it, and state which one applies. Today the implicit policy is Collect, and ADR-019 could say so in one sentence at no cost.
- **The complete / overlapping distinction.** DMN separates "do rules overlap" from "does every input match some rule". Mneme's `UNKNOWN` applicability is an incompleteness signal; describing it that way aligns the two without changing behaviour.
- **Declared inputs for applicability queries.** DMN's requirement that a decision service declare its input data is the right discipline for `decision.applicable_to`. A declared, typed change-context shape (the research `ChangeContext` is a starting list) would replace an informal one.
- **Sources as first-class elements.** When ADR-030 provenance is implemented, consider whether a source (an ADR file, a policy document) should be a record that several decisions reference, as DMN Knowledge Sources are, instead of evidence embedded in each decision. This is a design question for D1B/D1C, not a requirement.
- **Owner as an informational field.** `decisionOwner` and Mneme's unpopulated `owner` are the same concept. Populating it from ADR "Deciders" would be alignment with an existing field, with no authority semantics attached.

## 2. Semantics Mneme should deliberately keep distinct

- **The meaning of "decision".** Mneme's is a standing choice; DMN's is a repeatable determination. Any document or integration that maps one onto the other one-to-one will be wrong. Say this wherever the two are mentioned together.
- **Authority as a gate.** DMN authority is an annotation. Mneme's must stay an explicit human state transition (ADR-027). Do not let a DMN-style "authority requirement" link be read as conferring authority.
- **Decision scope versus rule applicability.** DMN has only rule-level applicability. ADR-023 §5 and ADR-020 keep the two apart for a reason (ADR-017); a DMN-shaped model would merge them.
- **Lifecycle, version identity, supersession** (ADR-030). No DMN counterpart; nothing to align with.
- **Evidence binding** (ADR-029). Rule annotations and unspecified service logs are not a substitute for bound, fail-closed evidence.
- **Fail-closed ambiguity.** DMN returns null and continues in its default lenient mode (7.3.8). Mneme's refusal to pick a winner or to treat `UNKNOWN` as a pass is a deliberate difference.
- **No rule from prose** (ADR-019, ADR-028). DMN permits uninterpreted expressions and natural-language decisions at conformance level 1; that is a modelling convenience, not something to mirror.

## 3. Realistic interoperability opportunities

Ordered by how much specification support each has.

1. **Read-only export of the decision set as a DMN requirements-level model (conformance level 1).** Each source document becomes a Knowledge Source (`type`, `locationURI`); each enforcement check becomes a Decision; Authority Requirements link them. Mneme-only data (lifecycle, version ids, digests) travels in `extensionElements`, which the spec provides for exactly this and warns may be lost in interchange (6.3.16). Value: decisions become viewable in existing DMN tooling. Cost: a serializer. Risk: readers assume a Mneme decision is a DMN Decision; the mapping above avoids that only if it is documented.
2. **Export of typed rules as decision tables.** A decision's `FORBID_LITERAL` rules with path selectors render as a Collect table. Feasible, but the literal-match semantics would need a FEEL expression or the "uninterpreted" expression-language URI (6.3.2), so the table would be documentation, not portable executable logic.
3. **BPMN linkage through `usingTask` / `usingProcess`.** DMN already defines how a decision references a process task. This is the standard-backed version of "Experiment B" in the PR #418 note, and the spec is explicit that it is informational only.
4. **Import of DMN Knowledge Sources as proposals.** A DMN model's Knowledge Sources are pointers to policy documents. They could enter through `decision.propose` as candidates like any other producer output (ADR-027). Low value: a Knowledge Source carries a name and a URI, not a decision statement.

Not realistic: importing DMN decision tables as Mneme rules (no rule type could hold them), or executing DMN (see below).

## 4. Things we should explicitly not build

- A FEEL interpreter, or any DMN execution engine. It contradicts the deferral of a policy DSL and the Layer 1 freeze, and DMN evaluation is not enforcement.
- A DMN parser in the runtime, or DMN as a storage format. DMN has no lifecycle, version, or provenance fields, so the canonical index would live almost entirely in extension elements.
- A claim of DMN conformance or compatibility. Conformance is defined against clauses 6 to 8 at minimum (2.1); an export that reuses element names is not conformance.
- A mapping of Mneme decisions to DMN Decisions. The correct mapping is to Knowledge Sources.
- Exceptions modelled as overriding rules with a First or Priority policy. It would create ungoverned deviations with no authority record.
- Relationship kinds borrowed from DMN requirements (`information`, `knowledge`). They describe evaluation data flow that Mneme does not have, and ADR-030 §11 bars new relationship kinds.
- Any of the above ahead of a demonstrated consumer. Opportunity 1 is the only candidate, and only if someone asks to view Mneme decisions in a DMN tool.

## 5. Findings that affect specific ADRs

None of these requires an amendment now. Each is a note for the next time the ADR is touched.

- **ADR-023.**
  - §7 `owner` and DMN `decisionOwner` are the same informational concept; the field is defined but never populated. Either populate it or record that it is reserved.
  - §8 source evidence is the one structure with a DMN counterpart (Knowledge Source plus Authority Requirement). The comparison supports §8's statement that provenance does not create authority: DMN, which has the richer source model, also gives it no operative force.
  - §9 lists `depends_on`, `refines`, `implements` as possible future relationships. DMN shows that dependency relationships earn their place when they carry evaluation semantics. Without that, they stay labels, which is what §9 already says.
  - §5 (scope is not applicability) has no DMN analogue and is confirmed as a deliberate Mneme distinction.
- **ADR-027.**
  - §6 `decision.applicable_to` would benefit from a declared input contract in the manner of a DMN decision service interface. This is the most concrete alignment available.
  - §3 and §7 are unaffected. DMN offers no authority mechanism that could substitute for or weaken the acceptance boundary.
- **ADR-028.** No effect. DMN has no concept of prescriptive versus advisory intent in prose. The spec does distinguish descriptive from prescriptive *use of a model* (5.2.1, 5.2.2), which is a different axis and should not be conflated with ADR-026 intent.
- **ADR-029.** No effect on the binding semantics, and no reusable primitive. DMN's rule annotations and optional service logs are unspecified in format and unbound to subject or configuration; they are an example of the "control ran" evidence ADR-029 refuses to accept.
- **ADR-030** (proposed).
  - Mutation, versioning, and lifecycle have no DMN counterpart, so nothing in §4 to §6 or §11 duplicates the standard.
  - §10 provenance: consider first-class shared source records before the snapshot format is frozen (see section 1).
  - §7 rule identity hashes `value` and `applicability`. If a second rule type or a combination policy is ever added, the policy belongs in what is hashed or in the rule type, and the DMN hit-policy terms are the vocabulary to use.
- **ADR-019 / ADR-020** (not in the requested list, but where the overlap actually is). The typed-rule contract is implicitly a Collect policy over a single-input table. Stating that explicitly would cost one sentence and would make the consequence of adding conflicting rule types visible in advance.

## Limits of this comparison

- Absence claims (no lifecycle, no supersession, no provenance, no enforcement, no exceptions) rest on the XSD plus keyword searches of the full extracted text for: `supersed`, `deprecat`, `life-cycle`, `provenance`, `audit`, `governance`, `exception`, `version`, `effective date`, `valid from`, `enforce`, `approval`, `trace`. A concept expressed in other words in an unread clause would be missed. The FEEL clauses (9 to 11) and worked examples (12) were not read in full.
- The decision-table evaluation semantics in 10.3.2.10 were not read; hit-policy statements rest on 8.2.11 and 8.3.1.
- DMN tool vendors add versioning, governance, and audit features outside the standard. This note compares the standard only. A comparison against a specific product would reach different conclusions on lifecycle and audit.
- ADR-030 is proposed. Target-state statements describe a design contract, not behaviour.

## Recommendation

No concrete reusable primitive and no interoperability path with a demonstrated consumer came out of this comparison. There is nothing to hand to implementation.

What is worth keeping:

1. the re-mapping (a Mneme decision corresponds to a DMN Knowledge Source, a Mneme check to a DMN Decision), to stop future comparisons starting from the wrong place;
2. the hit-policy vocabulary, to be used when and if rule combination semantics ever need naming;
3. the declared-input discipline for `decision.applicable_to`;
4. the shared-source question for ADR-030 §10.

Items 3 and 4 are inputs to existing or planned work (the Decision MCP contract, D1B/D1C). Neither justifies a new track.
