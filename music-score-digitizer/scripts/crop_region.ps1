param(
    [Parameter(Mandatory = $true)][string]$Src,
    [Parameter(Mandatory = $true)][string]$Out,
    [int]$X,
    [int]$Y,
    [int]$W,
    [int]$H,
    [double]$Scale = 4
)

# Crop a region and upscale it for reading one staff system at a time.
# Upscaling does NOT add information; it only makes the existing pixels easier
# for a vision model / human to inspect. Use the original-resolution source.

Add-Type -AssemblyName System.Drawing

$img = [System.Drawing.Image]::FromFile($Src)
$dw = [int]($W * $Scale)
$dh = [int]($H * $Scale)
$bmp = New-Object System.Drawing.Bitmap($dw, $dh)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$dest = New-Object System.Drawing.Rectangle(0, 0, $dw, $dh)
$srcRect = New-Object System.Drawing.Rectangle($X, $Y, $W, $H)
$g.DrawImage($img, $dest, $srcRect, [System.Drawing.GraphicsUnit]::Pixel)
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
$img.Dispose()

Write-Output ("{0} {1}x{2} (source {3},{4} {5}x{6} @ {7}x)" -f $Out, $dw, $dh, $X, $Y, $W, $H, $Scale)
