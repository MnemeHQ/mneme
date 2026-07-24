# Security Policy

## Supported Versions

Currently, the `0.5.x` series is supported with security updates.

| Version | Supported          |
| ------- | ------------------ |
| 0.5.x   | :white_check_mark: |
| < 0.5.0 | :x:                |

## Reporting a Vulnerability

Please do **not** report security vulnerabilities through public GitHub issues, discussions, or social media.

Instead, report them privately via GitHub's **Private Vulnerability Reporting**:
1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.

We consider the following to be security issues:
- Path traversal in the CLI or hook loader.
- Unauthorized execution of arbitrary commands.
- Silent failure modes in enforcement hooks that cause the system to fail open without warning in `strict` mode (bypassing governance).

We will try to acknowledge your report within 48 hours and will provide updates as the issue is investigated and patched.
