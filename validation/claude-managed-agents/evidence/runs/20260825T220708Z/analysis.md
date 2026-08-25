# M0-A cloud permission boundary - analysis

Generated: 2026-08-25T22:08:15Z

| Check | Result |
| --- | --- |
| A1_pre_execution_write_interception | True |
| A2_trusted_deny_byte_preserving_with_recovery | True |
| A3_cloud_edit_governable_by_unchanged_evaluator | False |
| A3_violation_landed_despite_gate | True |

## Central-gate note (A3)

- The unchanged evaluator materializes an edit by reading the complete current file.
- Cloud sandbox bytes are not reachable by the approval client through the local filesystem;
  see approval_client_access_to_current_bytes in results.json for the probed alternatives.
- Observed consequence of running evaluate_mutation unchanged against the remote path: violation landed=True.

Wire shapes: raw-events.jsonl. Full detail: results.json.
