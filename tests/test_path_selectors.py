import pytest

from mneme.path_selectors import (
    SelectorOutcome,
    evaluate_path_selectors,
    normalize_input_path,
    path_matches,
    policy_root,
    validate_path_pattern,
)


@pytest.mark.parametrize("pattern", [
    "README.md",
    "docs/*.md",
    "docs/**",
    "**/*.md",
    "src/test_*.py",
])
def test_selector_grammar_accepts_supported_patterns(pattern):
    assert validate_path_pattern(pattern) == pattern


@pytest.mark.parametrize("pattern", [
    "",
    "/docs/*.md",
    "C:/docs/*.md",
    "docs\\*.md",
    "docs//*.md",
    "./docs/*.md",
    "docs/../*.md",
    "!docs/*.md",
    "docs/file?.md",
    "docs/[ab].md",
    "docs/**.md",
    "docs/a**b.md",
])
def test_selector_grammar_rejects_unsupported_patterns(pattern):
    with pytest.raises(ValueError):
        validate_path_pattern(pattern)


@pytest.mark.parametrize("pattern,path", [
    ("docs/*.md", "docs/guide.md"),
    ("docs/**", "docs/guide.md"),
    ("docs/**", "docs/reference/guide.md"),
    ("docs/**/guide.md", "docs/guide.md"),
    ("**/*.md", "README.md"),
    ("**/*.md", "docs/README.md"),
])
def test_selector_matching(pattern, path):
    assert path_matches(pattern, path)


def test_selector_matching_is_case_sensitive():
    assert not path_matches("docs/*.md", "Docs/guide.md")


def test_policy_root_for_canonical_and_custom_memory(tmp_path):
    canonical = tmp_path / ".mneme" / "project_memory.json"
    custom = tmp_path / "policy" / "memory.json"
    assert policy_root(canonical) == tmp_path.resolve()
    assert policy_root(custom) == custom.parent.resolve()


def test_normalize_input_path_rejects_outside_policy_root(tmp_path):
    memory = tmp_path / "repo" / ".mneme" / "project_memory.json"
    outside = tmp_path / "other" / "file.md"
    with pytest.raises(ValueError, match="outside"):
        normalize_input_path(outside, memory)


def test_exclude_selector_overrides_include(tmp_path):
    memory = tmp_path / ".mneme" / "project_memory.json"
    target = tmp_path / "docs" / "generated" / "guide.md"
    selection = evaluate_path_selectors(
        include_paths=("docs/**",),
        exclude_paths=("docs/generated/**",),
        input_path=target,
        memory_path=memory,
    )
    assert selection.outcome == SelectorOutcome.EXCLUDED
    assert selection.input_path == "docs/generated/guide.md"
    assert selection.selector == "docs/generated/**"


def test_scoped_rule_without_path_is_unknown(tmp_path):
    selection = evaluate_path_selectors(
        include_paths=("docs/**",),
        exclude_paths=(),
        input_path=None,
        memory_path=tmp_path / ".mneme" / "project_memory.json",
    )
    assert selection.outcome == SelectorOutcome.UNKNOWN


def test_global_rule_does_not_require_path_metadata():
    selection = evaluate_path_selectors(
        include_paths=None,
        exclude_paths=(),
        input_path=None,
        memory_path=None,
    )
    assert selection.outcome == SelectorOutcome.APPLIED


def test_canonical_policy_source_is_excluded(tmp_path):
    source = tmp_path / "docs" / "adr" / "ADR-020.md"
    selection = evaluate_path_selectors(
        include_paths=("docs/**",),
        exclude_paths=(),
        input_path=source,
        memory_path=tmp_path / ".mneme" / "project_memory.json",
        policy_paths=(source,),
    )
    assert selection.outcome == SelectorOutcome.EXCLUDED
    assert selection.selector == "<canonical-policy-source>"
