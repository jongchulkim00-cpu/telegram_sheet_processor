$Target = 'C:\Users\jongc\OneDrive\문서\New project 2\telegram_sheet_processor'
for ($i = 0; $i -lt 60; $i++) {
  if (-not (Test-Path -LiteralPath $Target)) { exit 0 }
  try {
    Remove-Item -LiteralPath $Target -Recurse -Force -ErrorAction Stop
    exit 0
  } catch {
    Start-Sleep -Seconds 2
  }
}
Write-Host 'Could not delete locked folder. Close IDE/Explorer/OneDrive handles and run this script again.'
