param(
    [string]$BaseUrl = "http://127.0.0.1:8010"
)

$ErrorActionPreference = "Stop"

Write-Host "Checking $BaseUrl/health"
Invoke-RestMethod -Uri "$BaseUrl/health" | ConvertTo-Json -Depth 8

Write-Host "`nChecking $BaseUrl/source-status"
Invoke-RestMethod -Uri "$BaseUrl/source-status" | ConvertTo-Json -Depth 8

Write-Host "`nChecking cache freshness for 039030,011790"
Invoke-RestMethod -Uri "$BaseUrl/cache-audit?tickers=039030,011790" | ConvertTo-Json -Depth 8

