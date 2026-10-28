# ADR-034 G2-1 R3: preliminary owner key-custody boundary verification

**Date:** 2026-10-28
**Status:** ACCOUNT-LEVEL CHECKS OBSERVED; R3 §9.5 GATE NOT YET CLOSED

**Scope.** This is a metadata-only record of owner-reported synthetic checks after
the R2 custody finding (#693 §9.5). It contains no concealed case bytes,
labels, passphrases, secret key exports, private machine paths or key material.
The checks were executed interactively by the owner and relayed in the owner's
working session; they were not independently witnessed by a separate security
reviewer or rerun by this record's author.

## 1. Reported account and key separation

- The owner created a separate Standard Windows account for the private key
  (`MnemeOwner`) and a different Standard account for validation agents
  (`MnemeAgent`). The existing development account (`hi`) remains an
  administrator; R3 must not execute its agents under that account.
- The owner imported the secret key into `MnemeOwner` and successfully
  encrypted and decrypted synthetic text there.
- The owner removed the secret key from the `hi` GPG keyring and removed
  temporary unencrypted exports and the transfer archive from the `hi`
  transfer folder, based on subsequent owner-reported checks.
- An encrypted backup was retained in owner-controlled storage.
- `MnemeAgent` imported only the public key. Its `gpg --list-secret-keys`
  returned no keys.
- The agent account's attempt to read the owner's GPG private-key directory
  returned `Access is denied`.
- Under `MnemeAgent`, the owner successfully encrypted a synthetic text to
  the owner encryption subkey; `gpg --batch --no-tty --decrypt` on the resulting
  ciphertext returned `No secret key`.

These observations establish the reported interactive account-level boundary
for that test. They do not establish forensic erasure, absence of all external
backups, or an agent-host security guarantee.

## 2. Remaining §9.5 gate

Before **any R3 corpus is sealed**, independently verify that the **actual
sealing and scoring agent sessions**, on their designated machines and
under their effective Windows identities, cannot decrypt owner-key
ciphertexts. At a minimum the verification must:

1. Record the effective user and elevation level of each actual agent process;
   require execution under the dedicated Standard account, with no inherited
   owner credentials, private GPG home, secret-key files or elevated path.
2. Under that same agent execution context, test public-key encryption and
   attempted decryption using **only disposable synthetic material**, recording
   return status and redacted diagnostic (no private evidence content).
3. Confirm that owner-controlled decryption works outside the agent context,
   that the agent cannot access the owner's private GPG directory, and that
   the working directories and reachable transfer locations contain no
   accessible secret-key exports or owner backup credentials.
4. Record execution environment, test evidence, verification actor,
   isolation limitations, and the owner's explicit gate decision **before
   corpus sealing**.

A failure, unverified execution context or available elevation path blocks
sealing. This record alone does **not** close #693 §9.5.

## 3. R3 sequencing and unchanged validation contract

- D3 implementation PR #697 is merged at `1b0957af`. The future R3
  pre-registration must pin the exact implementation and its build artifacts.
- A new independent corpus author, independent scorer and independent
  pre-registered scoring harness are required.
- The scorer must independently treat missing, empty, or non-string
  `rule_id` as **unattributed**, even when `rule_type` is recognizable;
  the hook's regression tests are not a substitute.
- No reuse of R1 or R2 held-out content, retrospective scoring, corpus
  generation, R3 execution, production claim or PASS is authorized here.
- R1 and R2 remain **FAIL**. G2-1 remains **FAIL** until R3 passes its
  frozen protocol.

## 4. Information handling

This public document intentionally omits owner-private findings, Windows
user-specific paths, secret material and concealed validation content.
Do not attach raw outputs that reveal secrets or sealed corpus data.
