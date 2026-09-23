"""
mneme.open_architecture.classifiers.anthropic — Research-only Anthropic semantic classifier adapter.

Implements the SemanticClassifier protocol for O1A research benchmarks:
- Backend: "anthropic"
- Classifier version: "0.1"
- Model: "claude-sonnet-4-6"
- Deterministic structured output via output_config.format with task-specific JSON schemas
- Strictly bounded: no tools, no thinking, no web search, no repository execution
- No canonical writes, no DecisionProposal creation, no production LLMAdapter coupling
- Calibrated/genuine confidence only (defaults to None; never fabricated)
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import jsonschema

from mneme.open_architecture.classification import (
    ClassifierResult,
    ClassifierTask,
    ClassifierTaskType,
    SemanticClassifier,
)
from mneme.open_architecture.schemas import (
    VALID_AUTHORITIES,
    VALID_CLASSIFICATIONS,
    VALID_DOMAINS,
    VALID_ENFORCEMENT_POTENTIAL,
    VALID_LIFECYCLES,
    VALID_PURPOSES,
    VALID_RELATIONSHIP_TYPES,
    VALID_SCOPE_TYPES,
)


MIN_ANTHROPIC_SDK_VERSION = "0.25.0"


class AnthropicClassifierError(Exception):
    """Base exception for Anthropic classifier errors."""


class AnthropicAuthenticationError(AnthropicClassifierError):
    """Raised when authentication with Anthropic API fails."""


class AnthropicRateLimitError(AnthropicClassifierError):
    """Raised when Anthropic API rate limit is exceeded."""


class AnthropicMalformedResponseError(AnthropicClassifierError):
    """Raised when Anthropic response is malformed or violates task JSON schema."""


# ── Eight Explicit Structured-Output Schemas ───────────────────────────────────

TASK_SCHEMAS: dict[ClassifierTaskType, dict[str, Any]] = {
    ClassifierTaskType.DECISION_CLASSIFICATION: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "DecisionClassificationOutput",
        "type": "object",
        "properties": {
            "classification": {
                "type": "string",
                "enum": sorted(VALID_CLASSIFICATIONS),
                "description": "Primary architectural decision classification",
            },
            "rationale": {
                "type": "string",
                "description": "Brief evidence-grounded explanation for classification",
            },
        },
        "required": ["classification"],
        "additionalProperties": False,
    },
    ClassifierTaskType.DOMAINS: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "DecisionDomainsOutput",
        "type": "object",
        "properties": {
            "domains": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": sorted(VALID_DOMAINS),
                },
                "minItems": 1,
                "description": "Applicable architectural domains",
            },
        },
        "required": ["domains"],
        "additionalProperties": False,
    },
    ClassifierTaskType.PURPOSES: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "DecisionPurposesOutput",
        "type": "object",
        "properties": {
            "purposes": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": sorted(VALID_PURPOSES),
                },
                "minItems": 1,
                "description": "Architectural purposes of the decision",
            },
        },
        "required": ["purposes"],
        "additionalProperties": False,
    },
    ClassifierTaskType.AUTHORITY: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "DecisionAuthorityOutput",
        "type": "object",
        "properties": {
            "authority": {
                "type": "string",
                "enum": sorted(VALID_AUTHORITIES),
                "description": "Authority state as indicated by the source repository evidence",
            },
            "evidence": {
                "type": "string",
                "description": "Text evidence indicating repository authority state",
            },
        },
        "required": ["authority"],
        "additionalProperties": False,
    },
    ClassifierTaskType.SCOPE: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "DecisionScopeOutput",
        "type": "object",
        "properties": {
            "scopes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "scope_type": {
                            "type": "string",
                            "enum": sorted(VALID_SCOPE_TYPES),
                        },
                        "scope_expression": {
                            "type": ["string", "null"],
                            "description": "Target identifier, path, or pattern",
                        },
                    },
                    "required": ["scope_type"],
                    "additionalProperties": False,
                },
                "description": "Applicable architectural scopes",
            },
        },
        "required": ["scopes"],
        "additionalProperties": False,
    },
    ClassifierTaskType.LIFECYCLE: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "DecisionLifecycleOutput",
        "type": "object",
        "properties": {
            "lifecycle": {
                "type": "string",
                "enum": sorted(VALID_LIFECYCLES),
                "description": "Lifecycle state of the decision",
            },
            "supersedes": {
                "type": ["string", "null"],
                "description": "Decision or document superseded by this candidate",
            },
            "superseded_by": {
                "type": ["string", "null"],
                "description": "Decision or document superseding this candidate",
            },
        },
        "required": ["lifecycle"],
        "additionalProperties": False,
    },
    ClassifierTaskType.RELATIONSHIPS: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "DecisionRelationshipsOutput",
        "type": "object",
        "properties": {
            "relationships": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "relationship_type": {
                            "type": "string",
                            "enum": sorted(VALID_RELATIONSHIP_TYPES),
                        },
                        "target_reference": {
                            "type": ["string", "null"],
                            "description": "Referenced document, decision, or technology",
                        },
                        "evidence_reference": {
                            "type": ["string", "null"],
                            "description": "Text evidence for this relationship",
                        },
                    },
                    "required": ["relationship_type"],
                    "additionalProperties": False,
                },
                "description": "Relationships to other decisions or artifacts",
            },
        },
        "required": ["relationships"],
        "additionalProperties": False,
    },
    ClassifierTaskType.ENFORCEMENT_POTENTIAL: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "DecisionEnforcementPotentialOutput",
        "type": "object",
        "properties": {
            "enforcement_potential": {
                "type": "string",
                "enum": sorted(VALID_ENFORCEMENT_POTENTIAL),
                "description": "Mechanical enforcement potential of this decision",
            },
            "candidate_rule": {
                "type": ["string", "null"],
                "description": "Proposed deterministic rule description if mechanically enforceable",
            },
            "rationale": {
                "type": ["string", "null"],
                "description": "Brief explanation for the enforcement potential assessment",
            },
        },
        "required": ["enforcement_potential"],
        "additionalProperties": False,
    },
}


# ── Classifier Implementation ──────────────────────────────────────────────────


class AnthropicClassifier:
    """Research-only SemanticClassifier adapter using the Anthropic Messages API.

    Implements the SemanticClassifier protocol for O1A research benchmarks.
    Configured explicitly for claude-sonnet-4-6 with output_config.format.
    """

    def __init__(
        self,
        *,
        model_identifier: str = "claude-sonnet-4-6",
        classifier_version: str = "0.1",
        api_key: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout: float = 60.0,
        max_retries: int = 2,
        client: Any | None = None,
    ) -> None:
        self._backend_id = "anthropic"
        self._classifier_version = classifier_version
        self._model_identifier = model_identifier
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = client

    @property
    def backend_id(self) -> str:
        return self._backend_id

    @property
    def classifier_version(self) -> str:
        return self._classifier_version

    @property
    def model_identifier(self) -> str | None:
        return self._model_identifier

    @classmethod
    def get_task_schema(cls, task_type: ClassifierTaskType) -> dict[str, Any]:
        """Return the explicit JSON schema for a given ClassifierTaskType."""
        if task_type not in TASK_SCHEMAS:
            raise ValueError(f"No schema defined for task type: {task_type}")
        return TASK_SCHEMAS[task_type]

    def build_system_prompt(self, task: ClassifierTask) -> str:
        """Deterministic system prompt enforcing research boundary and objectivity."""
        return (
            f"You are an objective research semantic classifier for the Mneme Open Architecture Benchmark (Taxonomy {task.taxonomy_version}).\n"
            "Your sole function is to classify architectural decision evidence identified in open source repositories according to the research taxonomy.\n\n"
            "Core principles:\n"
            "- Classify the supplied repository evidence objectively based ONLY on what the document content and surrounding context state.\n"
            "- Do NOT decide what should be enforced or promote any candidate into project authority.\n"
            "- 'explicitly_accepted' means the source repository evidence indicates the project maintainers accepted this decision. It does NOT grant canonical Mneme authority.\n"
            "- Output MUST conform strictly to the requested JSON schema.\n"
            "- Do NOT include chain-of-thought, reasoning steps, or conversational commentary."
        )

    def build_user_prompt(self, task: ClassifierTask) -> str:
        """Deterministic user prompt binding task evidence."""
        return (
            f"Task: {task.task_type.value}\n"
            f"Repository: {task.repository_identifier} @ {task.repository_commit_sha}\n"
            f"Source file: {task.source_path} ({task.source_location})\n\n"
            f"Extracted statement:\n"
            f"\"\"\"\n{task.raw_statement}\n\"\"\"\n\n"
            f"Surrounding document context:\n"
            f"\"\"\"\n{task.source_context}\n\"\"\"\n\n"
            f"Classify this architectural evidence according to the schema for '{task.task_type.value}'."
        )

    def build_request_payload(self, task: ClassifierTask) -> dict[str, Any]:
        """Construct deterministic request payload for Anthropic Messages API."""
        schema = self.get_task_schema(task.task_type)
        return {
            "model": self._model_identifier,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "system": self.build_system_prompt(task),
            "messages": [
                {"role": "user", "content": self.build_user_prompt(task)},
            ],
            "extra_body": {
                "output_config": {
                    "format": {
                        "type": "json_schema",
                        "schema": schema,
                    }
                }
            },
        }

    def _get_client(self) -> Any:
        """Lazily initialize the Anthropic client on remote execution attempt."""
        if self._client is not None:
            return self._client

        try:
            import anthropic
        except ImportError as exc:
            raise AnthropicClassifierError(
                f"anthropic package is required for AnthropicClassifier: {exc}"
            ) from exc

        api_key = self._api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key or not api_key.strip():
            raise AnthropicAuthenticationError(
                "ANTHROPIC_API_KEY environment variable is not set and no api_key was provided"
            )

        self._client = anthropic.Anthropic(
            api_key=api_key.strip(),
            timeout=self._timeout,
            max_retries=self._max_retries,
        )
        return self._client

    def _extract_response_text(self, response: Any) -> str:
        """Extract text from Anthropic Message content blocks."""
        content = getattr(response, "content", None)
        if not content:
            raise AnthropicMalformedResponseError("Anthropic API returned empty or missing content")

        text_parts = []
        for block in content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
            elif isinstance(block, dict) and "text" in block:
                text_parts.append(block["text"])

        if not text_parts:
            raise AnthropicMalformedResponseError(
                f"Anthropic API returned content without text blocks: {content!r}"
            )

        return "".join(text_parts).strip()

    def execute(self, task: ClassifierTask) -> ClassifierResult:
        """Execute a single classifier task and return structured ClassifierResult."""
        client = self._get_client()
        payload = self.build_request_payload(task)

        start_time = time.perf_counter()
        try:
            response = client.messages.create(**payload)
        except Exception as exc:
            exc_name = type(exc).__name__
            if "Authentication" in exc_name or "Permission" in exc_name:
                raise AnthropicAuthenticationError(f"Anthropic authentication failed: {exc}") from exc
            if "RateLimit" in exc_name:
                raise AnthropicRateLimitError(f"Anthropic rate limit exceeded: {exc}") from exc
            if isinstance(exc, (AnthropicClassifierError, jsonschema.ValidationError)):
                raise
            raise AnthropicClassifierError(f"Anthropic API call failed ({exc_name}): {exc}") from exc

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        raw_text = self._extract_response_text(response)
        try:
            structured_output = json.loads(raw_text)
        except Exception as exc:
            raise AnthropicMalformedResponseError(
                f"Failed to parse Anthropic response as JSON: {exc}. Content: {raw_text[:200]!r}"
            ) from exc

        if not isinstance(structured_output, dict):
            raise AnthropicMalformedResponseError(
                f"Expected JSON object output, got {type(structured_output).__name__}"
            )

        schema = self.get_task_schema(task.task_type)
        try:
            jsonschema.validate(instance=structured_output, schema=schema)
        except jsonschema.ValidationError as exc:
            raise AnthropicMalformedResponseError(
                f"Anthropic response failed schema validation for {task.task_type.value}: {exc.message}"
            ) from exc

        # Preserve token usage in output metadata if available
        if hasattr(response, "usage") and response.usage is not None:
            usage = response.usage
            structured_output["_usage"] = {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            }

        return ClassifierResult(
            task_type=task.task_type,
            backend_id=self.backend_id,
            classifier_version=self.classifier_version,
            model_identifier=self.model_identifier,
            taxonomy_version=task.taxonomy_version,
            candidate_id=task.candidate_id,
            output=structured_output,
            confidence=None,  # Never fabricated
            latency_ms=latency_ms,
            cost_amount=None,
            cost_currency=None,
            escalated=False,
        )


__all__ = [
    "MIN_ANTHROPIC_SDK_VERSION",
    "AnthropicClassifierError",
    "AnthropicAuthenticationError",
    "AnthropicRateLimitError",
    "AnthropicMalformedResponseError",
    "TASK_SCHEMAS",
    "AnthropicClassifier",
]
