# Resolve .exe/.lnk path; follow nested shortcuts (max depth 25).
param(
    [Parameter(Mandatory = $true)][string]$Path
)

$ErrorActionPreference = 'Stop'

function Resolve-TargetPath {
    param(
        [string]$InputPath,
        [int]$Depth = 0
    )
    if ($Depth -gt 25) { return $null }
    $InputPath = $InputPath.Trim().Trim('"')
    if (-not $InputPath) { return $null }
    if (-not (Test-Path -LiteralPath $InputPath)) { return $null }

    $item = Get-Item -LiteralPath $InputPath
    if ($item.PSIsContainer) { return $item.FullName }

    if ($item.Extension -ieq '.lnk') {
        $shell = New-Object -ComObject WScript.Shell
        $target = $shell.CreateShortcut($item.FullName).TargetPath
        if ($target) {
            return Resolve-TargetPath -InputPath $target -Depth ($Depth + 1)
        }
        return $null
    }

    return $item.FullName
}

Resolve-TargetPath -InputPath $Path -Depth 0
