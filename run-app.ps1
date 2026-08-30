[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $repoRoot "phase-b\spacecraft-sim\backend"
$frontendDir = Join-Path $repoRoot "phase-b\spacecraft-sim\frontend"
$phaseADir = Join-Path $repoRoot "phase-a"
$phaseCDir = Join-Path $repoRoot "phase-c"
$venvDir = Join-Path $backendDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$envFile = Join-Path $backendDir ".env"
$envExample = Join-Path $backendDir ".env.example"
$logDir = Join-Path $backendDir ".run-logs"

$backendProcess = $null
$frontendProcess = $null
$restoreCtrlCBehavior = $false
$previousCtrlCBehavior = $false

function Wait-ForPortFree {
    param([int]$Port, [int]$TimeoutSeconds = 15)

    # A killed server can leave its listening socket behind for a moment. Give
    # that a chance to clear, then say exactly who still holds the port rather
    # than letting uvicorn fail to bind with a bare OSError.
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $held = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
        if ($held.Count -eq 0) { return }
        Start-Sleep -Milliseconds 500
    }

    $held = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    if ($held.Count -eq 0) { return }
    $owners = foreach ($conn in $held) {
        $owner = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        if ($owner) { "PID $($conn.OwningProcess) ($($owner.ProcessName))" }
        else { "PID $($conn.OwningProcess) (already exited; the socket should clear shortly)" }
    }
    throw ("Port $Port is still in use by: " + ($owners -join ", ") +
           ". Close that process and run this script again.")
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    # Kill children first: a parent that dies alone orphans a worker which
    # keeps holding the port.
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-ProcessTree -ProcessId $_.ProcessId }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-OurServers {
    # Match both the uvicorn entry point and this repository's venv executable.
    # `app.main:app` alone is common and could terminate an unrelated project.
    $venvPattern = [Regex]::Escape($venvPython)
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -match 'uvicorn' -and
            $_.CommandLine -match 'app\.main:app' -and
            ($_.ExecutablePath -eq $venvPython -or $_.CommandLine -match $venvPattern)
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function Write-Step([string]$message) {
    Write-Host "`n==> $message" -ForegroundColor Cyan
}

function Assert-CommandSucceeded([string]$description) {
    if ($LASTEXITCODE -ne 0) {
        throw "$description failed with exit code $LASTEXITCODE."
    }
}

function Test-NativeCommand {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList
    )

    # Windows PowerShell 5.1 can turn a native program's stderr into a
    # terminating error when ErrorActionPreference is Stop. Probe commands are
    # expected to fail sometimes, so isolate that behavior here.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & $FilePath @ArgumentList *> $null
        return $LASTEXITCODE -eq 0
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Wait-ForUrl {
    param(
        [string]$Uri,
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $Process.Refresh()
        if ($Process.HasExited) {
            throw "Process $($Process.Id) exited before $Uri became ready."
        }
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2 | Out-Null
            return
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    throw "Timed out waiting for $Uri."
}

function Show-LogTail([string]$path, [string]$label) {
    if (Test-Path -LiteralPath $path) {
        Write-Host "`n$label (last 30 lines):" -ForegroundColor Yellow
        Get-Content -LiteralPath $path -Tail 30
    }
}

foreach ($requiredDir in @($backendDir, $frontendDir, $phaseADir, $phaseCDir)) {
    if (-not (Test-Path -LiteralPath $requiredDir -PathType Container)) {
        throw "Required project directory is missing: $requiredDir"
    }
}

if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    Copy-Item -LiteralPath $envExample -Destination $envFile
    Write-Warning "Created backend\.env from .env.example. Fill in your IBM credentials to enable Advisor."
}
elseif (Select-String -LiteralPath $envFile -Quiet -Pattern "YOUR_IBM_API_KEY|YOUR_WATSONX_PROJECT_ID|YOUR_REGION|PUT_YOUR_") {
    Write-Warning "backend\.env still contains placeholders. The simulator will work, but Advisor will remain disabled."
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Write-Step "Creating the Python virtual environment"
    $uvCommand = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($null -ne $uvCommand) {
        & $uvCommand.Source venv --python 3.11 --seed $venvDir
        Assert-CommandSucceeded "uv venv"
    }
    else {
        $created = $false
        $pyCommand = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($null -ne $pyCommand) {
            if (Test-NativeCommand -FilePath $pyCommand.Source -ArgumentList @("-3", "-c", "import sys; assert sys.version_info >= (3, 11)")) {
                & $pyCommand.Source -3 -m venv $venvDir
                Assert-CommandSucceeded "Python venv creation"
                $created = $true
            }
        }
        if (-not $created) {
            $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
            if ($null -eq $pythonCommand) {
                throw "Python 3.11 or newer was not found. Install Python and try again."
            }
            if (-not (Test-NativeCommand -FilePath $pythonCommand.Source -ArgumentList @("-c", "import sys; assert sys.version_info >= (3, 11)"))) {
                throw "The available python.exe is older than Python 3.11. Install a supported Python version or uv and try again."
            }
            & $pythonCommand.Source -m venv $venvDir
            Assert-CommandSucceeded "Python venv creation"
        }
    }
}
else {
    Write-Step "Reusing the existing Python virtual environment"
}

if (-not (Test-NativeCommand -FilePath $venvPython -ArgumentList @("-m", "pip", "--version"))) {
    & $venvPython -m ensurepip --upgrade
    Assert-CommandSucceeded "pip bootstrap"
}

if (-not (Test-NativeCommand -FilePath $venvPython -ArgumentList @("-c", "import dotenv, fastapi, uvicorn, spacecraft_sim, phase_c, ibm_watsonx_ai"))) {
    Write-Step "Installing backend, simulator, and Granite dependencies (first launch)"
    & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $backendDir "requirements.txt")
    Assert-CommandSucceeded "Backend dependency installation"
    & $venvPython -m pip install --disable-pip-version-check -e $phaseADir -e ("{0}[granite]" -f $phaseCDir)
    Assert-CommandSucceeded "Local package installation"
}
else {
    Write-Step "Python dependencies are already installed"
}

$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($null -eq $nodeCommand -or $null -eq $npmCommand) {
    throw "Node.js and npm were not found on PATH. Install Node.js 20.19+ or 22.12+ and try again."
}

$nodeVersionText = (& $nodeCommand.Source --version).TrimStart("v")
$nodeVersion = [Version]$nodeVersionText
$nodeSupported = (
    ($nodeVersion.Major -eq 20 -and $nodeVersion -ge [Version]"20.19.0") -or
    ($nodeVersion -ge [Version]"22.12.0")
)
if (-not $nodeSupported) {
    throw "Node.js 20.19+ or 22.12+ is required by Vite; found v$nodeVersionText."
}

$viteEntry = Join-Path $frontendDir "node_modules\vite\bin\vite.js"
if (-not (Test-Path -LiteralPath $viteEntry -PathType Leaf)) {
    Write-Step "Installing frontend dependencies (first launch)"
    Push-Location $frontendDir
    try {
        & $npmCommand.Source ci
        Assert-CommandSucceeded "Frontend dependency installation"
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Step "Frontend dependencies are already installed"
}

New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$backendOut = Join-Path $logDir "backend.stdout.log"
$backendErr = Join-Path $logDir "backend.stderr.log"
$frontendOut = Join-Path $logDir "frontend.stdout.log"
$frontendErr = Join-Path $logDir "frontend.stderr.log"

try {
    # A server left over from an earlier run would keep port 8000 and serve
    # its stale code, so clear ours before binding.
    Stop-OurServers
    Wait-ForPortFree -Port 8000

    Write-Step "Starting FastAPI and Vite"
    # Deliberately NOT --reload. Its watcher runs the app in a multiprocessing
    # worker whose command line is a bare `spawn_main(...)` bootstrap - no
    # "uvicorn", no "app.main:app". If the parent dies the worker is orphaned,
    # keeps the listening socket, and goes on serving the code it loaded, while
    # being invisible both to a command-line search and to the port's owner
    # (Windows still credits the socket to the dead parent). That is the very
    # stale-server failure this launcher exists to prevent, made unfindable.
    # One plain process per server stays killable and greppable instead.
    $backendArgs = @(
        "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1", "--port", "8000"
    )
    $backendProcess = Start-Process `
        -FilePath $venvPython `
        -ArgumentList $backendArgs `
        -WorkingDirectory $backendDir `
        -RedirectStandardOutput $backendOut `
        -RedirectStandardError $backendErr `
        -WindowStyle Hidden `
        -PassThru

    $frontendProcess = Start-Process `
        -FilePath $nodeCommand.Source `
        -ArgumentList @("`"$viteEntry`"", "--host", "127.0.0.1") `
        -WorkingDirectory $frontendDir `
        -RedirectStandardOutput $frontendOut `
        -RedirectStandardError $frontendErr `
        -WindowStyle Hidden `
        -PassThru

    Wait-ForUrl -Uri "http://127.0.0.1:8000/" -Process $backendProcess
    Wait-ForUrl -Uri "http://127.0.0.1:5173/" -Process $frontendProcess

    Write-Host "`nApp is ready: http://localhost:5173" -ForegroundColor Green
    Write-Host "Backend:     http://localhost:8000" -ForegroundColor Green
    Write-Host "Press Ctrl+C in this window to stop both servers."

    if (-not $NoBrowser) {
        Start-Process "http://localhost:5173"
    }

    if (-not [Console]::IsInputRedirected) {
        $previousCtrlCBehavior = [Console]::TreatControlCAsInput
        [Console]::TreatControlCAsInput = $true
        $restoreCtrlCBehavior = $true
    }

    while ($true) {
        Start-Sleep -Milliseconds 250
        if ($restoreCtrlCBehavior -and [Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            $controlPressed = ($key.Modifiers -band [ConsoleModifiers]::Control) -ne 0
            if ($controlPressed -and $key.Key -eq [ConsoleKey]::C) {
                Write-Host "`nStopping both servers..." -ForegroundColor Cyan
                break
            }
        }
        $backendProcess.Refresh()
        $frontendProcess.Refresh()
        if ($backendProcess.HasExited -or $frontendProcess.HasExited) {
            throw "A server stopped unexpectedly."
        }
    }
}
catch {
    Write-Error $_
    Show-LogTail -path $backendErr -label "Backend error log"
    Show-LogTail -path $frontendErr -label "Frontend error log"
    throw
}
finally {
    if ($restoreCtrlCBehavior) {
        [Console]::TreatControlCAsInput = $previousCtrlCBehavior
    }
    foreach ($process in @($backendProcess, $frontendProcess)) {
        if ($null -ne $process) {
            try {
                $process.Refresh()
                if (-not $process.HasExited) {
                    Stop-ProcessTree -ProcessId $process.Id
                }
            }
            catch {
                # The process may have exited between Refresh and Stop-Process.
            }
        }
    }

    # Belt and braces: the launchers fork, and a surviving child keeps port
    # 8000 and its already-loaded code alive. A server that outlives its
    # launcher is the failure that looks like a bug in whatever you last
    # edited, so nothing of ours is left listening.
    Stop-OurServers
}
