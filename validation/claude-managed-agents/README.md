# Claude Managed Agents × Mneme — M0 Capability Gate

Validation-only milestone. It determines whether Claude Managed Agents
(`agent_toolset_20260401`, `managed-agents-2026-04-01` beta) provides a
trustworthy integration boundary for Mneme's existing deterministic
retrieval and enforcement architecture.

**This is not a production adapter and must not become one.** The only code
here is a probe harness that (a) drives live Managed Agents sessions and
(b) translates captured `agent.tool_use` events onto Mneme's *existing*
evaluation surfaces, unchanged:

```text
Managed Agents event
    → existing Mneme ToolEvent / evaluator        (mneme.integrations.agent_sdk.adapter)
    → existing mneme check contract               (subprocess, mneme.check/v1 verdict)
    → user.tool_confirmation allow/deny
```

No retrieval, applicability, conflict-resolution, enforcement,
introduced-delta, or benchmark semantics are introduced or modified.

## Layout

```text
validation/claude-managed-agents/
├── README.md                  this file
├── capability-matrix.md       documented capability vs. proven result
├── probe.py                   validation-only probe harness
├── fixture/
│   └── .mneme/
│       └── project_memory.json  isolated policy: FORBID_LITERAL sentinel
└── evidence/
    └── runs/<UTC-run-id>/     environment.json, raw-events.jsonl,
                               results.json, filesystem-hashes.json, analysis.md
```

The fixture is deliberately isolated from the repository's own
`.mneme/project_memory.json`: it contains exactly one mechanically
enforceable typed rule (`FORBID_LITERAL` on the distinctive literal
`MANAGED_AGENTS_FORBIDDEN_XYZ`) so every observed enforcement outcome is
attributable to this validation alone.

## Running

Requires an existing `ANTHROPIC_API_KEY` (process env or a `.env` discovered
above the worktree). The key is never printed, copied, or committed. The
harness runs under an isolated Python environment with the Managed
Agents-capable SDK; it is not added to Mneme's runtime dependencies.

```bash
<venv-python> probe.py identity          # record environment identity
<venv-python> probe.py a                 # A1 pre-execution write, A2 denied write, A3 edit materialization
<venv-python> probe.py a4                # A4 bash coverage (heredoc + in-context opaque attempt)
<venv-python> probe.py a4b               # A4b isolated opaque-write bypass (no prior denial context)
<venv-python> probe.py b                 # M0-B multi-agent propagation
```

Each invocation creates `evidence/runs/<UTC-run-id>/` and appends its
resource identity to that run's `environment.json`.

## Scrubbing

All persisted evidence passes a scrubber: API keys and bearer material are
redacted; session, agent, environment, thread, file, and event IDs are
shortened consistently within a run (prefix + 6 chars + short hash). Full IDs
are never written to disk.

## Hard boundaries honored by this directory

* Validation code and evidence only; no production adapter.
* No changes to `DecisionRetriever`, `ConflictDetector`, `mneme check`,
  typed-rule evaluation, ADR semantics, benchmarks, or existing integrations.
* No runtime dependency changes in `pyproject.toml`.
* The integration support matrix is not updated here.
* Only `validation/claude-managed-agents/**` may be committed from this work.
