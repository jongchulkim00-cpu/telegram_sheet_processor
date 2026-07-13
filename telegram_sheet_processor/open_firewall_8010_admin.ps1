$ErrorActionPreference = "Stop"

$ruleName = "Telegram Sheet Stock API 8010"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue

if ($existing) {
    Write-Host "Firewall rule already exists: $ruleName"
    exit 0
}

New-NetFirewallRule `
    -DisplayName $ruleName `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort 8010 `
    -Action Allow | Out-Host

Write-Host "Firewall rule created: $ruleName"

