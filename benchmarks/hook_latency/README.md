# Hook PreToolUse latency benchmark

Measures how long `mneme-hook` takes to answer one PreToolUse event, end to end, the way Claude Code runs it: a fresh process per event, with the envelope on stdin. Tracking issue: MnemeHQ/mneme-growth-ops#60.

## Cells

| Cell | What runs |
|---|---|
| `edit_allowed/subprocess`, `edit_blocked/subprocess` | Today's hook: the hook process starts a second interpreter for `mneme check` |
| `edit_allowed/inprocess`, `edit_blocked/inprocess` | `MNEME_HOOK_CHECK_TRANSPORT=inprocess`: the same check, run inside the hook's interpreter (benchmark-only) |
| `baseline/python_pass` | `python -c pass`: bare interpreter startup |
| `baseline/import_hook` | `python -c "import mneme.integrations.claude_code.hook"`: startup plus hook import |

Every run's exit code is checked: 0 for allowed, 2 for blocked. If any run gives the wrong verdict, the harness exits 1 and writes nothing.

## Run

Editable install (measures this checkout):

```bash
pip install -e .
python benchmarks/hook_latency/run.py --python python --runs 50 --warmup 5 \
  --out benchmarks/hook_latency/results/<date>-<os>-editable.json
```

Wheel install (measures a normal install, ignoring this checkout):

```bash
python -m build
python -m venv .bench-wheel
.bench-wheel/Scripts/pip install dist/*.whl        # Linux/macOS: .bench-wheel/bin/pip
python benchmarks/hook_latency/run.py --python .bench-wheel/Scripts/python --pythonpath "" \
  --runs 50 --warmup 5 --out benchmarks/hook_latency/results/<date>-<os>-wheel.json
```

`--pythonpath` defaults to this checkout, so editable runs measure the branch under test even when another checkout is installed. Pass `""` for wheel runs. Check `mneme_file` in the output JSON to confirm which install was measured.

## Read the output

The JSON holds environment details (`python_version`, `platform`, `mneme_file`, `git_sha`), the settings, and for each cell a summary (`n`, `p50`, `p95`, `max`, `mean`, in ms) plus the raw samples. Stdout gets a markdown table, including the in-process minus subprocess delta for each scenario.

Attribution, using p50:

- (a) `python_pass`
- (b) `import_hook` - (a)
- (c) `edit_*/subprocess` - `import_hook`
- (d) `edit_*/inprocess` - `import_hook`

(c) - (d) approximates the cost of the second interpreter.
