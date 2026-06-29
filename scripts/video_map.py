"""slug -> (video_id, is_core). Core pages already carry VideoObject schema."""

VIDEO_MAP = {
    # --- Core: already have VideoObject schema, need facade only ---
    "concepts/architectural-compiler": ("jNXDtxu0_-s", True),
    "concepts/architectural-drift": ("hP8jMyVA6D4", True),
    "concepts/governance-before-generation": ("tO_Z9rqXXfQ", True),
    "concepts/precedence-semantics": ("tktp6ik0Gxk", True),
    "insights/ai-native-engineering-intent-debt": ("nwSBZXolBhA", True),
    "insights/architectural-governance-across-heterogeneous-ai-coding-agents": ("xtTDcb2JB2c", True),
    "insights/autonomous-code-remediation-requires-architectural-governance": ("DDo0x1lkBNI", True),
    "insights/github-copilot-space-framework": ("Rjlzm0psfB4", True),
    "insights/harness-engineering-still-needs-governance": ("kHDZshGw7M8", True),
    "insights/memory-is-not-governance": ("EDBVYFtkOb4", True),
    "insights/prompt-engineering-is-not-governance": ("kIswxPe7bGc", True),
    "insights/why-claude-md-stops-scaling": ("5QxAbdLg0nw", True),
    "insights/why-code-review-cannot-scale-with-ai-output": ("8sklibjfO6A", True),
    "insights/why-observability-is-not-governance": ("yAwz5SISip8", True),
    "insights/why-rag-fails-for-architectural-governance": ("0kC4OEG-yig", True),
    # --- Extension: confirmed title match, need schema + facade ---
    "insights/rag-is-not-memory": ("4EbbZojgWKs", False),
    "insights/spec-driven-development-still-needs-governance": ("pcL4fD5MyC8", False),
    "insights/why-context-alone-doesnt-prevent-architectural-drift": ("fseagcnHzhU", False),
    "concepts/model-independent-governance": ("W4MG-SQY20o", False),
    "concepts/deterministic-enforcement": ("k5lpI83ONnI", False),
}

# Real YouTube metadata for the 5 extension videos (confirmed 1:1 title matches
# via the mneme-youtube MCP youtube_get_video / youtube_list_videos on 2026-06-29).
# `description` is the real first ~200 chars of the channel description.
# `duration` is omitted: the youtube_get_video MCP does not expose contentDetails
# duration, and the plan forbids fabricating metadata. A VideoObject is valid
# without `duration`; process_page emits it only when present and truthy.
EXTENSION_META = {
    "4EbbZojgWKs": {
        "name": "RAG Is Not Memory | Architectural Governance for AI Coding Teams — Mneme HQ",
        "description": (
            "👉 Try Mneme HQ — architectural governance for AI coding: "
            "https://mnemehq.com/?utm_source=youtube&utm_medium=video&utm_campaign=mneme_youtube&utm_content=rag_is_not_memory\n"
            "Mneme HQ turns architectural decisions into enforceable rules for AI coding agents."
        ),
        "uploadDate": "2026-06-23T17:37:02Z",
        "duration": "",
    },
    "pcL4fD5MyC8": {
        "name": "Spec-Driven Development Still Needs Governance | Architectural Governance for AI Coding Teams — Mneme HQ",
        "description": (
            "👉 Try Mneme HQ — architectural governance for AI coding: "
            "https://mnemehq.com/?utm_source=youtube&utm_medium=video&utm_campaign=mneme_youtube&utm_content=spec_driven_development_governance\n"
            "Mneme HQ turns architectural decisions into enforceable rules for AI coding agents."
        ),
        "uploadDate": "2026-06-23T17:36:34Z",
        "duration": "",
    },
    "fseagcnHzhU": {
        "name": "Why Context Alone Doesn't Prevent Architectural Drift | Architectural Governance for AI Coding Teams — Mneme HQ",
        "description": (
            "👉 Try Mneme HQ — architectural governance for AI coding: "
            "https://mnemehq.com/?utm_source=youtube&utm_medium=video&utm_campaign=mneme_youtube&utm_content=context_alone_doesnt_prevent_drift\n"
            "Mneme HQ turns architectural decisions into enforceable rules for AI coding agents."
        ),
        "uploadDate": "2026-06-23T17:38:08Z",
        "duration": "",
    },
    "W4MG-SQY20o": {
        "name": "Model-Independent Governance: Why Your Architecture Outlives the Model | Architectural Governance for AI Coding Teams — Mneme HQ",
        "description": (
            "👉 Try Mneme HQ — architectural governance for AI coding: "
            "https://mnemehq.com/?utm_source=youtube&utm_medium=video&utm_campaign=mneme_youtube&utm_content=model_independent_governance\n"
            "Mneme HQ turns architectural decisions into enforceable rules for AI coding agents."
        ),
        "uploadDate": "2026-06-23T17:35:14Z",
        "duration": "",
    },
    "k5lpI83ONnI": {
        "name": "What Is Deterministic Enforcement? | Architectural Governance for AI Coding Teams — Mneme HQ",
        "description": (
            "👉 Try Mneme HQ — architectural governance for AI coding: "
            "https://mnemehq.com/?utm_source=youtube&utm_medium=video&utm_campaign=mneme_youtube&utm_content=deterministic_enforcement\n"
            "Mneme HQ turns architectural decisions into enforceable rules for AI coding agents."
        ),
        "uploadDate": "2026-06-23T17:20:49Z",
        "duration": "",
    },
}
