TITLE: Harness engineering still needs governance
CANONICAL: https://mnemehq.com/insights/harness-engineering-still-needs-governance/
SUBTITLE: Harness engineering solves execution, orchestration, retries, and tool use. It does not enforce architectural intent. Governance is the miss

---

In this article

  1. The shift: prompts, harnesses, execution systems
  2. What harness engineering solves
  3. The governance gap
  4. Why observability is insufficient
  5. Governance propagation across execution surfaces
  6. The next layer: governance infrastructure
  7. Where Mneme fits
  8. FAQ

## The shift: prompts, harnesses, execution systems

Three years ago, the prevailing question was how to phrase a prompt. The model was the product, and prompt engineering was the surface where teams competed.

That framing no longer matches what is being built. OpenAI's recent [harness work on Codex](https://openai.com/index/harness-engineering/), Anthropic's pattern for [long-running managed agents](https://www.anthropic.com/engineering/managed-agents), Cursor's background-agent runtime, Claude Code's session-aware workflow, and the open-source frameworks — LangGraph, CrewAI, AutoGen — all converge on the same architectural move: the model is wrapped inside an execution system that handles tools, memory, retries, planning, and continuity.

Single calls have given way to execution loops. Assistants have given way to autonomous workflows. The model is no longer the product boundary. The execution environment is.

That is the right move. Anyone building agentic systems in 2026 needs a harness. But it is also incomplete. As soon as agents are doing real work across many sessions, on real codebases, the harness reveals what it does not cover: _architectural intent_.

## What harness engineering solves

It is worth being precise about what the current generation of harnesses solves, because the answer is genuinely impressive. These are the problems prompt engineering could never address and that single-call APIs treated as out of scope.

Problems harness engineering handles well

01

Context lifecycle management

Loading the right context at session start, evicting stale context, summarizing history, and injecting the working set the agent needs for the next step. Without this, every long conversation degenerates into context pressure.

02

Tool orchestration

Tool selection, schema validation, parallel calls where safe, sequencing where required, and recovery when a tool fails or returns unexpected output. The harness is what makes tool use composable rather than fragile.

03

Retries and error recovery

Idempotent retries on transient failures, backoff on rate limits, recovery from partial tool failures, and the bookkeeping required to avoid double-applying side effects. Robust autonomous workflows are mostly retry logic in disguise.

04

Planning and execution loops

Decomposing a goal into steps, running steps, checking results, and replanning when the plan no longer fits reality. The harness encodes the agentic loop and gives it durable state across iterations.

05

Memory injection and continuity

Persistent notes, feature lists, progress logs, and session handoffs that let the next agent pick up where the last one stopped. This is the relay-team infrastructure that makes long-running work possible.

06

Observability and execution coordination

Tracing what the agent did, when, with which tools, on which inputs. This is what makes the workflow auditable after the fact and operable at scale.
[code] 
    Model
      ↓
    Harness
      ↓
    Tools / Memory / Execution / Retries
[/code]

This is a major architectural advancement over prompt engineering. Treating the execution environment as the product boundary lets autonomous workflows survive contact with real systems: rate limits, partial failures, long horizons, multi-tool coordination, and cross-session continuity.

None of what follows is an argument against any of that. The argument is that this layer alone is not enough.

## The governance gap

A harness can make an agent faster, more persistent, more autonomous, and more capable. It cannot, by construction, make the agent _architecturally aligned_. Continuity is not constraint. Orchestration is not enforcement. Memory of past decisions is not authority to refuse a future one.

The failures look like this:

  * **An ADR is bypassed.** The repo has a recorded decision — "do not introduce a runtime ORM" — that the agent does not read at session start, because the harness does not treat ADRs as first-class inputs. The agent introduces an ORM because it solves the immediate ticket.
  * **A forbidden dependency reappears.** A package was removed for a documented reason. A later session reintroduces it because the prohibition lives only in a stale doc, not in an enforcement hook.
  * **A governed system is rewritten.** The agent refactors a module that had a specific layering contract. The new version is functionally equivalent and passes tests, but violates the layering rule that was the entire point of the original design.
  * **Layering boundaries are crossed.** A controller starts calling into a data layer that the architecture forbids it from touching directly. The change is locally sensible, globally corrosive.
  * **Naming conventions drift.** Each session is internally consistent. Across sessions, the naming gradually changes, and the next agent infers the new pattern from recent files.
  * **Infrastructure patterns mutate.** A standard for how services are exposed, configured, or deployed is silently replaced by a sensible-looking alternative that the rest of the system does not expect.
  * **Automation artifacts become inconsistent.** Branch names, commit messages, PR titles, and CI configs all drift away from team conventions because no layer is enforcing them.

None of these failures are caused by the harness being bad. They are caused by the harness being the wrong place to enforce architectural decisions. The harness's job is to keep work moving. Its incentives are continuity and throughput, not refusal.

_Harnesses preserve execution continuity._ They do not preserve architectural intent.

That distinction matters because architectural intent is exactly what a long-running, autonomous workflow erodes by default. Each session makes locally plausible choices. The cumulative effect is drift — and no progress log, retry policy, or tool router catches drift, because none of them know what the architecture was supposed to be.

## Why observability is insufficient

The most common response to the governance gap is to lean harder on observability. Trace every tool call. Log every diff. Pipe agent activity into a dashboard. If we can see what the agent did, we can correct it.

That argument confuses two different questions.

Observability vs governance · what each layer answers

Layer| Question it answers  
---|---  
Traces| Which steps ran?  
Logs| What was emitted?  
Metrics| How often, how fast, how reliably?  
Dashboards| Is the system healthy?  
Governance| Was the action allowed?  
  
Observability answers _what happened_. Governance answers _what should have been allowed_. These are not the same problem, and tools built for the first are structurally unable to solve the second.

  * **Logs are not policy.** A log records that a forbidden dependency was added. It does not refuse the add.
  * **Traces are not invariants.** A trace shows the call graph. It does not declare which call graphs are valid.
  * **Visibility is not enforcement.** A dashboard surfaces drift after it occurs. It does not block the change that produced the drift.

Observability is necessary — you cannot govern what you cannot see — but it sits on the wrong side of the action. By the time the trace reaches the dashboard, the commit has already happened, the PR may already be merged, the artifact may already be deployed. Governance has to sit _in front of_ the action it constrains, with a deterministic rule about whether to allow it.

The next layer is not better dashboards. It is enforceable contracts.

## Governance propagation across execution surfaces

Here is where most discussions of agent governance fall short. They treat governance as a property of the source tree: the code the agent writes must satisfy certain architectural constraints, and that is the whole problem.

That is too narrow. Long-running, autonomous agents do not only write source code. They write everywhere the workflow touches:

Execution surfaces produced by autonomous workflows

01

Branch names and PR titles

Auto-generated by the harness, often outside the team's branch and title taxonomy. Conventions that exist for a reason — downstream tooling, release notes, audit traceability — quietly stop working.

02

Commit messages and tags

Workflow-generated commits accumulate in history. Tag policies built around durable milestones get diluted by operational commits and ephemeral checkpoints.

03

CI metadata and pipeline config

Workflow files, environment definitions, secret references, and runner configurations are written by agents the same way they write code — but their governance constraints (least privilege, approval gates, allowlists) are stricter and less visible.

04

Deployment artifacts and release notes

Manifests, container tags, generated changelogs, and release announcements all carry organizational intent that ungoverned automation can silently violate.

05

Generated configuration

Feature flags, routing rules, scaling policies, and integration configs are generated as code. They are rarely reviewed with the same rigor and almost never checked against architectural decisions.

06

Agent-produced documentation

READMEs, ADR drafts, runbooks, and inline comments authored by the agent become the next agent's training context. Drift in docs propagates faster than drift in code, because the next session reads docs as authoritative.

Governance must propagate across every surface touched by autonomous execution.

This is the part of the problem the industry is barely talking about. A governance layer that enforces ADR compliance in `src/` but ignores commit messages, PR titles, CI config, and generated docs is governing a fraction of the agent's output. The interesting, expensive failures live exactly at the boundaries the agent crosses on its way to "shipping a change": the branch, the title, the workflow file, the deployment manifest, the release note.

Repository policies like the one in this codebase — conventional branch prefixes, squash-merge with curated titles, durable-milestone-only tag policy — exist precisely because automation artifacts left ungoverned will rot the operational story of the repo. Encoding those policies as ADRs and propagating them into the agent's pre-commit, pre-PR, and CI checks is the only way they survive automation.

## The next layer: governance infrastructure

The clean way to think about the emerging stack is to stop treating it as a model-plus-tooling problem and start treating it as a layered system.
[code] 
    Models           — produce candidate output
      ↓
    Harnesses        — coordinate execution, retries, tools
      ↓
    Execution        — long-running loops, sessions, memory
      ↓
    Governance       — defines and enforces architectural constraints
      ↓
    Verification     — tests, builds, deploy-time checks
[/code]

Each layer answers a question the layer above it cannot:

  * **Harnesses** answer _how does the agent act?_
  * **Execution systems** answer _how does the agent keep working across time?_
  * **Governance** answers _which actions are allowed, and according to which decisions?_
  * **Verification** answers _did the resulting system still pass its objective checks?_

Governance is its own layer because the problem it solves is not solvable inside any of the others. Models produce text. Harnesses coordinate. Memory recalls. None of them can deterministically resolve which ADR governs a given change, or block output that violates the active decision graph. That requires a layer with its own data model (decisions, supersedes relationships, scopes), its own resolver (precedence semantics), and its own enforcement hooks (session start, pre-tool, pre-commit, pre-PR, CI).

This is what makes governance infrastructure a category, not a feature. It cannot be folded into the harness without giving the harness an enforcement responsibility that conflicts with its continuity responsibility. It cannot be folded into observability without losing its blocking authority. It cannot be folded into the model, because the model has no source of truth about the repository's decisions.

Harnesses coordinate execution. Governance defines constraints. Verification enforces invariants. Each layer has a job; none can do the others' jobs well.

## Where Mneme fits

Mneme is a deliberately narrow layer in this stack. It does not orchestrate tools. It does not retry calls. It does not manage memory or context. It does one thing: it compiles the repository's ADR corpus into a deterministic decision graph and enforces it at the boundaries where agents make consequential changes.

  * **Repo-native.** ADRs live in the repository. The decision graph is rebuilt from them on every check. There is no separate hosted policy store to drift out of sync.
  * **Deterministic enforcement.** Given the same decision graph and the same change, the result is the same every time. No probabilistic recall, no model in the loop at the enforcement boundary.
  * **Architectural decision verification.** Status, supersedes, and scope are first-class fields. Conflicts between active decisions are resolved by declared precedence, not by ordering accidents.
  * **Governance before generation.** `mneme check --mode warn` at session start tells the agent which decisions are active before it writes anything. `mneme check --mode strict` at pre-commit and CI is the enforcement gate.

The framing matters: Mneme is complementary to harness engineering, not competitive with it. A team running Codex, Claude Code, Cursor background agents, or any of the open-source agent frameworks should still run a harness. They should also run a governance layer beside it.

**Harnesses help agents act.** Governance ensures they act within architectural boundaries. Verification confirms the result. All three layers are infrastructure. None of them substitute for the others.

Long-running agents need more than memory and orchestration. They need enforceable architectural boundaries. The next phase of agent infrastructure is the layer that provides them.

## FAQ

Is harness engineering bad or unnecessary?

No. Harness engineering is a major architectural advancement over prompt engineering. Harnesses solve real, hard problems: context lifecycle management, retries, tool orchestration, planning and execution loops, memory injection, and observability. Long-running agent systems are not viable without them. The point of this article is that harnesses are necessary but not sufficient. They make agents act effectively; they do not make agents act within architectural boundaries.

Isn't observability enough? If you can see what the agent did, you can correct it.

Observability tells you what happened. Governance defines what should have been allowed. Logs are not policy. Traces are not invariants. Visibility is not enforcement. A trace can show that an agent introduced a forbidden dependency; only governance can stop the change from being proposed, written, committed, or merged in the first place. Observability is the audit log of a system. Governance is the constraint that the system must satisfy. See [Why Observability Is Not Governance](/insights/why-observability-is-not-governance/) for the long version.

What is "governance propagation across execution surfaces"?

Long-running agents do not just touch code. They touch PR titles, branch names, commit messages, CI metadata, deployment artifacts, generated config, release notes, and agent-produced documentation. Architectural intent must hold across all of those surfaces, not just the source tree. A governance layer that enforces invariants in code but ignores the surrounding automation artifacts leaves most of the agent's output ungoverned. Governance must propagate to every surface the agent writes to.

Where does Mneme fit relative to a harness?

Mneme runs beside the harness, not instead of it. The harness coordinates execution; Mneme enforces architectural decisions. At session start, `mneme check --mode warn` loads active ADRs and surfaces existing violations. Before commit or PR, `mneme check --mode strict` blocks output that violates the active decision graph. In CI, the same check is the team-level backstop. Mneme does not replace tool use, retries, or memory; it enforces the constraints those layers cannot enforce. See the [open-source repository](https://github.com/TheoV823/mneme) for setup details.

Why is this a "category" rather than a feature?

Because the problem governance infrastructure solves is not solvable inside a model, a harness, or a memory system. Models produce text. Harnesses coordinate execution. Memory recalls context. None of those layers can deterministically resolve which architectural decision applies to a given change, or block output that violates it. That requires a separate layer with its own data model, its own resolver, and its own enforcement hooks. When a layer cannot be folded into any adjacent layer, it is a category.