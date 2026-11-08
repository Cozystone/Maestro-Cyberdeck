# Blocks ALL inbound connections from the HP laptop (192.168.0.149) to this 5080 PC.
# Run in an *Administrator* PowerShell:
#   & 'D:\ATANOR-assistant\pc\block-laptop-on-pc.ps1'
# The model tunnel is an OUTBOUND connection from this PC, so it is not affected.

$ErrorActionPreference = 'Stop'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host 'NOT ADMIN: open PowerShell with "Run as administrator" and run this again.' -ForegroundColor Red
    exit 1
}
$name = 'ATANOR - block HP laptop inbound'
Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $name -Direction Inbound -RemoteAddress 192.168.0.149 -Action Block -Profile Any `
    -Description 'Laptop runs an AI agent with root. It must never reach this PC except via the outbound SSH model tunnel.' | Out-Null
Get-NetFirewallRule -DisplayName $name | Select-Object DisplayName, Enabled, Direction, Action | Format-List
Write-Host 'DONE: inbound from the laptop is blocked.' -ForegroundColor Green
