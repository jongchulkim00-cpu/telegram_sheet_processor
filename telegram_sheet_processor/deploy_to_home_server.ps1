param(
    [Parameter(Mandatory = $true)]
    [string]$SshTarget,

    [string]$RemoteDir = "~/telegram_sheet_processor",
    [string]$PackagePath = "outputs\stock-api-deploy.zip",
    [string]$PublicUrl = "https://asset.jongchul-server.duckdns.org"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (!(Test-Path $PackagePath)) {
    .\package_for_home_server.ps1 -OutputPath $PackagePath
}

Write-Host "Creating remote directory..."
ssh $SshTarget "mkdir -p $RemoteDir"

Write-Host "Uploading package..."
scp $PackagePath "${SshTarget}:$RemoteDir/stock-api-deploy.zip"

Write-Host "Unpacking and rebuilding stock-api..."
ssh $SshTarget "cd $RemoteDir && (command -v unzip >/dev/null 2>&1 && unzip -o stock-api-deploy.zip || python3 -m zipfile -e stock-api-deploy.zip .) && chmod +x *.sh scripts/*.sh && cp -n .env.example .env && ./repair_stock_api_502.sh $PublicUrl"
