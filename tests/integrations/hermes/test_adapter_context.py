"""H1 context-injection tests: pre_llm_call through the existing retrieval path."""

import json

import pytest

from mneme.integrations.hermes.adapter import MnemeHermes


@pytest.fixture()
def governed(tmp_path):
    mem = tmp_path / ".mneme" / "project_memory.json"
    mem.parent.mkdir(parents=True, exist_ok=True)
    mem.write_text(
        json.dumps(
            {
                "meta": {
                    "name": "fixture",
                    "description": "test project memory",
                },
                "version": 1,
                "decisions": [
                    {
                        "id": "D-DB-1",
                        "decision": "PostgreSQL via psycopg2 is the only approved storage layer",
                        "rationale": "one canonical persistence path",
                        "scope": ["database", "storage"],
                        "rules": [{"type": "FORBID_LITERAL", "value": "import redis"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return mem


class TestContextForTurn:
    def test_injects_retrieved_decisions(self, tmp_path, governed):
        gate = MnemeHermes(project_dir=tmp_path)
        injection = gate.context_for_turn("which storage backend for the session cache?")
        assert "[Mneme decisions applied]" in injection.text
        assert injection.decision_ids == ["D-DB-1"]
        assert injection.memory_path.endswith("project_memory.json")

    def test_pre_llm_call_returns_hermes_context_shape(self, tmp_path, governed):
        gate = MnemeHermes(project_dir=tmp_path)
        payload = gate.pre_llm_call(user_message="database layer question")
        assert isinstance(payload, dict)
        assert set(payload) == {"context"}
        assert "[Mneme decisions applied]" in payload["context"]

    def test_irrelevant_query_injects_nothing(self, tmp_path):
        gate = MnemeHermes(project_dir=tmp_path)
        # Lexical retrieval scores zero; format_decisions returns "".
        payload = gate.pre_llm_call(user_message="zzz qqq xxx")
        assert payload is None

    def test_no_project_memory_injects_nothing(self, tmp_path):
        gate = MnemeHermes(project_dir=tmp_path / "empty")
        payload = gate.pre_llm_call(user_message="anything")
        assert payload is None
