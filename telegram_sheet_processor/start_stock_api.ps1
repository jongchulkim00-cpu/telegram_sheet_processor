param(
    [string]$HostName = "0.0.0.0",
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^\s*#" -or $_ -notmatch "=") { return }
        $name, $value = $_ -split "=", 2
        if ($name) {
            [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), "Process")
        }
    }
}

$env:API_HOST = $HostName
$env:API_PORT = [string]$Port

python -m uvicorn scripts.api_server:app --host $HostName --port $Port

