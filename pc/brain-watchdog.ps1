# ASIGINT 두뇌 워치독 — PC의 ollama(11434)와 게이트(11435)가 죽으면 되살린다.
# 'ATANOR Brain Watchdog' 예약 작업이 2분마다 실행한다. 두뇌 끊김을 자동 복구.
$ErrorActionPreference = 'SilentlyContinue'

# 1) ollama (두뇌 본체, 11434)
$ollamaUp = $false
try { Invoke-RestMethod "http://127.0.0.1:11434/api/version" -TimeoutSec 4 | Out-Null; $ollamaUp = $true } catch { }
if (-not $ollamaUp) {
    $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    if (-not (Test-Path $ollama)) { $c = Get-Command ollama -ErrorAction SilentlyContinue; if ($c) { $ollama = $c.Source } }
    if (Test-Path $ollama) {
        Start-Process -WindowStyle Hidden -FilePath $ollama -ArgumentList "serve"
        "$(Get-Date -Format s)  ollama restarted" | Out-File -Append "$env:LOCALAPPDATA\atanor-tunnel\watchdog.log"
        Start-Sleep -Seconds 5
    }
}

# 2) 게이트 (11435, 노트북이 두뇌에 닿는 관문)
$gateUp = (Get-NetTCPConnection -LocalPort 11435 -State Listen -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0
if (-not $gateUp) {
    $pyw  = "C:\ProgramData\miniconda3\pythonw.exe"
    $gate = "D:\ATANOR-assistant\pc\ollama_gate.py"
    $log  = "$env:LOCALAPPDATA\atanor-tunnel\gate.log"
    if ((Test-Path $pyw) -and (Test-Path $gate)) {
        Start-Process -WindowStyle Hidden -FilePath $pyw -ArgumentList $gate, $log
        "$(Get-Date -Format s)  gate restarted" | Out-File -Append "$env:LOCALAPPDATA\atanor-tunnel\watchdog.log"
    }
}
