# Corrected Human-Ground-Truth Adjudication: O1A B-T1C Arm B

**Artifact Authority:** `benchmarks/open_architecture/batch_01/treatments/b_t1c/arm_b/ground_truth_adjudication.json`
**Execution HEAD:** `346825435b4c0fde96de66d15c3f964b5f6af423`
**Arm B Profile Hash:** `e4b6bad47ebcc290924782172fb96d8d`
**Base Reference Corpus Hash:** `0455bd66aae52551c35b37a63c2d185f`
**Status:** Corrected documentation-only adjudication artifact; zero model calls made, zero corpus files modified.

---

## 1. Architecture Constraints from ADR-023 and O1A Methodology

1. **ADR-023 Relationship Semantics:**
   - ADR-023 (§9) defines relationships as explicit records within a logical decision graph, independent of underlying storage technology.
   - Its current and validated canonical production semantics are deliberately narrower: D0 requires compatibility strictly with `supersedes` and `derived_from`.
   - ADR-023 explicitly anticipates future relationship types, noting: *"Future relationships may include `depends_on`, `conflicts_with`, `refines`, or `implements`, but they gain no operational semantics merely by being representable."*
   - O1A Taxonomy 0.1 independently investigates seven research relationship types: `requires`, `prohibits`, `depends_on`, `refines`, `conflicts_with`, `supersedes`, and `exception_to`.
   - Inclusion in the O1A research taxonomy does **not** grant any type production canonical operational semantics.

2. **ADR-030 §11 Attribution & Non-Normative Metadata:**
   - ADR-030 (§11) establishes the exact architectural boundary: *"D1 must not invent `related_to` or promote producer `related_decision_ids` into authoritative relationships; they remain proposal history. Only already-sanctioned relationship semantics are included."*
   - ADR-030 does not explicitly mention Markdown `**Related:**` headers or repository `relatesTo` metadata.
   - Treating generic `**Related:**` header blocks and repository `relatesTo` YAML metadata as contextual/retrieval pointers rather than normative relationships is an **O1A annotation policy**, strictly consistent with ADR-030's authority boundary and the existing human-reviewed Batch 01 annotations.

3. **Ground-Truth Epistemology:**
   - Batch 01 reference labels represent **versioned human reference ground truth, frozen within an experiment**.
   - Corrections require explicit evidence, human adjudication, and a new corpus version/hash, and must not be motivated by improving model scores.

---

## 2. Verdict for Each of the Four Proposed Label Changes

### 1. `ref-gsa-agentic-coding-quickstart-005` (ADR-0028)
* **Current Label:** `[('refines', '0026')]`
* **Human Note in Corpus:** *"Human-approved. Added refines -> 0026 relationship (ADR-0028 resolves ADR-0026 Windows secret-storage caveat)..."*
* **Source Evidence Analysis:** The target identifier `"0026"` (or `"ADR-0026"`) occurs **zero times** in the classifier-visible `raw_evidence`. The human reviewer added this relationship by importing external repository history not contained in the candidate evidence text.
* **Verdict:** **ACCEPT AS OBJECTIVE CORRECTION.**
  *Rationale:* Grounding defect. Because the target entity is physically absent from the candidate input text, no compliant classifier evaluated on visible evidence can predict it. Ground truth must be corrected to `[]`.

### 2. `ref-helix-013` (ADR-0031)
* **Current Label:** `[]`
* **Human Note in Corpus:** *"Human-approved... Kept authority_status: candidate, effective_date: null, relationships: [], enforcement_potential: deterministic_rule."*
* **Source Evidence Analysis:** The phrase *"the attested instruction this extends"* occurs inside the document metadata header: `**Related:** ADR [0006](...), [0005](...), [0013](0013-egress-trust-model.md) (egress trust model — the attested instruction this extends)...`
* **Verdict:** **REJECT.**
  *Rationale:* The existing human review explicitly inspected this record and retained `relationships: []`. Promoting a parenthetical clause inside a generic `**Related:**` metadata header into an authoritative relationship directly contradicts the O1A non-normative metadata policy. Relationships must not be inferred ad-hoc merely to improve benchmark accuracy. Ground truth remains `[]`.

### 3. `ref-helix-020` (ADR-0028)
* **Current Label:** `[]`
* **Human Note in Corpus:** *"Human-approved... Kept ONTOLOGY_GAP for no parameterizes relationship type. No supersession relationships invented. Preserved ONTOLOGY_GAP for no parameterizes relationship type. relationships: ()"*
* **Source Evidence Analysis:** Document declares parentage (*"ADR-0022... this ADR's parent"*) and parameterization (*"parameterizes architecture decision 11 and reframes ADR-0019"*).
* **Verdict:** **ONTOLOGY GAP.**
  *Rationale:* The human reviewer explicitly evaluated this evidence, identified that Taxonomy 0.1 lacks `parameterizes` and `derived_from` (parentage), recorded an `ONTOLOGY_GAP`, and deliberately retained `relationships: ()`. `parameterizes`, `reframes`, and `parent` (`derived_from`) are distinct architectural concepts that must not be forced into `refines` unless Taxonomy 0.1 explicitly equates them. Ground truth remains `[]`.

### 4. `ref-adrkit-015` (ADR-0015)
* **Current Label:** `[('refines', '0012')]`
* **Human Note in Corpus:** *"Approved after correction... removed generic relatesTo relationships (not in O1A vocabulary); kept refines -> 0012 directly supported by pinned ADR-0015 evidence..."*
* **Source Evidence Analysis:** Evidence states descriptor admissibility is evaluated against Backstage validators at the commit ADR-0012 pins.
* **Verdict:** **RETAIN PENDING SEMANTIC ADJUDICATION (REJECT AS CORRECTION).**
  *Rationale:* The human reviewer deliberately retained `refines -> 0012`. Re-labeling from `refines` to `requires` represents a subjective semantic re-interpretation of whether relying on an upstream commit pin is an architectural "prerequisite" or an adapter "refinement", not an objective factual defect. O1A methodology forbids reference label churn across subjective semantic borders. The current label `[('refines', '0012')]` is retained.

---

## 3. Contradictions Between Previous Normative Rules and Case Decisions

1. **Metadata Header Contradiction (`ref-helix-013`):**
   The previous adjudication formulated a normative rule stating that generic cross-reference lists (`**Related:**`) are non-normative context metadata and must not be extracted as relationships, but simultaneously proposed adding `refines -> 0013` based entirely on a clause inside a `**Related:**` header.
   *Correction:* The rule is upheld. `ref-helix-013` remains `[]`.

2. **Ontology Dilution Contradiction (`ref-helix-020`):**
   The previous adjudication warned against distorting existing taxonomy semantics, but proposed forcing `parameterizes` and `parent` (`derived_from`) into `refines`.
   *Correction:* The human reviewer's explicit `ONTOLOGY_GAP` determination is preserved. Unrepresented semantics remain an ontology gap, not a reason to alter ground truth. `ref-helix-020` remains `[]`.

---

## 4. Corrected Position on `depends_on`

* **Ontological Validity:** ADR-023 (§9) explicitly anticipates `depends_on` as a canonical decision relationship representing functional or operational dependency distinct from prerequisite constraints (`requires`) or rule specializations (`refines`).
* **Batch 01 Empirical Status:** `depends_on` is **unobserved / unvalidated** in the Batch 01 human-reviewed reference labels (0 instances).
* **Classifier Overuse vs. Ontology Definition:**
  The classifier's overuse of `depends_on` (72 instances in Arm B) reflects probabilistic model calibration and prompt defaulting, not an invalid ontology concept.
* **Policy:** `depends_on` **remains an active, valid type in Taxonomy 0.1**. It must not be deprecated or removed from the schema without independent architectural justification.

---

## 5. Minimal Proposed Corpus Revision (Objective Corrections Only)

The **only** modification clearing the objective-correction bar is eliminating the ungrounded target from `ref-gsa-agentic-coding-quickstart-005`:

```yaml
corpus_revision: "batch_01_v0.2-grounding"
base_reference_corpus_hash: "0455bd66aae52551c35b37a63c2d185f"
modifications:
  - reference_id: "ref-gsa-agentic-coding-quickstart-005"
    file: "benchmarks/open_architecture/batch_01/reference_decisions/gsa_agentic_coding_quickstart/ref-gsa-agentic-coding-quickstart-005.jsonl"
    field: "relationships"
    old_value:
      - relationship_type: "refines"
        target_reference: "0026"
        evidence_reference: "ADR-0026 states supported Windows path needs Windows-native secret backend; ADR-0028 explicitly unblocks that secret-storage caveat"
    new_value: []
    defect_type: "GROUNDING_DEFECT"
    rationale: "Target ADR 0026 occurs 0 times in candidate raw_evidence. External knowledge imported into human reference label."
```

*(No corpus files are modified in this step).*

---

## 6. Counterfactual Arm B Strict Accuracy Under Accepted Corrections

Using persisted Arm B outcomes without model calls:

* **Current Arm B Exact Matches:** 58 / 100 (`0.5800`)
* **`ref-gsa-agentic-coding-quickstart-005` Predicted Output:** `[]`
* **New Exact Match on `ref-gsa-005`:** Predicted `[]` matches Corrected Expected `[]` (+1 exact match).
* **Counterfactual Arm B Strict Accuracy:** **59 / 100 (`0.5900`)**
* **Per-Repository Strict Accuracy:**
  - `adrkit`: `0.3500` (7 / 20)
  - `archlint`: `1.0000` (20 / 20)
  - `gsa_agentic_coding_quickstart`: **`0.6500` (13 / 20)** (up from `0.6000`)
  - `helix`: `0.0500` (1 / 20)
  - `modonome`: `0.9000` (18 / 20)
* **Target Entity Recovery:** **18 / 18 (100.0%)** of all classifier-visible expected targets recovered.

---

## 7. Corrected Expected-Empty, Non-Empty, and Tuple Counts

| Metric | Current Batch 01 (v0.1) | Corrected Batch 01 (v0.2) | Change |
| :--- | :---: | :---: | :---: |
| **Total Reference Decisions** | 100 | 100 | 0 |
| **Expected-Empty References** | 87 | **88** | +1 |
| **Expected-Empty Exact Matches (Arm B)** | 55 | **56** | +1 |
| **Expected-Empty False Positives (Arm B)** | 32 | **32** | 0 |
| **Expected Non-Empty References** | 13 | **12** | -1 |
| **Expected Non-Empty Exact Matches (Arm B)** | 3 | **3** | 0 |
| **Total Expected Relationship Tuples** | 19 | **18** | -1 |
| **Visible Target Entities in Evidence** | 18 | **18** | 0 |
| **Target Entity Recovery Rate (Arm B)** | 18 / 19 (94.74%) | **18 / 18 (100.00%)** | +5.26% |
| **Strict Accuracy (Arm B)** | 58 / 100 (58.0%) | **59 / 100 (59.0%)** | +1.0% |

---

## 8. Artifact Corrections Required

1. **Residual Error Decomposition (`residual_error_decomposition.json`):**
   - Records `ref-gsa-agentic-coding-quickstart-005` as an objective `GROUNDING_DEFECT`.
   - Records `ref-helix-020` as an `ONTOLOGY_GAP`, retaining ground truth `[]`.
   - Records `ref-helix-013` as a `contextual/cross-reference mention`, retaining ground truth `[]`.
   - Preserves `ref-adrkit-015` as `[('refines', '0012')]`.
2. **Corpus File (`ref-gsa-agentic-coding-quickstart-005.jsonl`):**
   - Awaits explicit human authorization before updating `relationships` to `[]`.
