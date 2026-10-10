import io
import time

from mneme import cli as mneme_cli
from mneme.usage import cli
from mneme.usage.contracts import ExecutionContext, Operation, Surface
from mneme.usage.store import UsageStore


def test_enable_status_disable_and_purge_lifecycle(tmp_path):
    store = UsageStore(tmp_path / "usage")
    enabled_out = io.StringIO()
    assert cli.enable(store, stdout=enabled_out) == 0
    assert "U1 never sends data over the network" in enabled_out.getvalue()
    state = store.read_raw()
    assert state is not None and state.has_current_consent()
    assert len(bytes.fromhex(state.secret_hex)) == 32

    before = store.paths.state.read_bytes()
    status_out = io.StringIO()
    assert cli.status(store, stdout=status_out) == 0
    assert "Usage measurement: enabled" in status_out.getvalue()
    assert "Scheduler: unavailable in U1" in status_out.getvalue()
    assert store.paths.state.read_bytes() == before

    assert cli.disable(store, stdout=io.StringIO()) == 0
    assert store.read_raw() is not None
    assert not store.read_raw().has_current_consent()
    assert cli.purge(store, stdout=io.StringIO()) == 0
    assert not store.paths.state.exists()
    assert not store.paths.lock.exists()


def test_absent_status_disable_and_purge_are_write_free(tmp_path):
    store = UsageStore(tmp_path / "usage")
    assert cli.status(store, stdout=io.StringIO()) == 0
    assert cli.disable(store, stdout=io.StringIO()) == 0
    assert cli.purge(store, stdout=io.StringIO()) == 0
    assert not store.paths.directory.exists()


def test_preview_materializes_exact_stable_payload_and_never_consumes(tmp_path):
    store = UsageStore(tmp_path / "usage")
    assert cli.enable(store, stdout=io.StringIO()) == 0
    assert store.try_increment(
        unix_seconds=time.time(),
        surface=Surface.CLI,
        operation=Operation.CLI_CHECK,
        execution_context=ExecutionContext.INTERACTIVE,
    )
    first = io.StringIO()
    assert cli.preview(store, stdout=first) == 0
    first_bytes = first.getvalue().encode("ascii")
    assert first_bytes.endswith(b"\n")
    state = store.read_raw()
    assert state is not None
    assert state.counters == ()
    assert state.snapshots[0].payload_bytes == first_bytes

    before = store.paths.state.read_bytes()
    second = io.StringIO()
    assert cli.preview(store, stdout=second) == 0
    assert second.getvalue() == first.getvalue()
    assert store.paths.state.read_bytes() == before


def test_preview_requires_current_consent_without_writing(tmp_path):
    store = UsageStore(tmp_path / "usage")
    assert cli.enable(store, stdout=io.StringIO()) == 0
    assert cli.disable(store, stdout=io.StringIO()) == 0
    before = store.paths.state.read_bytes()
    error = io.StringIO()
    assert cli.preview(store, stdout=io.StringIO(), stderr=error) == 2
    assert "current consent" in error.getvalue()
    assert store.paths.state.read_bytes() == before


def test_purge_then_enable_rotates_secret(tmp_path):
    store = UsageStore(tmp_path / "usage")
    assert cli.enable(store, stdout=io.StringIO()) == 0
    first = store.read_raw().secret_hex
    assert cli.purge(store, stdout=io.StringIO()) == 0
    assert cli.enable(store, stdout=io.StringIO()) == 0
    assert store.read_raw().secret_hex != first


def test_corrupt_state_can_be_purged_without_a_preexisting_lock(tmp_path):
    directory = tmp_path / "usage"
    directory.mkdir()
    (directory / "state.json").write_text("broken", encoding="utf-8")
    store = UsageStore(directory)
    error = io.StringIO()
    assert cli.status(store, stdout=io.StringIO(), stderr=error) == 2
    assert cli.purge(store, stdout=io.StringIO()) == 0
    assert not (directory / "state.json").exists()


def test_usage_command_surface_has_no_submit_or_weekly_mode(
    monkeypatch, tmp_path, capsys
):
    store = UsageStore(tmp_path / "usage")
    monkeypatch.setattr(mneme_cli, "_usage_store", lambda: store)
    assert mneme_cli.main(["usage", "enable"]) == 0
    output = capsys.readouterr()
    assert "local-only" in output.out

    parser = mneme_cli._build_parser()
    try:
        parser.parse_args(["usage", "submit"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("U2 submit command must not exist")

    try:
        parser.parse_args(["usage", "enable", "--submission", "weekly"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("U2 weekly mode must not exist")
