# M0-A/A2b existing-file overwrite - analysis

Generated: 2026-08-26T00:59:23Z

| Check | Result |
| --- | --- |
| preexisting_sentinel_established | True |
| measured_write_submitted | True |
| cloud_evaluator_denies_whole_rewrite | True |
| denial_reason_targets_preexisting_line | True |
| ground_truth_introduced_lines | SAFE_APPENDED_NOTES_LINE |
| ground_truth_verdict_with_real_bytes | PASS |
| ground_truth_matches_adr018_no_blame_for_preexisting | True |
| recovery_write_observed | True |
| final_state_sentinel_removed_by_recovery | True |
| existing_file_lines_cannot_be_preserved_via_cloud_write | True |

Interpretation: with real current bytes, only SAFE_APPENDED_NOTES_LINE is
introduced and the fixture rule does not fire (ADR-018 attribution). The
unchanged cloud evaluator cannot read the current file, treats it as new,
and therefore blames the preserved pre-existing sentinel line by denying
the whole proposal. The observed recovery path removes the pre-existing
content entirely: under cloud conditions an existing governed line cannot
be carried through any full-file write. This refines 'write' governance
to new-file writes.

Wire shapes: raw-events.jsonl; full detail: results.json.
