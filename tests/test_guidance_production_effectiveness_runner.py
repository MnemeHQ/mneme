from __future__ import annotations

import json
import os
import sys

import pytest

from scripts import run_guidance_production_effectiveness_ab as production


def _hook_events(context: str, *, late: bool = False):
    start = {
        "type": "system",
        "subtype": "hook_started",
        "hook_id": "guidance-1",
        "hook_event": "UserPromptSubmit",
    }
    response = {
        "type": "system",
        "subtype": "hook_response",
        "hook_id": "guidance-1",
        "hook_event": "UserPromptSubmit",
        "outcome": "success",
        "exit_code": 0,
        "output": json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context,
                }
            }
        ),
    }
    assistant = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "working"}]},
    }
    return [start, assistant, response] if late else [start, response, assistant]


def _task(task_id: str):
    return next(task for task in production.shared.TASKS if task["id"] == task_id)


def _valid_init():
    return {
        "type": "system",
        "subtype": "init",
        "tools": ["Edit", "Glob", "Grep", "Read", "Write"],
        "permissionMode": "acceptEdits",
        "skills": [],
        "slash_commands": [],
        "mcp_servers": [],
        "plugins": [
            {
                "name": "mneme",
                "path": str(production.PRODUCTION_PLUGIN.resolve()),
                "source": "mneme@inline",
            }
        ],
        "model": production.shared.EXPECTED_MODEL,
        "claude_code_version": production.shared.CLAUDE_VERSION,
        "apiKeySource": production.shared.EXPECTED_API_KEY_SOURCE,
    }


def test_frozen_production_schedule_has_exact_paired_42_slots():
    schedule = production._schedule()

    assert len(schedule) == 42
    assert {item["evaluation"] for item in schedule} == {
        "production_effectiveness"
    }
    assert sum(item["arm"] == "baseline" for item in schedule) == 21
    assert sum(item["arm"] == "treatment" for item in schedule) == 21
    for task in production.shared.TASKS:
        slots = [item for item in schedule if item["task_id"] == task["id"]]
        assert len(slots) == 6
        assert {
            (item["arm"], item["repetition"]) for item in slots
        } == {
            (arm, repetition)
            for arm in production.shared.ARMS
            for repetition in (1, 2, 3)
        }


def test_production_permissions_do_not_hide_mneme_memory():
    rules = production._production_permission_rules()

    assert all(".mneme" not in rule for rule in rules)
    assert all("project_memory.json" not in rule for rule in rules)


def test_shared_runner_lock_adapter_exposes_frozen_claude_launcher():
    locked = {
        "runtime": {
            "claude": {
                "launch_chain": {
                    "launcher": {"path": "C:/locked/claude.cmd"},
                    "runtime_binary": {"path": "C:/locked/claude.exe"},
                }
            }
        }
    }

    adapted = production._adapt_lock_for_shared_runner(locked)

    assert adapted["claude"]["executable"] == "C:/locked/claude.exe"
    assert adapted["runtime"] == locked["runtime"]


def test_neutral_cwd_editable_loader_resolves_hooks_to_this_repository():
    manifest = production._editable_loader_manifest()
    expected = production.REPO_ROOT / "mneme"

    assert manifest["neutral_cwd_imports"]
    for value in manifest["neutral_cwd_imports"].values():
        assert production.Path(value).resolve().is_relative_to(expected.resolve())


def test_pyyaml_runtime_manifest_locks_python_and_native_imports():
    manifest = production._pyyaml_runtime_manifest()

    assert manifest["distribution"] == "PyYAML"
    assert manifest["version"]
    locked_files = {
        production.Path(value).resolve() for value in manifest["files"]
    }
    for value in manifest["neutral_cwd_imports"].values():
        assert production.Path(value).resolve() in locked_files
    assert any(path.suffix == ".py" for path in locked_files)
    assert any(path.suffix == ".pyd" for path in locked_files)
    assert any(".dist-info" in path.as_posix() for path in locked_files)


def test_actual_hook_import_environment_is_sanitized_and_restored(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "C:/unexpected")
    monkeypatch.setenv("PYTHONHOME", "C:/unexpected-home")

    with production._sanitized_python_environment():
        assert "PYTHONPATH" not in production.os.environ
        assert "PYTHONHOME" not in production.os.environ

    assert production.os.environ["PYTHONPATH"] == "C:/unexpected"
    assert production.os.environ["PYTHONHOME"] == "C:/unexpected-home"


def test_streaming_capture_records_monotonic_line_arrival():
    command = [
        sys.executable,
        "-u",
        "-c",
        (
            "import json, time; print(json.dumps({'one': 1}), flush=True); "
            "time.sleep(0.02); print(json.dumps({'two': 2}), flush=True)"
        ),
        "--output-format",
        "stream-json",
    ]

    completed = production._streaming_run(
        command,
        input="prompt",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
        check=False,
    )
    capture = production._LAST_STREAM_CAPTURE

    assert completed.returncode == 0
    assert capture is not None
    assert capture["event_count"] == 2
    assert capture["line_count"] == 2
    assert capture["lines"][0]["event_index"] == 0
    assert capture["lines"][1]["event_index"] == 1
    assert (
        capture["lines"][1]["elapsed_seconds_from_prompt_submission"]
        > capture["lines"][0]["elapsed_seconds_from_prompt_submission"]
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows process-tree regression")
def test_streaming_timeout_terminates_wrapper_child_without_hanging():
    command = [
        "cmd.exe",
        "/c",
        sys.executable,
        "-u",
        "-c",
        (
            "import json, time; print(json.dumps({'started': True}), flush=True); "
            "time.sleep(5)"
        ),
        "--output-format",
        "stream-json",
    ]
    started = production.time.perf_counter()

    with pytest.raises(production.subprocess.TimeoutExpired):
        production._streaming_run(
            command,
            input="prompt",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=0.1,
            check=False,
        )

    assert production.time.perf_counter() - started < 4
    assert production._LAST_STREAM_CAPTURE is not None


def test_streaming_early_exit_preserves_capture_despite_broken_input_pipe():
    command = [
        sys.executable,
        "-c",
        "raise SystemExit(0)",
        "--output-format",
        "stream-json",
    ]

    completed = production._streaming_run(
        command,
        input="prompt" * 1_000_000,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
        check=False,
    )

    assert completed.returncode == 0
    assert production._LAST_STREAM_CAPTURE is not None
    assert production._LAST_STREAM_CAPTURE["line_count"] == 0


def test_attempt_metric_annotation_fills_elapsed_time_and_usage(tmp_path):
    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "id": "message-1",
                "usage": {"input_tokens": 3, "output_tokens": 4},
                "content": [
                    {"type": "tool_use", "name": "Edit", "input": {}}
                ],
            },
        }
    ) + "\n"
    events = production.parse_events(line)
    (tmp_path / "attempts.json").write_text(
        json.dumps([{"ordinal": 1, "event_index": 0}]), encoding="utf-8"
    )
    capture = {
        "schema": "mneme.production-stream-timing/v1",
        "clock": "time.perf_counter_ns",
        "process_started_utc": "2026-08-14T00:00:00+00:00",
        "prompt_submission_started_seconds_after_process_start": 0.25,
        "line_count": 1,
        "event_count": 1,
        "lines": [
            {
                "line_index": 0,
                "event_index": 0,
                "line_sha256": production._sha256(line.encode("utf-8")),
                "elapsed_seconds_from_process_start": 1.5,
                "elapsed_seconds_from_prompt_submission": 1.25,
            }
        ],
    }
    result = {}

    production._annotate_attempt_metrics(
        tmp_path, result, events, line, capture
    )

    attempts = json.loads((tmp_path / "attempts.json").read_text())
    assert result["seconds_to_first_attempt"] == 1.25
    assert attempts[0]["elapsed_seconds_from_prompt_submission"] == 1.25
    assert attempts[0]["model_usage_through_attempt"]["input_tokens"] == 3
    assert attempts[0]["model_usage_through_attempt"]["output_tokens"] == 4


def test_exact_production_init_controls_pass():
    result = production.assess_init_contamination([_valid_init()])

    assert result["pass"] is True
    assert result["violations"] == []


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("tools", ["Read", "Write", "Bash"], "allowed tools"),
        ("permissionMode", "bypassPermissions", "permission mode"),
        ("skills", ["unexpected"], "skills differ"),
        ("mcp_servers", [{"name": "unexpected"}], "MCP servers differ"),
        ("memory_paths", ["C:/auto-memory"], "auto-memory"),
        ("plugins", [], "exactly one production plugin"),
    ],
)
def test_production_init_contamination_is_detected(field, value, message):
    init = _valid_init()
    init[field] = value

    result = production.assess_init_contamination([init])

    assert result["pass"] is False
    assert any(message in violation for violation in result["violations"])


def test_no_turn_init_event_still_requires_contamination_validation():
    assert production._init_validation_required(
        [_valid_init()], technical_invalid=True
    )
    assert not production._init_validation_required([], technical_invalid=True)


def test_orphan_prompt_hook_response_counts_as_delivery_processing_started():
    response = _hook_events("")[1]

    assert production._prompt_hook_observed([response]) is True
    assert production._prompt_hook_observed([]) is False


def test_governed_treatment_exact_pre_generation_delivery_passes():
    task = _task("auth-1")
    expected = production._expected_guidance()[task["id"]]
    context = production.build_guidance(
        production.MEMORY_FIXTURE, task["prompt"]
    ).context

    result = production.assess_injection_delivery(
        _hook_events(context), task, "treatment", expected
    )

    assert result["delivery_pass"] is True
    assert result["scored_treatment_operational_failure"] is False
    assert result["stop_campaign"] is False


def test_missing_governed_treatment_delivery_is_scored_and_never_rerun():
    task = _task("auth-1")
    expected = production._expected_guidance()[task["id"]]

    result = production.assess_injection_delivery(
        _hook_events(""), task, "treatment", expected
    )

    assert result["delivery_pass"] is False
    assert result["scored_treatment_operational_failure"] is True
    assert result["rerun_permitted"] is False
    assert result["stop_campaign"] is True


def test_late_governed_treatment_delivery_is_scored_and_stops():
    task = _task("auth-1")
    expected = production._expected_guidance()[task["id"]]
    context = production.build_guidance(
        production.MEMORY_FIXTURE, task["prompt"]
    ).context

    result = production.assess_injection_delivery(
        _hook_events(context, late=True), task, "treatment", expected
    )

    assert result["delivery_pass"] is False
    assert result["scored_treatment_operational_failure"] is True
    assert result["rerun_permitted"] is False
    assert result["stop_campaign"] is True


def test_duplicate_governed_hook_response_is_scored_and_stops():
    task = _task("auth-1")
    expected = production._expected_guidance()[task["id"]]
    context = production.build_guidance(
        production.MEMORY_FIXTURE, task["prompt"]
    ).context
    events = _hook_events(context)
    events.insert(2, {**events[1], "output": ""})

    result = production.assess_injection_delivery(
        events, task, "treatment", expected
    )

    assert result["delivery_pass"] is False
    assert result["scored_treatment_operational_failure"] is True
    assert result["rerun_permitted"] is False
    assert result["stop_campaign"] is True


def test_unmatched_duplicate_governed_hook_start_is_scored_and_stops():
    task = _task("auth-1")
    expected = production._expected_guidance()[task["id"]]
    context = production.build_guidance(
        production.MEMORY_FIXTURE, task["prompt"]
    ).context
    events = _hook_events(context)
    events.insert(1, {**events[0], "hook_id": "guidance-extra"})

    result = production.assess_injection_delivery(
        events, task, "treatment", expected
    )

    assert result["delivery_pass"] is False
    assert result["scored_treatment_operational_failure"] is True
    assert result["rerun_permitted"] is False
    assert result["stop_campaign"] is True


@pytest.mark.parametrize(
    ("task_id", "arm"),
    [
        ("auth-1", "baseline"),
        ("auth-1", "treatment"),
        ("control-1", "treatment"),
    ],
)
def test_missing_hook_ids_fail_transport_for_every_arm(task_id, arm):
    task = _task(task_id)
    expected = production._expected_guidance()[task["id"]]
    events = _hook_events("")
    events[0].pop("hook_id")
    events[1].pop("hook_id")

    result = production.assess_injection_delivery(events, task, arm, expected)

    assert result["delivery_pass"] is False
    assert result["scored_operational_failure"] is True
    assert result["stop_campaign"] is True


def test_non_object_hook_output_is_scored_as_missing_delivery():
    task = _task("auth-1")
    expected = production._expected_guidance()[task["id"]]
    events = _hook_events("")
    events[1]["output"] = json.dumps({"hookSpecificOutput": None})

    result = production.assess_injection_delivery(
        events, task, "treatment", expected
    )

    assert result["delivery_pass"] is False
    assert result["scored_treatment_operational_failure"] is True
    assert result["stop_campaign"] is True


def test_baseline_automatic_context_is_arm_isolation_failure():
    task = _task("auth-1")
    expected = production._expected_guidance()[task["id"]]
    context = production.build_guidance(
        production.MEMORY_FIXTURE, task["prompt"]
    ).context

    result = production.assess_injection_delivery(
        _hook_events(context), task, "baseline", expected
    )

    assert result["arm_isolation_failure"] is True
    assert result["stop_campaign"] is True
    assert result["scored_treatment_operational_failure"] is False


def test_baseline_automatic_context_remains_isolation_failure_with_transport_defect():
    task = _task("auth-1")
    expected = production._expected_guidance()[task["id"]]
    context = production.build_guidance(
        production.MEMORY_FIXTURE, task["prompt"]
    ).context
    events = _hook_events(context)
    events.insert(1, {**events[0], "hook_id": "guidance-extra"})

    result = production.assess_injection_delivery(
        events, task, "baseline", expected
    )

    assert result["delivery_pass"] is False
    assert result["scored_operational_failure"] is True
    assert result["arm_isolation_failure"] is True
    assert result["stop_campaign"] is True


def test_baseline_missing_hook_evidence_is_scored_operational_failure():
    task = _task("auth-1")
    expected = production._expected_guidance()[task["id"]]

    result = production.assess_injection_delivery(
        [], task, "baseline", expected
    )

    assert result["delivery_pass"] is False
    assert result["scored_operational_failure"] is True
    assert result["rerun_permitted"] is False
    assert result["stop_campaign"] is True


def test_treatment_control_guidance_is_retained_as_product_outcome():
    task = _task("control-1")
    expected = production._expected_guidance()[task["id"]]

    result = production.assess_injection_delivery(
        _hook_events("unexpected context"), task, "treatment", expected
    )

    assert result["delivery_pass"] is False
    assert result["arm_isolation_failure"] is False
    assert result["scored_treatment_operational_failure"] is False
    assert result["stop_campaign"] is False


def test_treatment_control_missing_hook_evidence_is_scored_and_stops():
    task = _task("control-1")
    expected = production._expected_guidance()[task["id"]]

    result = production.assess_injection_delivery(
        [], task, "treatment", expected
    )

    assert result["delivery_pass"] is False
    assert result["scored_operational_failure"] is True
    assert result["scored_treatment_operational_failure"] is True
    assert result["rerun_permitted"] is False
    assert result["stop_campaign"] is True


def _write_preserved_slot(
    root,
    item,
    *,
    events=None,
    archived=False,
    technical_invalid=False,
):
    task = _task(item["task_id"])
    if events is None:
        events = [_valid_init(), *_hook_events("")]
    label = production._slot_key(
        item["task_id"], item["arm"], item["repetition"]
    )
    if archived:
        slot_root = (
            root / production.EVALUATION / "invalidations" / f"{label}__test-01"
        )
    else:
        slot_root = production._slot_metadata(root, item).parent
    slot_root.mkdir(parents=True)
    stdout = "".join(json.dumps(event) + "\n" for event in events)
    (slot_root / "stdout.jsonl").write_text(stdout, encoding="utf-8")
    lines = []
    for index, line in enumerate(stdout.splitlines(keepends=True)):
        lines.append(
            {
                "line_index": index,
                "event_index": index,
                "line_sha256": production._sha256(line.encode("utf-8")),
                "elapsed_seconds_from_process_start": round(index * 0.01, 6),
                "elapsed_seconds_from_prompt_submission": round(index * 0.01, 6),
            }
        )
    timing = {
        "schema": "mneme.production-stream-timing/v1",
        "clock": "time.perf_counter_ns",
        "process_started_utc": "2026-08-14T00:00:00+00:00",
        "prompt_submission_started_seconds_after_process_start": 0.0,
        "line_count": len(lines),
        "event_count": len(events),
        "lines": lines,
    }
    (slot_root / "event_timing.json").write_text(json.dumps(timing), encoding="utf-8")
    (slot_root / "attempts.json").write_text("[]", encoding="utf-8")
    lock = json.loads(production.EXECUTION_LOCK.read_text(encoding="utf-8"))
    metadata = {
        "evaluation": production.EVALUATION,
        "task_id": item["task_id"],
        "arm": item["arm"],
        "repetition": item["repetition"],
        "technical_invalid": technical_invalid,
        "isolation_pass": True,
        "isolation_violations": [],
        "seconds_to_first_attempt": None,
        "execution_lock_sha256": production._path_sha256(
            production.EXECUTION_LOCK
        ),
    }
    if archived:
        metadata["archived_to"] = str(slot_root)
    else:
        blind_id = f"review-{label}"
        metadata["blind_id"] = blind_id
        evaluation_root = root / production.EVALUATION
        review = evaluation_root / "blinded" / blind_id / "review.json"
        review.parent.mkdir(parents=True)
        review.write_text("{}", encoding="utf-8")
        mapping = evaluation_root / "private" / "blinding-map.json"
        mapping.parent.mkdir(parents=True)
        current = (
            json.loads(mapping.read_text(encoding="utf-8"))
            if mapping.is_file()
            else {"runs": {}}
        )
        current["runs"][blind_id] = label
        mapping.write_text(json.dumps(current), encoding="utf-8")
    delivery = production._classify_slot_delivery(
        events,
        metadata,
        task,
        item["arm"],
        lock["expected_guidance"][item["task_id"]],
    )
    metadata["injection_delivery"] = delivery
    (slot_root / "injection_delivery.json").write_text(
        json.dumps(delivery), encoding="utf-8"
    )
    (slot_root / "hook_events.json").write_text(
        json.dumps(production.shared.hook_events(events)), encoding="utf-8"
    )
    (slot_root / "isolation.json").write_text(
        json.dumps(
            {
                "evaluation": production.EVALUATION,
                "pass": True,
                "violations": [],
            }
        ),
        encoding="utf-8",
    )
    for name, content in {
        "stderr.log": "",
        "first_attempt.json": "{}",
        "first_attempt_workspace.json": "null",
        "first_attempt.diff": "",
        "offline_enforcement.json": "[]",
        "final_workspace.json": "{}",
        "workspace.diff": "",
    }.items():
        (slot_root / name).write_text(content, encoding="utf-8")
    (slot_root / "metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    return slot_root


def test_single_slot_selection_cannot_bypass_frozen_order(tmp_path):
    schedule = production._schedule()
    second = schedule[1]
    task = _task(second["task_id"])

    with pytest.raises(RuntimeError, match="frozen schedule requires"):
        production._assert_slot_order(
            task, second["arm"], second["repetition"], root=tmp_path
        )


def test_next_slot_is_allowed_after_complete_delivery_evidence(tmp_path):
    schedule = production._schedule()
    _write_preserved_slot(tmp_path, schedule[0])
    second = schedule[1]

    production._assert_slot_order(
        _task(second["task_id"]),
        second["arm"],
        second["repetition"],
        root=tmp_path,
    )


def test_preserved_stop_outcome_blocks_every_later_slot(tmp_path):
    schedule = production._schedule()
    task = _task(schedule[0]["task_id"])
    context = production.build_guidance(
        production.MEMORY_FIXTURE, task["prompt"]
    ).context
    _write_preserved_slot(
        tmp_path,
        schedule[0],
        events=[_valid_init(), *_hook_events(context)],
    )
    second = schedule[1]

    with pytest.raises(RuntimeError, match="campaign is stopped"):
        production._assert_slot_order(
            _task(second["task_id"]),
            second["arm"],
            second["repetition"],
            root=tmp_path,
        )


def test_completed_slot_missing_delivery_artifact_blocks_progress(tmp_path):
    schedule = production._schedule()
    slot_root = _write_preserved_slot(tmp_path, schedule[0])
    (slot_root / "injection_delivery.json").unlink()
    second = schedule[1]

    with pytest.raises(RuntimeError, match="lacks required artifacts"):
        production._assert_slot_order(
            _task(second["task_id"]),
            second["arm"],
            second["repetition"],
            root=tmp_path,
        )


def test_completed_slot_corrupt_event_timing_blocks_progress(tmp_path):
    schedule = production._schedule()
    slot_root = _write_preserved_slot(tmp_path, schedule[0])
    timing_path = slot_root / "event_timing.json"
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    timing["lines"][0]["line_sha256"] = "0" * 64
    timing_path.write_text(json.dumps(timing), encoding="utf-8")
    second = schedule[1]

    with pytest.raises(RuntimeError, match="does not match stdout"):
        production._assert_slot_order(
            _task(second["task_id"]),
            second["arm"],
            second["repetition"],
            root=tmp_path,
        )


def test_future_completed_slot_breaks_contiguous_prefix(tmp_path):
    schedule = production._schedule()
    _write_preserved_slot(tmp_path, schedule[1])
    first = schedule[0]

    with pytest.raises(RuntimeError, match="future completed slot"):
        production._assert_slot_order(
            _task(first["task_id"]),
            first["arm"],
            first["repetition"],
            root=tmp_path,
        )


def test_future_archived_invalidation_breaks_schedule_order(tmp_path):
    schedule = production._schedule()
    _write_preserved_slot(
        tmp_path,
        schedule[1],
        events=[],
        archived=True,
        technical_invalid=True,
    )
    first = schedule[0]

    with pytest.raises(RuntimeError, match="future archived invalidation"):
        production._assert_slot_order(
            _task(first["task_id"]),
            first["arm"],
            first["repetition"],
            root=tmp_path,
        )


def test_archived_nonrerunnable_delivery_failure_blocks_progress(tmp_path):
    schedule = production._schedule()
    _write_preserved_slot(
        tmp_path,
        schedule[0],
        events=[_valid_init(), _hook_events("")[0]],
        archived=True,
        technical_invalid=True,
    )
    first = schedule[0]

    with pytest.raises(RuntimeError, match="archived delivery failure"):
        production._assert_slot_order(
            _task(first["task_id"]),
            first["arm"],
            first["repetition"],
            root=tmp_path,
        )


def test_archived_true_technical_invalidation_allows_same_slot_rerun(tmp_path):
    schedule = production._schedule()
    _write_preserved_slot(
        tmp_path,
        schedule[0],
        events=[],
        archived=True,
        technical_invalid=True,
    )
    first = schedule[0]

    production._assert_slot_order(
        _task(first["task_id"]),
        first["arm"],
        first["repetition"],
        root=tmp_path,
    )


def test_unresolved_staging_artifact_blocks_any_launch(tmp_path):
    first = production._schedule()[0]
    staging = tmp_path / production.EVALUATION / ".staging" / "partial-slot"
    staging.mkdir(parents=True)

    with pytest.raises(RuntimeError, match="unresolved staging artifacts"):
        production._assert_slot_order(
            _task(first["task_id"]),
            first["arm"],
            first["repetition"],
            root=tmp_path,
        )


def test_invalidation_directory_without_metadata_blocks_any_launch(tmp_path):
    first = production._schedule()[0]
    invalid = tmp_path / production.EVALUATION / "invalidations" / "partial"
    invalid.mkdir(parents=True)

    with pytest.raises(RuntimeError, match="unresolved invalidation artifact"):
        production._assert_slot_order(
            _task(first["task_id"]),
            first["arm"],
            first["repetition"],
            root=tmp_path,
        )


def test_run_directory_without_metadata_blocks_any_launch(tmp_path):
    first = production._schedule()[0]
    production._slot_metadata(tmp_path, first).parent.mkdir(parents=True)

    with pytest.raises(RuntimeError, match="run slot exists without frozen metadata"):
        production._assert_slot_order(
            _task(first["task_id"]),
            first["arm"],
            first["repetition"],
            root=tmp_path,
        )
