<#
.SYNOPSIS
    Build the distributable Hung Phat Accounting Suite package.

.DESCRIPTION
    Runs PyInstaller against packaging/ketoan.spec, then zips the resulting
    one-folder distribution so it can be uploaded and handed to users. If Inno
    Setup 6 is installed, -Installer additionally compiles a setup .exe.

.EXAMPLE
    .\packaging\build.ps1
    .\packaging\build.ps1 -Clean -Installer
#>
[CmdletBinding()]
param(
    # Delete build/ and dist/ first. Use after changing the spec or deps.
    [switch]$Clean,
    # Also compile packaging/installer.iss (requires Inno Setup 6).
    [switch]$Installer,
    # Interpreter holding PySide6 + PyInstaller. Defaults to the venv the app
    # runs from (the sibling .venv, not a project-local one).
    [string]$Python = "C:\Users\ADMIN\PycharmProjects\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root "dist"
$work = Join-Path $root "build"
$appDir = Join-Path $dist "HungPhatAccounting"

if (-not (Test-Path $Python)) {
    throw "Khong tim thay Python: $Python  (dung -Python de chi dinh)"
}

# Read the version straight from pyproject so the zip name never drifts.
$match = Select-String -Path (Join-Path $root "pyproject.toml") `
    -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
$version = if ($match) { $match.Matches[0].Groups[1].Value } else { "0.0.0" }

Write-Host "==> Hung Phat Accounting $version" -ForegroundColor Cyan

& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "==> Cai PyInstaller..." -ForegroundColor Yellow
    & $Python -m pip install "pyinstaller>=6.16"
    if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller that bai" }
}

if ($Clean) {
    Write-Host "==> Xoa build/ va dist/" -ForegroundColor Yellow
    foreach ($p in @($work, $dist)) {
        if (Test-Path $p) { Remove-Item $p -Recurse -Force }
    }
}

Write-Host "==> PyInstaller..." -ForegroundColor Yellow
& $Python -m PyInstaller (Join-Path $PSScriptRoot "ketoan.spec") `
    --noconfirm --distpath $dist --workpath $work --log-level WARN
if ($LASTEXITCODE -ne 0) { throw "PyInstaller that bai" }

$exe = Join-Path $appDir "HungPhatAccounting.exe"
if (-not (Test-Path $exe)) { throw "Khong sinh ra $exe" }

# Smoke test: a missing Qt plugin or data file shows up as an instant exit,
# so a build that dies here must never be shipped.
Write-Host "==> Kiem tra khoi dong..." -ForegroundColor Yellow
$proc = Start-Process $exe -PassThru
Start-Sleep -Seconds 12
if ($proc.HasExited) {
    throw "App thoat ngay khi khoi dong (ma loi $($proc.ExitCode)) - khong dong goi."
}
Stop-Process -Id $proc.Id -Force
Write-Host "    OK - cua so mo binh thuong." -ForegroundColor Green

# Ships beside the .exe so the first thing a user sees after unzipping is how
# to run it and where their data lives.
Copy-Item (Join-Path $PSScriptRoot "HUONG-DAN.txt") `
    -Destination (Join-Path $appDir "HUONG DAN.txt") -Force

$zip = Join-Path $dist "HungPhatAccounting-$version-win64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Write-Host "==> Nen ZIP..." -ForegroundColor Yellow
Compress-Archive -Path $appDir -DestinationPath $zip -CompressionLevel Optimal

# PyInstaller leaves a bare copy of the .exe in the work directory. It has no
# _internal\ beside it, so double-clicking it fails with "Failed to load Python
# DLL" — delete it so the only runnable .exe on disk is the real one in dist\.
# PyInstaller simply rebuilds it next time.
$stub = Join-Path $work "ketoan\HungPhatAccounting.exe"
if (Test-Path $stub) { Remove-Item $stub -Force }

if ($Installer) {
    $iscc = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) {
        Write-Warning "Chua cai Inno Setup 6 - bo qua installer. Tai: https://jrsoftware.org/isdl.php"
    } else {
        Write-Host "==> Inno Setup..." -ForegroundColor Yellow
        & $iscc "/DAppVersion=$version" (Join-Path $PSScriptRoot "installer.iss")
        if ($LASTEXITCODE -ne 0) { throw "ISCC that bai" }
    }
}

Write-Host ""
Write-Host "==> Xong. San pham trong dist\:" -ForegroundColor Cyan
Get-ChildItem $dist -File | ForEach-Object {
    "{0,-46} {1,8:N1} MB" -f $_.Name, ($_.Length / 1MB)
}
