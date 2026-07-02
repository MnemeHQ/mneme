"""Mode resolution for the Claude Code hook adapter.

Precedence: MNEME_HOOK_MODE > CLAUDE_PLUGIN_OPTION_MODE > "strict".
The first variable that is *set* wins; unrecognized values fall back to strict.
"""
import pytest

from mneme.integrations.claude_code.hook import resolve_mode


@pytest.fixture(autouse=True)
def _clean_mode_env(monkeypatch):
    monkeypatch.delenv("MNEME_HOOK_MODE", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_MODE", raising=False)


# 1 & 2: explicit MNEME_HOOK_MODE
def test_mneme_hook_mode_strict(monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "strict")
    assert resolve_mode() == "strict"


def test_mneme_hook_mode_warn(monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    assert resolve_mode() == "warn"


# 3: plugin option used when MNEME_HOOK_MODE is absent
def test_plugin_option_used_when_hook_mode_absent(monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_MODE", "warn")
    assert resolve_mode() == "warn"


# 4: explicit MNEME_HOOK_MODE overrides the plugin option
def test_hook_mode_overrides_plugin_option(monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "warn")
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_MODE", "strict")
    assert resolve_mode() == "warn"


# 5: invalid values fall back to strict
def test_invalid_hook_mode_falls_back_to_strict(monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "banana")
    assert resolve_mode() == "strict"


def test_invalid_plugin_option_falls_back_to_strict(monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_MODE", "loose")
    assert resolve_mode() == "strict"


# default: neither set
def test_default_is_strict():
    assert resolve_mode() == "strict"


# a set-but-invalid explicit override does not silently defer to the plugin
def test_invalid_explicit_override_does_not_fall_through(monkeypatch):
    monkeypatch.setenv("MNEME_HOOK_MODE", "nonsense")
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_MODE", "warn")
    assert resolve_mode() == "strict"


# tolerant of case and surrounding whitespace
@pytest.mark.parametrize("raw,expected", [("WARN", "warn"), ("  warn  ", "warn"), ("Strict", "strict")])
def test_normalizes_case_and_whitespace(monkeypatch, raw, expected):
    monkeypatch.setenv("MNEME_HOOK_MODE", raw)
    assert resolve_mode() == expected
