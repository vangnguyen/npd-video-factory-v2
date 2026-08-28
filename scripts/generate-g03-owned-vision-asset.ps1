param(
    [string]$OutputPath = "docs/acceptance/v3-01/assets/g03-a-owned-vision-test.png"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$resolvedOutput = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputPath))
$outputDirectory = [System.IO.Path]::GetDirectoryName($resolvedOutput)
[System.IO.Directory]::CreateDirectory($outputDirectory) | Out-Null

$bitmap = [System.Drawing.Bitmap]::new(1024, 1024)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit

$navy = [System.Drawing.Color]::FromArgb(255, 13, 31, 53)
$blue = [System.Drawing.Color]::FromArgb(255, 30, 91, 131)
$sky = [System.Drawing.Color]::FromArgb(255, 212, 237, 246)
$green = [System.Drawing.Color]::FromArgb(255, 34, 111, 84)
$lightGreen = [System.Drawing.Color]::FromArgb(255, 135, 190, 143)
$gold = [System.Drawing.Color]::FromArgb(255, 222, 174, 63)
$cream = [System.Drawing.Color]::FromArgb(255, 250, 247, 235)
$white = [System.Drawing.Color]::White

$background = [System.Drawing.Drawing2D.LinearGradientBrush]::new(
    [System.Drawing.Rectangle]::new(0, 0, 1024, 1024),
    $sky,
    $cream,
    90
)
$graphics.FillRectangle($background, 0, 0, 1024, 1024)

$navyBrush = [System.Drawing.SolidBrush]::new($navy)
$blueBrush = [System.Drawing.SolidBrush]::new($blue)
$greenBrush = [System.Drawing.SolidBrush]::new($green)
$lightGreenBrush = [System.Drawing.SolidBrush]::new($lightGreen)
$goldBrush = [System.Drawing.SolidBrush]::new($gold)
$whiteBrush = [System.Drawing.SolidBrush]::new($white)
$creamBrush = [System.Drawing.SolidBrush]::new($cream)
$navyPen = [System.Drawing.Pen]::new($navy, 8)
$goldPen = [System.Drawing.Pen]::new($gold, 6)
$whitePen = [System.Drawing.Pen]::new($white, 3)

$graphics.FillRectangle($navyBrush, 0, 0, 1024, 160)
$graphics.FillEllipse($goldBrush, 830, 205, 110, 110)
$graphics.FillRectangle($greenBrush, 0, 770, 1024, 254)
$graphics.FillEllipse($lightGreenBrush, -120, 690, 650, 260)
$graphics.FillEllipse($greenBrush, 420, 705, 760, 260)

$graphics.FillRectangle($blueBrush, 250, 365, 190, 410)
$graphics.FillRectangle($navyBrush, 455, 285, 250, 490)
$graphics.FillRectangle($blueBrush, 720, 425, 120, 350)
$graphics.DrawRectangle($goldPen, 455, 285, 250, 490)

foreach ($x in 282, 342, 487, 557, 627, 750) {
    foreach ($y in 400, 475, 550, 625, 700) {
        if (($x -lt 440 -and $y -ge 400) -or ($x -ge 455 -and $x -lt 705 -and $y -ge 325) -or ($x -ge 720 -and $y -ge 450)) {
            $graphics.FillRectangle($creamBrush, $x, $y, 28, 38)
        }
    }
}

$graphics.FillRectangle($creamBrush, 548, 650, 64, 125)
$graphics.DrawLine($whitePen, 0, 815, 1024, 815)

$titleFont = [System.Drawing.Font]::new("Arial", 48, [System.Drawing.FontStyle]::Bold)
$subtitleFont = [System.Drawing.Font]::new("Arial", 25, [System.Drawing.FontStyle]::Bold)
$labelFont = [System.Drawing.Font]::new("Arial", 20, [System.Drawing.FontStyle]::Regular)
$badgeFont = [System.Drawing.Font]::new("Arial", 18, [System.Drawing.FontStyle]::Bold)
$center = [System.Drawing.StringFormat]::new()
$center.Alignment = [System.Drawing.StringAlignment]::Center
$center.LineAlignment = [System.Drawing.StringAlignment]::Center

$graphics.DrawString(
    "NPD VISION ACCEPTANCE",
    $titleFont,
    $whiteBrush,
    [System.Drawing.RectangleF]::new(45, 28, 934, 64),
    $center
)
$graphics.DrawString(
    "OWNED TEST ASSET 01",
    $subtitleFont,
    $goldBrush,
    [System.Drawing.RectangleF]::new(45, 96, 934, 40),
    $center
)
$graphics.DrawString(
    "REAL ESTATE SCENE / BUILDINGS / LANDSCAPE / OCR",
    $labelFont,
    $navyBrush,
    [System.Drawing.RectangleF]::new(50, 190, 700, 80)
)

$badge = [System.Drawing.RectangleF]::new(115, 885, 794, 72)
$graphics.FillRectangle($navyBrush, $badge)
$graphics.DrawRectangle($goldPen, 115, 885, 794, 72)
$graphics.DrawString(
    "INTERNAL • NO PERSON • NO THIRD-PARTY TRADEMARK",
    $badgeFont,
    $whiteBrush,
    $badge,
    $center
)

$bitmap.Save($resolvedOutput, [System.Drawing.Imaging.ImageFormat]::Png)

foreach ($resource in @(
    $center, $badgeFont, $labelFont, $subtitleFont, $titleFont,
    $whitePen, $goldPen, $navyPen, $creamBrush, $whiteBrush, $goldBrush,
    $lightGreenBrush, $greenBrush, $blueBrush, $navyBrush, $background,
    $graphics, $bitmap
)) {
    if ($null -ne $resource) {
        $resource.Dispose()
    }
}

$hash = (Get-FileHash -LiteralPath $resolvedOutput -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "Generated $resolvedOutput"
Write-Output "SHA256 $hash"
