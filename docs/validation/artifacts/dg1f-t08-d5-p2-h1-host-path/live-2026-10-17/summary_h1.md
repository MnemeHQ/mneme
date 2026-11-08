# H1 Claude Code host-output-path probe summary

| Path | Path type | Label | Passes | Audience | Echoed | Reasons |
|---|---|---|---|---|---|---|
| H1a-edit | command_tool_event | INCONCLUSIVE | False | none recorded | True | unexplained host-event difference between arms (emitter ['thinking_tokens', 'thinking_tokens', 'thinking_tokens', 'thinking_tokens'], control ['thinking_tokens', 'thinking_tokens']); nonce found in locations the category table does not recognise; review needed |
| H1a-bash | command_tool_event | INCONCLUSIVE | False | none recorded | True | unexplained host-event difference between arms (emitter ['task_notification', 'task_started'], control ['task_notification', 'task_started', 'thinking_tokens', 'thinking_tokens']); nonce found in locations the category table does not recognise; review needed |
| H1b-start | command_lifecycle_event | INCONCLUSIVE | False | none recorded | True | nonce found in locations the category table does not recognise; review needed |
| H1c-stop | command_lifecycle_event | INCONCLUSIVE | False | none recorded | True | nonce found in locations the category table does not recognise; review needed |

H1 gate (every path passes): **NOT MET**

Only the gate line above decides H1. `H1_DONE` means only that the batch finished and every outcome was written; it never means H1 passed.
