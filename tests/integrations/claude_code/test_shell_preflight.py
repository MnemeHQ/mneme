"""ADR-021: shell preflight classification and reconstruction.

The classifier must be conservative and deterministic: only quoted-delimiter
heredoc writes through `cat >`/`cat >>` are reconstructable; everything else
is potentially mutating unless provably read-only.
"""
import pytest

from mneme.integrations.claude_code.shell_preflight import (
    Classification,
    classify_command,
    reconstruct_heredoc_write,
)


class TestReconstruction:
    def test_simple_overwrite(self):
        rec = reconstruct_heredoc_write("cat > src/db.py << 'EOF'\nimport psycopg2\nEOF")
        assert rec is not None
        assert rec.target_path == "src/db.py"
        assert rec.append is False
        assert rec.proposed_content == "import psycopg2\n"

    def test_double_quoted_delimiter_is_literal(self):
        rec = reconstruct_heredoc_write('cat > out.txt << "MNEME"\nline $keep `raw`\nMNEME')
        assert rec is not None
        assert rec.proposed_content == "line $keep `raw`\n"

    def test_append_form(self):
        rec = reconstruct_heredoc_write("cat >> log.txt << 'EOF'\nappended\nEOF")
        assert rec is not None
        assert rec.append is True
        assert rec.proposed_content == "appended\n"

    def test_absolute_target(self):
        rec = reconstruct_heredoc_write("cat > /etc/hosts.deny << 'X'\nall\nX")
        assert rec is not None
        assert rec.target_path == "/etc/hosts.deny"

    def test_multiline_body_preserved_verbatim(self):
        body = "def f():\n    return 1\n\n\n"
        cmd = f"cat > a.py << 'EOF'\n{body}EOF"
        rec = reconstruct_heredoc_write(cmd)
        assert rec is not None
        assert rec.proposed_content == body

    def test_crlf_input_normalized(self):
        rec = reconstruct_heredoc_write("cat > a.txt << 'EOF'\r\nhi\r\nEOF\r\n")
        assert rec is not None
        assert rec.proposed_content == "hi\n"


class TestNonReconstructable:
    """Cases that must NOT be treated as deterministic reconstruction."""

    @pytest.mark.parametrize(
        "cmd",
        [
            # Unquoted delimiter: expansion happens, bytes unknowable.
            "cat > out.txt << EOF\n$HOME\nEOF",
            'cat > out.txt << EOF\n$(whoami)\nEOF',
            # Tab-stripping delimiter has post-processing semantics.
            "cat > out.txt <<- 'EOF'\nhi\nEOF",
            # Pipelines / chains / substitutions.
            "echo hi | tee out.txt",
            "cd src && cat > db.py << 'EOF'\nx\nEOF",
            "python -c \"open('a.py','w').write('x')\"",
            "node -e 'require(\"fs\").writeFileSync(\"a\",\"b\")'",
            "git checkout -- storage_db.py",
            "./scripts/generate.sh",
            # Multiple redirections.
            "cat > a.txt << 'EOF'\nx\nEOF\ncat > b.txt << 'EOF'\ny\nEOF",
            # Unterminated heredoc.
            "cat > a.txt << 'EOF'\nno terminator",
            # Redirect target with expansion.
            "cat > $OUT << 'EOF'\nx\nEOF",
            "cat > ~/fuzz/*.txt << 'EOF'\nx\nEOF",
            # Not cat.
            "tee a.txt << 'EOF'\nx\nEOF",
            # Empty command.
            "",
            "   ",
        ],
    )
    def test_not_reconstructable(self, cmd):
        assert reconstruct_heredoc_write(cmd) is None

    def test_delimiter_appearing_early_terminates_body(self):
        """First line equal to the delimiter ends the document."""
        cmd = "cat > a.txt << 'EOF'\nfirst\nEOF"
        rec = reconstruct_heredoc_write(cmd)
        assert rec is not None
        assert rec.proposed_content == "first\n"

    def test_trailing_content_after_delimiter_refused(self):
        """A second command after the closing delimiter is not reconstructed."""
        cmd = "cat > a.txt << 'EOF'\nfirst\nEOF\necho pwned > b.txt"
        assert reconstruct_heredoc_write(cmd) is None


class TestClassification:
    def test_reconstructable_classified_a(self):
        assert classify_command("cat > a.py << 'EOF'\nx\nEOF") is Classification.RECONSTRUCTABLE

    @pytest.mark.parametrize(
        "cmd",
        [
            "rm -rf build/",
            "mv a b",
            "cp a b",
            "touch a.txt",
            "sed -i s/a/b/ f.txt",
            "chmod +x run.sh",
            "pip install requests",
            "npm run build",
            "python gen.py",
            "make all",
            "git commit -m x",
            "echo hi > out.txt",
            "ls | wc -l",
            "foo_bar_unknown_binary --flag",
            'sh -c "echo hi"',
        ],
    )
    def test_potentially_mutating(self, cmd):
        assert (
            classify_command(cmd) is Classification.POTENTIALLY_MUTATING
        ), f"{cmd!r} must not be classified safe"

    @pytest.mark.parametrize(
        "cmd",
        [
            "ls -la",
            "pwd",
            "cat README.md",
            "grep -rn psycopg2 src/",
            "head -n 5 file.txt",
            "tail -20 log.txt",
            "wc -l src/*.py",
            "which python",
            "file data.bin",
            "diff a.txt b.txt",
            "git status",
            "git diff",
            "git log --oneline -3",
            "echo hello",
        ],
    )
    def test_non_mutating(self, cmd):
        assert classify_command(cmd) is Classification.NON_MUTATING

    def test_classification_is_deterministic(self):
        cmd = "cat > weird << 'D'\n$x\nD"
        results = {classify_command(cmd) for _ in range(5)}
        assert len(results) == 1
