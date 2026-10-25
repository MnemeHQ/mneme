# CM-01-B0-A D1-H - Restricted Code Mode Host Threat-Model Review

**Status:** PROPOSAL FOR REVIEW - **not built, not tested, not accepted, and not authorized for execution**.

**Date:** 2026-10-25  
**Issue:** #659; parent #640.  
**D0 design:** PR #654, squash-merged at `8060b9bc318e0a0cb206d0cc9d3e6833977e367c`.  
**D1 resolution:** PR #655, squash-merged at `4b8471149d49f6f4a2a4ddfd0d3601d59355c337`.  
**Governing architecture:** ADR-017, ADR-022, ADR-023 and ADR-027.

This document reviews the smallest enforceable, validation-only execution boundary for model-generated Code Mode programs. It does not build a host, run hostile code, make a model/API call, change production, alter the MCP inventory, authorize a pilot or take S1-A2 work.

F1's in-process QuickJS is **not** a hardened hostile-code sandbox. F1 proves client cancellation and promise settlement, not OS-level termination, network isolation, secret isolation or container security. No hardening claim is made until independent red-team evidence exists.

## 1. Assets and threat model

### 1.1 Assets

- model API credentials and billing authority;
- trusted orchestrator and model prompts;
- genuine Decision MCP server and read-only fixture;
- evidence logs, usage ledger and scenario/expected-answer manifests;
- host OS, container runtime and other workloads;
- benchmark integrity and reproducibility;
- provider account and data-retention boundary.

### 1.2 Threat sources

Untrusted inputs include:

- model-generated JavaScript/TypeScript source executed by Code Mode;
- tool results and corpus text that may contain prompt injection or hostile strings;
- model final output and generated code;
- malformed JSON, very large arguments or results;
- adversarial network/filesystem/process attempts;
- compromised or drifted container image/runtime.

### 1.3 Threats

- arbitrary host filesystem read/write or repository access;
- network egress, DNS access or data exfiltration;
- process creation, privilege escalation, namespace escape or container escape;
- secret/environment/credential access;
- CPU, memory, PID, disk or output exhaustion;
- infinite loops or non-terminating code;
- unauthorized `decision.propose`, `proposal_batch` or unknown MCP method;
- argument-schema bypass, oversized arguments or oversized results;
- prompt injection that tries to change the task, tools or authority;
- tampering with logs, usage records, cancellation state or evidence hashes;
- incomplete termination or surviving child processes;
- QuickJS/WASM/runtime vulnerability;
- image supply-chain compromise;
- host clock, locale or path drift.

## 2. Trust boundaries

| Boundary | Trust | Responsibility |
|---|---|---|
| Model provider | external, untrusted output | Returns model text/code and usage |
| Trusted orchestrator | trusted control plane | Model API, prompts, task state, evidence writer, authorization |
| Restricted guest | untrusted | Runs only the pinned F1 executor/adapter and model-generated code |
| MCP broker | trusted narrow bridge | Four read methods only; schema validation; quotas; no proposal methods |
| Decision MCP | trusted pinned server | Genuine six-tool upstream inventory; read-only fixture |
| Evidence store | trusted, outside guest | Immutable logs, manifests and usage ledger |
| Container runtime/OS | trusted if independently hardened | Namespaces, cgroups, seccomp, kill, mount isolation |

The model API client and credentials stay in the trusted orchestrator. The guest never receives provider API keys, host SSH/cloud tokens, repository checkouts or production environment variables.

## 3. Smallest concrete architecture

### 3.1 One disposable guest per Code Mode execution

- Linux OCI container, or microVM if the reviewed container boundary is insufficient. The final runtime choice is **TBD** and must be security-reviewed.
- Rootless runtime where supported; otherwise a dedicated non-root UID/GID with all Linux capabilities dropped.
- Read-only root filesystem; no general host mounts; only a dedicated broker socket or VM channel and a small no-exec/no-suid tmpfs.
- A **private isolated network namespace** with no host-network mode, no external interface or route, and no DNS or network egress. Loopback is disabled or tightly controlled. The guest must not reach the model provider or any external endpoint; its single explicitly mounted Unix-domain broker socket (or separately approved VM channel) is the only IPC exception. Confirm network isolation from outside the guest.
- PID, mount and user namespaces; cgroup v2 CPU, memory, PID, IO and wall-clock limits.
- `no_new_privs`, deny-by-default seccomp and AppArmor/SELinux confinement.
- One execution per guest; never reuse a guest across arms, scenarios, repetitions or users.
- Guest files contain only the pinned F1 executor/adapter, their runtime dependencies, and the model-generated program.

### 3.2 Trusted orchestrator

The trusted orchestrator:

- owns the model API client, credentials and budget;
- constructs prompts/tool schemas and records their hashes;
- launches the guest and passes only the generated code;
- receives only the final structured result through the broker/guest channel;
- writes evidence outside the guest;
- decides incident stop and termination;
- never executes model-generated code in its own process.

### 3.3 Narrow MCP broker

The broker runs outside the guest and inside the trusted boundary.

- Exposes exactly `decision.get`, `decision.search`, `decision.applicable_to` and `decision.trace`.
- Rejects `decision.propose`, `decision.propose_batch`, unknown methods, extra authority fields and malformed arguments.
- Validates arguments against the real ADR-027 schemas.
- Forwards to the genuine Decision MCP with a read-only fixture and no proposal store.
- Enforces per-execution call quotas, argument-size limits, result-size limits and timeouts.
- Records request ID, method, argument hash, result identity/size, outcome and execution ID.
- Returns no rules or enforcement data beyond the genuine read result.
- Never gives the guest a generic MCP client, token or socket to the upstream server.

The upstream MCP inventory remains exactly six tools. The guest sees only four.

### 3.4 F1 executor/adapter reuse

- The merged F1 `quickjs-executor.mjs` and `adapter.mjs` are loaded read-only and hash-pinned.
- No F1 source is edited.
- The adapter receives a broker-backed `client` shim implemented outside F1; the shim exposes only `callTool` for the four allowed methods.
- The F1 executor runs inside the guest with its existing memory/stack/time limits, plus the host's stronger limits.
- Model-generated code is passed to the adapter only inside the guest.
- The in-process QuickJS executor is not relied on for filesystem/network/process isolation; the guest boundary provides it.
- F1 client cancellation is not accepted as proof of server-thread or child-process termination. The host must kill the guest cgroup/process tree and verify no survivors.

### 3.5 Broker-backed F1 cancellation contract — proposed test requirements

The broker-backed `client` shim must preserve the F1 client-call lifecycle without changing the F1 executor/adapter source. The review must specify and later test how the original `callTool` request and its per-call cancellation signal reach the bridge, how request IDs correlate across shim, broker and genuine MCP, and how an abort/timeout produces exactly one settled rejection and the required matching cancellation notification if the upstream request is still pending. If a request already completed, no cancellation is sent. Late results must never revive a settled call; disposal must reject all pending calls and prohibit post-disposal callbacks.

Tests must exercise abort during an in-flight read, abort after completion, broker transport close, guest timeout, and a racing late upstream response. They must verify explicit **OS-level termination/no survivor** independently from F1 client-side promise settlement and must not infer server-side cancellation from the notification alone. Capture separate host and broker evidence plus pinned F1 hashes. These tests are **requirements only**; no restricted host or shim has been implemented or validated.

## 4. Isolation controls

### 4.1 Filesystem

- Read-only root; no sensitive host paths; no repository checkout.
- Tmpfs is small, `noexec`, `nosuid`, `nodev`.
- No writable persistent volume.
- Evidence is written outside the guest; the guest cannot edit it.

### 4.2 Network

- Private isolated network namespace; **never** inherit host networking. No external interfaces, routes, DNS or egress; only approved Unix-domain broker IPC.
- No DNS.
- Broker only over a dedicated Unix socket or VM channel, not a network listener.
- Host verifies egress denial with an independent test.

### 4.3 Process and privilege

- Non-root user; all capabilities dropped.
- `no_new_privs`; seccomp default deny.
- No `fork`/`exec` where the runtime permits; PID limit 1 where feasible.
- Host kills the cgroup/container, not just the Node process.

### 4.4 Resource limits

- CPU quota and wall-clock timeout.
- Memory limit with OOM kill.
- PID limit.
- Output/stderr/log byte limit.
- Broker per-execution call quota and result-size limit.
- Disk/tmpfs size limit.

### 4.5 Credentials

- Provider API key only in the trusted orchestrator.
- Broker credential, if used, is ephemeral, per-execution, scoped to four methods and not exposed to model code.
- No host environment, cloud metadata, SSH agent, repository token or production secret in the guest.
- Evidence redacts secrets.

## 5. Red-team test matrix

The host is **not demonstrated** by this design. Before any pilot, an independent security reviewer must witness the following tests and retain evidence.

| Test | Attempt | Required result | Evidence |
|---|---|---|---|
| Egress | `fetch`, raw socket, DNS, provider endpoint | Denied; no packet/DNS | Network namespace/egress log |
| Host filesystem | Read `/etc/passwd`, repository path, host home | Denied/not mounted | Mount table, syscall log |
| Guest write | Write outside tmpfs | Read-only failure | Filesystem log |
| Exec | `child_process`, `execve`, shell | Denied | Seccomp/PID evidence |
| Credentials | Enumerate env, metadata, provider key | No secret present | Environment scan |
| Fork bomb | Rapid process creation | PID limit kills; no survivors | Cgroup/process tree |
| Memory bomb | Large allocation | OOM kill; host survives | cgroup memory event |
| Infinite loop | Non-terminating code | Wall-clock kill; no survivors | Timeout/exit evidence |
| Output flood | Large stdout/stderr/result | Truncated/killed; broker size limit | Output ledger |
| Unauthorized MCP | `decision.propose`, batch, unknown method | Rejected by broker; FAIL | Broker audit log |
| Argument bypass | Extra authority/invalid schema/oversized args | Rejected | Broker audit log |
| Prompt injection | Tool/corpus text attempts to change tools/task | No capability change; task result scored as produced | Evidence and evaluator |
| Log tampering | Guest writes evidence path | Denied; host log intact | Hash/immutability evidence |
| Cancellation | Client cancel/timeout | F1 rejects; host kills guest; no survivors | F1 + host termination logs |
| Incomplete exit | Kill during execution | Cgroup/container cleanup; no mount/process | Process/mount audit |
| Image drift | Changed image digest/config | Start blocked; no run | Image digest allowlist |
| Runtime drift | Missing seccomp/AppArmor/cgroup | Start blocked | Host preflight |

A test passes only when the attempt is denied or terminated **and** the evidence is complete. A benign error without containment evidence is not a pass.

### 5.1 Red-team negative probes versus production security incidents

The deliberate prohibited actions in Section 5 are **authorized negative test inputs**, not automatically benchmark incidents. A negative test **PASSES containment** only if the action is denied/terminated **and** the external observer records complete evidence with no access, leaked process or surviving resource. A missing audit record is not a containment pass. An actual successful prohibited access, escaped resource limit, missing termination evidence or unexpected host exposure during a red-team run is a **security-test FAIL** and stops that suite. The red-team ledger is separate from the future B0-A trial/outcome ledger.

During any subsequently authorized model-mediated benchmark, **unplanned attempts** to invoke a forbidden method, reach external network/host files, access a secret or bypass an isolation rule follow the preapproved incident-stop and study-FAIL policy, even if individual attempts were blocked. Do not convert deliberate red-team denial events into a falsely failed benchmark or convert actual benchmark incidents into benign test passes.

## 6. Cleanup and termination

On completion, cancellation, timeout or incident:

1. Stop accepting broker calls.
2. Send OS-level termination to the guest cgroup/container.
3. Wait for exit with a bounded timeout.
4. Kill remaining processes if any.
5. Unmount/remove guest filesystem and tmpfs.
6. Verify no process, mount, socket or container remains.
7. Write exit code/signal, resource peaks, seccomp/AppArmor events, broker audit and cleanup evidence outside the guest.
8. Mark the execution `FAIL` if termination or cleanup is incomplete.

Client-side cancellation alone is insufficient. A leaked child, relay, server, mount or container is a `FAIL`.

## 7. Incident stop conditions

Stop the trial and preserve evidence on:

- any unauthorized method or schema bypass;
- any network/DNS attempt or unexpected socket;
- any host filesystem/secret/process access;
- any seccomp/AppArmor/cgroup violation;
- container/runtime escape signal;
- OOM/PID/time/output limit breach;
- missing or corrupted evidence;
- credential exposure;
- image, runtime or host drift;
- broker audit gap;
- cleanup failure.

A security incident is `FAIL`, not `INCONCLUSIVE`, unless the stop is an external provider/infrastructure event unrelated to containment. In that case affected pairs are incomplete and the outcome is `INCONCLUSIVE`.

## 8. Evidence required

- container/VM image digest and runtime version;
- seccomp/AppArmor/cgroup configuration hashes;
- guest launch command and mount/network namespace state;
- F1 executor/adapter hashes;
- broker method allowlist and argument/result limits;
- per-execution broker audit log;
- red-team test source hashes and results;
- process tree, cgroup events and exit status;
- cleanup proof and no-survivor check;
- incident/stop records;
- independent reviewer sign-off.

Evidence is written outside the guest and protected from guest modification. The guest gets no evidence-write mount.

## 9. Non-demonstrated claims

This review does **not** demonstrate:

- a built or hardened host;
- container escape resistance in practice;
- rootless runtime availability;
- correct seccomp/AppArmor/cgroup behavior;
- OS-level termination at all kernel/runtime versions;
- provider credential isolation in a live run;
- F1 adapter behavior with a broker shim;
- production, Workers, cross-platform, server-thread termination or S1-A2 properties.

No model-generated code has been executed under this design.

## 10. Unresolved parameter register

| Parameter | Proposed state | Required evidence/approval |
|---|---|---|
| Container vs microVM | TBD | Security review |
| Runtime/image | TBD | Image digest, supply-chain review |
| Rootless vs dedicated UID | TBD | Host capability test |
| Seccomp/AppArmor profile | TBD | Independent review and red-team |
| Cgroup limits | TBD | Resource test evidence |
| Broker transport | Unix socket or VM channel (TBD) | Isolation review |
| Broker quota/timeouts | TBD | Abuse-test evidence |
| Argument/result size limits | TBD | Broker tests |
| Guest filesystem contents | TBD | Image review |
| Credential custody | Proposed orchestrator-only | Security review |
| Incident stop procedure | Proposed Section 7 | Human/security approval |
| Red-team corpus | TBD | Security review |
| Independent security reviewer | TBD | Human assignment |
| Host build authorization | NOT AUTHORIZED | Human approval |
| Pilot execution | NOT AUTHORIZED | Separate model/API and safety approval |

## 11. Design-review verdict, checklist and prerequisites

### 11.1 Verdict

**Design review: ACCEPT AS A PROPOSAL FOR SECURITY REVIEW ONLY.** This is not a security approval, a build authorization, a penetration-test result or a production claim. The host remains undemonstrated.

### 11.2 Independent security-reviewer checklist

The reviewer must confirm:

1. the threat model covers arbitrary code, exfiltration, resource abuse, unauthorized MCP methods, prompt injection, logging tampering and incomplete termination;
2. the trusted orchestrator, guest, broker, MCP and evidence boundaries match Section 2;
3. the guest has no provider credentials, network/DNS, host filesystem, repository checkout or general host mounts;
4. rootless/non-root, read-only root, no-exec tmpfs, dropped capabilities, `no_new_privs`, seccomp/AppArmor and cgroup limits are concrete and testable;
5. the broker exposes only four read methods, validates real ADR-027 schemas, retains six upstream tools and rejects proposal/mutation methods;
6. the F1 executor/adapter hashes are verified and unmodified, and the broker shim is outside F1;
7. OS-level cgroup/container kill and no-survivor verification are demonstrated, not inferred from client cancellation;
8. every red-team row in Section 5 has pass/fail evidence and an incident-stop path;
9. evidence is written outside the guest, integrity-protected and secret-redacted;
10. no production, Workers, server-side termination, cross-platform or S1-A2 claim is made.

### 11.3 Build prerequisites

Before any host build or hostile-code execution:

- written human authorization for the validation-only build;
- approved Linux host and container/VM runtime, with image digest and supply-chain review;
- cgroup v2, seccomp and AppArmor/SELinux availability verified;
- rootless/non-root runtime decision and non-root UID/GID;
- approved broker implementation and four-method schema tests;
- pinned F1 executor/adapter hashes and a broker shim review;
- independent red-team suite and evidence-store design;
- incident-stop and cleanup runbooks;
- named independent security reviewer;
- separate model/API authorization and budget before any pilot.

## 12. Readiness

- **Threat-model/host design review:** READY for review as a proposal.
- **Host build and hostile-code execution:** NOT AUTHORIZED.
- **Red-team execution:** NOT AUTHORIZED.
- **B0-A pilot/confirmatory execution:** NOT AUTHORIZED.
- **D1-C preregistration:** BLOCKED.
- **S1-A2:** undefined and blocked.

The host remains unbuilt and undemonstrated. No network, filesystem, process, credential, termination or isolation guarantee is claimed.
