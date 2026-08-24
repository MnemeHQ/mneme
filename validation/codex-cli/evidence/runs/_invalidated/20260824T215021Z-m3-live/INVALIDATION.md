Classification: harness-preflight failure. subprocess stdout reader thread
crashed decoding non-ASCII Codex output under the default cp1252 codec, so
transcripts/stop-block detection lost their data (blocks=0 across all
cases). No capability conclusion. Fix: encoding="utf-8", errors="replace"
on the runner subprocess call.
