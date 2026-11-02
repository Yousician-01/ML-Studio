param(
    [switch]$FromSource,
    [string]$ArtifactDirectory,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'ML Studio CLI\tools')
)
$ErrorActionPreference = 'Stop'
if ($FromSource -and $ArtifactDirectory) {
    throw 'Choose either -FromSource or -ArtifactDirectory, not both.'
}
$repo = Split-Path -Parent $PSScriptRoot
if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
    throw 'This bootstrap targets Windows x64 only.'
}
$bin = Join-Path $InstallRoot 'bin'
if ($FromSource) {
    if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
        throw 'Install the Rust toolchain from https://rustup.rs, or obtain a verified CLI release artifact. No binary is downloaded by this script.'
    }
    & cargo install --path (Join-Path $repo 'cli') --locked --root $InstallRoot
    if ($LASTEXITCODE -ne 0) { throw 'Cargo installation failed.' }
} elseif ($ArtifactDirectory) {
    $name = 'mls-windows-x64.exe'
    $source = Join-Path $ArtifactDirectory $name
    $checksums = Join-Path $ArtifactDirectory 'SHA256SUMS'
    $line = Get-Content -LiteralPath $checksums | Where-Object { $_ -match ('^[0-9a-fA-F]{64}\s+\*?' + [regex]::Escape($name) + '$') }
    if (@($line).Count -ne 1) { throw 'Expected exactly one matching checksum in SHA256SUMS.' }
    $expected = ($line -split '\s+')[0]
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash
    if ($actual -ne $expected) { throw 'CLI checksum mismatch. Nothing installed.' }
    New-Item -ItemType Directory -Force -Path $bin | Out-Null
    Copy-Item -LiteralPath $source -Destination (Join-Path $bin 'mls.exe')
} else {
    throw 'Choose -FromSource (requires Cargo) or -ArtifactDirectory <verified local release assets>. Prebuilt assets are not downloaded or assumed published.'
}
Write-Output "CLI installed in $bin"
Write-Output 'Add that directory to your user PATH manually, or run:'
Write-Output "& '$bin\mls.exe' --repo '$repo' install"
Write-Output "& '$bin\mls.exe' --repo '$repo' start"
