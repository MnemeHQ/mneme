"""Idempotent, project-scoped installer for the Mneme Kiro hook.

Writes (or upserts) ``.kiro/hooks/mneme.json`` under the target project
root. Kiro activates hook files in that directory automatically at session
start; project scope is the default because Mneme Layer 1 is project-scoped.
No global installation is provided.

Behavior:

- Fresh install: creates ``.kiro/hooks/mneme.json`` with the single
  ``mneme-governance-gate`` hook definition from
  ``integrations/kiro/hooks/mneme.json``.
- Existing file that parses as a v1 hooks file: preserves every foreign
  hook entry and upserts only the ``mneme-governance-gate`` entry.
- Existing file that is not valid JSON or not a v1 hooks object: aborts
  without writing. An unrelated Kiro hooks file is never clobbered.
- Re-running produces a byte-identical file (idempotent).

Usage::

    python scripts/install_kiro.py [PROJECT_DIR]
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HOOK_NAME = "mneme-governance-gate"

_TEMPLATE = Path(__file__).resolve().parent.parent / "integrations" / "kiro" / "hooks" / "mneme.json"


def load_template() -> dict:
    with _TEMPLATE.open(encoding="utf-8") as fh:
        template = json.load(fh)
    if template.get("version") != "v1" or not isinstance(template.get("hooks"), list) \
            or len(template["hooks"]) != 1:
        raise ValueError("mneme.json template is not a single-hook v1 file")
    return template


def _is_v1_hooks_file(payload: object) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("version") == "v1"
        and isinstance(payload.get("hooks"), list)
    )


def compute_target(existing: dict | None) -> dict:
    """Return the file content to write given an existing parsed file."""
    template = load_template()
    ours = template["hooks"][0]
    if existing is None:
        return {"version": "v1", "hooks": [ours]}
    hooks = [h for h in existing["hooks"] if not (isinstance(h, dict) and h.get("name") == HOOK_NAME)]
    hooks.append(ours)
    return {"version": "v1", "hooks": hooks}


def install(project_dir: Path) -> Path:
    """Install or update ``<project>/.kiro/hooks/mneme.json``; returns its path."""
    hooks_dir = project_dir / ".kiro" / "hooks"
    target = hooks_dir / "mneme.json"

    existing = None
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeError) as e:
            raise SystemExit(
                f"refusing to touch {target}: it is not valid UTF-8 JSON ({e}). "
                "Resolve it manually before installing."
            )
        if not _is_v1_hooks_file(existing):
            raise SystemExit(
                f"refusing to touch {target}: it exists but is not a "
                '{"version": "v1", "hooks": [...]} file. Resolve it manually '
                "before installing."
            )

    content = compute_target(existing)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(content, indent=2, ensure_ascii=True) + "\n"
    if target.exists() and target.read_text(encoding="utf-8") == rendered:
        print(f"mneme-kiro-hook already installed at {target} (no change)")
    else:
        target.write_text(rendered, encoding="utf-8")
        print(f"installed mneme-kiro-hook at {target}")

    if shutil.which("mneme-kiro-hook") is None:
        print(
            "warning: 'mneme-kiro-hook' was not found on PATH. Install the "
            "package first (e.g. pipx install mneme-hq), otherwise the hook "
            "will fail open on every event."
        )
    return target


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    project_dir = Path(argv[0]).resolve() if argv else Path.cwd()
    if not project_dir.is_dir():
        print(f"project directory does not exist: {project_dir}", file=sys.stderr)
        return 1
    install(project_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
