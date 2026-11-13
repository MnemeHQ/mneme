"""Synthetic regression tests for reclassify_a2.completeness().

The A2 check must compare each raw entry with what collect_a2 publishes:
hook_* attachments with `rendered`, and api-request-blob entries as nonce-line
excerpts. A nonce in any material collect_a2 omits must be detected, including
a `rendered` field on a non-hook attachment, a blob field outside the excerpted
text lines, the paired emitter's nonce in a control arm, and stderr. Published
occurrences must not count, and an omitted hit records its location only.
Synthetic data only; no real evidence is read.
"""
import importlib.util
import json
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("reclassify_a2", HARNESS / "reclassify_a2.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

OWN = "MNEME-PROBE-0123456789abcdef"
EMIT = "MNEME-PROBE-fedcba9876543210"


def _arm(tmp_path, transcript, events=(), stderr="", nonces=(OWN,), sel=OWN):
    out = tmp_path / "arch" / "H1a-edit" / "out"
    out.mkdir(parents=True)
    (out / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    (out / "transcript.jsonl").write_text("".join(json.dumps(e) + "\n" for e in transcript), encoding="utf-8")
    (out / "claude.stderr.txt").write_text(stderr, encoding="utf-8")
    red = R.redactor(r"C:\dev\d5p2-h1-a2-live", "py", "claude")
    return R.completeness(tmp_path / "arch", "H1a-edit", list(nonces), sel, red)


def _hook(content, rendered=True):
    e = {"type": "attachment", "attachment": {"type": "hook_additional_context", "content": [content],
                                              "hookName": "PreToolUse:Edit", "hookEvent": "PreToolUse"}}
    if rendered:
        e["rendered"] = [{"content": f"<system-reminder>\nPreToolUse:Edit hook additional context: {content}\n</system-reminder>"}]
        e["renderedRole"] = "system"
    return e


def _blob(lines, **extra):
    e = {"type": "api-request-blob", "hash": "h1",
         "message": {"role": "system", "content": [{"type": "text", "text": "\n".join(lines)}]}}
    e.update(extra)
    return e


def test_published_hook_rendered_and_blob_line_do_not_count(tmp_path):
    c = _arm(tmp_path, [_hook(f"ctx {OWN}"),
                        _blob(["preamble", f"PreToolUse:Edit hook additional context: ctx {OWN}", "tail"])])
    assert c["hits_total"] == 0
    t = c["entries"]["transcript"]
    assert t["whole"] == 1 and t["trimmed"] == 1  # the hook entry has no other fields; the blob is excerpted


def test_rendered_on_non_hook_attachment_is_detected(tmp_path):
    env = {"type": "attachment", "attachment": {"type": "environment", "content": "x"},
           "rendered": [{"content": OWN}]}
    c = _arm(tmp_path, [env])
    assert c["hits_total"] == 1
    h = c["omitted_hits"][0]
    assert h["kind"] == "dropped" and h["raw_json_paths"] == ["rendered[0].content"]
    assert "entry" not in h  # location only, never the entry


def test_blob_field_outside_excerpted_text_is_detected(tmp_path):
    blob = _blob([f"line {OWN}"])
    blob["message"]["content"].append({"type": "tool_result", "content": OWN})
    blob["system"] = OWN
    c = _arm(tmp_path, [blob])
    assert c["hits_total"] == 1
    assert c["omitted_hits"][0]["raw_occurrences"] == 3 and c["omitted_hits"][0]["published_occurrences"] == 1


def test_paired_emitter_nonce_in_control_arm_is_detected(tmp_path):
    c = _arm(tmp_path, [_blob([f"PreToolUse:Edit hook additional context: {EMIT}"])],
             nonces=(OWN, EMIT), sel=OWN)
    assert c["hits_total"] == 1
    h = c["omitted_hits"][0]
    assert h["nonce_role"] == "paired emitter" and h["kind"] == "dropped"


def test_dropped_event_and_stderr_are_detected(tmp_path):
    c = _arm(tmp_path, [], events=[{"type": "stream_event", "payload": OWN}], stderr=f"warn {OWN}\n")
    assert c["entries"]["events"]["dropped"] == 1
    assert c["stderr"]["nonce_occurrences"] == 1 and c["stderr"]["lines"] == 1
    assert c["hits_total"] == 2


def test_hook_entry_without_rendered_is_whole_or_trimmed_not_hit(tmp_path):
    c = _arm(tmp_path, [_hook(f"ctx {OWN}", rendered=False)])
    assert c["hits_total"] == 0


def test_load_recorded_masks_the_live_workspace(tmp_path):
    out = tmp_path / "arch" / "H1a-edit" / "out"
    out.mkdir(parents=True)
    (out / "nonce.txt").write_text(OWN, encoding="utf-8")
    arm = R.load_recorded(tmp_path / "arch", "H1a-edit")
    assert arm["nonce"] == OWN
    req = {"file_path": r"C:\dev\d5p2-h1-a2-live\H1a-edit\ws\notes.txt"}
    m = R.C.masked(req, arm, OWN)
    assert "<WS>" in m and "d5p2-h1-a2-live" not in m
    # Keyed to the archive path instead, the recorded workspace would not mask.
    unkeyed = R.C.load_arm(out)
    assert "<WS>" not in R.C.masked(req, unkeyed, OWN)


def test_changes_reports_category_change_only(tmp_path):
    loc = {"source": "transcript", "line": 5, "json_path": "rendered[0].content"}
    old = {"label": "INCONCLUSIVE", "rules": "R1-R4", "nonce_locations": [dict(loc, category="unclassified")]}
    new = {"label": "DELIVERED_TO_AGENT", "rules": "R1-R5", "nonce_locations": [dict(loc, category="host_record")]}
    d = R.changes(old, new)
    assert d["top_level_keys"] == ["label", "rules"] and d["location_set_unchanged"]
    assert d["nonce_location_categories"][0]["as_run"] == "unclassified"
    assert d["nonce_location_categories"][0]["r1r5"] == "host_record"
