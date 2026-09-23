[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ToolRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd([char]92)
$SkillsRoot = Split-Path -Parent $ToolRoot
$AgentsRoot = Split-Path -Parent $SkillsRoot
$WorkspaceRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $AgentsRoot)).TrimEnd([char]92)
$MetadataPath = Join-Path $ToolRoot 'install\install.json'
$CodexHome = Join-Path $env:USERPROFILE '.codex'
$HooksPath = Join-Path $CodexHome 'hooks.json'
$HookScriptPath = Join-Path $PSScriptRoot 'continuity.ps1'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Get-Value($Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}
function Read-Utf8Text([string]$Path) { return [System.IO.File]::ReadAllText($Path, $Utf8NoBom) }
function Write-JsonFile([string]$Path, $Value, [int]$Depth = 12) { [System.IO.File]::WriteAllText($Path, (($Value | ConvertTo-Json -Depth $Depth) + [Environment]::NewLine), $Utf8NoBom) }
if (-not (Test-Path -LiteralPath $MetadataPath -PathType Leaf)) { throw "Refusing to remove directory without Better Compact metadata: $ToolRoot" }
try { $metadata = Read-Utf8Text $MetadataPath | ConvertFrom-Json } catch { throw "Refusing to remove directory with invalid Better Compact metadata: $ToolRoot" }
if (([string](Get-Value $metadata 'product')) -ne 'better-compact' -or ([string](Get-Value $metadata 'workspaceRoot')).TrimEnd([char]92) -ne $WorkspaceRoot) { throw "Refusing to remove directory not identified as this workspace's Better Compact installation: $ToolRoot" }

if (Test-Path -LiteralPath $HooksPath -PathType Leaf) {
    try { $hookConfig = Read-Utf8Text $HooksPath | ConvertFrom-Json } catch { throw "Existing hooks.json is not valid JSON: $HooksPath" }
    $changed = $false
    foreach ($eventName in @('SessionStart', 'PreToolUse', 'PostToolUse', 'PreCompact')) {
        $property = $hookConfig.hooks.PSObject.Properties[$eventName]
        if ($null -eq $property) { continue }
        $groups = @($property.Value); $remainingGroups = New-Object System.Collections.Generic.List[object]
        foreach ($group in $groups) {
            $handlers = @($group.hooks)
            $remainingHandlers = @($handlers | Where-Object { [string]$_.command -notmatch [regex]::Escape($HookScriptPath) })
            if ($remainingHandlers.Count -ne $handlers.Count) { $changed = $true }
            if ($remainingHandlers.Count -gt 0) { $group.hooks = $remainingHandlers; [void]$remainingGroups.Add($group) }
        }
        if ($remainingGroups.Count -ne $groups.Count) { $changed = $true }
        $hookConfig.hooks.$eventName = $remainingGroups.ToArray()
    }
    if ($changed) {
        Copy-Item -LiteralPath $HooksPath -Destination "$HooksPath.better-compact-backup-$([DateTime]::UtcNow.ToString('yyyyMMddHHmmss')).json" -Force
        Write-JsonFile $HooksPath $hookConfig
    }
}

Remove-Item -LiteralPath $ToolRoot -Recurse -Force
Write-Host "Removed Better Compact from $WorkspaceRoot" -ForegroundColor Green
