# Pack MetaHumanForMaya from local Maya modules into vendor/*.zip for GitHub Release.
param(
    [string]$SourceModules = "$env:USERPROFILE\Documents\maya\modules",
    [string]$OutZip = ""
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$vendor = Join-Path $root 'vendor'
if (-not (Test-Path -LiteralPath $vendor)) { New-Item -ItemType Directory -Path $vendor | Out-Null }

$folder = Join-Path $SourceModules 'MetaHumanForMaya'
$mod = Join-Path $SourceModules 'MetaHumanForMaya.mod'
if (-not (Test-Path -LiteralPath $folder)) { throw "Missing $folder" }
if (-not (Test-Path -LiteralPath $mod)) { throw "Missing $mod" }

if (-not $OutZip) {
    $OutZip = Join-Path $vendor 'MetaHumanForMaya-1.3.1-win64.zip'
}

$stage = Join-Path $env:TEMP ('mh2max_mh_pack_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    Copy-Item -LiteralPath $folder -Destination (Join-Path $stage 'MetaHumanForMaya') -Recurse -Force
    Copy-Item -LiteralPath $mod -Destination (Join-Path $stage 'MetaHumanForMaya.mod') -Force
    Copy-Item -LiteralPath $mod -Destination (Join-Path $vendor 'MetaHumanForMaya.mod') -Force
    if (Test-Path -LiteralPath $OutZip) { Remove-Item -LiteralPath $OutZip -Force }
    Write-Host "Compressing to $OutZip (may take several minutes)..."
    Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $OutZip -CompressionLevel Optimal
    $sizeMb = [math]::Round((Get-Item -LiteralPath $OutZip).Length / 1MB, 1)
    Write-Host "Done: $OutZip ($sizeMb MB)"
}
finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
