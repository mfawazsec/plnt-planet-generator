<#
    Shared harness for the PLNT PowerShell tooling.

    Every shell script in this project did the same four things: run Blender
    headless with a -P script, capture its output, pull a JSON document out of
    that output by marker, and report. They each reimplemented it, and the two
    ablation runners had already drifted apart by the time they were ported.
    One implementation, here.
#>

function Get-PlntRoot {
    <#  PLNT_output, resolved from this module's own location.  #>
    Split-Path -Parent $PSScriptRoot
}

function Get-PlntBlender {
    param([string]$Override)
    if ($Override) { return $Override }
    if ($env:PLNT_BLENDER) { return $env:PLNT_BLENDER }
    $candidates = @(
        'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe',
        'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe',
        'C:\Program Files\Blender Foundation\Blender 5.0\blender.exe'
    )
    foreach ($c in $candidates) { if (Test-Path -LiteralPath $c) { return $c } }
    $cmd = Get-Command blender.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw 'Blender not found. Set $env:PLNT_BLENDER or pass -Blender.'
}

function Get-PlntPython {
    <#
        Python for the tools that are NOT run inside Blender.

        montage.py and compare.py need Pillow, which Blender's bundled
        interpreter does not ship and cannot be given without writing into
        Program Files. tools\bootstrap.ps1 builds a venv next to this module;
        prefer it, and fall back to Blender's own python for callers that only
        need the standard library.
    #>
    param([switch]$RequirePillow)
    $venv = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venv) { return $venv }
    if ($RequirePillow) {
        throw 'No tools venv. Run tools\bootstrap.ps1 first (montage.py and compare.py need Pillow).'
    }
    $bl = Get-PlntBlender
    $py = Join-Path (Split-Path -Parent $bl) '5.2\python\bin\python.exe'
    if (Test-Path -LiteralPath $py) { return $py }
    throw 'No usable Python found.'
}

# ---------------------------------------------------------------- GPU gating

$script:Smi = Join-Path $env:SystemRoot 'System32\nvidia-smi.exe'

function Get-GpuStat {
    param([ValidateSet('temperature.gpu', 'clocks.sm')][string]$Query)
    if (-not (Test-Path -LiteralPath $script:Smi)) { return 0 }
    try {
        $v = & $script:Smi --query-gpu=$Query --format=csv,noheader,nounits
        if (-not $v) { return 0 }
        return [int](($v | Select-Object -First 1).ToString().Trim())
    } catch { return 0 }
}

function Get-GpuTemp  { Get-GpuStat -Query 'temperature.gpu' }
function Get-GpuClock { Get-GpuStat -Query 'clocks.sm' }

function Wait-GpuCool {
    <#
        Sustained load drops this card from 2100 to 1500 MHz, which silently
        made later cells ~6% slower and invalidated the whole first ablation
        matrix. Gate on the card returning near its measured idle floor.

        The floor is measured, not absolute: the desktop alone holds the GPU
        near 72C, so a fixed 64C gate is unreachable and every cell would stall
        for the full timeout.
    #>
    param(
        [Parameter(Mandatory = $true)][int]$Gate,
        [int]$MaxSeconds = 150,
        [scriptblock]$Log
    )
    $t0 = Get-Date
    while ((Get-GpuTemp) -gt $Gate) {
        if (((Get-Date) - $t0).TotalSeconds -ge $MaxSeconds) {
            if ($Log) { & $Log ('    settle: gave up after {0}s at {1}C' -f $MaxSeconds, (Get-GpuTemp)) }
            return $false
        }
        Start-Sleep -Seconds 10
    }
    if ($Log) { & $Log ('    settled at {0}C after {1}s' -f (Get-GpuTemp), [int]((Get-Date) - $t0).TotalSeconds) }
    return $true
}

# ------------------------------------------------------------ running Blender

function Invoke-Blender {
    <#
        Run Blender headless and return exit code, output and duration as a
        [pscustomobject] with ExitCode, Output, TimedOut, Seconds.
    #>
    [CmdletBinding()]
    param(
        [string]   $Blend,
        [string]   $Script,
        [string[]] $ScriptArgs = @(),
        [string]   $PythonExpr,
        [switch]   $FactoryStartup,
        [int]      $TimeoutSec = 2400,
        [string]   $Blender
    )
    $exe = Get-PlntBlender -Override $Blender
    $a = @('-b')
    if ($Blend) { $a += $Blend }
    if ($FactoryStartup) { $a += '--factory-startup' }
    $a += '--enable-autoexec'
    if ($Script)     { $a += @('-P', $Script) }
    if ($PythonExpr) { $a += @('--python-expr', $PythonExpr) }
    if ($ScriptArgs -and $ScriptArgs.Count -gt 0) { $a += @('--') + $ScriptArgs }

    # Start-Process joins ArgumentList with spaces and does not quote, so any
    # path containing a space has to be quoted here or Blender sees two args.
    $quoted = @()
    foreach ($x in $a) {
        $s = [string]$x
        if ($s -match '\s') { $quoted += ('"' + $s + '"') } else { $quoted += $s }
    }

    $so = [System.IO.Path]::GetTempFileName()
    $se = [System.IO.Path]::GetTempFileName()
    $t0 = Get-Date
    $timedOut = $false
    $proc = Start-Process -FilePath $exe -ArgumentList $quoted -NoNewWindow -PassThru `
                          -RedirectStandardOutput $so -RedirectStandardError $se
    # Touching Handle caches the process handle. Without it Windows releases the
    # handle on exit and ExitCode reads back as $null, which turns a clean
    # render into a reported failure.
    $null = $proc.Handle
    if ($proc.WaitForExit($TimeoutSec * 1000)) {
        # The timed overload can return before the redirected streams are
        # flushed; the parameterless call waits for that too.
        $proc.WaitForExit()
    } else {
        $timedOut = $true
        try { $proc.Kill() } catch { }
        $proc.WaitForExit()
    }
    $rc = $proc.ExitCode
    if ($null -eq $rc) { $rc = -1 }

    $text = ''
    foreach ($f in @($so, $se)) {
        if (Test-Path -LiteralPath $f) {
            $c = Get-Content -LiteralPath $f -Raw -ErrorAction SilentlyContinue
            if ($c) { $text += $c }
            Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue
        }
    }

    return [pscustomobject]@{
        ExitCode = $rc
        Output   = $text
        TimedOut = $timedOut
        Seconds  = [int]((Get-Date) - $t0).TotalSeconds
    }
}

function Get-ExitReason {
    <#
        Windows has no SIGTERM, so the rc=143 that identified an OOM kill on
        Linux never appears here. These are the codes Blender actually dies
        with when it runs out of memory.
    #>
    param([int]$Code, [switch]$TimedOut, [int]$TimeoutSec)
    if ($TimedOut) { return "timeout after ${TimeoutSec}s (killed)" }
    switch ($Code) {
        0           { return 'ok' }
        1           { return 'rc=1 (Blender reported an error)' }
        -1073741819 { return 'rc=0xC0000005 access violation (commonly out of memory)' }
        -1073741571 { return 'rc=0xC00000FD stack overflow' }
        -1073740940 { return 'rc=0xC0000374 heap corruption (commonly out of memory)' }
        -1073740791 { return 'rc=0xC0000409 stack buffer overrun' }
        default     { return "rc=$Code" }
    }
}

# --------------------------------------------------------------- JSON marking

function Get-MarkedJsonText {
    <#
        Pull the raw text of the JSON document that follows a marker line out
        of Blender's output.

        The bash version used sed -n '/^MARKER/,$p' because several of these
        tools print with indent=1, and a tail -N slices a multi-line document
        in half, and the parser then reports a failure that is entirely the
        harness's fault. Brace-matching from the marker is that idea done
        exactly: the equivalent of Python's raw_decode, stopping at the end of
        the first complete value and ignoring whatever Blender prints after it.
    #>
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text,
        [Parameter(Mandatory = $true)][string]$Marker
    )
    if (-not $Text) { return $null }
    $m = [regex]::Match($Text, '(?m)^' + [regex]::Escape($Marker) + '\s*')
    if (-not $m.Success) { return $null }
    $rest = $Text.Substring($m.Index + $m.Length)

    $start = $rest.IndexOfAny([char[]]@('{', '['))
    if ($start -lt 0) { return $null }
    $open = $rest[$start]
    if ($open -eq '{') { $close = '}' } else { $close = ']' }

    $depth = 0; $inStr = $false; $esc = $false; $end = -1
    for ($i = $start; $i -lt $rest.Length; $i++) {
        $ch = $rest[$i]
        if ($inStr) {
            if ($esc) { $esc = $false }
            elseif ($ch -eq '\') { $esc = $true }
            elseif ($ch -eq '"') { $inStr = $false }
            continue
        }
        if ($ch -eq '"') { $inStr = $true; continue }
        if ($ch -eq $open) { $depth++ }
        elseif ($ch -eq $close) { $depth--; if ($depth -eq 0) { $end = $i; break } }
    }
    if ($end -lt 0) { return $null }
    return $rest.Substring($start, $end - $start + 1)
}

function Get-MarkedJson {
    <#  Get-MarkedJsonText, parsed.  #>
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text,
        [Parameter(Mandatory = $true)][string]$Marker
    )
    $raw = Get-MarkedJsonText -Text $Text -Marker $Marker
    if (-not $raw) { return $null }
    try { return $raw | ConvertFrom-Json } catch { return $null }
}

function Get-JsonProperties {
    <#  PS 5.1 ConvertFrom-Json yields a PSCustomObject and has no
        -AsHashtable, so iterating a JSON object means walking
        PSObject.Properties.  #>
    param($Object)
    if ($null -eq $Object) { return @() }
    return @($Object.PSObject.Properties)
}

Export-ModuleMember -Function Get-PlntRoot, Get-PlntBlender, Get-PlntPython,
    Get-GpuStat, Get-GpuTemp, Get-GpuClock, Wait-GpuCool,
    Invoke-Blender, Get-ExitReason, Get-MarkedJsonText, Get-MarkedJson,
    Get-JsonProperties
