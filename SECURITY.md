# Security Policy

## Supported Versions

The following version is currently committed to security support:

| Version | Supported          |
| ------- | ------------------ |
| 0.5.0   | :white_check_mark: |
| < 0.5.0 | :x:                |

## Reporting a Vulnerability

Please do **not** report security vulnerabilities through public GitHub issues, discussions, or social media.

Report vulnerabilities privately through GitHub's **Private Vulnerability Reporting**, which is enabled on this repository:
1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.

We consider the following to be security issues:
- Path traversal in the CLI or hook loader.
- Unauthorized execution of arbitrary commands.
- Silent failure modes in enforcement hooks that cause the system to fail open without warning in `strict` mode (bypassing governance).
