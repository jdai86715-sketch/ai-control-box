[CmdletBinding()]
param([int]$Tail = 0)

$ErrorActionPreference = 'Stop'
$ToolRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd([char]92)
$LogPath = Join-Path $ToolRoot 'logs\continuity-diagnostic.jsonl'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogPath) | Out-Null
if (-not (Test-Path -LiteralPath $LogPath -PathType Leaf)) { New-Item -ItemType File -Path $LogPath | Out-Null }

Write-Host "Watching Better Compact diagnostics: $LogPath" -ForegroundColor Cyan
Write-Host 'Press Ctrl+C to stop.' -ForegroundColor DarkGray
Get-Content -LiteralPath $LogPath -Encoding utf8 -Tail $Tail -Wait | ForEach-Object {
    try {
        $event = $_ | ConvertFrom-Json
        $color = switch ($event.outcome) { 'recorded' { 'Green' } 'reloaded' { 'Green' } 'failed' { 'Red' } 'skipped' { 'Yellow' } 'ignored' { 'DarkGray' } default { 'White' } }
        $project = if ([string]::IsNullOrWhiteSpace([string]$event.project)) { '-' } else { $event.project }
        $source = if ($event.source) { " source=$($event.source)" } elseif ($event.trigger) { " trigger=$($event.trigger)" } else { '' }
        Write-Host ("[{0}] {1}/{2} project={3}{4} detail={5}" -f $event.timestampUtc, $event.stage, $event.outcome, $project, $source, $event.detail) -ForegroundColor $color
    } catch { Write-Host "[better-compact] unreadable diagnostic line: $_" -ForegroundColor Red }
}
