import ast
import json
import subprocess
import sys
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from mneme.usage.contracts import (
    Aggregate,
    ExecutionContext,
    Operation,
    Surface,
)
from mneme.usage.service import SECONDS_PER_DAY, disabled_state, new_enabled_state
from mneme.usage.store import UsageStateCorrupt, UsageStore


def _fingerprint(root: Path):
    if not root.exists():
        return None
    return {
        str(path.relative_to(root)): (
            path.is_dir(),
            None if path.is_dir() else path.read_bytes(),
            path.stat().st_mtime_ns,
        )
        for path in sorted(root.rglob("*"))
    }


def _enabled_store(tmp_path: Path, *, policy_version="1") -> UsageStore:
    store = UsageStore(tmp_path / "usage", policy_version=policy_version)
    store.initialize(
        new_enabled_state(
            accepted_at="2026-10-09T00:00:00Z",
            secret=b"s" * 32,
            policy_version=policy_version,
        )
    )
    return store


def _increment(store: UsageStore, *, now=1) -> bool:
    return store.try_increment(
        unix_seconds=now,
        surface=Surface.CLI,
        operation=Operation.CLI_CHECK,
        execution_context=ExecutionContext.INTERACTIVE,
    )


def test_absent_consent_creates_no_directory_or_lock(tmp_path):
    store = UsageStore(tmp_path / "missing")
    assert _increment(store) is False
    assert not store.paths.directory.exists()


@pytest.mark.parametrize("state_kind", ["disabled", "stale"])
def test_disabled_or_stale_consent_performs_no_filesystem_writes(tmp_path, state_kind):
    store = _enabled_store(tmp_path)
    if state_kind == "disabled":
        store.update_administratively(disabled_state, unix_seconds=1)
    else:
        store.update_administratively(
            lambda state: replace(
                state,
                consent=replace(state.consent, policy_version="0"),
            ),
            unix_seconds=1,
        )
    before = _fingerprint(store.paths.directory)
    assert _increment(store) is False
    assert _fingerprint(store.paths.directory) == before


def test_corrupt_state_fails_closed_without_creating_lock(tmp_path):
    directory = tmp_path / "usage"
    directory.mkdir()
    (directory / "state.json").write_text("{not-json", encoding="utf-8")
    store = UsageStore(directory)
    with pytest.raises(UsageStateCorrupt):
        store.read(unix_seconds=1)
    assert _increment(store) is False
    assert not store.paths.lock.exists()
    assert (directory / "state.json").read_text(encoding="utf-8") == "{not-json"


def test_read_only_logical_expiration_does_not_clean_up_disk(tmp_path):
    store = _enabled_store(tmp_path)
    store.update_administratively(
        lambda state: replace(
            state,
            counters=(
                Aggregate(
                    identifier_epoch=0,
                    weekly_bucket=0,
                    surface=Surface.CLI,
                    operation=Operation.CLI_CHECK,
                    execution_context=ExecutionContext.INTERACTIVE,
                ),
            ),
        ),
        unix_seconds=1,
    )
    before = store.paths.state.read_bytes()
    visible = store.read(unix_seconds=35 * SECONDS_PER_DAY)
    assert visible is not None and visible.counters == ()
    assert store.paths.state.read_bytes() == before


def test_concurrent_writers_never_lose_a_successful_increment_or_corrupt_state(
    tmp_path,
):
    store = _enabled_store(tmp_path)
    barrier = threading.Barrier(20)
    results = []
    results_lock = threading.Lock()

    def worker():
        barrier.wait()
        result = _increment(store)
        with results_lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    state = store.read(unix_seconds=1)
    assert state is not None
    assert state.counters[0].count == sum(results)
    assert sum(results) >= 1
    json.loads(store.paths.state.read_text(encoding="utf-8"))


def test_consent_is_rechecked_under_lock(monkeypatch, tmp_path):
    store = _enabled_store(tmp_path)
    enabled = store.read_raw()
    assert enabled is not None and enabled.consent is not None
    disabled = replace(enabled, consent=replace(enabled.consent, enabled=False))
    reads = iter((enabled, disabled))
    monkeypatch.setattr(store, "_read_raw", lambda: next(reads))
    before = store.paths.state.read_bytes()
    assert _increment(store) is False
    assert store.paths.state.read_bytes() == before


def test_concurrent_disable_wins_before_recorder_locked_recheck(monkeypatch, tmp_path):
    store = _enabled_store(tmp_path)
    original_read = store._read_raw
    preflight_complete = threading.Event()
    disable_complete = threading.Event()
    first_recorder_read = True

    def coordinated_read():
        nonlocal first_recorder_read
        state = original_read()
        if threading.current_thread().name == "recorder" and first_recorder_read:
            first_recorder_read = False
            preflight_complete.set()
            assert disable_complete.wait(timeout=5)
        return state

    monkeypatch.setattr(store, "_read_raw", coordinated_read)
    outcome = []
    recorder = threading.Thread(
        name="recorder", target=lambda: outcome.append(_increment(store))
    )
    recorder.start()
    assert preflight_complete.wait(timeout=5)
    store.update_administratively(disabled_state, unix_seconds=1)
    disable_complete.set()
    recorder.join(timeout=5)
    assert not recorder.is_alive()
    assert outcome == [False]
    state = original_read()
    assert state is not None and state.counters == ()
    assert not state.has_current_consent()


def test_disable_serializes_with_increment_and_prevents_later_writes(tmp_path):
    store = _enabled_store(tmp_path)
    store.update_administratively(disabled_state, unix_seconds=1)
    before = store.paths.state.read_bytes()
    assert _increment(store) is False
    assert store.paths.state.read_bytes() == before


def test_symlinked_state_fails_open_for_runtime_without_touching_target(tmp_path):
    directory = tmp_path / "usage"
    directory.mkdir()
    target = tmp_path / "target.json"
    target.write_text("do-not-touch", encoding="utf-8")
    try:
        (directory / "state.json").symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is not available")
    store = UsageStore(directory)
    assert _increment(store) is False
    assert target.read_text(encoding="utf-8") == "do-not-touch"
    assert not store.paths.lock.exists()


def test_usage_package_has_no_network_imports():
    package = Path(__file__).parents[2] / "mneme" / "usage"
    forbidden = {"socket", "http", "urllib", "requests", "aiohttp", "httpx"}
    violations = []
    for source_path in package.glob("*.py"):
        tree = ast.parse(
            source_path.read_text(encoding="utf-8"), filename=str(source_path)
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".", 1)[0]]
            else:
                names = []
            if forbidden.intersection(names):
                violations.append((source_path.name, node.lineno))
    assert violations == []


def test_atomic_replace_failure_preserves_original_state(monkeypatch, tmp_path):
    store = _enabled_store(tmp_path)
    before = store.paths.state.read_bytes()
    monkeypatch.setattr(
        "mneme.usage.store.os.replace",
        lambda *_args: (_ for _ in ()).throw(OSError("disk")),
    )
    assert _increment(store) is False
    assert store.paths.state.read_bytes() == before
    assert list(store.paths.directory.glob("*.tmp")) == []


def test_cross_process_locking_never_loses_a_reported_success(tmp_path):
    store = _enabled_store(tmp_path)
    script = """
import sys
from mneme.usage.contracts import ExecutionContext, Operation, Surface
from mneme.usage.store import UsageStore
ok = UsageStore(sys.argv[1]).try_increment(
    unix_seconds=1,
    surface=Surface.CLI,
    operation=Operation.CLI_CHECK,
    execution_context=ExecutionContext.INTERACTIVE,
)
print('1' if ok else '0')
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(store.paths.directory)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(12)
    ]
    successes = 0
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        successes += int(stdout.strip())
    state = store.read(unix_seconds=1)
    assert state is not None
    assert state.counters[0].count == successes
    assert successes >= 1
