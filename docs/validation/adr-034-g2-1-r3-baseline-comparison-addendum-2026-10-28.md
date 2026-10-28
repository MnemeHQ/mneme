# ADR-034 G2-1 R3: scorer B baseline wheel comparison addendum

**Status:** Evidence transcription, scorer B observed / read-only reviewer assessed. **Not an independent Windows execution. Not a completion or unblind authorization.**  
**Source:** User-supplied pasted transcript of scorer B's `evidence-707-scorer-b-addendum-1-baseline-2026-10-28.md`, including the text of `compare_baseline_wheels.py`. Scorer B reports the **original separate Windows addendum** was 5,982 bytes, SHA-256 `4fe39830f67d13a15845c4b7705a6bb4fcefd87bfdd293c5968c1823285f4718`. **This GitHub document is a normalized transcription, not those original bytes; its SHA is not claimed to equal that checksum.**  
**Scorer identity:** Claude Code scorer B session `3121484e-a5ab-4aad-85ae-ccca9d92a8a1`; `arxwn\mnemeagent`; 2026-10-28.  
**Scope:** Only historical R2 baseline wheel and scorer B's newly built R3 baseline wheel, under a narrow owner authorization. G2-1 **FAIL**; R3 **SEALED**.

## Custody and reference

The owner allowed scorer B **read-only access solely to** the historical R2 baseline wheel or its wheel `RECORD`, not earlier corpora, results, labels, harnesses or other artifacts. The first listing of `C:/dev/g2-1-r2-scoring/build/dist-baseline/` was denied by Windows ACLs; scorer B stopped without bypass. The owner copied exactly the authorized wheel into a neutral handoff location. Scorer B reports opening the staged wheel and its own R3 wheel read-only without modifying either or inspecting unrelated historical material.

| Reference | Observed identity / integrity |
|---|---|
| Historical R2 baseline wheel | `C:\dev\mneme-r3-baseline-handoff\mneme_hq-0.10.0-py3-none-any.whl` |
| R2 wheel size / SHA-256 | 541,776 bytes / `3497b5dd83942ef5df06fe522acaaa7e6e2833759dfdd25daa8866f65dacd1b2` |
| Scorer B R3 baseline wheel | `C:\Users\MnemeAgent\r3-work\r3-scorer-workspace\build\dist-f8591102b2693379dabec9b5704862e194eca4ce\mneme_hq-0.10.0-py3-none-any.whl` |
| R3 wheel size / SHA-256 | 545,569 bytes / `b24a2f8328855d2e41e6ae43eb16c7ae488afcc5944713e66300bc061f132421` |
| Accepted parity source commit | `f8591102b2693379dabec9b5704862e194eca4ce` |
| Accepted `mneme/` Git tree | `002fdddb254267d42a3810cfea669d75700372f2` |

## Comparison method and results (VERIFIED by scorer B; reviewed remotely, not reproduced locally)

Scorer B reports running this command from its isolated test Python (3.12.10):

```text
env\test\Scripts\python.exe -I compare_baseline_wheels.py <R2 staged wheel> <R3 scorer-built wheel> <mneme-public clone>
```

The provided script checks both complete wheel SHA-256 values; reads the pinned baseline Git tree and 111 source blobs; compares every common `mneme/` file as byte-identical, newline-only or substantive; inventories non-source ZIP metadata and `RECORD` row differences; and reports ZIP order/timestamps. It reads the wheel files read-only, performs `git cat-file` / `git ls-tree`, and makes no installation or modification.

| Payload comparison | Scorer B result |
|---|---|
| `mneme/` package file sets | Same 111 Python files, no extra/missing |
| Raw byte matches between wheel payloads | **4**, all no-linebreak `__init__.py` |
| CRLF/LF-only source differences | **107**; historical R2 LF, scorer R3 CRLF |
| Substantive source differences | **0** |
| Historical R2 payload versus accepted source tree | **111/111 raw exact** |
| R2 payload-manifest SHA-256 | `6b4e51987e3572896053d754e7f228d59f3cc90d3489807e356b142b34026d9a` |
| R3 payload-manifest SHA-256 | `e4848c41d08d1624cf50ce23572bf10cb24082ac143d04d08d540771fd32fcf2`; also scorer B's installed `env/base` manifest |

The four identical files are `mneme/integrations/__init__.py`, `mneme/integrations/antigravity/__init__.py`, `mneme/integrations/claude_code/__init__.py`, and `mneme/integrations/codex_cli/__init__.py`.

| Wheel metadata | Scorer B result |
|---|---|
| `METADATA`, `WHEEL`, `entry_points.txt`, `top_level.txt` | Byte-identical |
| `licenses/LICENSE` | CRLF/LF-only |
| `RECORD` | 108 changed rows: 107 Python files plus LICENSE |
| ZIP entries and order | Identical |
| ZIP entry timestamps | Historical R2 normalized to `2026-10-25 00:00:00`; scorer R3 real times `2026-10-25 01:46:28` through `2026-10-28 15:17:14` |

Wheel SHA difference is explained by source-newline bytes and packaging metadata. **This is source-content equivalence, not byte-identical wheel reproduction.** The comparison does not itself establish all runtime behavior or waive G5's byte-level stdout/stderr/exit parity. The R3 §6.1 contract requires an independently pinned R3 build/environment from the same accepted source, **not** the old R2 wheel's archive hash.

**Review decision:** On this evidence, **retain scorer B's existing R3 baseline candidate**. No replacement wheel or fresh environment is required merely to reproduce the historical wheel byte-for-byte. **Independent final Windows baseline-environment, installed `RECORD`, freeze, and custody attestations are separate gates and are not closed by this decision.** Owner's final pre-scoring completion authorization is still OPEN.

## Reproduction script as supplied in the pasted transcript

The following is the scorer-provided script transcribed from the chat paste, with indentation normalized for Markdown. It is supplied for inspection, **not** evidence that this reviewer executed it on the two wheels. The full original script bytes and output log have not been independently hashed.

```python
"""Scorer B: read-only payload comparison of the staged R2 baseline wheel vs the R3 baseline wheel.

Usage: python -I compare_baseline_wheels.py <r2_wheel> <r3_wheel> <git_clone>
Opens both wheels read-only as zip archives. Stops if either digest differs
from the authorized value. Compares every mneme/ payload file, also against
the accepted git tree 002fdddb (f8591102:mneme), then the .dist-info metadata.
"""
import difflib
import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

R2_SHA = "3497b5dd83942ef5df06fe522acaaa7e6e2833759dfdd25daa8866f65dacd1b2"
R3_SHA = "b24a2f8328855d2e41e6ae43eb16c7ae488afcc5944713e66300bc061f132421"
COMMIT, TREE = "f8591102b2693379dabec9b5704862e194eca4ce", "002fdddb254267d42a3810cfea669d75700372f2"
r2_path, r3_path, clone = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sha = lambda b: hashlib.sha256(b).hexdigest()

for label, path, want in (("R2 historical", r2_path, R2_SHA), ("R3 baseline", r3_path, R3_SHA)):
    got = sha(path.read_bytes())
    print(f"{label}: {path} size={path.stat().st_size} sha256={got} expected_match={got == want}")
    if got != want:
        sys.exit(f"STOP: {label} digest mismatch")

tree = subprocess.run(["git", "-C", str(clone), "rev-parse", f"{COMMIT}:mneme"],
                      capture_output=True, check=True).stdout.decode().strip()
print(f"git {COMMIT}:mneme tree = {tree} (accepted {TREE}): {tree == TREE}")
git_files = subprocess.run(["git", "-C", str(clone), "ls-tree", "-r", "--name-only", COMMIT, "mneme/"],
                           capture_output=True, check=True).stdout.decode().split()

with zipfile.ZipFile(r2_path) as z2, zipfile.ZipFile(r3_path) as z3:
    n2, n3 = set(z2.namelist()), set(z3.namelist())
    p2 = sorted(n for n in n2 if n.startswith("mneme/") and not n.endswith("/"))
    p3 = sorted(n for n in n3 if n.startswith("mneme/") and not n.endswith("/"))
    print(f"\nmneme/ payload files: R2 {len(p2)}, R3 {len(p3)}, git tree {len(git_files)}")
    print("only in R2:", sorted(set(p2) - set(p3)) or "none", "| only in R3:", sorted(set(p3) - set(p2)) or "none",
          "| R2 vs git set equal:", set(p2) == set(git_files))
    exact, eol, subst = [], [], []
    vs_git = {"exact": 0, "eol_only": 0, "substantive": []}
    for name in sorted(set(p2) & set(p3)):
        a, b = z2.read(name), z3.read(name)
        if a == b:
            exact.append(name)
        elif a.replace(b"\r\n", b"\n") == b.replace(b"\r\n", b"\n"):
            eol.append((name, b"\r\n" in a, b"\r\n" in b))
        else:
            subst.append(name)
        if name in git_files:
            g = subprocess.run(["git", "-C", str(clone), "cat-file", "blob", f"{COMMIT}:{name}"],
                               capture_output=True, check=True).stdout
            if a == g:
                vs_git["exact"] += 1
            elif a.replace(b"\r\n", b"\n") == g:
                vs_git["eol_only"] += 1
            else:
                vs_git["substantive"].append(name)
    print(f"\n1. exact byte matches R2 vs R3: {len(exact)}")
    print(f"2. CRLF/LF-only differences R2 vs R3: {len(eol)}"
          + (f" (examples: {[(n, 'R2 crlf' if c2 else 'R2 lf', 'R3 crlf' if c3 else 'R3 lf') for n, c2, c3 in eol[:3]]})" if eol else
             ""))
    print(f"3. substantive differences R2 vs R3: {len(subst)} {subst[:10]}")
    crlf2 = sum(b"\r\n" in z2.read(n) for n in p2)
    crlf3 = sum(b"\r\n" in z3.read(n) for n in p3)
    print(f"   files containing CRLF: R2 {crlf2}, R3 {crlf3}")
    print(f"   R2 payload vs accepted git tree: exact {vs_git['exact']}, CRLF->LF-only {vs_git['eol_only']}, "
          f"substantive {len(vs_git['substantive'])} {vs_git['substantive'][:5]}")
    m2 = "".join(f"{sha(z2.read(n))}  {n}\n" for n in p2)
    m3 = "".join(f"{sha(z3.read(n))}  {n}\n" for n in p3)
    print(f"   payload manifest sha256 (sorted '<sha256>  <path>\\n'): R2 {sha(m2.encode())} | R3 {sha(m3.encode())}")

    print("\n4. wheel metadata (.dist-info and other non-mneme entries)")
    meta2 = sorted(n for n in n2 if not n.startswith("mneme/"))
    meta3 = sorted(n for n in n3 if not n.startswith("mneme/"))
    print("   entries R2:", meta2)
    print("   entries R3:", meta3)
    for name in sorted(set(meta2) | set(meta3)):
        if name not in n2 or name not in n3:
            print(f"   {name}: present only in {'R2' if name in n2 else 'R3'}")
            continue
        a, b = z2.read(name), z3.read(name)
        if a == b:
            print(f"   {name}: identical")
            continue
        if name.endswith("/RECORD"):
            ra = {l.split(",")[0]: l for l in a.decode().splitlines()}
            rb = {l.split(",")[0]: l for l in b.decode().splitlines()}
            diff_rows = sorted(k for k in set(ra) | set(rb) if ra.get(k) != rb.get(k))
            print(f"   {name}: differs in {len(diff_rows)} rows: {diff_rows[:6]}")
            continue
        lines = [l for l in difflib.unified_diff(a.decode("utf-8", "replace").splitlines(),
                                                  b.decode("utf-8", "replace").splitlines(),
                                                  "R2", "R3", n=0, lineterm="") if not l.startswith(("---", "+++", "@@"))]
        print(f"   {name}: differs ({len(lines)} changed lines; EOL-only: {a.replace(b'\r\n', b'\n') == b.replace(b'\r\n', b'\n')})")
        for l in lines[:8]:
            print("      ", l[:150])
    zi2, zi3 = {i.filename: i for i in z2.infolist()}, {i.filename: i for i in z3.infolist()}
    dt = sorted({zi2[n].date_time for n in zi2}), sorted({zi3[n].date_time for n in zi3})
    print(f"   zip entry timestamps: R2 {dt[0][:1]}..{dt[0][-1:]} | R3 {dt[1][:1]}..{dt[1][-1:]}")
    print(f"   zip entry order identical: {[i.filename for i in z2.infolist()] == [i.filename for i in z3.infolist()]}")

```

## Remaining pre-scoring gates

Owner/independent verification of final baseline installed environment, Claude Code 2.1.312 §6.1 live-host characterization, scoring host and exact run root/command, final symlink and LF checks, custody independence, explicit structural-review acceptance, a separately completed/merged metadata-only record and a **later separate owner unblind GO** all remain OPEN. No G1–G8 run or concealed input access occurred by constructing this transcription.
