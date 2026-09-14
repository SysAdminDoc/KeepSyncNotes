param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildDir = Join-Path $repoRoot "build"
$distDir = Join-Path $repoRoot "dist"

foreach ($target in @($buildDir, $distDir)) {
    $fullTarget = [System.IO.Path]::GetFullPath($target)
    if (-not $fullTarget.StartsWith($repoRoot + [System.IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to clear a build path outside the repository: $fullTarget"
    }
    if (Test-Path -LiteralPath $fullTarget) {
        Remove-Item -LiteralPath $fullTarget -Recurse -Force
    }
}

$versionLine = Select-String -LiteralPath (Join-Path $repoRoot "keepsync_app_info.py") -Pattern '^APP_VERSION = "([^"]+)"$'
if (-not $versionLine) {
    throw "Could not read APP_VERSION."
}
$version = $versionLine.Matches[0].Groups[1].Value

Push-Location $repoRoot
try {
    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --name KeepSyncNotes `
        --icon icon.ico `
        --version-file packaging\version_info.txt `
        --runtime-hook packaging\runtime_hook_mp.py `
        --add-data "icon.ico;." `
        --add-data "icon.png;." `
        --collect-all customtkinter `
        --collect-all tkinterdnd2 `
        keepsync_notes.py
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    $exe = Join-Path $distDir "KeepSyncNotes.exe"
    if (-not (Test-Path -LiteralPath $exe)) {
        throw "The packaged executable was not created."
    }

    $zipRoot = Join-Path $distDir "KeepSyncNotes-$version-windows-x64"
    New-Item -ItemType Directory -Force -Path $zipRoot | Out-Null
    Copy-Item -LiteralPath $exe, (Join-Path $repoRoot "README.md"), (Join-Path $repoRoot "LICENSE") -Destination $zipRoot
    $zip = "$zipRoot.zip"
    Compress-Archive -Path (Join-Path $zipRoot "*") -DestinationPath $zip -CompressionLevel Optimal

    $checksums = Join-Path $distDir "SHA256SUMS.txt"
    $hashLines = @($exe, $zip) | ForEach-Object {
        $stream = [System.IO.File]::OpenRead($_)
        try {
            $digest = [System.Security.Cryptography.SHA256]::Create().ComputeHash($stream)
        }
        finally {
            $stream.Dispose()
        }
        $hex = ([System.BitConverter]::ToString($digest) -replace '-', '').ToLowerInvariant()
        "$hex  $([System.IO.Path]::GetFileName($_))"
    }
    [System.IO.File]::WriteAllLines($checksums, $hashLines, [System.Text.UTF8Encoding]::new($false))

    Write-Output $exe
    Write-Output $zip
    Write-Output $checksums
}
finally {
    Pop-Location
}
