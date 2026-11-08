"""Synthetic regression tests for reclassify_h1.completeness() (review of #553).

The completeness check must detect a nonce in ANY material the #549 collector
omits: a field stripped from a user/assistant entry, a whole stream event of an
unselected type, a dropped transcript entry, thinking content, and omitted
init/result fields. Nonce occurrences that are published must not count.
Synthetic data only; no real evidence is read.
"""
import importlib.util
import json
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("reclassify_h1", HARNESS / "reclassify_h1.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

NONCE = "MNEME-PROBE-0123456789abcdef"


def _arm(tmp_path, events, transcript):
    out = tmp_path / "arch" / "H1a-edit" / "out"
    out.mkdir(parents=True)
    (out / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    (out / "transcript.jsonl").write_text("".join(json.dumps(e) + "\n" for e in transcript), encoding="utf-8")
    red = R.COL.Redactor(Path(r"C:\dev\d5p2-h1-live"), HARNESS, "py", "claude")
    return R.completeness(tmp_path / "arch", "H1a-edit", NONCE, red)


def test_published_occurrences_do_not_count(tmp_path):
    c = _arm(tmp_path,
             [{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": NONCE}]}}],
             [{"type": "attachment", "attachment": {"type": "hook_additional_context", "content": [NONCE]}}])
    assert c["hits_total"] == 0


def test_stripped_field_of_assistant_entry_is_detected(tmp_path):
    c = _arm(tmp_path,
             [{"type": "assistant", "extra_field": NONCE,
               "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}}], [])
    assert c["hits_total"] == 1
    assert c["omitted_hits"][0]["kind"] == "trimmed" and c["omitted_hits"][0]["source"] == "events"


def test_stripped_message_field_of_user_entry_is_detected(tmp_path):
    c = _arm(tmp_path, [], [{"type": "user", "message": {"role": "user", "content": "hi", "model_note": NONCE}}])
    assert c["hits_total"] == 1 and c["omitted_hits"][0]["kind"] == "trimmed"


def test_dropped_stream_event_type_is_detected(tmp_path):
    c = _arm(tmp_path, [{"type": "stream_event", "payload": NONCE}], [])
    assert c["hits_total"] == 1 and c["omitted_hits"][0]["kind"] == "dropped"
    assert c["entries"]["events"]["dropped"] == 1


def test_dropped_transcript_entry_is_detected(tmp_path):
    c = _arm(tmp_path, [], [{"type": "summary", "text": NONCE},
                            {"type": "attachment", "attachment": {"type": "skill_listing", "content": NONCE}}])
    assert c["hits_total"] == 2 and {h["kind"] for h in c["omitted_hits"]} == {"dropped"}


def test_thinking_init_and_result_omissions_are_detected(tmp_path):
    c = _arm(tmp_path,
             [{"type": "system", "subtype": "init", "model": "m", "plugins": [NONCE]},
              {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": NONCE}]}},
              {"type": "result", "subtype": "success", "is_error": False, "usage": {"note": NONCE}}],
             [])
    assert c["hits_total"] == 3 and {h["kind"] for h in c["omitted_hits"]} == {"trimmed"}
