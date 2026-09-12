"""Integration tests for `mneme audit` CLI command (P1.2 Architecture Audit)."""
import json
import tempfile
from pathlib import Path

import pytest

from mneme.cli import main
from mneme.enforcer import ArchitectureProtectionReport, assess_protection
from mneme.memory_store import MemoryStore
from mneme.schemas import Decision, Rule


def _create_test_memory(tmp_path: Path, decisions: list[Decision]) -> Path:
    """Create a test project_memory.json with given decisions."""
    mem = tmp_path / "project_memory.json"
    mem.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "meta": {"name": "test", "description": "test"},
        "items": [],
        "examples": [],
        "decisions": [],
    }
    for d in decisions:
        entry = {
            "id": d.id,
            "decision": d.decision,
            "rationale": d.rationale,
            "scope": list(d.scope),
            "constraints": list(d.constraints),
            "anti_patterns": list(d.anti_patterns),
            "rules": [
                {
                    "type": r.type,
                    "value": r.value,
                    "exclude_paths": list(r.exclude_paths),
                }
                for r in d.rules
            ],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        # Only add include_paths if non-empty
        for i, r in enumerate(d.rules):
            if r.include_paths:
                entry["rules"][i]["include_paths"] = list(r.include_paths)
        data["decisions"].append(entry)
    mem.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return mem


class TestAuditCLI:
    """Integration tests for mneme audit CLI."""

    def test_audit_empty_memory(self, tmp_path):
        """Audit on empty memory returns gracefully."""
        mem = _create_test_memory(tmp_path, [])
        exit_code = main(["audit", "--memory", str(mem)])
        assert exit_code == 0

    def test_audit_protected_decision(self, tmp_path):
        """Decision with FORBID_LITERAL -> Protected."""
        decisions = [
            Decision(
                id="ADR-001",
                decision="Use JSON storage",
                rules=[Rule(type="FORBID_LITERAL", value="sqlite")],
            )
        ]
        mem = _create_test_memory(tmp_path, decisions)
        exit_code = main(["audit", "--memory", str(mem)])
        assert exit_code == 0

    def test_audit_mneme_ready_decision(self, tmp_path):
        """Decision with single-term anti-pattern -> Mneme-ready."""
        decisions = [
            Decision(
                id="ADR-002",
                decision="No ORM",
                anti_patterns=["orm"],
            )
        ]
        mem = _create_test_memory(tmp_path, decisions)
        exit_code = main(["audit", "--memory", str(mem)])
        assert exit_code == 0

    def test_audit_guidance_decision(self, tmp_path):
        """Decision with no mechanical rules -> Guidance."""
        decisions = [
            Decision(
                id="ADR-003",
                decision="Services should be loosely coupled",
                rationale="Architectural principle",
            )
        ]
        mem = _create_test_memory(tmp_path, decisions)
        exit_code = main(["audit", "--memory", str(mem)])
        assert exit_code == 0

    def test_audit_json_output(self, tmp_path):
        """JSON output contains expected schema and fields."""
        decisions = [
            Decision(
                id="ADR-001",
                decision="Use JSON storage",
                rules=[Rule(type="FORBID_LITERAL", value="sqlite")],
            )
        ]
        mem = _create_test_memory(tmp_path, decisions)
        json_out = tmp_path / "audit.json"
        exit_code = main(["audit", "--memory", str(mem), "--json", str(json_out)])
        assert exit_code == 0
        assert json_out.exists()

        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert data["schema"] == "mneme.audit/v1"
        assert "summary" in data
        assert "decisions" in data
        assert data["summary"]["total_decisions"] == 1
        assert data["summary"]["protection_relevant"] == 1
        assert data["summary"]["protected"] == 1
        assert data["summary"]["current_protection_pct"] == 100.0

    def test_audit_mixed_decisions(self, tmp_path):
        """Audit correctly classifies mixed decision types."""
        decisions = [
            Decision(
                id="ADR-001",
                decision="No sqlite",
                rules=[Rule(type="FORBID_LITERAL", value="sqlite")],
            ),
            Decision(
                id="ADR-002",
                decision="No ORM",
                anti_patterns=["orm"],
            ),
            Decision(
                id="ADR-003",
                decision="No complex deps",
                anti_patterns=["introduce ORM framework"],
            ),
            Decision(
                id="ADR-004",
                decision="No external DB",
                constraints=["no postgres"],
            ),
            Decision(
                id="ADR-005",
                decision="Loose coupling",
                rationale="Architectural principle",
            ),
        ]
        mem = _create_test_memory(tmp_path, decisions)
        json_out = tmp_path / "audit.json"
        exit_code = main(["audit", "--memory", str(mem), "--json", str(json_out)])
        assert exit_code == 0

        data = json.loads(json_out.read_text(encoding="utf-8"))
        summary = data["summary"]
        assert summary["total_decisions"] == 5
        assert summary["protection_relevant"] == 4  # 4 deterministic, 1 guidance
        assert summary["protected"] == 1
        assert summary["mneme_ready"] == 2  # ADR-002 (single-term AP) + ADR-004 (single-term no constraint)
        assert summary["requires_modelling"] == 1
        assert summary["guidance"] == 1
        # Current Protection = 1/4 = 25%
        assert summary["current_protection_pct"] == 25.0
        # Identified Mneme Potential = (1+2)/4 = 75%
        assert summary["identified_mneme_potential_pct"] == 75.0

    def test_audit_superseded_decisions_excluded(self, tmp_path):
        """Superseded decisions don't count toward protection-relevant."""
        decisions = [
            Decision(
                id="ADR-001",
                decision="No sqlite",
                rules=[Rule(type="FORBID_LITERAL", value="sqlite")],
            ),
            Decision(
                id="ADR-002",
                decision="No ORM",
                anti_patterns=["orm"],
            ),
        ]
        # Manually create memory with status field
        mem = tmp_path / "project_memory.json"
        data = {
            "meta": {"name": "test", "description": "test"},
            "items": [],
            "examples": [],
            "decisions": [
                {
                    "id": "ADR-001",
                    "decision": "No sqlite",
                    "rationale": "",
                    "scope": [],
                    "constraints": [],
                    "anti_patterns": [],
                    "rules": [{"type": "FORBID_LITERAL", "value": "sqlite", "exclude_paths": []}],
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "status": "active",
                },
                {
                    "id": "ADR-002",
                    "decision": "No ORM",
                    "rationale": "",
                    "scope": [],
                    "constraints": [],
                    "anti_patterns": ["orm"],
                    "rules": [],
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "status": "superseded",
                },
            ],
        }
        mem.write_text(json.dumps(data, indent=2), encoding="utf-8")

        json_out = tmp_path / "audit.json"
        exit_code = main(["audit", "--memory", str(mem), "--json", str(json_out)])
        assert exit_code == 0

        data = json.loads(json_out.read_text(encoding="utf-8"))
        summary = data["summary"]
        # Only 1 active decision counts
        assert summary["protection_relevant"] == 1
        assert summary["protected"] == 1
        assert summary["current_protection_pct"] == 100.0

    def test_audit_repo_root_scans_evidence(self, tmp_path):
        """Audit with repo-root scans external enforcement evidence."""
        decisions = [
            Decision(
                id="ADR-001",
                decision="No psycopg2",
                anti_patterns=["psycopg2"],
            )
        ]
        mem = _create_test_memory(tmp_path, decisions)

        # Create repo with CI workflow
        repo = tmp_path / "repo"
        repo.mkdir()
        workflows = repo / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("""
name: CI
on: [push]
jobs:
  test:
    steps:
      - run: grep -r "psycopg2" . && exit 1 || exit 0
""")

        json_out = tmp_path / "audit.json"
        exit_code = main(["audit", "--memory", str(mem), "--repo-root", str(repo), "--json", str(json_out)])
        assert exit_code == 0

        data = json.loads(json_out.read_text(encoding="utf-8"))
        # Should be protected due to verified CI
        assert data["summary"]["protected"] == 1
        assert data["summary"]["current_protection_pct"] == 100.0

        # Check evidence sources
        decision = data["decisions"][0]
        assert decision["evidence_confidence"] == "verified"
        assert any("ci:verified:" in e for e in decision["evidence_sources"])

    def test_audit_candidate_evidence_not_protected(self, tmp_path):
        """Candidate evidence (no enforcement pattern) doesn't make Protected."""
        decisions = [
            Decision(
                id="ADR-001",
                decision="No psycopg2",
                anti_patterns=["psycopg2"],
            )
        ]
        mem = _create_test_memory(tmp_path, decisions)

        # Create repo with CI workflow that mentions but doesn't enforce
        repo = tmp_path / "repo"
        repo.mkdir()
        workflows = repo / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "deploy.yml").write_text("""
name: Deploy
on: [push]
jobs:
  build:
    steps:
      - run: echo "using psycopg2 in production"
""")

        json_out = tmp_path / "audit.json"
        exit_code = main(["audit", "--memory", str(mem), "--repo-root", str(repo), "--json", str(json_out)])
        assert exit_code == 1  # Candidate evidence -> exit 1 (warning)

        data = json.loads(json_out.read_text(encoding="utf-8"))
        # Should be mneme_ready, not protected
        assert data["summary"]["mneme_ready"] == 1
        assert data["summary"]["protected"] == 0
        assert data["summary"]["identified_mneme_potential_pct"] == 100.0

        # Check evidence is candidate
        decision = data["decisions"][0]
        assert decision["evidence_confidence"] == "candidate"
        assert any("ci:candidate:" in e for e in decision["evidence_sources"])

    def test_audit_guarded_block_ci_verified(self, tmp_path):
        """Guarded if/then block failing on token detection -> verified/Protected."""
        decisions = [
            Decision(
                id="ADR-001",
                decision="No psycopg2",
                anti_patterns=["psycopg2"],
            )
        ]
        mem = _create_test_memory(tmp_path, decisions)

        repo = tmp_path / "repo"
        repo.mkdir()
        workflows = repo / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("""
name: CI
on: [push]
jobs:
  test:
    steps:
      - run: |
          if grep -r "psycopg2" .; then
            echo "forbidden dependency detected"
            exit 1
          fi
""")

        json_out = tmp_path / "audit.json"
        exit_code = main(["audit", "--memory", str(mem), "--repo-root", str(repo), "--json", str(json_out)])
        assert exit_code == 0

        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert data["summary"]["protected"] == 1
        assert data["summary"]["current_protection_pct"] == 100.0
        decision = data["decisions"][0]
        assert decision["evidence_confidence"] == "verified"
        assert any("ci:verified:" in e for e in decision["evidence_sources"])

    def test_audit_unrelated_exit_stays_candidate(self, tmp_path):
        """Token mention plus unrelated exit 1 elsewhere -> candidate, not Protected.

        The exit 1 lives in a different step and no token line reaches it;
        file-level co-occurrence must not upgrade to verified.
        """
        decisions = [
            Decision(
                id="ADR-001",
                decision="No psycopg2",
                anti_patterns=["psycopg2"],
            )
        ]
        mem = _create_test_memory(tmp_path, decisions)

        repo = tmp_path / "repo"
        repo.mkdir()
        workflows = repo / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "deploy.yml").write_text("""
name: Deploy
on: [push]
jobs:
  build:
    steps:
      - run: echo "using psycopg2 in production"
      - run: exit 1
""")

        json_out = tmp_path / "audit.json"
        exit_code = main(["audit", "--memory", str(mem), "--repo-root", str(repo), "--json", str(json_out)])
        assert exit_code == 1  # candidate evidence remains a warning

        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert data["summary"]["protected"] == 0
        assert data["summary"]["mneme_ready"] == 1
        assert data["summary"]["current_protection_pct"] == 0.0
        decision = data["decisions"][0]
        assert decision["evidence_confidence"] == "candidate"
        assert any("ci:candidate:" in e for e in decision["evidence_sources"])
        assert not any("ci:verified:" in e for e in decision["evidence_sources"])

    def test_audit_ci_without_token_no_evidence(self, tmp_path):
        """Workflow fails on something else; token never mentioned -> no evidence."""
        decisions = [
            Decision(
                id="ADR-001",
                decision="No psycopg2",
                anti_patterns=["psycopg2"],
            )
        ]
        mem = _create_test_memory(tmp_path, decisions)

        repo = tmp_path / "repo"
        repo.mkdir()
        workflows = repo / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("""
name: CI
on: [push]
jobs:
  test:
    steps:
      - run: exit 1
""")

        json_out = tmp_path / "audit.json"
        exit_code = main(["audit", "--memory", str(mem), "--repo-root", str(repo), "--json", str(json_out)])
        assert exit_code == 0  # no candidate evidence either

        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert data["summary"]["protected"] == 0
        assert data["summary"]["mneme_ready"] == 1
        assert data["summary"]["current_protection_pct"] == 0.0
        decision = data["decisions"][0]
        assert decision["evidence_confidence"] == "none"
        assert decision["evidence_sources"] == []

    def test_audit_inverted_failure_stays_candidate(self, tmp_path):
        """|| exit 1 and negated guards require token PRESENCE -> candidate.

        "<detect> || exit 1" and "if ! grep ..." fail when the token is
        ABSENT — an allow-list/requirement, not a prohibition — so neither
        may verify a FORBID-style decision.
        """
        decisions = [
            Decision(
                id="ADR-001",
                decision="No psycopg2",
                anti_patterns=["psycopg2"],
            )
        ]
        mem = _create_test_memory(tmp_path, decisions)

        repo = tmp_path / "repo"
        repo.mkdir()
        workflows = repo / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("""
name: CI
on: [push]
jobs:
  test:
    steps:
      - run: grep -q "psycopg2" ./required.txt || exit 1
      - run: |
          if ! grep -q "psycopg2" ./flagship.txt; then
            exit 1
          fi
""")

        json_out = tmp_path / "audit.json"
        exit_code = main(["audit", "--memory", str(mem), "--repo-root", str(repo), "--json", str(json_out)])
        assert exit_code == 1  # candidate evidence warning

        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert data["summary"]["protected"] == 0
        assert data["summary"]["mneme_ready"] == 1
        decision = data["decisions"][0]
        assert decision["evidence_confidence"] == "candidate"
        assert not any("ci:verified:" in e for e in decision["evidence_sources"])

    def test_audit_terminal_output_contains_key_fields(self, tmp_path, capsys):
        """Terminal output shows all required fields."""
        decisions = [
            Decision(
                id="ADR-001",
                decision="No sqlite",
                rules=[Rule(type="FORBID_LITERAL", value="sqlite")],
            ),
            Decision(
                id="ADR-002",
                decision="No ORM",
                anti_patterns=["orm"],
            ),
            Decision(
                id="ADR-003",
                decision="Loose coupling",
                rationale="Architectural principle",
            ),
        ]
        mem = _create_test_memory(tmp_path, decisions)
        main(["audit", "--memory", str(mem)])
        out = capsys.readouterr().out

        assert "Architecture Protection Audit" in out
        assert "Decisions discovered:" in out
        assert "Protection-relevant:" in out
        assert "Protected today:" in out
        assert "Mneme-ready:" in out
        assert "Requires modelling:" in out
        assert "Guidance-only:" in out
        assert "Current Protection:" in out
        assert "Per-decision breakdown:" in out

    def test_audit_terminal_presents_protection_gap(self, tmp_path, capsys):
        """ADR-026: the human-facing output shows Current Protection and
        Protection Gap, and never presents Identified Mneme Potential as an
        independent headline metric."""
        decisions = [
            Decision(
                id="ADR-001",
                decision="No sqlite",
                rules=[Rule(type="FORBID_LITERAL", value="sqlite")],
            ),
            Decision(
                id="ADR-002",
                decision="No ORM",
                anti_patterns=["orm"],
            ),
            Decision(
                id="ADR-003",
                decision="Loose coupling",
                rationale="Architectural principle",
            ),
        ]
        mem = _create_test_memory(tmp_path, decisions)
        exit_code = main(["audit", "--memory", str(mem)])
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "Current Protection:" in out
        assert "Protection Gap:" in out
        assert "Identified Mneme Potential" not in out

        # Gap and Current Protection are complementary (1 protected,
        # 1 mneme-ready, 1 guidance → PR = 2, gap = 50%).
        assert "Current Protection:           50.0%" in out
        assert "Protection Gap:               50.0%" in out

    def test_audit_json_retains_identified_mneme_potential(self, tmp_path):
        """mneme.audit/v1 keeps identified_mneme_potential_pct for
        compatibility; only the human presentation changed (no schema bump)."""
        decisions = [
            Decision(
                id="ADR-001",
                decision="No sqlite",
                rules=[Rule(type="FORBID_LITERAL", value="sqlite")],
            ),
            Decision(
                id="ADR-002",
                decision="No ORM",
                anti_patterns=["orm"],
            ),
        ]
        mem = _create_test_memory(tmp_path, decisions)
        json_out = tmp_path / "audit.json"
        exit_code = main(["audit", "--memory", str(mem), "--json", str(json_out)])
        assert exit_code == 0

        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert data["schema"] == "mneme.audit/v1"
        summary = data["summary"]
        assert "identified_mneme_potential_pct" in summary
        assert "protection_gap_pct" in summary
        assert "current_protection_pct" in summary
        # Compatibility metric is numerically identical to the gap.
        assert summary["identified_mneme_potential_pct"] == (
            summary["protection_gap_pct"]
        )


class TestAuditSemanticContract:
    """Tests verifying the semantic contract from the design document."""

    def test_guidance_never_in_denominator(self, tmp_path):
        """Guidance decisions never enter protection_relevant denominator."""
        decisions = [
            Decision(
                id="ADR-001",
                decision="No sqlite",
                rules=[Rule(type="FORBID_LITERAL", value="sqlite")],
            ),
            Decision(
                id="ADR-002",
                decision="Architectural principle",
                rationale="Guidance only",
            ),
        ]
        mem = _create_test_memory(tmp_path, decisions)

        store = MemoryStore(str(mem))
        store.load()
        decisions_loaded = store.decisions()

        report = assess_protection(decisions_loaded[0])  # Protected
        report2 = assess_protection(decisions_loaded[1])  # Guidance

        # Verify at assessment level
        assert report.intent == "deterministic"
        assert report2.intent == "guidance"
        assert report2.protection_tier == "guidance"

        # Verify at report level
        from mneme.enforcer import generate_protection_report
        full_report = generate_protection_report(decisions_loaded)
        assert full_report.protection_relevant == 1
        assert full_report.guidance == 1
        assert full_report.current_protection_pct == 100.0  # 1/1

    def test_evidence_cannot_upgrade_guidance(self, tmp_path):
        """Even with external evidence, guidance stays guidance."""
        decisions = [
            Decision(
                id="ADR-001",
                decision="Architectural principle",
                rationale="Guidance only",
            )
        ]
        mem = _create_test_memory(tmp_path, decisions)

        # Create repo with CI that mentions the term
        repo = tmp_path / "repo"
        repo.mkdir()
        workflows = repo / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("""
name: CI
on: [push]
jobs:
  test:
    steps:
      - run: echo "checking something"
""")

        from mneme.enforcer import generate_protection_report
        store = MemoryStore(str(mem))
        store.load()
        decisions_loaded = store.decisions()

        full_report = generate_protection_report(decisions_loaded, repo_root=repo)
        # Guidance stays guidance, not counted in protection_relevant
        assert full_report.protection_relevant == 0
        assert full_report.guidance == 1
        assert full_report.current_protection_pct == 0.0

    def test_mneme_ready_requires_guardrail(self, tmp_path):
        """Mneme-ready decisions must have explicit guardrail description."""
        decisions = [
            Decision(
                id="ADR-001",
                decision="No ORM",
                anti_patterns=["orm"],
            ),
            Decision(
                id="ADR-002",
                decision="No psycopg2",
                anti_patterns=["psycopg2"],
            ),
        ]
        mem = _create_test_memory(tmp_path, decisions)

        store = MemoryStore(str(mem))
        store.load()
        decisions_loaded = store.decisions()

        for d in decisions_loaded:
            assessment = assess_protection(d)
            if assessment.protection_tier == "mneme_ready":
                assert assessment.mneme_guardrail is not None
                assert "FORBID_LITERAL" in assessment.mneme_guardrail

    def test_percentages_reconstructable_from_decisions(self, tmp_path):
        """All percentages must be exactly recomputable from decisions array."""
        decisions = [
            Decision(
                id="ADR-001",
                decision="No sqlite",
                rules=[Rule(type="FORBID_LITERAL", value="sqlite")],
            ),
            Decision(
                id="ADR-002",
                decision="No ORM",
                anti_patterns=["orm"],
            ),
            Decision(
                id="ADR-003",
                decision="No complex deps",
                anti_patterns=["introduce ORM framework"],
            ),
            Decision(
                id="ADR-004",
                decision="No external DB",
                constraints=["no postgres"],
            ),
            Decision(
                id="ADR-005",
                decision="Loose coupling",
                rationale="Architectural principle",
            ),
        ]
        mem = _create_test_memory(tmp_path, decisions)

        store = MemoryStore(str(mem))
        store.load()
        decisions_loaded = store.decisions()

        from mneme.enforcer import generate_protection_report
        report = generate_protection_report(decisions_loaded)

        # Reconstruct from decisions array
        active = [a for a in report.decisions if a.status == "active"]
        p = sum(1 for a in active if a.protection_tier == "protected")
        m = sum(1 for a in active if a.protection_tier == "mneme_ready")
        r = sum(1 for a in active if a.protection_tier == "requires_modelling")
        g = sum(1 for a in active if a.protection_tier == "guidance")
        pr = p + m + r

        assert report.protection_relevant == pr
        assert report.protected == p
        assert report.mneme_ready == m
        assert report.requires_modelling == r
        assert report.guidance == g

        if pr > 0:
            expected_cp = round(p / pr * 100, 1)
            # ADR-026: Potential counts Mneme-ready + Requires modelling
            # (deterministically enforceable in principle, not yet enforced),
            # not only decisions immediately expressible by existing rules.
            expected_imp = round((m + r) / pr * 100, 1)
            expected_gap = round((m + r) / pr * 100, 1)
            assert report.current_protection_pct == expected_cp
            assert report.identified_mneme_potential_pct == expected_imp
            assert report.protection_gap_pct == expected_gap
            assert report.current_protection_pct + report.identified_mneme_potential_pct == 100.0

    def test_mixed_status_decisions(self, tmp_path):
        """Decisions with different statuses handled correctly."""
        mem = tmp_path / "project_memory.json"
        data = {
            "meta": {"name": "test", "description": "test"},
            "items": [],
            "examples": [],
            "decisions": [
                {
                    "id": "ADR-001",
                    "decision": "Active protected",
                    "rationale": "",
                    "scope": [],
                    "constraints": [],
                    "anti_patterns": [],
                    "rules": [{"type": "FORBID_LITERAL", "value": "sqlite", "exclude_paths": []}],
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "status": "active",
                },
                {
                    "id": "ADR-002",
                    "decision": "Superseded mneme-ready",
                    "rationale": "",
                    "scope": [],
                    "constraints": [],
                    "anti_patterns": ["orm"],
                    "rules": [],
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "status": "superseded",
                },
                {
                    "id": "ADR-003",
                    "decision": "Deprecated guidance",
                    "rationale": "Architectural principle",
                    "scope": [],
                    "constraints": [],
                    "anti_patterns": [],
                    "rules": [],
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "status": "deprecated",
                },
            ],
        }
        mem.write_text(json.dumps(data, indent=2), encoding="utf-8")

        store = MemoryStore(str(mem))
        store.load()
        decisions_loaded = store.decisions()

        from mneme.enforcer import generate_protection_report
        report = generate_protection_report(decisions_loaded)

        # Only active decisions count toward protection-relevant metrics
        # All 3 decisions appear in report, but only active counted in PR
        assert report.total_decisions == 3
        assert report.protection_relevant == 1
        assert report.protected == 1
        assert report.guidance == 0  # Only active decisions counted for any tier