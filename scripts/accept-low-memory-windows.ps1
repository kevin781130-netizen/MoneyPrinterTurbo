# One-command, non-Docker Windows pre-device validation for the opt-in
# low-memory FFmpeg renderer. Run from an existing branch checkout:
# powershell -NoProfile -File .\scripts\accept-low-memory-windows.ps1
# No packages are installed; no remote video/TTS provider is contacted.
[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$EvidenceDirectory = "evidence"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EvidencePath = if ([IO.Path]::IsPathRooted($EvidenceDirectory)) {
    $EvidenceDirectory
} else {
    Join-Path $Root $EvidenceDirectory
}
$ExpectedBranch = "dev/mpt-slim-20261103"
$ExitCode = 1
$Stage = "preflight"
$Result = [ordered]@{
    gate = "MPT_WINDOWS_LOW_MEMORY_PRE_DEVICE"
    status = "ENVIRONMENT_BLOCKED"
    branch = $null
    sha = $null
    host_platform = [Environment]::OSVersion.VersionString
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    scope = "single-source-no-subtitles-no-bgm-1080-square"
    checks = [ordered]@{
        python = "NOT_RUN"
        prerequisites = "NOT_RUN"
        ffmpeg = "NOT_RUN"
        ffprobe = "NOT_RUN"
        unit_regressions = "NOT_RUN"
        offline_smoke = "NOT_RUN"
        actual_api_e2e_1080 = "NOT_RUN"
    }
    prerequisites = $null
    error = $null
}

$EnvNames = @(
    "MPT_API_E2E",
    "MPT_API_E2E_LOW_MEMORY",
    "MPT_API_E2E_RESOLUTION",
    "MPT_API_E2E_SOURCE_RESOLUTION"
)
$PriorEnv = @{}
foreach ($Name in $EnvNames) {
    $PriorEnv[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
}

try {
    if (-not $IsWindows -and $PSVersionTable.PSEdition -eq "Core") {
        throw "This acceptance entrypoint requires Windows."
    }
    if ($env:OS -ne "Windows_NT") {
        throw "This acceptance entrypoint requires Windows."
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Missing git. Use an existing branch checkout."
    }
    if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
        throw "Missing Python executable: $Python"
    }
    # FFmpeg/FFprobe codec and runtime validation are handled by the
    # read-only Python preflight so all blockers appear in one JSON report.

    Push-Location $Root
    try {
        $Result.branch = ((& git branch --show-current) | Out-String).Trim()
        $Result.sha = ((& git rev-parse HEAD) | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $Result.branch -ne $ExpectedBranch) {
            throw "Checkout $ExpectedBranch before running; refusing to validate main or a detached ref."
        }

        & $Python --version *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Python is not usable."
        }
        $Result.checks.python = "PASS"

        New-Item -ItemType Directory -Path $EvidencePath -Force | Out-Null
        $Stage = "preflight"
        $PrereqFile = Join-Path $EvidencePath "mpt-low-memory-prerequisites.json"
        $PrereqLog = Join-Path $EvidencePath "mpt-low-memory-prerequisites.log"
        & $Python scripts/check_windows_prereqs.py --json-out $PrereqFile *> $PrereqLog
        $PrereqExit = $LASTEXITCODE
        if (-not (Test-Path $PrereqFile)) {
            throw "Prerequisites produced no evidence. Review $PrereqLog"
        }
        $Prereq = Get-Content $PrereqFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $Result.prerequisites = $Prereq
        if ($PrereqExit -ne 0 -or $Prereq.status -ne "PASS") {
            $Brief = [string]::Join("; ", @($Prereq.blockers))
            throw "Windows prerequisites blocked: $Brief. Review $PrereqFile"
        }
        $Result.checks.prerequisites = "PASS"
        $Result.checks.ffmpeg = "PASS"
        $Result.checks.ffprobe = "PASS"

        $Stage = "unit_regressions"
        $UnitLog = Join-Path $EvidencePath "mpt-low-memory-unit.log"
        & $Python -m unittest test.services.test_ffmpeg_low_memory -v *> $UnitLog
        if ($LASTEXITCODE -ne 0) {
            throw "Low-memory regression suite failed. Review $UnitLog"
        }
        $Result.checks.unit_regressions = "PASS"

        # Force the standalone smoke to remain a local test, even when the
        # caller had Render-specific flags in their environment.
        $env:MPT_API_E2E = "0"
        $Stage = "offline_smoke"
        $SmokeFile = Join-Path $EvidencePath "mpt-low-memory-offline.json"
        $SmokeLog = Join-Path $EvidencePath "mpt-low-memory-offline.log"
        & $Python scripts/offline_smoke.py --json-out $SmokeFile *> $SmokeLog
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $SmokeFile)) {
            throw "Offline smoke failed. Review $SmokeLog"
        }
        $Smoke = Get-Content $SmokeFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($Smoke.status -ne "PASS" -or $Smoke.checks.Count -ne 5) {
            throw "Offline smoke evidence is not 5/5 PASS."
        }
        $Result.checks.offline_smoke = "PASS"

        # The E2E owns a temporary MPT_HOME and uses synthetic video, an
        # explicit script and silent narration; no paid AI/network calls.
        $env:MPT_API_E2E_RESOLUTION = "1080"
        $env:MPT_API_E2E_SOURCE_RESOLUTION = "540"
        $env:MPT_API_E2E_LOW_MEMORY = "1"
        $Stage = "actual_api_e2e_1080"
        $ApiFile = Join-Path $EvidencePath "mpt-low-memory-api-1080.json"
        $ApiLog = Join-Path $EvidencePath "mpt-low-memory-api-1080.log"
        & $Python scripts/api_offline_e2e.py --json-out $ApiFile *> $ApiLog
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ApiFile)) {
            throw "Real FastAPI E2E failed. Review $ApiLog"
        }
        $Api = Get-Content $ApiFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if (
            $Api.status -ne "PASS" -or
            $Api.checks.Count -ne 4 -or
            $Api.width -ne 1080 -or
            $Api.height -ne 1080 -or
            $Api.source_resolution -ne 540 -or
            -not $Api.low_memory_ffmpeg_enabled -or
            -not $Api.production_resolution_tested
        ) {
            throw "Real FastAPI E2E did not return the exact 1080p 4/4 PASS."
        }
        $Result.checks.actual_api_e2e_1080 = "PASS"
        $Result.status = "PASS"
        $ExitCode = 0
    } finally {
        Pop-Location
    }
} catch {
    $Result.error = $_.Exception.Message
    $Result.status = if ($Stage -eq "preflight") { "ENVIRONMENT_BLOCKED" } else { "FAIL" }
    $ExitCode = if ($Stage -eq "preflight") { 2 } else { 1 }
} finally {
    foreach ($Name in $EnvNames) {
        [Environment]::SetEnvironmentVariable($Name, $PriorEnv[$Name], "Process")
    }
    New-Item -ItemType Directory -Path $EvidencePath -Force | Out-Null
    $EvidenceJson = Join-Path $EvidencePath "mpt-low-memory-windows-gate.json"
    $Result | ConvertTo-Json -Depth 8 | Set-Content -Path $EvidenceJson -Encoding UTF8
    Write-Output ("MPT_WINDOWS_LOW_MEMORY_RESULT=" + ($Result | ConvertTo-Json -Depth 8 -Compress))
    Write-Output "Evidence: $EvidenceJson"
}
exit $ExitCode
