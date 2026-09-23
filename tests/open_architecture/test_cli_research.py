"""
tests.open_architecture.test_cli_research — Tests for research CLI namespace.

Covers:
- `mneme research open-architecture validate`
- `mneme research open-architecture run` (dry-run preflight, explicit backend contract)
- `mneme research open-architecture export`
- `mneme research open-architecture report`
- Preservation of `mneme benchmark`
- Namespace separation (research namespace required)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mneme.cli import main

MANIFEST_PATH = Path("benchmarks/open_architecture/batch_01/manifest.yaml")


class TestResearchCli:
    def test_research_namespace_help(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["research", "open-architecture", "--help"])
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "validate" in out
        assert "run" in out
        assert "export" in out
        assert "report" in out

    def test_top_level_open_architecture_rejected(self):
        # Top-level 'mneme open-architecture' must NOT exist
        with pytest.raises(SystemExit):
            main(["open-architecture"])

    def test_existing_benchmark_command_preserved(self, capsys):
        # Existing frozen benchmark command is preserved unchanged
        with pytest.raises(SystemExit) as exc_info:
            main(["benchmark", "--help"])
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "usage: mneme benchmark" in out
        assert "--memory" in out

    def test_validate_valid_manifest(self, capsys):
        rc = main(["research", "open-architecture", "validate", "--manifest", str(MANIFEST_PATH)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "O1A Manifest Validation: OK" in out
        assert "Batch ID:           o1a-batch-01" in out
        assert "Configuration Hash:" in out
        assert "adrkit" in out

    def test_validate_missing_manifest_fails(self, capsys):
        rc = main(["research", "open-architecture", "validate", "--manifest", "non_existent_file.yaml"])
        assert rc == 2
        err = capsys.readouterr().err
        assert "does not exist" in err

    def test_run_dry_run_preflight(self, capsys):
        rc = main([
            "research", "open-architecture", "run",
            "--manifest", str(MANIFEST_PATH),
            "--repo-id", "adrkit",
            "--dry-run",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "O1A Run Preflight: OK" in out
        assert "Dry run complete" in out

    def test_run_without_backend_fails_with_guidance(self, capsys):
        rc = main([
            "research", "open-architecture", "run",
            "--manifest", str(MANIFEST_PATH),
            "--repo-id", "adrkit",
        ])
        assert rc == 2
        err = capsys.readouterr().err
        assert "No semantic classifier backend configured" in err
        assert "O1A3" in err

    def test_report_command(self, tmp_path: Path, capsys):
        bundle_dir = tmp_path / "bundle"
        bundle_dir.mkdir()
        (bundle_dir / "report.md").write_text("# Report Markdown\nContent\n", encoding="utf-8")
        (bundle_dir / "report.json").write_text('{"report_schema": "o1a.report/v1"}\n', encoding="utf-8")

        # Human-readable Markdown
        rc = main(["research", "open-architecture", "report", "--bundle-dir", str(bundle_dir)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Report Markdown" in out

        # JSON mode
        rc_json = main(["research", "open-architecture", "report", "--bundle-dir", str(bundle_dir), "--json"])
        assert rc_json == 0
        out_json = capsys.readouterr().out
        assert "o1a.report/v1" in out_json

    def test_export_command(self, tmp_path: Path, capsys):
        bundle_dir = tmp_path / "bundle"
        bundle_dir.mkdir()
        bundle_data = {
            "bundle_content_sha256": "sha256:1234567890abcdef",
            "repository_identifier": "mbeacom/adrkit",
            "status": "completed",
            "configuration_hash": "conf123",
        }
        (bundle_dir / "bundle.json").write_text(json.dumps(bundle_data), encoding="utf-8")

        rc = main(["research", "open-architecture", "export", "--bundle-dir", str(bundle_dir)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "sha256:1234567890abcdef" in out
        assert "mbeacom/adrkit" in out
