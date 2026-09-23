[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$WorkspaceRoot,
    [Parameter(Mandatory)]
    [string]$ToolRoot
)

$ErrorActionPreference = 'Stop'
$WorkspaceRoot = [System.IO.Path]::GetFullPath($WorkspaceRoot).TrimEnd([char]92)
$ToolRoot = [System.IO.Path]::GetFullPath($ToolRoot).TrimEnd([char]92)
$ConfigPath = Join-Path $ToolRoot 'config\workspace.json'
$RecoveryDirectory = Join-Path $ToolRoot 'recovery'
$ActivePath = Join-Path $RecoveryDirectory 'active-projects.json'
$LogDirectory = Join-Path $ToolRoot 'logs'
$DiagnosticPath = Join-Path $LogDirectory 'continuity-diagnostic.jsonl'
$AuditPath = Join-Path $LogDirectory 'recovery-audit.jsonl'
$TaskStatePromptPath = Join-Path $ToolRoot 'prompts\task-state.md'
$RecoveryFileLimit = 12
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom

function Read-Utf8Text([string]$Path) { return [System.IO.File]::ReadAllText($Path, $Utf8NoBom) }
function Write-Utf8Text([string]$Path, [string]$Text) { [System.IO.File]::WriteAllText($Path, $Text, $Utf8NoBom) }

function Get-Value($Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    if ($Object -is [System.Collections.IDictionary]) { return $Object[$Name] }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Read-Config {
    $default = [pscustomobject]@{ coreEnabled = $true; taskStateEnabled = $true }
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) { return $default }
    try {
        $parsed = Read-Utf8Text $ConfigPath | ConvertFrom-Json
        if ($null -eq $parsed) { return $default }
        return [pscustomobject]@{
            coreEnabled = if ($null -eq (Get-Value $parsed 'coreEnabled')) { $true } else { [bool](Get-Value $parsed 'coreEnabled') }
            taskStateEnabled = if ($null -eq (Get-Value $parsed 'taskStateEnabled')) { $true } else { [bool](Get-Value $parsed 'taskStateEnabled') }
        }
    } catch { return $default }
}

$config = Read-Config
if (-not $config.coreEnabled) { exit 0 }
New-Item -ItemType Directory -Force -Path $RecoveryDirectory, $LogDirectory | Out-Null

function Write-JsonLine([string]$Path, $Value) { [System.IO.File]::AppendAllText($Path, (($Value | ConvertTo-Json -Depth 12 -Compress) + [Environment]::NewLine), $Utf8NoBom) }
function Write-Diagnostic([string]$Stage, [string]$Outcome, [string]$Project, [string]$Detail, $Event) {
    Write-JsonLine $DiagnosticPath ([ordered]@{
        timestampUtc = [DateTime]::UtcNow.ToString('o'); stage = $Stage; outcome = $Outcome; project = $Project
        source = [string](Get-Value $Event 'source'); trigger = [string](Get-Value $Event 'trigger'); detail = $Detail
    })
    [Console]::Error.WriteLine("[better-compact] $Stage/$Outcome project=$Project detail=$Detail")
}
function Write-Audit([string]$Stage, [string]$Project, [string]$Detail, $Event) {
    Write-JsonLine $AuditPath ([ordered]@{ timestampUtc = [DateTime]::UtcNow.ToString('o'); stage = $Stage; project = $Project; sessionId = [string](Get-Value $Event 'session_id'); detail = $Detail })
}
function Get-PathKey([string]$Path) { return [System.IO.Path]::GetFullPath($Path).TrimEnd([char]92).ToLowerInvariant() }
function Read-ActiveProjects {
    if (-not (Test-Path -LiteralPath $ActivePath -PathType Leaf)) { return [pscustomobject]@{} }
    try { return Read-Utf8Text $ActivePath | ConvertFrom-Json } catch { return [pscustomobject]@{} }
}
function Set-ActiveProject([string]$Cwd, [string]$Project) {
    $active = Read-ActiveProjects; $key = Get-PathKey $Cwd; $property = $active.PSObject.Properties[$key]
    if ($null -eq $property) { $active | Add-Member -NotePropertyName $key -NotePropertyValue $Project } else { $property.Value = $Project }
    Write-Utf8Text $ActivePath (($active | ConvertTo-Json -Depth 6) + [Environment]::NewLine)
}
function Get-ActiveProject([string]$Cwd) {
    $active = Read-ActiveProjects
    foreach ($candidate in @($Cwd, $WorkspaceRoot)) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        $property = $active.PSObject.Properties[(Get-PathKey $candidate)]
        if ($null -ne $property -and -not [string]::IsNullOrWhiteSpace([string]$property.Value)) { return [string]$property.Value }
    }
    return $null
}
function Get-ProjectNameForPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $null }
    try {
        $candidate = if ([System.IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path $WorkspaceRoot $Path }
        $fullPath = [System.IO.Path]::GetFullPath($candidate)
    } catch { return $null }
    $prefix = $WorkspaceRoot + [char]92
    if (-not $fullPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { return $null }
    $relative = $fullPath.Substring($prefix.Length)
    if ([string]::IsNullOrWhiteSpace($relative) -or $relative -notmatch '^[^\\/]+') { return $null }
    $project = ($relative -split '[\\/]')[0]
    if ($project -in @('.agents', '.codex', 'docs')) { return $null }
    if (-not (Test-Path -LiteralPath (Join-Path $WorkspaceRoot $project) -PathType Container)) { return $null }
    return $project
}
function Get-PatchTargetPaths($Event) {
    $command = [string](Get-Value (Get-Value $Event 'tool_input') 'command')
    if ([string]::IsNullOrWhiteSpace($command)) { return @() }
    return @([regex]::Matches($command, '(?m)^\*\*\* (?:Add|Update|Delete) File: ([^\r\n]+)$') | ForEach-Object { $_.Groups[1].Value.Trim() })
}
function Test-ApplyPatchSucceeded($Event) {
    $response = Get-Value $Event 'tool_response'
    if ($null -eq $response) { return $false }
    foreach ($name in @('isError', 'is_error', 'failed')) {
        if ((Get-Value $response $name) -eq $true) { return $false }
    }
    $error = Get-Value $response 'error'
    if ($null -ne $error -and -not [string]::IsNullOrWhiteSpace([string]$error)) { return $false }
    foreach ($name in @('exit_code', 'exitCode')) {
        $value = Get-Value $response $name
        if ($null -ne $value -and [int]$value -ne 0) { return $false }
    }
    if ((Get-Value $response 'success') -eq $false) { return $false }
    return $true
}
function Read-ContextFile([string]$Label, [string]$Path, [int]$Limit = 5000) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $text = Read-Utf8Text $Path
    if ($Limit -gt 0 -and $text.Length -gt $Limit) { $text = $text.Substring(0, $Limit) + "`n[truncated]" }
    return "### ${Label}: $Path`n$text"
}
function Get-RuleContext([string]$Project) {
    # Codex already supplies the workspace-root AGENTS.md.  Only add a
    # project rule file when recovery is resuming a project from the root cwd.
    if (-not $Project) { return $null }
    return Read-ContextFile 'Rules' (Join-Path (Join-Path $WorkspaceRoot $Project) 'AGENTS.md')
}
function Get-RecoveryCardPath([string]$Project) { return Join-Path $RecoveryDirectory "$Project.json" }
function Read-RecoveryCard([string]$Project) {
    $path = Get-RecoveryCardPath $Project
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    try { return Read-Utf8Text $path | ConvertFrom-Json } catch { return $null }
}
function ConvertTo-RecoveryRelativePath([string]$Project, [string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Project) -or [string]::IsNullOrWhiteSpace($Path)) { return $null }
    $projectRoot = Join-Path $WorkspaceRoot $Project
    try {
        if ([System.IO.Path]::IsPathRooted($Path)) { $candidate = $Path }
        elseif ($Path -match ('^' + [regex]::Escape($Project) + '[\\/]')) { $candidate = Join-Path $WorkspaceRoot $Path }
        else { $candidate = Join-Path $projectRoot $Path }
        $fullPath = [System.IO.Path]::GetFullPath($candidate)
    } catch { return $null }
    $prefix = $projectRoot.TrimEnd([char]92) + [char]92
    if (-not $fullPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { return $null }
    return $fullPath.Substring($prefix.Length).Replace('/', '\')
}
function Get-NormalizedRecoveryFiles([string]$Project, $Files) {
    $normalized = New-Object System.Collections.Generic.List[string]
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($file in @($Files)) {
        $relative = ConvertTo-RecoveryRelativePath $Project ([string]$file)
        if ($relative -and $seen.Add($relative)) { [void]$normalized.Add($relative) }
    }
    while ($normalized.Count -gt $RecoveryFileLimit) { $normalized.RemoveAt(0) }
    return @($normalized)
}
function Write-RecoveryCard([string]$Project, [string[]]$Targets, $Event) {
    $previous = Read-RecoveryCard $Project
    $files = New-Object System.Collections.Generic.List[string]
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    $allFiles = @()
    $allFiles += @(Get-Value $previous 'files')
    $allFiles += @($Targets)
    foreach ($file in $allFiles) {
        $relative = ConvertTo-RecoveryRelativePath $Project ([string]$file)
        if ($relative -and $seen.Add($relative)) { [void]$files.Add($relative) }
    }
    while ($files.Count -gt $RecoveryFileLimit) { $files.RemoveAt(0) }
    $card = [ordered]@{
        schemaVersion = 2; project = $Project; lastSuccessfulEditAt = [DateTime]::UtcNow.ToString('o'); lastSuccessfulEditSessionId = [string](Get-Value $Event 'session_id')
        lastCompactedAt = Get-Value $previous 'lastCompactedAt'; lastCompactedSessionId = Get-Value $previous 'lastCompactedSessionId'; files = @($files)
    }
    Write-Utf8Text (Get-RecoveryCardPath $Project) (($card | ConvertTo-Json -Depth 8) + [Environment]::NewLine)
    return $card
}
function Mark-RecoveryCardCompacted([string]$Project, $Event) {
    $card = Read-RecoveryCard $Project
    if ($null -eq $card) { return $false }
    $card.lastCompactedAt = [DateTime]::UtcNow.ToString('o'); $card.lastCompactedSessionId = [string](Get-Value $Event 'session_id')
    Write-Utf8Text (Get-RecoveryCardPath $Project) (($card | ConvertTo-Json -Depth 8) + [Environment]::NewLine)
    return $true
}
function Format-RecoveryCardContext([string]$Project, $Card) {
    if ($null -eq $Card) { return $null }
    $lines = New-Object System.Collections.Generic.List[string]
    [void]$lines.Add("### Recovery Card: $Project")
    $lastEdit = [string](Get-Value $Card 'lastSuccessfulEditAt')
    $lastCompact = [string](Get-Value $Card 'lastCompactedAt')
    if ($lastEdit) { [void]$lines.Add("- Last successful edit: $lastEdit") }
    if ($lastCompact) { [void]$lines.Add("- Last compact: $lastCompact") }
    $files = @(Get-NormalizedRecoveryFiles $Project (Get-Value $Card 'files'))
    if ($files.Count -gt 0) {
        [void]$lines.Add("- Recent files ($($files.Count)):")
        foreach ($file in $files) { [void]$lines.Add("  - $file") }
    }
    return ($lines -join "`n")
}
function Send-Context([string]$HookEventName, [string]$Context) {
    if ([string]::IsNullOrWhiteSpace($Context)) { return }
    [Console]::Out.WriteLine(([ordered]@{ hookSpecificOutput = [ordered]@{ hookEventName = $HookEventName; additionalContext = $Context } } | ConvertTo-Json -Depth 8 -Compress))
}

try {
    $rawEvent = [Console]::In.ReadToEnd(); if ([string]::IsNullOrWhiteSpace($rawEvent)) { exit 0 }
    try { $event = $rawEvent | ConvertFrom-Json } catch {
        Write-Diagnostic 'Dispatch' 'failed' '-' "reason=invalid-hook-json; inputLength=$($rawEvent.Length)" $null
        exit 0
    }
    $stage = [string](Get-Value $event 'hook_event_name'); $cwd = [string](Get-Value $event 'cwd')
    if ([string]::IsNullOrWhiteSpace($cwd)) { $cwd = $WorkspaceRoot }
    switch ($stage) {
        'PostToolUse' {
            if (-not (Test-ApplyPatchSucceeded $event)) { Write-Diagnostic $stage 'skipped' '-' 'reason=tool-unsuccessful' $event; break }
            $targets = @(Get-PatchTargetPaths $event); $projects = @($targets | ForEach-Object { Get-ProjectNameForPath $_ } | Where-Object { $_ } | Select-Object -Unique)
            if ($projects.Count -eq 0) { Write-Diagnostic $stage 'skipped' '-' 'reason=no-workspace-project-targets' $event; break }
            foreach ($project in $projects) {
                $projectTargets = @($targets | Where-Object { (Get-ProjectNameForPath $_) -eq $project })
                [void](Write-RecoveryCard $project $projectTargets $event); Set-ActiveProject $cwd $project; Write-Audit $stage $project "targetCount=$($projectTargets.Count)" $event
            }
            Write-Diagnostic $stage 'recorded' ($projects -join ',') "recordedProjects=$($projects -join ',')" $event
        }
        'PreCompact' {
            $project = Get-ActiveProject $cwd
            if (-not $project) { Write-Diagnostic $stage 'skipped' '-' 'reason=no-active-project' $event; break }
            if (Mark-RecoveryCardCompacted $project $event) { Write-Audit $stage $project 'recovery-card-marked-compacted' $event; Write-Diagnostic $stage 'recorded' $project 'recovery-card-marked-compacted' $event }
            else { Write-Diagnostic $stage 'skipped' $project 'reason=no-recovery-card' $event }
        }
        'SessionStart' {
            $source = [string](Get-Value $event 'source'); if ($source -notin @('compact', 'resume')) { break }
            $project = Get-ActiveProject $cwd; $parts = New-Object System.Collections.Generic.List[string]; $rules = Get-RuleContext $project
            if ($rules) { [void]$parts.Add($rules) }
            if ($config.taskStateEnabled) {
                $prompt = Read-ContextFile 'TASK_STATE management prompt' $TaskStatePromptPath 0; if ($prompt) { [void]$parts.Add($prompt) }
                if ($project) { $taskState = Read-ContextFile 'TASK_STATE' (Join-Path (Join-Path $WorkspaceRoot $project) 'TASK_STATE.md'); if ($taskState) { [void]$parts.Add($taskState) } }
            }
            $card = if ($project) { Read-RecoveryCard $project } else { $null }
            $cardContext = if ($card) { Format-RecoveryCardContext $project $card } else { $null }
            if ($cardContext) { [void]$parts.Add($cardContext) }
            Send-Context $stage ($parts -join "`n`n")
            Write-Diagnostic $stage 'reloaded' $(if ($project) { $project } else { '-' }) "source=$source; cardFound=$([bool]$card); taskStateEnabled=$($config.taskStateEnabled)" $event
            Write-Audit $stage $(if ($project) { $project } else { '-' }) "source=$source; cardFound=$([bool]$card)" $event
        }
        default { Write-Diagnostic $stage 'ignored' '-' 'reason=unsupported-event' $event }
    }
} catch {
    $inputLength = if ($null -eq $rawEvent) { 0 } else { $rawEvent.Length }
    try { Write-Diagnostic 'Dispatch' 'failed' '-' "reason=dispatch-failed; exception=$($_.Exception.GetType().Name); inputLength=$inputLength" $null } catch { [Console]::Error.WriteLine("[better-compact] Dispatch/failed: $($_.Exception.GetType().Name)") }
    exit 0
}
