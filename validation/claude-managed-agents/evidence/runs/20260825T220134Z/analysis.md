# M0-B multi-agent propagation - analysis

Generated: 2026-08-25T22:02:18Z

| Check | Result |
| --- | --- |
| cross_posted_to_primary_stream | True |
| originating_session_thread_identified | True |
| central_handler_denied_subagent_mutation | True |
| denial_routed_back_and_session_resolved | True |
| forbidden_bytes_never_landed | True |
| thread_lifecycle_events_observed | 19 |
| deny_contexts | [{'agent_name': 'ma-m0-b-worker-220134', 'session_thread_id': 'sthr_015e..f75a79'}] |

Pause-context captures prove whether the cross-posted requires_action carried
the originating session_thread_id on the primary stream. Wire shapes:
raw-events.jsonl; full detail: results.json.
