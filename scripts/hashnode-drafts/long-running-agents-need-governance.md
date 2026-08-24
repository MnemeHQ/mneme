TITLE: Long-running agents need more than memory
CANONICAL: https://mnemehq.com/insights/long-running-agents-need-governance/
SUBTITLE: Anthropic's managed-agent harness solves continuity: progress logs, feature lists, git checkpoints. But continuity is not governance. As age

---

In this article

  1. Agents as shift workers
  2. What Anthropic's harness gets right
  3. The remaining gap: continuity is not governance
  4. Why this gets harder as agents run longer
  5. The role of governance
  6. ADRs as durable intent, not documentation
  7. Where governance checkpoints belong
  8. Conclusion
  9. FAQ

In May 2026, Anthropic published a detailed look at how their internal engineering teams use [Claude Code as a long-running managed agent](https://www.anthropic.com/engineering/managed-agents). The infrastructure pattern they describe is worth reading carefully: initializer agents that prepare the workspace, feature lists that define remaining work, progress files that record what happened, git commits that preserve recoverable state, startup checks that orient each new session, and end-to-end tests that stop agents from declaring victory prematurely.

This is not prompt engineering. It is operational infrastructure for agents working across many sessions on the same codebase. The problems it solves are real, and the solutions are well-reasoned.

But the pattern solves continuity. It does not solve governance. Those are two different problems, and conflating them is the most expensive mistake a team can make when designing long-running agent workflows.

## Agents as shift workers

The framing that makes the managed-agent pattern click is the relay team metaphor. A long-running agent workflow looks less like one developer with a prompt and more like a team of engineers handing work across shifts.

Each shift worker arrives, reads the handoff notes, picks up where the last person stopped, makes progress, and leaves a record for the next person. The work continues across interruptions. The codebase evolves across sessions. No single session owns the full context.

That framing makes the continuity infrastructure obvious. You need:

  * **Handoff notes** that are authoritative, not just descriptive (progress files)
  * **A work queue** that persists across shifts (feature lists)
  * **Recoverable state** at every checkpoint (git commits)
  * **Orientation scripts** so each shift starts correctly (startup checks)
  * **Pass/fail criteria** that the work must satisfy (E2E tests)

Anthropic's harness provides all five. What it does not provide is the architectural contract that defines what kind of work each shift is allowed to do.

In a real engineering team, that contract exists in ADRs, architecture review boards, code review standards, and the accumulated institutional knowledge of senior engineers. In a long-running agent loop, none of that is automatically present. The harness tells the agent what happened. It does not tell the agent what must remain true.

## What Anthropic's managed-agent harness gets right

Before addressing the gap, it is worth being precise about what the harness actually solves, because it solves real problems well.

Continuity infrastructure from Anthropic's harness

01

Initializer agent

Prepares the workspace before the main agent session begins. Ensures the environment is in a known state, dependencies are resolved, and relevant context is loaded. Removes a class of session-start failures that otherwise compound across a long loop.

02

Feature list

A durable queue of remaining work, written as discrete, completable items. Prevents sessions from re-litigating scope, duplicating work, or missing items that were already planned. The feature list is authoritative about what remains; the progress file is authoritative about what happened.

03

Progress file

A running record of what each session changed, decided, and left incomplete. The next session reads the progress file before touching code. This is the handoff note that makes the relay team metaphor operational.

04

Git commits as checkpoints

Every meaningful unit of work lands as a recoverable commit. If a session goes sideways, the codebase can be restored to the last known-good state without losing all prior progress. Git history becomes the audit trail for what the agent loop actually did.

05

E2E tests as the victory condition

Agents cannot declare a feature complete until the tests pass. This prevents the most common long-running-agent failure mode: partial implementations marked done because no local signal caught the gap. Tests enforce a floor on output quality that subjective progress notes cannot.

The pattern is good engineering. Each piece of infrastructure corresponds to a real failure mode that long-running agents encounter in practice. Anthropic's teams built this because they hit these failures, and the solutions are worth adopting.

## The remaining gap: continuity is not governance

A progress file can tell the next agent: _"Here is what I changed."_

It cannot reliably tell the agent: _"This architecture boundary must not be crossed. This dependency is forbidden. This ADR supersedes that older decision. This pattern is allowed only in this scope. This change conflicts with the repository's architectural intent."_

That distinction matters in practice because the questions a progress file answers and the questions a governance layer answers are different in kind, not just degree.

Continuity vs governance · what each layer answers

Layer| Question it answers  
---|---  
Progress log| What happened?  
Feature list| What remains?  
Git history| What changed?  
Test harness| Does it work?  
Governance layer| Is this allowed?  
  
The first four layers are all answered by the managed-agent harness. The fifth is not. A test suite can verify that the output is functionally correct. It cannot verify that the output is architecturally compliant. Those are different properties, and a codebase can be full of passing tests while being full of architectural violations.

_Agent harnesses preserve continuity._ Governance preserves intent.

## Why this gets harder as agents run longer

The governance gap is not specific to long-running agents. Any AI coding workflow can produce architecturally non-compliant output. But long-running agents increase the surface area for drift in ways that matter.

Over many sessions, a long-running agent loop may:

  * **Infer outdated patterns from old code.** A session reads existing files as examples of how things are done. If earlier sessions used a deprecated pattern, the new session infers that pattern is correct and continues it.
  * **Reintroduce forbidden dependencies.** A dependency was removed for a documented architectural reason. A later session adds it back because it solves the immediate problem and the prohibition is not in any artifact the agent reads.
  * **Bypass undocumented conventions.** Architecture that exists in institutional memory but not in enforceable documents is invisible to the agent. The agent makes the locally sensible decision that violates the convention.
  * **Mark incomplete work as complete.** A session finishes the functional layer of a feature and marks it done in the feature list. The non-functional architectural constraints—error handling conventions, logging standards, security requirements—are not captured in any test and are not enforced.
  * **Optimize locally while violating system-level constraints.** Each session makes a locally reasonable change. The cumulative effect crosses an architectural boundary that no single session was responsible for maintaining.

None of these failures show up in a progress file. None of them cause a test suite to fail. They accumulate silently across sessions and become visible only when the codebase is far enough from its architectural intent that the cost of correction is high.

The longer the loop, the more important invariant preservation becomes. The problem is not that agents forget. The problem is that they improvise when authority is unclear.

## The role of governance

Governance sits beside the harness. It does not replace progress logs, tests, or git. It gives the agent a deterministic way to check architectural compatibility at each session boundary and at each commit boundary.

The managed-agent startup sequence, extended with governance, looks like this:
[code] 
    pwd
    git log --oneline -20
    cat claude-progress.txt
    cat feature_list.json
    mneme check --mode warn
[/code]

Before commit or PR:
[code] 
    mneme check --mode strict
[/code]

In CI, on every push:
[code] 
    mneme check --mode strict --ci
[/code]

The framing is important: the harness tells the agent where it is. Governance tells it what boundaries it must respect. Both are necessary. Neither substitutes for the other.

SESSION FLOW \+ GOVERNANCE Agent session starts git log · progress.txt · feature_list.json Agent reads continuity artifacts understands what happened · what remains Agent performs work code changes · commits · progress updates Tests pass functional quality enforced · victory condition Session ends · handoff written next session inherits progress · loop continues GOVERNANCE CHECKPOINTS Session-start check mneme check --mode warn load constraints before any code is written Pre-commit check mneme check --mode strict catch local drift before branch history Governance state preserved next session inherits constraints, not just progress harness (left) gives the agent its map · governance (right) gives it its boundaries Fig 1 · Long-running agent session flow extended with governance checkpoints. The harness ensures the agent knows what happened. Governance ensures it knows what is allowed.

## ADRs as durable intent, not documentation

The governance layer requires a source of architectural authority. In well-run engineering teams, that source is the ADR corpus: Architecture Decision Records that capture not just what was decided, but why, what alternatives were rejected, and what constraints the decision implies.

ADRs are the canonical form of architectural intent. But for most teams, they sit in `/docs/adr` and are read only when someone thinks to look. They are documentation, not enforcement. A long-running agent will not read them at session start. A commit hook will not check against them. They accumulate as an increasingly stale record of decisions that no longer govern anything.

The Mneme approach makes ADRs into enforceable inputs. Rather than reading the ADR folder as a documentation corpus, a governance layer compiles the ADR corpus into a decision graph with declared properties:

  * Which decisions are active, superseded, or deprecated?
  * Which decision applies to which file, service, or scope?
  * Which decision is newer and overrides an older one?
  * Which dependencies or patterns does each decision forbid or require?
  * When two decisions conflict on the same scope, which one wins?

A long-running agent operating under that system can answer: _which decision applies to this change, and am I compliant with it?_ That is a different question from _what did the progress file say?_ and it requires a different infrastructure to answer.

The underlying work is the [precedence semantics problem](/insights/why-architectural-governance-needs-precedence-semantics/): given a set of architectural decisions with declared supersedes relationships, scope constraints, and status fields, compute the single decision that governs any given code location. That is the deterministic resolver that governance requires. Without it, ADRs are documents. With it, they are enforceable contracts.

## Where governance checkpoints belong

Governance is not a single check at a single moment. It is a layer with enforcement points distributed across the agent's workflow. The right enforcement points correspond to the moments of highest leverage:

01 Session start warn mode 02 Pre-tool execution block early 03 Pre-commit strict mode 04 Pre-PR explainable 05 CI gate team-level Load constraints before work starts Block obviously forbidden actions Catch drift before branch history Explainable warnings/failures Enforce team-level architectural contracts five enforcement points · each catches a different class of drift Fig 2 · Governance enforcement points in a long-running agent workflow. Each checkpoint catches drift at a different cost. Earlier checkpoints are cheaper to enforce; later checkpoints catch what slipped through.

**Session start** is the cheapest checkpoint. Before any code is written, the incoming agent loads the current architectural constraints, learns which decisions are active, and understands which scopes they cover. A warn-mode check at session start surfaces existing violations without blocking work, and primes the agent to avoid introducing new ones.

**Pre-tool execution** blocks actions that are obviously forbidden before they happen. If the agent is about to add a dependency that a governance rule prohibits, stopping it before the write is cheaper than detecting and reverting after.

**Pre-commit** is the primary enforcement gate in the agent's own workflow. A strict-mode check before commit catches architectural drift in the agent's output before it becomes branch history. This is the equivalent of a developer running linters locally before pushing.

**Pre-PR** produces an explainable report: which rules applied, which passed, which failed, and why. This is the output that a human reviewer can read to understand what architectural decisions the agent was operating under, and where it deviated.

**CI** enforces team-level architectural contracts on every push, regardless of whether the agent ran its local governance checks. This is the backstop that catches violations that the agent introduced without triggering its own enforcement points, and the gate that catches changes made by humans after an agent session.

**The harness ensures the agent knows where it is.** Governance ensures the agent knows where it must not go. Both are infrastructure. Neither is a nice-to-have for long-running loops.

## Conclusion: memory is not enough

Anthropic's managed-agent harness is well-designed infrastructure for a real problem. Progress logs, feature lists, git checkpoints, and E2E tests are the right primitives for keeping a long-running agent loop coherent across sessions. Teams building on Claude Code or similar agent systems should study and adopt this pattern.

But a progress file is descriptive, not prescriptive. It records what happened. It does not enforce what must remain true. And as agent loops grow longer, the gap between those two things grows wider.

The next phase of agent infrastructure needs a governance layer. Not a memory layer with architectural content indexed into it—that is still a recall system, still probabilistic, still without an enforcement hook. A governance layer: one that resolves competing ADRs deterministically, produces explainable audit traces, and enforces architectural contracts at the boundaries where agents make consequential changes.

Long-running agents need memory to continue work.  
They need governance to continue work safely.

The next generation of agent infrastructure will not just preserve context. It will preserve intent.

## FAQ

Is this a criticism of Anthropic's harness?

No. Anthropic's [managed-agent harness](https://www.anthropic.com/engineering/managed-agents) solves the continuity problem well. Progress logs, feature lists, git checkpoints, and E2E tests are the right operational primitives for long-running work. The article's point is that continuity and governance are two different problems, and solving the first does not automatically solve the second.

Can't a progress file just describe architectural rules?

It can record them as text. But text in a progress file has no enforcement authority. The next agent session can read that text and then do something else. Governance requires a deterministic resolver and an enforcement point that output must pass through. A progress note is advisory; a governance check is blocking.

What happens without governance in a long-running agent loop?

The loop drifts. Each session adds sensible local changes. Over dozens of sessions, the codebase drifts from its architectural intent without any single session making an obviously wrong decision. The problem is cumulative, and no individual progress log captures it. The symptom is a codebase that passes its tests but violates its architecture.

Where exactly does Mneme fit in this workflow?

Mneme is the governance layer that runs alongside the harness. At session start, `mneme check --mode warn` tells the incoming agent which architectural constraints apply and whether any are already violated. Before commit or PR, `mneme check --mode strict` enforces them. Mneme does not replace the progress log, git, or tests. It enforces the constraints those artifacts cannot enforce. See the [open-source repository](https://github.com/TheoV823/mneme) for setup details.

Why is governance harder when agents run longer?

Because the surface area for drift grows with each session. A single prompt session makes a bounded set of changes. A long-running loop makes changes across many files, services, and sessions. Each change is locally plausible but collectively drifts from architectural intent. The harness ensures the agent knows what happened. Governance ensures it knows what must remain true.