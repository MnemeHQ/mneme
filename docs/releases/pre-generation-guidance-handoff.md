# Pre-generation Guidance Release Handoff

**Status:** local candidate ready; outcome gate pending  
**Default:** off

## Completed locally

- [x] Charter amendment records guidance/enforcement separation.
- [x] Task-to-decision corpus and input hashes are locked.
- [x] Unchanged-retriever baseline was recorded before scorer work.
- [x] The only scorer change is typed-rule value weight `1.5`; selectors remain
  outside relevance scoring.
- [x] Guidance selection is deterministic, confidence-gated, K <= 3, and
  bounded to 8,000 characters.
- [x] ADR-020 selectors are described conditionally at prompt time.
- [x] `UserPromptSubmit` adapter is current-prompt-only, opt-in, and fail-open.
- [x] Existing `PreToolUse` behavior and tests remain intact.
- [x] Plugin schema, installer idempotency, locked retrieval gates, full test
  suite, compilation, and local latency gates pass.
- [x] Protocol-discovery runs are preserved and explicitly excluded from
  confirmatory scoring.
- [x] Checkpoint 6 is re-locked as separate mechanism-isolation and
  production-effectiveness evaluations.

## Required before publishing the runtime/plugin pair

- [ ] Build and mechanically validate the revised two-mode confirmatory harness,
  first-attempt capture, silent offline enforcement observation, and blinded
  artifact exporter.
- [ ] Execute 42 new mechanism-isolation runs and attach raw artifacts plus
  blinded scoring.
- [ ] Execute 42 new production-effectiveness runs and report compliance,
  policy discovery, work-to-first-compliant-attempt, completion, and scope
  expansion separately.
- [ ] Apply only the outcome-specific claims allowed by the two locked gates.
- [ ] Run the manual smoke matrix on Windows, macOS, and Linux.
- [ ] Choose the release version, update `pyproject.toml`, move `Unreleased`
  changelog entries into that release, and add a release note.
- [ ] Update both integration READMEs from the current source-install wording to
  the exact published `mneme-hq` version floor.
- [ ] Bump the Claude Code plugin manifest version as part of its release.
- [ ] Build wheel and sdist; inspect both for `mneme/guidance.py`,
  `mneme/guidance_eval.py`, and
  `mneme/integrations/claude_code/guidance_hook.py`.
- [ ] Install the candidate wheel in a clean environment and confirm all three
  console scripts resolve: `mneme`, `mneme-hook`, and
  `mneme-guidance-hook`.
- [ ] Re-run the full suite, frozen benchmark, locked guidance evaluation,
  plugin strict validation, and both Claude Code smoke flows from the clean
  install.

## Claim gate

Allowed before the live outcome gate passes:

> Mneme provides opt-in, deterministic pre-generation architectural guidance
> for Claude Code and retains independent pre-write enforcement.

Not allowed before the gate passes:

- guidance improves first-proposal compliance;
- pre-generation enforcement in Claude Code; or
- guidance is safe to enable by default.

After the outcome and cross-platform gates pass, the default-on choice remains a
separate product decision; passing the experiment does not silently change the
configuration default.
