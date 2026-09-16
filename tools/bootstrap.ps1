<#
.SYNOPSIS
  Build the Python venv the non-Blender tools need.

.DESCRIPTION
  montage.py and compare.py import Pillow (and compare.py numpy). Blender's
  bundled interpreter has numpy but not Pillow, and it lives under Program
  Files where installing a package needs admin rights. This machine has no
  system Python at all, so those two tools cannot run without a venv.

  Prefers uv. Falls back to Blender's own python + pip, which is enough to
  build a venv somewhere writable.

.EXAMPLE
  .\bootstrap.ps1
#>
[CmdletBinding()]
param([switch]$Force)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'PlntBuild.psm1') -Force

$venv = Join-Path $PSScriptRoot '.venv'
$py   = Join-Path $venv 'Scripts\python.exe'

if ((Test-Path -LiteralPath $py) -and -not $Force) {
    Write-Host "venv already present: $venv"
    & $py -c "import PIL, numpy; print('Pillow', PIL.__version__, '/ numpy', numpy.__version__)"
    return
}
if ($Force -and (Test-Path -LiteralPath $venv)) {
    Remove-Item -LiteralPath $venv -Recurse -Force
}

function Find-Uv {
    $cmd = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $known = @(
        (Join-Path $env:USERPROFILE '.local\bin\uv.exe'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\uv.exe')
    )
    foreach ($k in $known) { if (Test-Path -LiteralPath $k) { return $k } }
    $pkg = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
    if (Test-Path -LiteralPath $pkg) {
        $hit = Get-ChildItem -LiteralPath $pkg -Filter 'uv.exe' -Recurse -ErrorAction SilentlyContinue |
               Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

$uv = Find-Uv
if ($uv) {
    Write-Host "uv: $uv"
    & $uv venv --python 3.12 $venv
    if ($LASTEXITCODE -ne 0) {
        # uv keeps its managed interpreters behind a minor-version directory
        # link. That link can go stale, and every `uv venv` then fails with
        # "Missing expected target directory"; deleting it makes uv rebuild it.
        Write-Warning 'uv venv failed; clearing a possibly stale managed-python link and retrying'
        $link = Join-Path $env:APPDATA 'uv\python\cpython-3.12-windows-x86_64-none'
        if (Test-Path -LiteralPath $link) { Remove-Item -LiteralPath $link -Recurse -Force }
        & $uv venv --python 3.12 $venv
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'uv could not provide a Python; falling back to Blender''s interpreter'
        $uv = $null
    } else {
        & $uv pip install --python $py pillow numpy
        if ($LASTEXITCODE -ne 0) { throw 'uv pip install failed' }
    }
}

if (-not $uv) {
    $blpy = Get-PlntPython            # Blender's bundled python
    Write-Host "falling back to: $blpy"
    & $blpy -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'could not create a venv from Blender''s python' }
    & $py -m pip install --upgrade pip
    & $py -m pip install pillow numpy
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }
}

& $py -c "import PIL, numpy; print('Pillow', PIL.__version__, '/ numpy', numpy.__version__)"
Write-Host "BOOTSTRAP_COMPLETE  $venv"
