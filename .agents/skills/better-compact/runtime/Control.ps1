[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('SetCore', 'SetTaskState', 'Status')]
    [string]$Action,
    [bool]$Enabled = $true
)

$ErrorActionPreference = 'Stop'
$ToolRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd([char]92)
$SkillsRoot = Split-Path -Parent $ToolRoot
$AgentsRoot = Split-Path -Parent $SkillsRoot
$WorkspaceRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $AgentsRoot)).TrimEnd([char]92)
$ConfigDirectory = Join-Path $ToolRoot 'config'
$ConfigPath = Join-Path $ConfigDirectory 'workspace.json'
$RecoveryDirectory = Join-Path $ToolRoot 'recovery'
$ActivePath = Join-Path $RecoveryDirectory 'active-projects.json'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Read-Utf8Text([string]$Path) { return [System.IO.File]::ReadAllText($Path, $Utf8NoBom) }
function Write-Utf8Text([string]$Path, [string]$Text) { [System.IO.File]::WriteAllText($Path, $Text, $Utf8NoBom) }

function Get-Value($Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    if ($Object -is [System.Collections.IDictionary]) { return $Object[$Name] }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Get-DefaultConfig {
    return [pscustomobject]@{ schemaVersion = 1; coreEnabled = $true; taskStateEnabled = $true }
}

function Read-Config {
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) { return Get-DefaultConfig }
    try {
        $parsed = Read-Utf8Text $ConfigPath | ConvertFrom-Json
        if ($null -eq $parsed) { return Get-DefaultConfig }
        return [pscustomobject]@{
            schemaVersion = 1
            coreEnabled = if ($null -eq (Get-Value $parsed 'coreEnabled')) { $true } else { [bool](Get-Value $parsed 'coreEnabled') }
            taskStateEnabled = if ($null -eq (Get-Value $parsed 'taskStateEnabled')) { $true } else { [bool](Get-Value $parsed 'taskStateEnabled') }
        }
    } catch { return Get-DefaultConfig }
}

function Write-Config($Config) {
    New-Item -ItemType Directory -Force -Path $ConfigDirectory | Out-Null
    $temporary = Join-Path $ConfigDirectory ('.workspace-' + [guid]::NewGuid().ToString('N') + '.json')
    try {
        Write-Utf8Text $temporary (($Config | ConvertTo-Json) + [Environment]::NewLine)
        Move-Item -LiteralPath $temporary -Destination $ConfigPath -Force
    } finally {
        if (Test-Path -LiteralPath $temporary -PathType Leaf) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Get-PathKey([string]$Path) {
    return [System.IO.Path]::GetFullPath($Path).TrimEnd([char]92).ToLowerInvariant()
}

function Get-ActiveProject {
    if (-not (Test-Path -LiteralPath $ActivePath -PathType Leaf)) { return '-' }
    try {
        $active = Read-Utf8Text $ActivePath | ConvertFrom-Json
        $property = $active.PSObject.Properties[(Get-PathKey $WorkspaceRoot)]
        if ($null -eq $property -or [string]::IsNullOrWhiteSpace([string]$property.Value)) { return '-' }
        return [string]$property.Value
    } catch { return '-' }
}

$config = Read-Config
switch ($Action) {
    'SetCore' { $config.coreEnabled = [bool]$Enabled; Write-Config $config; Write-Host ("Core: {0}" -f $(if ($config.coreEnabled) { 'ON' } else { 'OFF' })) }
    'SetTaskState' { $config.taskStateEnabled = [bool]$Enabled; Write-Config $config; Write-Host ("TASK_STATE: {0}" -f $(if ($config.taskStateEnabled) { 'ON' } else { 'OFF' })) }
    'Status' {
        Write-Output ("Core: {0}" -f $(if ($config.coreEnabled) { 'ON' } else { 'OFF' }))
        Write-Output ("TASK_STATE: {0}" -f $(if ($config.taskStateEnabled) { 'ON' } else { 'OFF' }))
        Write-Output "Workspace: $WorkspaceRoot"
        Write-Output "Tool directory: $ToolRoot"
        Write-Output "Active project: $(Get-ActiveProject)"
        Write-Output "Recovery Card directory: $RecoveryDirectory"
    }
}
