<#
.SYNOPSIS
  Everything that can be verified without rendering.

.DESCRIPTION
  Covers the failure modes this project has actually hit: dead nodes, sockets
  with no UI, sockets with no tooltip, inputs that cannot reach an output,
  preset bleed, a broken extension package, and a planet larger than its own
  atmosphere.

  The bash original shelled out to python3 five times to parse the JSON each
  check prints. There is no system python here, and PowerShell can read JSON
  natively, so those inline parsers are gone.

.EXAMPLE
  .\check_all.ps1
#>
[CmdletBinding()]
param(
    [string]$Blend,
    [int]   $TimeoutSec = 1800,
    [string]$Blender
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'PlntBuild.psm1') -Force

$B = Get-PlntRoot
if (-not $Blend) { $Blend = Join-Path $B 'PLNT_PlanetGen.blend' }
$logs = Join-Path $B 'logs'
if (-not (Test-Path -LiteralPath $logs)) { New-Item -ItemType Directory -Path $logs | Out-Null }

$fail = 0

function Get-Prop {
    <#  Safe property read: these documents legitimately omit keys.  #>
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { return $null }
    return $p.Value
}

function Get-PropArray {
    <#  @($null) is a ONE-element array in PowerShell, so a JSON null read back
        as a list counts as one item and fails a check that should pass. Always
        go through here when the count is what matters.  #>
    param($Object, [string]$Name)
    $v = Get-Prop -Object $Object -Name $Name
    if ($null -eq $v) { return @() }
    return @($v)
}

function Invoke-Check {
    param([string]$Label, [string]$BlendFile, [string]$Script, [string]$Marker)
    Write-Host "--- $Label"
    $sp = @{ Script = (Join-Path $PSScriptRoot $Script); TimeoutSec = $TimeoutSec; Blender = $Blender }
    if ($BlendFile) { $sp.Blend = $BlendFile } else { $sp.FactoryStartup = $true }
    $r = Invoke-Blender @sp

    # Keep the raw output on disk exactly as the bash version did -- when a
    # check fails, the JSON alone rarely says why.
    Set-Content -LiteralPath (Join-Path $logs "check_$Label.txt") -Value $r.Output -Encoding utf8

    if ($r.TimedOut) { Write-Host "   TIMED OUT after ${TimeoutSec}s"; return $null }
    $doc = Get-MarkedJson -Text $r.Output -Marker $Marker
    if ($null -eq $doc) {
        Write-Host ("   no {0} document in output ({1})" -f $Marker, (Get-ExitReason -Code $r.ExitCode))
        Write-Host "   see logs\check_$Label.txt"
    }
    return $doc
}

# ---- every node group builds, and no group contains unreachable nodes -------
$d = Invoke-Check -Label 'builders' -Script 'validate_build.py' -Marker 'VALIDATE'
if ($null -eq $d) { $fail = 1 } else {
    $bad = @(); $dead = @()
    foreach ($p in Get-JsonProperties $d) {
        $v = $p.Value
        if (-not (Get-Prop $v 'ok')) { $bad += $p.Name; continue }
        $dn = Get-Prop (Get-Prop $v 'value') 'dead_nodes'
        if ($dn) { $dead += ('{0}={1}' -f $p.Name, ($dn -join ',')) }
    }
    if ($bad)  { Write-Host ('   builders failing: ' + ($bad -join ', ')) }  else { Write-Host '   builders failing: none' }
    if ($dead) { Write-Host ('   dead nodes: ' + ($dead -join '; ')) }       else { Write-Host '   dead nodes: none' }
    if ($bad -or $dead) { $fail = 1 }
}

# ---- an empty scene becomes a planet, with no orphan or undocumented socket -
$d = Invoke-Check -Label 'scaffold' -Script 'test_scaffold.py' -Marker 'SCAFFOLD'
if ($null -eq $d) { $fail = 1 } else {
    $a        = Get-Prop $d 'audit'
    $orphans  = Get-PropArray $a 'orphans'
    $undoc    = Get-PropArray $a 'undocumented'
    $inert    = Get-PropArray $d 'inert_inputs'
    $ok       = [bool](Get-Prop $d 'ok')
    Write-Host ('   scaffold ok: {0}' -f $ok)
    Write-Host ('   orphans: {0}  undocumented: {1}' -f $orphans.Count, $undoc.Count)
    if ($inert.Count) { Write-Host ('   inert inputs: ' + ($inert -join ', ')) } else { Write-Host '   inert inputs: none' }
    if (-not $ok -or $orphans.Count -or $undoc.Count -or $inert.Count) { $fail = 1 }
}

# ---- the built zip imports and registers ------------------------------------
$d = Invoke-Check -Label 'extension' -Script 'test_extension.py' -Marker 'EXTTEST'
if ($d -and (Get-Prop $d 'ok')) { Write-Host '   extension registers: yes' }
else { Write-Host '   extension FAILED'; $fail = 1 }

# ---- applying one preset does not leave another preset's values behind ------
$d = Invoke-Check -Label 'presets' -BlendFile $Blend -Script 'test_presets.py' -Marker 'PRESETS'
if ($d -and (Get-Prop $d 'ok')) { Write-Host '   presets bleed-free: yes' }
else { Write-Host '   preset bleed DETECTED'; $fail = 1 }

# ---- the shipped .blend itself ----------------------------------------------
$d = Invoke-Check -Label 'audit' -BlendFile $Blend -Script 'audit_blend.py' -Marker 'AUDIT'
if ($null -eq $d) { $fail = 1 } else {
    $a       = Get-Prop $d 'audit'
    $orphans = Get-PropArray $a 'orphans'
    $undoc   = Get-PropArray $a 'undocumented'
    Write-Host ('   reachable: {0}  orphans: {1}  undocumented: {2}' -f (Get-Prop $a 'reachable'), $orphans.Count, $undoc.Count)
    if ($orphans.Count -or $undoc.Count) { $fail = 1 }
}

Write-Host ''
if ($fail -eq 0) { Write-Host 'ALL CHECKS PASSED' } else { Write-Host 'CHECKS FAILED' }
exit $fail
