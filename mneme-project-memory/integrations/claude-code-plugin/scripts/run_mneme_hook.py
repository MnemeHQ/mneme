#!/usr/bin/env python3
"""Cross-platform launcher for the Mneme PreToolUse hook.

This wrapper is what the plugin's ``hooks.json`` invokes. Its only job is to
locate the ``mneme-hook`` console script (installed with the ``mneme-hq``
package) and delegate to it, while keeping a friendly, fail-open experience
when Mneme is not installed.

Why a wrapper instead of calling ``mneme-hook`` directly:

* **One place for the "not installed" message.** Without this, a missing
  ``mneme-hook`` surfaces as Claude Code's generic "command not found" error
  with no guidance. Here we print an actionable install command instead.
* **Consistent mode selection.** The plugin's ``mode`` user-config value is
  exported by Claude Code as ``CLAUDE_PLUGIN_OPTION_MODE``; we translate it
  into the ``MNEME_HOOK_MODE`` env var that ``mneme-hook`` understands.
* **Fail-open guarantee is preserved.** If Mneme is absent we exit 0 so edits
  are never blocked; only a real verdict from ``mneme check`` (propagated as
  exit code 2 by ``mneme-hook``) blocks an edit.

Deliberately *not* bundled/self-installing yet — the dependency stays explicit
for this release. A later marketplace-readiness change can add a self-contained
runtime. This wrapper needs only the Python standard library.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

INSTALL_HINT = 'pipx install "mneme-hq>=0.4.2"'


def resolve_mode() -> str:
    """Map the plugin's user-config value onto MNEME_HOOK_MODE."""
    mode = os.environ.get("CLAUDE_PLUGIN_OPTION_MODE", "strict").strip().lower()
    return mode if mode in ("strict", "warn") else "strict"


def main() -> int:
    exe = shutil.which("mneme-hook")
    if exe is None:
        print(
            "mneme (Claude Code plugin): mneme-hook not found on PATH, so "
            "architectural governance is inactive. Install Mneme to enable it:\n"
            f"    {INSTALL_HINT}",
            file=sys.stderr,
        )
        # Fail open: never block an edit just because Mneme is not installed.
        return 0

    env = dict(os.environ)
    env["MNEME_HOOK_MODE"] = resolve_mode()

    # Delegate to the real hook. stdin (the tool-event JSON), stdout, and
    # stderr are inherited untouched, and we propagate its exact exit code
    # (2 == block the edit, 0 == allow).
    try:
        completed = subprocess.run([exe], env=env)
    except OSError as exc:  # pragma: no cover - defensive, fail open
        print(f"mneme (Claude Code plugin): could not run mneme-hook ({exc}).", file=sys.stderr)
        return 0
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
