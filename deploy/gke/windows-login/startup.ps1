# Prepare a real Windows desktop for interactive LinkedIn login.
# Windows containers do not support RDP/GUI, so this runs on a GCE VM that
# shares the GKE Cloud NAT egress IP.

$ErrorActionPreference = "Stop"
$root = "C:\jobsrss"
$log = "$root\startup.log"
New-Item -ItemType Directory -Force -Path $root | Out-Null
Start-Transcript -Path $log -Append

function Get-Meta([string]$name) {
    Invoke-RestMethod -Headers @{ "Metadata-Flavor" = "Google" } `
        -Uri "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$name"
}

if (-not (Test-Path "$root\.python-ready")) {
    Write-Output "Installing Python"
    $py = "$env:TEMP\python-installer.exe"
    Invoke-WebRequest -UseBasicParsing `
        -Uri "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe" -OutFile $py
    Start-Process -Wait -FilePath $py -ArgumentList @(
        "/quiet", "InstallAllUsers=1", "PrependPath=1", "Include_test=0"
    )
    New-Item -ItemType File -Force -Path "$root\.python-ready" | Out-Null
}

$env:Path = "C:\Program Files\Python312;C:\Program Files\Python312\Scripts;$env:Path"

if (-not (Test-Path "$root\.playwright-ready")) {
    Write-Output "Installing Playwright + Chromium"
    python -m pip install --upgrade pip
    python -m pip install playwright
    python -m playwright install chromium
    New-Item -ItemType File -Force -Path "$root\.playwright-ready" | Out-Null
}

Write-Output "Writing session.py"
Get-Meta "jobsrss-session-py" | Set-Content -Encoding UTF8 -Path "$root\session.py"

$desktop = "C:\Users\Public\Desktop"

@"
@echo off
set JOBSRSS_SESSION_DIR=C:\jobsrss
set PATH=C:\Program Files\Python312;C:\Program Files\Python312\Scripts;%PATH%
echo A Chromium window will open. Log into LinkedIn until your feed loads.
echo Leave this black window open.
python C:\jobsrss\session.py
pause
"@ | Set-Content -Encoding ASCII -Path "$desktop\1-start-linkedin-login.bat"

@"
@echo off
set PATH=C:\Program Files\Python312;C:\Program Files\Python312\Scripts;%PATH%
python -c "import json,urllib.request; req=urllib.request.Request('http://127.0.0.1:8080/export',method='POST'); print(urllib.request.urlopen(req,timeout=30).read().decode())"
echo Cookies written to C:\jobsrss\linkedin_state.json
pause
"@ | Set-Content -Encoding ASCII -Path "$desktop\2-export-cookies.bat"

Write-Output "Ready"
Stop-Transcript
