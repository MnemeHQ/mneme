## ADR-033 C4 trusted gate

- Result: **REFUSED** (failure)
- Availability: `open`; violation mode: `strict`
- Base `9137c93b66c2b8534f2222f125378b6761f6aae3` / head `fbcf70e35d664482e1e8a8743cc3cfc1b91c1aa1`
- Reason: gate/c4-l4-note.txt: trusted surface: PR changes never reach the gate's own inputs

| Path | Result | Reason |
|---|---|---|
| `gate/c4-l4-note.txt` | REFUSED | trusted surface: PR changes never reach the gate's own inputs |
