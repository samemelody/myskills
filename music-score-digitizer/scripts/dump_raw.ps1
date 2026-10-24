param(
    [Parameter(Mandatory = $true)][string]$Src,
    [Parameter(Mandatory = $true)][string]$Out
)

# Dump a 24bpp BGR raw copy of an image for fast pixel analysis in Python.
# Format: ASCII header line "SCORERAW <width> <height> <stride>\n" + raw bytes.

Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap($Src)
$w = $bmp.Width
$h = $bmp.Height
$rect = New-Object System.Drawing.Rectangle(0, 0, $w, $h)
$data = $bmp.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
$stride = $data.Stride
$len = $stride * $h
$bytes = New-Object byte[] $len
[System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $bytes, 0, $len)
$bmp.UnlockBits($data)
$bmp.Dispose()

$fs = [System.IO.File]::Create($Out)
$bw = New-Object System.IO.BinaryWriter($fs)
$header = [System.Text.Encoding]::ASCII.GetBytes(("SCORERAW {0} {1} {2}`n" -f $w, $h, $stride))
$bw.Write($header)
$bw.Write($bytes)
$bw.Close()
Write-Output ("wrote {0} ({1}x{2}, stride {3})" -f $Out, $w, $h, $stride)
