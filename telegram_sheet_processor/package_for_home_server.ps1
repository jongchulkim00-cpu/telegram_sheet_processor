param(
    [string]$OutputPath = "outputs\stock-api-deploy.zip"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null

$excludeDirs = @(
    "\.git\",
    "\__pycache__\",
    "\outputs\",
    "\data\cache\",
    "\outputs\stock-api-deploy",
    "\outputs\stock-api-deploy.zip"
)

$files = Get-ChildItem -Recurse -File | Where-Object {
    $full = $_.FullName
    if ($_.Name -eq ".env") { return $false }
    foreach ($dir in $excludeDirs) {
        if ($full -like "*$dir*") { return $false }
    }
    return $true
}

$stage = Join-Path $root "outputs\stock-api-deploy"
if (Test-Path $stage) {
    Remove-Item -Recurse -Force -LiteralPath $stage
}
New-Item -ItemType Directory -Force -Path $stage | Out-Null

foreach ($file in $files) {
    $relative = Resolve-Path -LiteralPath $file.FullName -Relative
    if ($relative.StartsWith(".\")) {
        $relative = $relative.Substring(2)
    } elseif ($relative.StartsWith("./")) {
        $relative = $relative.Substring(2)
    }
    $target = Join-Path $stage $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $target -Force
}

if (Test-Path $OutputPath) {
    Remove-Item -Force -LiteralPath $OutputPath
}

$zipFullPath = Join-Path $root $OutputPath
$stageFullPath = (Resolve-Path -LiteralPath $stage).Path
$env:STOCK_API_DEPLOY_STAGE = $stageFullPath
$env:STOCK_API_DEPLOY_ZIP = $zipFullPath
@"
import pathlib
import zipfile
import os

stage = pathlib.Path(os.environ["STOCK_API_DEPLOY_STAGE"])
zip_path = pathlib.Path(os.environ["STOCK_API_DEPLOY_ZIP"])

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(stage.rglob("*")):
        if path.is_file():
            arcname = path.relative_to(stage).as_posix()
            zf.write(path, arcname)
"@ | python -
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create deploy zip"
}
Remove-Item Env:\STOCK_API_DEPLOY_STAGE -ErrorAction SilentlyContinue
Remove-Item Env:\STOCK_API_DEPLOY_ZIP -ErrorAction SilentlyContinue

Write-Host "Created deploy package: $OutputPath"
