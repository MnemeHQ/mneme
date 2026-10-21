"""ADR-033 C2b verified availability authorization (charter §9).

Remotes are local bare repositories reached through the verifier's real Git
code path with one difference: ``allow_file=True`` also allows the ``file``
protocol. That switch is a function argument only; the hook's
``live_verifier`` never passes it, so the shipped HTTPS-only rule is tested
separately (V13). No test uses the network.

Groups: V (verifier), H (real hook entry point), A (authority commands).
The C2a matrix (P1/P2, D1-D9, S1) stays in ``test_availability_c2a.py`` and
passes unchanged: its fixtures have no Git repository, so the live verifier
returns ``AUTHORIZATION_UNVERIFIABLE(VERIFIER_CONFIG_MISSING)`` there.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from mneme import availability_authority as aa
from mneme import cli
from mneme.availability_authority import (
    AUTHORIZED, REVOKED, UNVERIFIABLE, VERIFIED_ABSENT, Verification,
    classify_git_failure, event_digest, normalize_url, validate_declaration,
    verify,
)
from mneme.integrations.claude_code import availability, hook
from tests.integrations.check_contract import check_payload, check_result

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "availability_policy" / "v1"
ACTIVE_MEMORY = (FIXTURES / "active_memory.json").read_bytes()
ACTIVATED_AT = "2026-10-21T09:00:00Z"
REVIEW = {
    "recorded_by": "Test Owner",
    "independent_approver_attested": False,
    "baseline_protection_attested": True,
}
CONTENT_MARKER = "c2b_submitted_content_marker"


# ── test remotes ──────────────────────────────────────────────────────────────

def _setup_env(home: Path) -> dict[str, str]:
    """Isolated Git for fixture setup only (not the verifier's environment)."""
    env = dict(os.environ)
    empty = home / "setup.gitconfig"
    empty.write_text("", encoding="utf-8")
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(empty),
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    })
    return env


class Baseline:
    """A bare remote ``origin`` plus a working clone at the policy root."""

    def __init__(self, tmp: Path, *, branch: str = "main") -> None:
        self.tmp = tmp
        self.env = _setup_env(tmp)
        self.remote = tmp / "remote.git"
        self.work = tmp / "work"
        self.branch = branch
        self.git("init", "--bare", "-q", "-b", branch, str(self.remote), cwd=tmp)
        self.git("init", "-q", "-b", branch, str(self.work), cwd=tmp)
        self.url = self.remote.resolve().as_uri()
        self.git("remote", "add", "origin", self.url)
        self.normalized = normalize_url(self.url)
        self.events: list[dict] = []

    def git(self, *args: str, cwd: Path | None = None, env: dict | None = None) -> str:
        return subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "-c", "protocol.file.allow=always", *args],
            cwd=str(cwd or self.work), env=env or self.env, check=True,
            capture_output=True, text=True,
        ).stdout

    def write(self, rel: str, data: bytes | None) -> None:
        path = self.work / rel
        if data is None:
            if path.exists():
                path.unlink()
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def commit(self, message: str, *, env: dict | None = None) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message, env=env)
        self.git("push", "-q", "origin", f"HEAD:{self.branch}")
        return self.git("rev-parse", "HEAD").strip()

    def declaration(self, events=None, **overrides) -> dict:
        document = {
            "schema": "mneme.availability/v1",
            "availability": "closed",
            "memory_path": ".mneme/project_memory.json",
            "repository": {"url": self.normalized, "branch": self.branch},
            "authority": {"events": list(self.events if events is None else events)},
        }
        document.update(overrides)
        return document

    def add_event(self, op: str, **activation) -> dict:
        event = {
            "seq": len(self.events) + 1,
            "op": op,
            "prev": event_digest(self.events[-1]) if self.events else None,
            "review": dict(REVIEW),
        }
        if op == "authorize":
            event["activation"] = {
                "activated_at": activation.get("activated_at", ACTIVATED_AT),
                "protected_decisions": activation.get("protected_decisions", ["d_ready"]),
            }
        self.events.append(event)
        return event

    def publish(self, document: dict | None = None, message: str = "declaration") -> str:
        doc = self.declaration() if document is None else document
        self.write(aa.DECLARATION_PATH, (json.dumps(doc, indent=2) + "\n").encode())
        return self.commit(message)

    def verify(self, **kwargs) -> Verification:
        return verify(self.work, allow_file=True, **kwargs)


def _memory_commit(base: Baseline) -> None:
    base.write(aa.MEMORY_PATH, ACTIVE_MEMORY)
    base.commit("memory")


@pytest.fixture
def base(tmp_path) -> Baseline:
    b = Baseline(tmp_path)
    _memory_commit(b)
    return b


@pytest.fixture
def authorized(base) -> Baseline:
    base.add_event("authorize")
    base.publish()
    return base


# ── V: verifier ───────────────────────────────────────────────────────────────

def test_v1_authorized(authorized):
    result = authorized.verify()
    assert (result.authorization, result.reason) == (AUTHORIZED, "")
    assert result.branch == "main" and len(result.tip) == 40
    assert result.baseline == authorized.declaration()


def test_v2_revoked(authorized):
    authorized.add_event("revoke")
    authorized.publish()
    assert authorized.verify().authorization == REVOKED


def test_v3_reauthorized(authorized):
    authorized.add_event("revoke")
    authorized.publish()
    authorized.add_event("authorize")
    authorized.publish()
    assert authorized.verify().authorization == AUTHORIZED


def test_v4_verified_absent(base):
    base.commit("more history")
    assert base.verify().authorization == VERIFIED_ABSENT


def test_v5_shallow_history_is_unverifiable_never_absent(base, tmp_path):
    shallow = tmp_path / "shallow.git"
    base.commit("second")
    base.git("clone", "-q", "--bare", "--depth", "1", base.url, str(shallow), cwd=tmp_path)
    base.git("remote", "set-url", "origin", shallow.resolve().as_uri())
    result = base.verify()
    assert (result.authorization, result.reason) == (UNVERIFIABLE, aa.HISTORY_INCOMPLETE)


def test_v6_deleted_after_authorize_is_evidence_invalid(authorized):
    """RR-7: deletion at the baseline without a revocation record."""
    authorized.write(aa.DECLARATION_PATH, None)
    authorized.commit("delete declaration")
    result = authorized.verify()
    assert (result.authorization, result.reason) == (UNVERIFIABLE, aa.EVIDENCE_INVALID)


def test_v7_deleted_after_revoke_is_revoked(authorized):
    authorized.add_event("revoke")
    authorized.publish()
    authorized.write(aa.DECLARATION_PATH, None)
    authorized.commit("delete declaration")
    assert authorized.verify().authorization == REVOKED


def _break(events: list[dict], how: str) -> list[dict]:
    events = json.loads(json.dumps(events))
    if how == "seq_gap":
        events[1]["seq"] = 3
    elif how == "wrong_prev":
        events[1]["prev"] = "sha256:" + "0" * 64
    elif how == "repeated_op":
        events[1]["op"] = "authorize"
        events[1]["activation"] = dict(events[0]["activation"])
    elif how == "empty":
        events = []
    elif how == "unknown_key":
        events[0]["timestamp"] = "2026-01-01"
    elif how == "bool_seq":
        events[0]["seq"] = True
    return events


@pytest.mark.parametrize("how", [
    "seq_gap", "wrong_prev", "repeated_op", "empty", "unknown_key", "bool_seq",
])
def test_v8_broken_chain_is_evidence_invalid(authorized, how):
    authorized.add_event("revoke")
    authorized.publish(authorized.declaration(_break(authorized.events, how)))
    result = authorized.verify()
    assert (result.authorization, result.reason) == (UNVERIFIABLE, aa.EVIDENCE_INVALID)


def test_v9_forged_dates_do_not_reorder(base):
    """RR-5: later events carry earlier commit dates; position still governs."""
    dates = iter(["2030-01-01T00:00:00", "2001-01-01T00:00:00", "1999-01-01T00:00:00"])
    for op in ("authorize", "revoke", "authorize"):
        base.add_event(op)
        date = next(dates)
        env = dict(base.env, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        base.write(aa.DECLARATION_PATH, json.dumps(base.declaration()).encode())
        base.commit(op, env=env)
    assert base.verify().authorization == AUTHORIZED


def test_v10_mirror_substitution_is_evidence_invalid(authorized, tmp_path):
    mirror = tmp_path / "mirror.git"
    authorized.git("clone", "-q", "--bare", authorized.url, str(mirror), cwd=tmp_path)
    authorized.git("remote", "set-url", "origin", mirror.resolve().as_uri())
    result = authorized.verify()
    assert (result.authorization, result.reason) == (UNVERIFIABLE, aa.EVIDENCE_INVALID)


def test_v11_branch_mismatch_is_evidence_invalid(base):
    base.add_event("authorize")
    doc = base.declaration()
    doc["repository"] = {"url": base.normalized, "branch": "trunk"}
    base.publish(doc)
    result = base.verify()
    assert (result.authorization, result.reason) == (UNVERIFIABLE, aa.EVIDENCE_INVALID)


def _memory_variant(change: str) -> bytes | None:
    document = json.loads(ACTIVE_MEMORY)
    if change == "missing":
        return None
    if change == "not_active":
        document["activation"]["state"] = "setup"
    elif change == "activated_at":
        document["activation"]["activated_at"] = "2026-10-22T00:00:00Z"
    elif change == "no_index":
        document.pop("decision_index")
    return json.dumps(document).encode()


@pytest.mark.parametrize("change", [
    "missing", "not_active", "activated_at", "no_index", "protection_removed",
])
def test_v12_activation_evidence_must_hold_at_tip(base, change):
    if change == "protection_removed":
        base.add_event("authorize", protected_decisions=["d_other", "d_ready"])
    else:
        base.add_event("authorize")
        base.write(aa.MEMORY_PATH, _memory_variant(change))
    base.publish()
    result = base.verify()
    assert (result.authorization, result.reason) == (UNVERIFIABLE, aa.EVIDENCE_INVALID)


@pytest.mark.parametrize("setup", [
    "no_git", "no_origin", "two_urls", "ssh", "file_without_test_transport",
    "userinfo", "not_top_level",
])
def test_v13_location_preconditions(base, tmp_path, setup):
    root = base.work
    allow_file = True
    if setup == "no_git":
        root = tmp_path / "plain"
        (root / ".mneme").mkdir(parents=True)
    elif setup == "no_origin":
        base.git("remote", "remove", "origin")
    elif setup == "two_urls":
        base.git("config", "--add", "remote.origin.url", "https://example.com/x")
    elif setup == "ssh":
        base.git("remote", "set-url", "origin", "git@example.com:x/y.git")
    elif setup == "file_without_test_transport":
        allow_file = False
    elif setup == "userinfo":
        base.git("remote", "set-url", "origin", "https://user:pw@example.com/x")
    elif setup == "not_top_level":
        root = base.work / "nested"
        (root / ".mneme").mkdir(parents=True)
    result = verify(root, allow_file=allow_file)
    assert (result.authorization, result.reason) == (UNVERIFIABLE, aa.VERIFIER_CONFIG_MISSING)


_ALLOWED_ENV = {
    "PATH", "SYSTEMROOT", "COMSPEC", "PATHEXT", "WINDIR", "HOME", "USERPROFILE",
    "XDG_CONFIG_HOME", "TMP", "TEMP", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL",
    "GIT_TERMINAL_PROMPT", "GIT_CEILING_DIRECTORIES",
}


def _recording(calls: list):
    real = aa._run_git

    def run(argv, *, env, cwd, timeout):
        recorded = dict(env)
        # Captured now: the temporary directory is gone after verification.
        recorded["__global_config_bytes"] = Path(env["GIT_CONFIG_GLOBAL"]).read_bytes()
        calls.append((list(argv), recorded, Path(cwd)))
        return real(argv, env=env, cwd=cwd, timeout=timeout)
    return run


def test_v14_ambient_configuration_never_reaches_git(authorized, monkeypatch):
    authorized.git("config", f"url.https://blackhole.invalid/.insteadOf", authorized.url)
    authorized.git("config", "http.proxy", "http://127.0.0.1:9")
    for name, value in {
        "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9",
        "GIT_DIR": "/nonexistent", "GIT_CONFIG_PARAMETERS": "'url.x.insteadOf'='y'",
        "GIT_SSL_CAINFO": "/nonexistent", "SSL_CERT_FILE": "/nonexistent",
        "MNEME_MEMORY": "/nonexistent", "GIT_ASKPASS": "evil",
    }.items():
        monkeypatch.setenv(name, value)
    calls: list = []
    monkeypatch.setattr(aa, "_run_git", _recording(calls))
    assert authorized.verify().authorization == AUTHORIZED
    assert calls
    for argv, env, cwd in calls:
        assert env.pop("__global_config_bytes") == b""
        assert set(env) <= _ALLOWED_ENV, set(env) - _ALLOWED_ENV
        assert env["GIT_CONFIG_NOSYSTEM"] == "1"
        assert authorized.work.resolve() not in [cwd.resolve(), *cwd.resolve().parents]
        assert "blackhole" not in " ".join(argv)
        if "--git-dir" in argv:
            assert authorized.work.resolve() not in Path(
                argv[argv.index("--git-dir") + 1]).resolve().parents


def test_v15_remote_tracking_refs_are_ignored(authorized):
    first = authorized.git("rev-list", "--max-parents=0", "HEAD").strip()
    authorized.git("fetch", "-q", "origin")
    authorized.git("update-ref", "refs/remotes/origin/main", first)
    assert authorized.verify().authorization == AUTHORIZED


@pytest.mark.parametrize("stderr,reason", [
    ("fatal: unable to access 'x': Could not resolve host: example.invalid", aa.DNS),
    ("fatal: unable to access 'x': Failed to connect to h port 443", aa.NETWORK),
    ("fatal: unable to access 'x': Connection refused", aa.NETWORK),
    ("fatal: unable to access 'x': SSL certificate problem: self signed", aa.TLS_IDENTITY_MISMATCH),
    ("fatal: could not read Username for 'https://h': terminal prompts disabled", aa.AUTH),
    ("fatal: Authentication failed for 'https://h/'", aa.AUTH),
    ("fatal: something unexpected", aa.VERIFIER_CRASH),
])
def test_v16_failure_mapping(stderr, reason):
    assert classify_git_failure(stderr) == reason


def test_v16_unreachable_remote_never_absent(base, tmp_path):
    base.git("remote", "set-url", "origin", (tmp_path / "missing.git").as_uri())
    result = base.verify()
    assert result.authorization == UNVERIFIABLE
    assert result.reason not in ("", aa.EVIDENCE_INVALID)


def test_v16_empty_remote_is_ref_missing(tmp_path):
    b = Baseline(tmp_path)
    result = b.verify()
    assert (result.authorization, result.reason) == (UNVERIFIABLE, aa.REF_MISSING)


@pytest.mark.parametrize("error,reason", [
    (OSError("git not found"), aa.VERIFIER_CRASH),
    (subprocess.TimeoutExpired("git", 1), aa.TIMEOUT),
])
def test_v16_process_failures(authorized, monkeypatch, error, reason):
    calls = {"n": 0}
    real = aa._run_git

    def run(argv, **kwargs):
        calls["n"] += 1
        if "ls-remote" in argv:
            raise error
        return real(argv, **kwargs)
    monkeypatch.setattr(aa, "_run_git", run)
    result = authorized.verify()
    assert (result.authorization, result.reason) == (UNVERIFIABLE, reason)


def test_v17_no_cache_and_nothing_left_behind(authorized, monkeypatch):
    created: list[Path] = []
    real_mkdtemp = aa.tempfile.mkdtemp

    def mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created.append(Path(path))
        return path
    monkeypatch.setattr(aa.tempfile, "mkdtemp", mkdtemp)
    calls: list = []
    monkeypatch.setattr(aa, "_run_git", _recording(calls))
    before = sorted(p.relative_to(authorized.work) for p in authorized.work.rglob("*"))
    assert authorized.verify().authorization == AUTHORIZED
    assert authorized.verify().authorization == AUTHORIZED
    fetches = [argv for argv, _, _ in calls if "fetch" in argv]
    ls_remotes = [argv for argv, _, _ in calls if "ls-remote" in argv]
    assert len(fetches) == 2 and len(ls_remotes) == 2
    assert created and not any(path.exists() for path in created)
    after = sorted(p.relative_to(authorized.work) for p in authorized.work.rglob("*"))
    assert before == after


def test_v18_budget_exhausted_is_timeout(authorized):
    result = authorized.verify(timeout=0.0)
    assert (result.authorization, result.reason) == (UNVERIFIABLE, aa.TIMEOUT)


def test_v18_slow_git_is_bounded(authorized, monkeypatch):
    def slow(argv, *, env, cwd, timeout):
        raise subprocess.TimeoutExpired(argv, timeout)
    monkeypatch.setattr(aa, "_run_git", slow)
    result = authorized.verify(timeout=1.0)
    assert (result.authorization, result.reason) == (UNVERIFIABLE, aa.TIMEOUT)


def test_declaration_validation_accepts_published_shape(authorized):
    validate_declaration(authorized.declaration())


# ── H: real hook entry point ─────────────────────────────────────────────────

def _clean_env(monkeypatch):
    for name in ("MNEME_MEMORY", "MNEME_HOOK_MODE", "CLAUDE_PLUGIN_OPTION_MODE",
                 "MNEME_HOOK_CHECK_TRANSPORT"):
        monkeypatch.delenv(name, raising=False)


def _envelope(target: Path, content: str = f"{CONTENT_MARKER} = 1\n", *, tool="Write", **extra):
    data = {"file_path": str(target), "content": content} | extra
    return {"hook_event_name": "PreToolUse", "tool_name": tool,
            "cwd": str(target.parent), "tool_input": data}


def _run_hook(envelope, *, response="real"):
    out, err = io.StringIO(), io.StringIO()
    if response == "real":
        rc = hook.handle_event(envelope, stderr=err, stdout=out)
    else:
        with patch.object(hook, "_invoke_check", return_value=response):
            rc = hook.handle_event(envelope, stderr=err, stdout=out)
    return rc, out.getvalue(), err.getvalue()


@pytest.fixture
def e2e(authorized, monkeypatch):
    """The live verifier with the test transport; local declaration matches."""
    _clean_env(monkeypatch)
    monkeypatch.setattr(availability, "live_verifier",
                        lambda declaration: verify(declaration.root, allow_file=True))
    return authorized


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """A fixed Verification through the hook's verifier seam (no Git)."""
    _clean_env(monkeypatch)
    root = tmp_path / "fake"
    (root / ".mneme").mkdir(parents=True)
    (root / ".mneme" / "project_memory.json").write_bytes(ACTIVE_MEMORY)
    b = Baseline.__new__(Baseline)
    b.normalized, b.branch, b.events = "https://example.com/project", "main", []
    b.add_event("authorize")
    document = b.declaration()
    (root / ".mneme" / "availability.json").write_text(json.dumps(document), encoding="utf-8")

    def use(authorization=AUTHORIZED, reason=""):
        result = Verification(authorization, reason, url=b.normalized, branch="main",
                              tip="a" * 40, baseline=document if authorization == AUTHORIZED
                              else None)
        monkeypatch.setattr(availability, "live_verifier", lambda _d: result)
        return root
    use.document = document
    return use


def _assert_operational(err: str, category: str):
    assert f"operational refusal (UNEVALUATED: {category})." in err
    assert "not a decision violation" in err
    assert "architectural decision violated" not in err
    assert CONTENT_MARKER not in err


def test_h1_authorized_missing_memory_refuses_end_to_end(e2e):
    """The first practical proof, through the real verifier (also H15)."""
    (e2e.work / aa.MEMORY_PATH).unlink()
    rc, out, err = _run_hook(_envelope(e2e.work / "service.py"))
    assert (rc, out) == (2, "")
    assert "mneme-hook: availability AUTHORIZED; baseline=main@" in err
    _assert_operational(err, "MEMORY_MISSING")


def test_h2_authorized_complete_pass_proceeds_end_to_end(e2e):
    rc, out, err = _run_hook(_envelope(e2e.work / "service.py", "value = 1\n"))
    assert (rc, out) == (0, "")
    assert "evaluation=TRUSTED_COMPLETE; availability did not refuse." in err


def test_h3_authorized_strict_fail_keeps_violation_block(e2e):
    rc, _, err = _run_hook(_envelope(e2e.work / "service.py", "import postgres\n"))
    assert rc == 2
    assert "architectural decision violated" in err
    assert "operational refusal" not in err


@pytest.mark.parametrize("response,category", [
    (check_result("PASS", complete=False), "EVALUATION_INCOMPLETE"),
    (subprocess.CompletedProcess([], 0, json.dumps(
        {k: v for k, v in check_payload("PASS").items() if k != "evaluation_complete"}), ""),
     "COMPLETENESS_UNSTATED"),
    (subprocess.CompletedProcess([], 1, "Traceback: crash", ""), "CHECK_UNTRUSTED"),
    (None, "CHECK_NOT_RUN"),
])
def test_h4_authorized_unavailable_evaluation_refuses(fake, response, category):
    root = fake()
    rc, out, err = _run_hook(_envelope(root / "service.py"), response=response)
    assert (rc, out) == (2, "")
    _assert_operational(err, category)


def test_h4_authorized_materialization_failure_refuses(fake):
    root = fake()
    target = root / "service.py"
    target.write_text("unrelated\n", encoding="utf-8")
    envelope = _envelope(target, tool="Edit", old_string="missing", new_string="new")
    envelope["tool_input"].pop("content")
    rc, _, err = _run_hook(envelope, response=check_result("PASS"))
    assert rc == 2
    _assert_operational(err, "CHECK_NOT_RUN")


def test_h5_mixed_partial_refuses_as_unevaluated(fake):
    root = fake()
    rc, _, err = _run_hook(_envelope(root / "service.py"),
                           response=check_result("FAIL", complete=False))
    assert rc == 2
    _assert_operational(err, "EVALUATION_INCOMPLETE")
    assert "matched in a partial evaluation, not a complete rule verdict" in err


@pytest.mark.parametrize("relation", ["behind", "diverges", "invalid"])
def test_h6_local_declaration_tampered_refuses_even_on_pass(fake, relation):
    root = fake()
    path = root / ".mneme" / "availability.json"
    document = json.loads(json.dumps(fake.document))
    if relation == "behind":
        b = Baseline.__new__(Baseline)
        b.normalized, b.branch, b.events = "https://example.com/project", "main", []
        b.add_event("authorize")
        b.add_event("revoke")
        b.add_event("authorize")
        newer = b.declaration()
        # The baseline is two events ahead of the local file.
        result = Verification(AUTHORIZED, url=b.normalized, branch="main", tip="b" * 40,
                              baseline=newer)
        availability_live = lambda _d: result  # noqa: E731
        with patch.object(availability, "live_verifier", availability_live):
            rc, _, err = _run_hook(_envelope(root / "service.py"),
                                   response=check_result("PASS"))
        assert rc == 2
        _assert_operational(err, "LOCAL_DECLARATION_TAMPERED")
        assert "local declaration behind" in err
        return
    if relation == "diverges":
        document["repository"]["url"] = "https://example.com/elsewhere"
        path.write_text(json.dumps(document), encoding="utf-8")
    else:
        path.write_text("{broken", encoding="utf-8")
    rc, _, err = _run_hook(_envelope(root / "service.py"), response=check_result("PASS"))
    assert rc == 2
    _assert_operational(err, "LOCAL_DECLARATION_TAMPERED")
    assert f"local declaration {relation}" in err


def test_h6_line_endings_and_key_order_still_match(fake):
    root = fake()
    path = root / ".mneme" / "availability.json"
    text = json.dumps(fake.document, indent=2, sort_keys=True).replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))
    rc, _, err = _run_hook(_envelope(root / "service.py"), response=check_result("PASS"))
    assert rc == 0 and "availability did not refuse" in err


def test_h7_mneme_memory_mismatch_refuses(fake, tmp_path, monkeypatch):
    root = fake()
    other = tmp_path / "other.json"
    other.write_bytes(ACTIVE_MEMORY)
    monkeypatch.setenv("MNEME_MEMORY", str(other))
    rc, _, err = _run_hook(_envelope(root / "service.py"), response=check_result("PASS"))
    assert rc == 2
    _assert_operational(err, "MEMORY_PATH_MISMATCH")


def test_h8_warn_mode_defers_as_today(fake, monkeypatch):
    root = fake()
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    rc, out, err = _run_hook(_envelope(root / "service.py"),
                             response=check_result("FAIL", mode="warn"))
    assert rc == 0 and "operational refusal" not in err


def test_h9_empty_delta_skips(fake):
    root = fake()
    rc, _, err = _run_hook(_envelope(root / "service.py", "   \n"))
    assert rc == 0 and "evaluation=SKIPPED; availability did not refuse." in err


@pytest.mark.parametrize("authorization", [REVOKED, VERIFIED_ABSENT])
@pytest.mark.parametrize("memory", [True, False])
def test_h10_revoked_or_absent_never_refuse(fake, authorization, memory):
    root = fake(authorization)
    if not memory:
        (root / ".mneme" / "project_memory.json").unlink()
    rc, _, err = _run_hook(_envelope(root / "service.py"), response=check_result("PASS"))
    assert rc == 0
    assert f"availability {authorization}; baseline=main@aaaaaaa;" in err
    assert "availability did not refuse." in err


@pytest.mark.parametrize("reason", [
    aa.NETWORK, aa.DNS, aa.TLS_IDENTITY_MISMATCH, aa.AUTH, aa.TIMEOUT,
    aa.VERIFIER_CRASH, aa.REF_MISSING, aa.HISTORY_INCOMPLETE, aa.EVIDENCE_INVALID,
    aa.VERIFIER_CONFIG_MISSING,
])
def test_h11_unverifiable_still_blocks_strict_fail(fake, reason):
    """U-10 / BP-9: UNVERIFIABLE never short-circuits enforcement."""
    root = fake(UNVERIFIABLE, reason)
    rc, _, err = _run_hook(_envelope(root / "service.py"), response=check_result("FAIL"))
    assert rc == 2
    assert f"availability {UNVERIFIABLE}({reason}); evaluation=TRUSTED_COMPLETE; " \
           "availability did not refuse." in err
    assert "architectural decision violated" in err


def test_h11_unverifiable_unavailable_evaluation_proceeds(fake):
    root = fake(UNVERIFIABLE, aa.NETWORK)
    rc, _, err = _run_hook(_envelope(root / "service.py"), response=None)
    assert rc == 0 and "evaluation=NOT_RUN; availability did not refuse." in err


def test_h12_unverifiable_mismatch_is_reported_not_refused(fake, tmp_path, monkeypatch):
    root = fake(UNVERIFIABLE, aa.NETWORK)
    other = tmp_path / "other.json"
    other.write_bytes(ACTIVE_MEMORY)
    monkeypatch.setenv("MNEME_MEMORY", str(other))
    rc, _, err = _run_hook(_envelope(root / "service.py"), response=check_result("PASS"))
    assert rc == 0
    assert "SS-3 memory path mismatch; evaluation not bound to declaration." in err


def test_h13_deleted_local_declaration_never_triggers(e2e, monkeypatch):
    (e2e.work / aa.DECLARATION_PATH).unlink()

    def forbidden(_declaration):
        raise AssertionError("verifier must not run without a declaration")
    monkeypatch.setattr(availability, "live_verifier", forbidden)
    rc, out, err = _run_hook(_envelope(e2e.work / "service.py", "value = 1\n"))
    assert (rc, out, err) == (0, "", "")


def test_h13_deleted_local_declaration_with_missing_memory_proceeds(e2e, monkeypatch):
    (e2e.work / aa.DECLARATION_PATH).unlink()
    (e2e.work / aa.MEMORY_PATH).unlink()
    monkeypatch.setattr(availability, "live_verifier", None)
    assert _run_hook(_envelope(e2e.work / "service.py")) == (0, "", "")


def test_h14_tamper_end_to_end_is_operational(e2e):
    path = e2e.work / aa.DECLARATION_PATH
    document = json.loads(path.read_text(encoding="utf-8"))
    document["authority"]["events"][0]["review"]["recorded_by"] = "Someone Else"
    path.write_text(json.dumps(document), encoding="utf-8")
    rc, _, err = _run_hook(_envelope(e2e.work / "service.py"))
    assert rc == 2
    _assert_operational(err, "LOCAL_DECLARATION_TAMPERED")


def test_hook_never_passes_the_test_transport(fake, monkeypatch):
    """The shipped live_verifier calls verify(root) with no file transport."""
    seen = []

    def fake_verify(root, **kwargs):
        seen.append(kwargs)
        return Verification(UNVERIFIABLE, aa.VERIFIER_CONFIG_MISSING)
    declaration = availability.discover_declaration(fake())
    monkeypatch.setattr(aa, "verify", fake_verify)
    _orig_live_verifier(declaration)
    assert seen == [{}]


_orig_live_verifier = availability.live_verifier


# ── A: authority commands ─────────────────────────────────────────────────────

@pytest.fixture
def cli_env(monkeypatch):
    real_verify = aa.verify
    monkeypatch.setattr(aa, "verify",
                        lambda root, **kw: real_verify(root, **{**kw, "allow_file": True}))
    answers: list[str] = []
    monkeypatch.setattr(cli, "_availability_is_interactive", lambda: True)
    monkeypatch.setattr(cli, "_availability_prompt", lambda _text: answers.pop(0))

    def run(root: Path, op: str, *extra: str, confirm: bool = True):
        answers[:] = ["Test Owner", "n", "y", op.upper() if confirm else "no"]
        return cli.main(["availability", op, "--repo-root", str(root), *extra])
    return run


def _tree_state(work: Path) -> dict:
    return {str(p.relative_to(work)): p.read_bytes() for p in work.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(work).parts}


def _head(base: Baseline) -> tuple[str, str]:
    return (base.git("rev-parse", "HEAD").strip(),
            base.git("status", "--porcelain", "--untracked-files=no"))


def test_a1_authorize_refused_when_already_authorized(authorized, cli_env):
    before = _tree_state(authorized.work)
    assert cli_env(authorized.work, "authorize") == 2
    assert _tree_state(authorized.work) == before


def test_a1_authorize_refused_when_unverifiable(base, cli_env):
    base.git("remote", "remove", "origin")
    assert cli_env(base.work, "authorize") == 2
    assert not (base.work / aa.DECLARATION_PATH).exists()


def test_a1_authorize_refused_without_active_protection(tmp_path, cli_env):
    b = Baseline(tmp_path)
    b.write(aa.MEMORY_PATH, _memory_variant("not_active"))
    b.commit("memory")
    assert cli_env(b.work, "authorize") == 2
    assert not (b.work / aa.DECLARATION_PATH).exists()


def test_a1_authorize_refused_without_tty(base, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_availability_is_interactive", lambda: False)
    assert cli.main(["availability", "authorize", "--repo-root", str(base.work)]) == 2
    assert "interactive terminal" in capsys.readouterr().err
    assert not (base.work / aa.DECLARATION_PATH).exists()


def test_a1_authorize_refused_without_confirmation(base, cli_env):
    assert cli_env(base.work, "authorize", confirm=False) == 2
    assert not (base.work / aa.DECLARATION_PATH).exists()


def test_a2_authorize_from_absent_writes_only_the_declaration(base, cli_env, monkeypatch):
    calls: list = []
    monkeypatch.setattr(aa, "_run_git", _recording(calls))
    before_head = _head(base)
    before = _tree_state(base.work)
    assert cli_env(base.work, "authorize") == 0
    after = _tree_state(base.work)
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    assert changed == {str(Path(aa.DECLARATION_PATH))}
    assert _head(base) == before_head
    document = validate_declaration(json.loads(after[str(Path(aa.DECLARATION_PATH))]))
    (event,) = document["authority"]["events"]
    assert event["op"] == "authorize" and event["prev"] is None
    assert event["activation"] == {"activated_at": ACTIVATED_AT,
                                   "protected_decisions": ["d_ready"]}
    assert event["review"] == REVIEW
    work = base.work.resolve()
    for argv, _, cwd in calls:
        assert work not in [cwd.resolve(), *cwd.resolve().parents]
        assert not {"commit", "push", "merge", "checkout", "reset"} & set(argv)
        if "add" in argv:
            git_dir = Path(argv[argv.index("--git-dir") + 1]).resolve()
            assert work not in git_dir.parents


def test_a2_authorize_from_revoked_extends_the_chain(authorized, cli_env):
    authorized.add_event("revoke")
    authorized.publish()
    assert cli_env(authorized.work, "authorize") == 0
    document = json.loads((authorized.work / aa.DECLARATION_PATH).read_text(encoding="utf-8"))
    events = validate_declaration(document)["authority"]["events"]
    assert [e["op"] for e in events] == ["authorize", "revoke", "authorize"]
    assert events[2]["prev"] == event_digest(events[1])
    authorized.commit("merge reauthorization")
    assert authorized.verify().authorization == AUTHORIZED


def test_a3_revoke_requires_authorized(base, cli_env):
    assert cli_env(base.work, "revoke") == 2
    assert not (base.work / aa.DECLARATION_PATH).exists()


def test_a3_revoke_from_authorized(authorized, cli_env):
    assert cli_env(authorized.work, "revoke") == 0
    authorized.commit("merge revocation")
    assert authorized.verify().authorization == REVOKED


def test_a4_status_is_read_only(authorized, cli_env, capsys):
    before, before_head = _tree_state(authorized.work), _head(authorized)
    assert cli.main(["availability", "status", "--repo-root", str(authorized.work)]) == 0
    out = capsys.readouterr().out
    assert "authorization: AUTHORIZED" in out
    assert "review attested, not verified" in out
    assert "local declaration: MATCH" in out
    assert _tree_state(authorized.work) == before and _head(authorized) == before_head


def test_a5_differing_local_declaration_needs_replace_local(base, cli_env):
    path = base.work / aa.DECLARATION_PATH
    path.write_text('{"stale": true}', encoding="utf-8")
    assert cli_env(base.work, "authorize") == 2
    assert path.read_text(encoding="utf-8") == '{"stale": true}'
    assert cli_env(base.work, "authorize", "--replace-local") == 0
    validate_declaration(json.loads(path.read_text(encoding="utf-8")))


# ── shared invariants ─────────────────────────────────────────────────────────

def test_canonical_memory_untouched_across_operations(authorized, cli_env):
    """Spec P-05: authority commands never write canonical memory."""
    memory = authorized.work / aa.MEMORY_PATH
    before = memory.read_bytes()
    cli_env(authorized.work, "revoke")
    cli.main(["availability", "status", "--repo-root", str(authorized.work)])
    assert memory.read_bytes() == before


def test_no_declaration_hook_path_does_not_import_the_verifier(tmp_path, monkeypatch):
    """Default-open parity: the C2b module loads only behind a declaration."""
    import sys
    _clean_env(monkeypatch)
    (tmp_path / ".mneme").mkdir()
    (tmp_path / ".mneme" / "project_memory.json").write_bytes(ACTIVE_MEMORY)
    monkeypatch.delitem(sys.modules, "mneme.availability_authority", raising=False)
    rc, _, err = _run_hook(_envelope(tmp_path / "service.py", "value = 1\n"),
                           response=check_result("PASS"))
    assert (rc, err) == (0, "")
    assert "mneme.availability_authority" not in sys.modules
    shutil.rmtree(tmp_path / ".mneme")
