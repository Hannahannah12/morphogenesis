$ErrorActionPreference = 'Stop'

$ruleName = 'Morphogenesis Website 8080'
Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

New-NetFirewallRule `
    -DisplayName $ruleName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort 8080 `
    -RemoteAddress LocalSubnet `
    -Profile Any | Out-Null
