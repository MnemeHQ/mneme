"""Mneme governance plugin for the Hermes Agent (POC).

Requires the ``mneme`` package to be importable from Hermes' Python
environment. All behavior lives in ``mneme.integrations.hermes.plugin``
and ``mneme.integrations.hermes.adapter``; this file only forwards the
plugin registration so the governed project can pin adapter behavior by
pinning its mneme version.

See docs/integrations/hermes.md in the Mneme repository for install,
enforcement boundary, and the H3 bypass coverage matrix.
"""

from mneme.integrations.hermes.plugin import register

__all__ = ["register"]
