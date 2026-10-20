# Orchestrator decision sandbox

A synthetic, offline experiment that measures which parts of one architectural
decision Mneme enforces today before an agent mutates a file, which parts it
does not, and what a custom orchestrator would need to expose for pre-write
enforcement.

The goal is a precise measurement, not a demonstration of perfect enforcement.
All names, code and documents here are fictional.

Results: [RESULTS.md](RESULTS.md). Plan:
[docs/plans/2026-10-20-orchestrator-decision-sandbox-plan.md](../../docs/plans/2026-10-20-orchestrator-decision-sandbox-plan.md).

## What is under test

- One accepted decision, [`adr/ADR-001.md`](adr/ADR-001.md), with three
  sub-constraints (C1 no disabled deadline, C2 deadline at most 5 s, C3 safe
  fallback) and one typed rule: `FORBID_LITERAL DISABLE_ROUTER_TIMEOUT`
  scoped to `src/**`. Only the literal aspect of C1 is enforced.
- Six candidate changes A to F ([`fixtures/cases.json`](fixtures/cases.json)),
  judged twice: by a functional oracle ([`scripts/oracle.py`](scripts/oracle.py))
  that never reads Mneme output, and by Mneme.
- The shipped `mneme check` / `mneme audit` CLI, and the shipped
  `MnemeLangChain` middleware through `langchain.agents.create_agent` with a
  scripted offline model, including a governed agent embedded in a
  `StateGraph` and two raw graph paths that bypass the middleware.

Nothing in `mneme/`, `docs/adr/`, the repository's `.mneme/` memory, or CI is
modified. Each case runs in a fresh temp fixture whose memory is created with
`mneme init` and `mneme adr import --dry-run` then `--apply`.

## Out of scope

Live models, shell or `execute` tools, remote or virtual file backends, custom
orchestrators, and any interception adapter beyond the shipped middleware.

## Reproduce from a clean checkout

Requires Python 3.12.10 and no network access beyond package installation.

```bash
python -m venv <venv>
<venv>/Scripts/python -m pip install -e ".[dev,langchain]" langchain==1.3.17 langchain-core==1.6.0 langchain-protocol==0.0.18 langgraph==1.2.11 langgraph-checkpoint==4.2.0 langgraph-prebuilt==1.1.0 langgraph-sdk==0.4.3 langsmith==0.11.1
<venv>/Scripts/python validation/orchestrator-decision-sandbox/scripts/run_sandbox.py
<venv>/Scripts/python -m pytest validation/orchestrator-decision-sandbox/tests -v
```

Use `<venv>/bin/python` on Linux or macOS. The versions are the exact set in
[`validation/langgraph/pinned-build.json`](../langgraph/pinned-build.json);
the runner exits 3 (blocker) if any installed version differs.

`run_sandbox.py` prints a transcript, writes raw output to
`evidence/runs/<UTC stamp>/` (git-ignored) and reports whether the fresh
deterministic summary is byte-identical to the committed
[`evidence/summary.json`](evidence/summary.json). Pass `--write-summary` only
when intentionally refreshing the committed summary.

The tests live outside the default `testpaths` and are not part of CI.
