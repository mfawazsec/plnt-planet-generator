<#
.SYNOPSIS
  Install the built zip into a throwaway Blender profile and confirm it enables.

.DESCRIPTION
  test_extension.py proves the package imports and registers; this proves
  Blender's own installer accepts it and the add-on turns on from a cold
  profile.

.EXAMPLE
  .\test_install.ps1
#>
[CmdletBinding()]
param(
    [string]$Zip,
    [int]   $TimeoutSec = 600,
    [string]$Blender
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'PlntBuild.psm1') -Force

$B = Get-PlntRoot
if (-not $Zip) {
    # Take the newest built zip rather than a hard-coded version: pinning the
    # name is how the shipped package stayed at 2.0.0 while the sources moved
    # on, and the install test kept passing against a stale build.
    # dist\ holds the shipped build; ext\ is where a local `extension build`
    # lands by default. Search both and take whichever is newer.
    $dirs = @('dist', 'ext') | ForEach-Object { Join-Path $B $_ } | Where-Object { Test-Path -LiteralPath $_ }
    $z = $dirs | ForEach-Object { Get-ChildItem -LiteralPath $_ -Filter 'plnt_planet-*.zip' -ErrorAction SilentlyContinue } |
         Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($z) { $Zip = $z.FullName } else { $Zip = Join-Path $B 'dist\plnt_planet.zip' }
}
Write-Host "zip: $Zip"
if (-not (Test-Path -LiteralPath $Zip)) { Write-Host "no zip at $Zip"; exit 1 }

# The bash version passed this through --python-expr. A multi-line expression
# survives a POSIX shell but not Windows command-line quoting, so it goes to a
# temp file and runs with -P instead.
$probe = Join-Path ([System.IO.Path]::GetTempPath()) ('plnt_install_{0}.py' -f ([guid]::NewGuid().ToString('N')))
$code = @'
import bpy, json, sys
argv = sys.argv
ZIP = argv[argv.index("--") + 1:][0]
res = {}
try:
    bpy.ops.extensions.package_install_files(
        filepath=ZIP, repo='user_default', enable_on_install=True)
    res['installed'] = True
except Exception as ex:
    res['installed'] = False
    res['error'] = '%s: %s' % (type(ex).__name__, ex)
res['addons_enabled'] = [a.module for a in bpy.context.preferences.addons
                         if 'plnt' in a.module.lower()]
res['panels'] = sorted(c for c in dir(bpy.types) if c.startswith('PLNT_PT_'))
res['operators'] = sorted(c for c in dir(bpy.types) if c.startswith('PLNT_OT_'))
res['scene_prop'] = hasattr(bpy.types.Scene, 'plnt')
print('INSTALL ' + json.dumps(res, default=str))
'@
Set-Content -LiteralPath $probe -Value $code -Encoding utf8

try {
    $r = Invoke-Blender -Script $probe -ScriptArgs @($Zip) -FactoryStartup `
                        -TimeoutSec $TimeoutSec -Blender $Blender
} finally {
    Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
}

$doc = Get-MarkedJson -Text $r.Output -Marker 'INSTALL'
if ($null -eq $doc) {
    Write-Host ('no INSTALL document ({0})' -f (Get-ExitReason -Code $r.ExitCode -TimedOut:$r.TimedOut -TimeoutSec $TimeoutSec))
    Write-Host $r.Output
    exit 1
}

$doc | ConvertTo-Json -Depth 10
# @($null).Count is 1, not 0, so guard before counting.
if ($null -eq $doc.panels)    { $panels = 0 } else { $panels = @($doc.panels).Count }
if ($null -eq $doc.operators) { $ops    = 0 } else { $ops    = @($doc.operators).Count }
Write-Host ''
Write-Host ('installed: {0}   panels: {1}   operators: {2}   scene prop: {3}' -f $doc.installed, $panels, $ops, $doc.scene_prop)
if (-not $doc.installed -or $panels -eq 0 -or $ops -eq 0) {
    Write-Host 'INSTALL_FAILED'
    exit 1
}
Write-Host 'INSTALL_OK'
