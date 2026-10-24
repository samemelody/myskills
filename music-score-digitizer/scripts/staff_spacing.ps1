param(
    [Parameter(Mandatory = $true)][string]$Src,
    [int]$Samples = 12,
    [int]$Lum = 170,
    [double]$RowThreshold = 0.5
)

# Measure staff-line spacing (px) to judge whether a scan has enough physical
# resolution for OMR. Samples columns in the left 15%-50% band to avoid dense
# notes / handwriting and to minimise the effect of page skew.
# Verdict: >=16px OK, 8-15px MARGINAL (needs per-note geometric checks), <8px TOO_LOW.

Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap($Src)
$w = $bmp.Width
$h = $bmp.Height

$x0 = [int]($w * 0.15)
$x1 = [int]($w * 0.50)
$xs = @()
$step = [Math]::Max(1, [int](($x1 - $x0) / $Samples))
for ($x = $x0; $x -lt $x1; $x += $step) { $xs += $x }

$score = @{}
for ($y = 0; $y -lt $h; $y++) {
    $dark = 0
    foreach ($x in $xs) {
        $c = $bmp.GetPixel($x, $y)
        $brightness = 0.299 * $c.R + 0.587 * $c.G + 0.114 * $c.B
        if ($brightness -lt $Lum) { $dark++ }
    }
    $score[$y] = $dark
}
$bmp.Dispose()

# Smooth over +/-1 row to tolerate 1-2px skew.
$need = [Math]::Ceiling($xs.Count * $RowThreshold)
$lineRows = @()
for ($y = 1; $y -lt $h - 1; $y++) {
    $s = $score[$y] + $score[$y - 1] + $score[$y + 1]
    if ($s -ge ($need * 2)) { $lineRows += $y }
}

# Merge consecutive rows into one line centre.
$lines = @()
$start = $null
$prev = $null
foreach ($y in $lineRows) {
    if ($null -eq $start) { $start = $y; $prev = $y; continue }
    if ($y - $prev -le 2) { $prev = $y; continue }
    $lines += [int](($start + $prev) / 2)
    $start = $y; $prev = $y
}
if ($null -ne $start) { $lines += [int](($start + $prev) / 2) }

if ($lines.Count -lt 4) {
    Write-Output ("NO_STAFF_FOUND (lines={0})" -f $lines.Count)
    exit 1
}

$gaps = @()
for ($i = 1; $i -lt $lines.Count; $i++) {
    $g = $lines[$i] - $lines[$i - 1]
    if ($g -ge 5 -and $g -le 45) { $gaps += $g }
}

if ($gaps.Count -eq 0) {
    Write-Output ("NO_STAFF_FOUND (lines={0}, no valid gaps)" -f $lines.Count)
    exit 1
}

$sorted = $gaps | Sort-Object
$median = $sorted[[int]([Math]::Floor($sorted.Count / 2))]

if ($median -ge 16) { $verdict = 'OK' }
elseif ($median -ge 8) { $verdict = 'MARGINAL' }
else { $verdict = 'TOO_LOW' }

Write-Output ("LINES={0} MEDIAN_GAP={1}px VERDICT={2}" -f $lines.Count, $median, $verdict)
Write-Output ("  lines: " + ($lines -join ','))
Write-Output ("  gaps:  " + ($gaps -join ','))
