# ADR-034 G2-1 R3 scoring harness (independent scorer B)

Scores R3 cases (`mneme-r3-case/v1`) against the frozen R3 contract:

- [R3 pre-registration](../../docs/validation/adr-034-g2-1-r3-preregistration-draft-2026-10-28.md) (#699);
- [AT-SI amendment](../../docs/validation/adr-034-g2-1-r3-pre-unblind-amendment-1-proposal-2026-10-28.md) (#701);
- the inherited [R1](../../docs/validation/adr-034-g2-1-validation-preregistration-2026-10-25.md) and
  [R2](../../docs/validation/adr-034-g2-1-revalidation-preregistration-2026-10-26.md)
  contracts, with their accepted amendments;
- ADR-017, -018, -019, -020, -029, -033 and -034 (§3a, §4, §5, §6a, §7a-§7c), and the G2-1 charter.

It was written from those documents and the 14 released public smoke cases
only. It copies, imports and reads no earlier scoring harness, and uses no
R1/R2/M4 corpus, no D3 regression fixture and no implementation output as a
source of expectations.

**Status:** harness for review. Running it on public or synthetic cases
yields `NO_VERDICT_PUBLIC_SMOKE` by construction. Nothing here authorizes
unblinding, concealed scoring or any PASS claim. G2-1 remains **FAIL**.

## Usage

```text
python -m benchmarks.adr034_g2_1_r3 score \
  --corpus <dir with <case>/case.json> --work <empty resolved dir> \
  --impl-python <pinned D3 build python> --base-python <pinned pre-G2 baseline python> \
  --host-version <pinned Claude Code version> --host-sha256 <pinned executable sha256> \
  --scoring public|concealed --report report.json [--observations obs.json] \
  [--public-smoke-tar <separate #703 public tar, for concealed scoring>]
```

The command makes two equivalent full passes over the corpus. Its report is
metadata only: case ids, classes, gate results and failure codes. Raw
observations are written only on request and stay with the corpus custodian.

Scorer-authored synthetic cases: `python -m benchmarks.adr034_g2_1_r3.synthetic OUT_DIR`.

## Modules

| Module | Role |
|---|---|
| `oracle.py` | Independent expectation: ADR parsing, `rule_id`, ADR-020 applicability, literal matching, routing, checker preconditions, expected G2 record. No Mneme import |
| `attribution.py` | Exact `(rule_id, rule_type)` comparison (ADR-034 §7c; R3 §3 G6) |
| `gates.py` | G1-G8 per case; floors; corpus decision |
| `coverage.py` | Independently checks frozen within-class and subtype distribution; no observed hook output used to award coverage |
| `public_smoke.py` | Verifies separately frozen public archive SHA-256, complete manifest and 14-class inventory; no concealed contents read |
| `runner.py` | Materializes fixtures and runs the pinned builds. Observation only |
| `pinned_child.py` | Runs inside the pinned build. Calls its `relevant_enforcement_per_rule()`, `relevant_enforcement_observed()` and `recorded_evaluation_complete()` (R2 §5 G6 steps 2-4) |
| `contract.py` | Frozen constants: floors, cause mapping, schemas |
| `synthetic.py` | Scorer-authored synthetic cases (never corpus cases) |

## Where each expected value comes from

| Expected value | Source |
|---|---|
| `rule_id` of every rule | ADR-030 §7 formula. Pinned by the four ADR-034 §5 golden vectors |
| Canonical numeric value, `max` normalization | ADR-034 §2, §5 |
| Applicability and exclusion mechanism (include miss or exclude match) | ADR-020 §3-§6; AT-SI amendment §2 |
| Literal violations | ADR-019 §2-§3, §6, on the text the checker evaluates (charter §3.5) |
| Routed / not checked | R1 A1.1, A1.2; charter §4.1; AMB-R2-03 |
| Trusted proposed source / routed fallback | ADR-034 §6a preconditions 1-5, plus at least one `APPLIED` numeric rule |
| Checker subject kind; record subject; record `rules` | R3 §3 table; AT-SI amendment; charter §3.5 |
| Applied rule-ID set | R2V-F3; R2A1.6 |
| Violation identities in the record | ADR-034 §7c.1 |
| Disposition, exit, cause | ADR-034 §7a verdict table; §8 M-a; ADR-033 §3 (`open`) |
| Per-rule and event relevance | ADR-034 §7b; R1 A1.3 |
| `evaluation_complete` | ADR-034 §4; R2 A2R2.2 |
| Numeric matcher status, outcome, primary reason, unknown reasons | **Frozen author labels.** The matcher is not re-implemented |
| Unrouted legacy exit and disposition | Frozen labels and G5 baseline parity |

Every derived value is cross-checked against the frozen labels (README I2).

## Gates

| Gate | Implemented check |
|---|---|
| G1 | An expected refusal observed without exit 2 **or with a non-refusing recorded disposition**. A gated non-clean numeric rule observed `NO_VIOLATION` (checker payload or record). Any pinned per-rule or event relevance `true` that the oracle does not expect |
| G2 | A case expected to proceed (contract exit 0) observed with exit 2. Baseline-observed cases are exempt (R1 A1.4) |
| G3 | The target is unchanged by the checker calls and by the hook, and an absent target stays absent |
| G4 | The primary reason of every gated unevaluated rule, in the checker payload and in the record. Well-formed unknown-reason **sets** are compared and reported as notes; only the primary reason is gated (AMB-R2-05). Malformed reason types are scoring-integrity failures under G8, not an exception that aborts the run |
| G5 | Hook level: stdout, stderr and exit byte-identical to the baseline hook, with R1 Amendment 2 traceback handling decided by the baseline's run. Checker level: `--proposed-new-file` against `--input` on the same carrier. The routed-CR exception moves a case to checker level only |
| G6 | Exactly one complete record for a routed case and none otherwise. Independently pinned Mneme version and host identity, decision-version bindings from fixture-compiled memory, event fields, digest and path joins, expected record subject and checker subject kind, mode, cause, hook outcome, exact violation identities. Then, in order: (1) the rule-ID set (short-circuits), record rule bindings and matcher fields; (2) per-rule relevance keys and values; (3) event relevance; (4) `evaluation_complete`, all from the pinned functions |
| G7 | The two full passes give identical observation bundles and identical expectations |
| G8 | Any harness, compile, oracle or per-case scoring failure, including malformed checker reason data, or any oracle/label conflict, fails that case and every other gate for it. Unexpected exception messages are redacted from metadata reports; subsequent cases remain scoreable |

The corpus decision requires every scored case to pass:
- the R3 floors (128 concealed cases over 14 classes, AT at least 2 per subclass), plus independently checked frozen within-class L/LIT/SC/MR/AT distributions, byte variety and AT smoke presence;
- the public-smoke rules, validated using the **separately archived** frozen
  public tar. Concealed scoring uses `--public-smoke-tar`: the harness
  verifies #703's exact tar SHA-256, the public archive's own
  `MANIFEST.sha256`, 14 public case files and one case per class, including
  AT. The public and concealed manifests are never combined. If the tar
  is absent or verification fails, the concealed verdict cannot PASS;
- manifest integrity;
- symlink capability. Without it the result is `INCOMPLETE`.

Public cases count toward no denominator.

## Interpretations fixed before decryption (for review)

- **I1** Gate participation is the **union** of the protocol-derived set and the
  label's `gates` / `g5` flags. Exemptions (the routed-CR exception) are never
  widened by a label.
- **I2** A disagreement between a derived value and a frozen label is an
  **oracle conflict**. It fails the case under G8 and is reported. It is never
  resolved after unblinding.
- **I3** A record's violation entry with a missing, empty or non-string
  `rule_id` (or `rule_type`) attributes nothing **and** fails G6 as a malformed
  entry. Untrusted checker data, a carrier or subject digest mismatch, or a
  malformed `violations` list earns no attribution.
- **I4** For ADR-019 §3, "identifier-like" edge characters and blocking
  neighbours are the same set: ASCII letters, digits, `_` and `-`.
- **I5** Memory is compiled once per case per scoring session with the pinned
  build (`mneme init`, then `mneme adr import docs/adr --apply`). The same bytes
  are used for both passes and for the baseline (AMB-R2-06). `mneme init`
  stamps a creation time, so recompiling per pass would make G7 measure the
  compiler rather than the hook.
- **I6** Cause mapping (AMB-R2-08): `numeric_violation`→`numeric_violation`,
  `other_rule`→`other_rule`, `none`→`no_violation`,
  `numeric_unevaluated`→`fail_open`. `legacy_unrouted` and `not_checked` have no
  record.
- **I7** Numeric matcher outcomes come from the frozen labels. Everything in
  the table above marked as a contract source is derived.
- **I8** Envelope: the case's `envelope_extras`, with `{{SESSION_ID}}` set to the
  constant `r3-scorer-session` and `{{ROOT}}` to the fixture root. No other host
  identifier is added. Hook mode is set via `MNEME_HOOK_MODE`. `MNEME_*`,
  `CLAUDE_*` and `PYTHON*` variables are stripped from child environments.
- **I9** The checker call a routed hook makes is replicated directly: same
  memory, carrier bytes, query, mode and `--target-path`. This observes the
  checker payload (G1(b), G4, G6 subject kind). The hook itself never exposes
  that payload.
- **I10** Fixture features the oracle cannot label from the contract alone
  make the case undetermined, a G8 failure. These are:
  - legacy constraint prose;
  - a non-`accepted` ADR status;
  - duplicate scopes or ids;
  - ADRs outside `docs/adr/*.md`;
  - availability other than `open`.
- **I11** G1 participates wherever any of its three conditions can arise.
- **I12** Fixtures are materialized at a fixed, resolved path per case
  (`<work>/cases/<case_id>/{root,outside}`). No ancestor of the work directory
  may contain `.mneme`.
- **I13** Checker-level parity compares stdout and exit (R1 G5).
- **I14** The compiled memory must carry exactly the derived typed-rule ids
  and no legacy constraints or anti-patterns. Otherwise the case fails G8.

## Known limitations

- The harness has been exercised only on the 14 public smoke cases and 10
  scorer-authored synthetic cases. Concealed cases may contain fixture
  features outside I10's supported set. Those fail G8 rather than being
  guessed.
- Host identity on public runs is the observed local Claude Code 2.1.312
  executable. The scoring pin belongs to the pre-scoring completion record,
  together with the R3 §6.1 live-host characterization.
- The harness does not re-implement the M4 numeric matcher. Matcher
  correctness is judged against the author's labels through G1, G4 and G6.
- Within-class coverage uses fixture-derived applicability and the frozen
  numeric labels, not checker observations. A missing or ambiguous eligibility
  proof fails corpus admission instead of relaxing the preregistered floor.
- G5 Amendment 2 ignores only traceback frame bytes. Summary lines, chain
  separators and all stderr outside frames retain their exact newline bytes.
- The F1-F4 corrections were made before unblind and must be independently
  reviewed by scorer B. Green CI alone is not review approval.
