param(
    [Parameter(Mandatory=$true)][string]$InputFile,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
# Open this presentation without a window and use a new output directory.
# PowerPoint must be installed. No application settings or add-ins are changed.
$ErrorActionPreference = 'Stop'
$deckInput = (Resolve-Path -LiteralPath $InputFile).Path
$deckOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $deckOutput) { throw 'Use a new output directory' }
if ([System.IO.Path]::GetExtension($deckInput).ToLowerInvariant() -ne '.pptx') { throw 'Render a .pptx file' }
$sourceHash = (Get-FileHash -LiteralPath $deckInput -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.Directory]::CreateDirectory($deckOutput) | Out-Null
$application = $null
$presentation = $null
try {
    $application = New-Object -ComObject PowerPoint.Application
    $presentation = $application.Presentations.Open($deckInput, -1, 0, 0)
    $presentation.SaveAs((Join-Path $deckOutput 'slides.pdf'), 32)
    $pixelWidth = 1600
    $pixelHeight = [int][Math]::Round($pixelWidth * $presentation.PageSetup.SlideHeight / $presentation.PageSetup.SlideWidth)
    $pages = @()
    foreach ($slide in $presentation.Slides) {
        $name = 'slide-{0:D3}.png' -f $slide.SlideIndex
        $slide.Export((Join-Path $deckOutput $name), 'PNG', $pixelWidth, $pixelHeight)
        $pages += $name
    }
    if ((Get-FileHash -LiteralPath $deckInput -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sourceHash) {
        throw 'Input deck changed during render'
    }
    $outputHashes = @{}
    foreach ($name in @('slides.pdf') + $pages) {
        $outputHashes[$name] = (Get-FileHash -LiteralPath (Join-Path $deckOutput $name) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $receipt = @{
        status = 'rendered'
        engine = 'Microsoft PowerPoint'; version = $application.Version
        input_sha256 = $sourceHash; pages = $pages
        width = $pixelWidth; height = $pixelHeight
        script_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
        output_sha256 = $outputHashes
        visual_review = 'pending'; scientific_verification = $false
    }
    $receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $deckOutput 'render.json') -Encoding UTF8
} catch {
    @{ status = 'failed'; message = $_.Exception.Message; input_sha256 = $sourceHash } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $deckOutput 'render-failure.json') -Encoding UTF8
    throw
} finally {
    if ($null -ne $presentation) {
        $presentation.Close()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation)
    }
    if ($null -ne $application) {
        # Quit only if this instance has no other open presentation.
        if ($application.Presentations.Count -eq 0) { $application.Quit() }
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($application)
    }
}
