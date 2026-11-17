# T-08 G3 live batch: E4 OS capture around G3-1. Run in an ELEVATED PowerShell.
# Starts pktmon, waits until the G3-1 probe signals it is done, then stops the
# capture and converts it. The capture files stay on this machine
# (<CAPTURE>) and are private: a full-packet capture of the whole
# machine. Only the extracted host list is ever published.
$ErrorActionPreference = 'Stop'
$d = '<CAPTURE>'

# 1. Refuse stale state: any marker or capture file from an earlier attempt.
foreach ($f in 'g3-1.etl', 'g3-1.pcapng', 'g3-1.done', 'capture.started', 'capture.converted') {
  if (Test-Path (Join-Path $d $f)) { throw "Refusing to start: $d\$f already exists (stale state from an earlier attempt)" }
}
New-Item -ItemType Directory -Force $d | Out-Null

$started = $false
$stopCode = 0
try {
  # 3. Native exit codes are checked explicitly ($ErrorActionPreference does not cover them).
  pktmon start --capture --pkt-size 0 -f "$d\g3-1.etl"
  if ($LASTEXITCODE -ne 0) { throw "pktmon start failed (exit $LASTEXITCODE)" }
  $started = $true
  New-Item -ItemType File "$d\capture.started" | Out-Null
  Write-Host 'Capture running. Waiting for the G3-1 probe to finish (up to 30 minutes)...'
  $deadline = (Get-Date).AddMinutes(30)
  while (-not (Test-Path "$d\g3-1.done")) {
    if ((Get-Date) -gt $deadline) { throw 'G3-1 did not finish within 30 minutes' }
    Start-Sleep -Seconds 2
  }
}
finally {
  # 2. The capture is always stopped once it has started: on success, on any
  #    error, and on Ctrl-C.
  if ($started) {
    pktmon stop
    $stopCode = $LASTEXITCODE
    if ($stopCode -ne 0) { Write-Host "WARNING: pktmon stop failed (exit $stopCode). Run 'pktmon stop' manually." -ForegroundColor Red }
  }
}
if ($stopCode -ne 0) { throw "pktmon stop failed (exit $stopCode)" }

pktmon etl2pcap "$d\g3-1.etl" --out "$d\g3-1.pcapng"
if ($LASTEXITCODE -ne 0) { throw "pktmon etl2pcap failed (exit $LASTEXITCODE)" }
if (-not (Test-Path "$d\g3-1.pcapng") -or (Get-Item "$d\g3-1.pcapng").Length -eq 0) { throw "conversion produced no $d\g3-1.pcapng" }
New-Item -ItemType File "$d\capture.converted" | Out-Null
Write-Host 'Capture stopped and converted. You can close this window.'
