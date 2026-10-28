# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
<#! Build a real per-user Inno Setup installer from a verified native GTK bundle. #>
[CmdletBinding()]
param(
    [string]$Bundle = (Join-Path $PSScriptRoot '..\dist\bundles\windows-x86_64\RatioLab'),
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\dist\installers'),
    [string]$ISCC = '',
    [string]$CertificateThumbprint = '',
    [string]$TimestampServer = 'https://timestamp.digicert.com'
)
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Build the Windows installer on Windows using the native UCRT64 bundle.'
}
$Bundle = (Resolve-Path -LiteralPath $Bundle).Path
$ManifestPath = Join-Path $Bundle 'bundle-manifest.json'
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Manifest.format -ne 'ratiolab-bundle/1' -or $Manifest.system -ne 'windows' -or $Manifest.arch -ne 'x86_64' -or -not $Manifest.notices_complete) {
    throw 'A verified windows-x86_64 RatioLab bundle with complete notices is required.'
}
foreach ($Record in $Manifest.files) {
    if ([IO.Path]::IsPathRooted($Record.path) -or ($Record.path -split '/') -contains '..') {
        throw "Unsafe manifest path: $($Record.path)"
    }
    $File = Join-Path $Bundle $Record.path
    if (-not (Test-Path -LiteralPath $File)) { throw "Missing bundle file: $($Record.path)" }
    if ($Record.kind -eq 'file') {
        if ((Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Record.sha256) {
            throw "Modified bundle file: $($Record.path)"
        }
    } elseif ($Record.kind -eq 'symlink') {
        $Target = (Get-Item -LiteralPath $File).Target
        if ($Target -ne $Record.target) { throw "Modified bundle link: $($Record.path)" }
    } else { throw "Unknown manifest entry: $($Record.path)" }
}
$Expected = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($Record in $Manifest.files) {
    if (-not $Expected.Add(($Record.path -replace '/', '\'))) { throw "Duplicate manifest path: $($Record.path)" }
}
$Actual = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($File in Get-ChildItem -LiteralPath $Bundle -Recurse -Force) {
    $IsLink = ($File.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
    if ($File.PSIsContainer -and -not $IsLink) { continue }
    $Relative = $File.FullName.Substring($Bundle.Length + 1)
    if ($Relative -eq 'bundle-manifest.json') { continue }
    [void]$Actual.Add($Relative)
    if (-not $Expected.Contains($Relative)) {
        throw "Unexpected file in bundle: $Relative"
    }
}
if (-not $Actual.SetEquals($Expected)) { throw 'Bundle inventory does not match manifest files and symlinks.' }
$Executable = Join-Path $Bundle 'RatioLab.exe'
$Report = Join-Path ([IO.Path]::GetTempPath()) ("ratiolab-check-" + [guid]::NewGuid() + '.json')
$SavedPath = $env:PATH
$SavedGi = $env:GI_TYPELIB_PATH
$SavedDll = $env:PYGI_DLL_PATH
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    Remove-Item Env:GI_TYPELIB_PATH, Env:PYGI_DLL_PATH -ErrorAction SilentlyContinue
    $Process = Start-Process -FilePath $Executable -ArgumentList @('--self-test', '--report', ('"' + $Report + '"')) -Wait -PassThru
    if ($Process.ExitCode -ne 0) {
        $Details = if (Test-Path -LiteralPath $Report) { Get-Content -LiteralPath $Report -Raw } else { 'No report was produced' }
        throw "Frozen Windows self-test failed: $Details"
    }
    $Result = Get-Content -LiteralPath $Report -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Result.self_test -ne 'passed' -or -not $Result.bundled) { throw 'The executable did not prove a bundled runtime.' }
} finally {
    $env:PATH = $SavedPath
    if ($null -eq $SavedGi) { Remove-Item Env:GI_TYPELIB_PATH -ErrorAction SilentlyContinue } else { $env:GI_TYPELIB_PATH = $SavedGi }
    if ($null -eq $SavedDll) { Remove-Item Env:PYGI_DLL_PATH -ErrorAction SilentlyContinue } else { $env:PYGI_DLL_PATH = $SavedDll }
    Remove-Item -LiteralPath $Report -Force -ErrorAction SilentlyContinue
}
if (-not $ISCC) {
    $Compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($Compiler) { $ISCC = $Compiler.Source }
    else {
        $Candidates = @("${env:ProgramFiles(x86)}\Inno Setup *\ISCC.exe", "$env:ProgramFiles\Inno Setup *\ISCC.exe")
        $ISCC = Get-ChildItem -Path $Candidates -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
    }
}
if (-not $ISCC -or -not (Test-Path -LiteralPath $ISCC)) { throw 'Install Inno Setup 6.3+ on the build machine, or pass -ISCC.' }
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$OutputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$Icon = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\packaging\icons\RatioLab.ico')).Path
& $ISCC "/DBundleDir=$Bundle" "/DOutputDir=$OutputDirectory" "/DAppVersion=$($Manifest.version)" "/DSetupIcon=$Icon" (Join-Path $PSScriptRoot 'package-windows.iss')
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed with exit code $LASTEXITCODE" }
$Installer = Join-Path $OutputDirectory "RatioLab-$($Manifest.version)-windows-x86_64-setup.exe"
if (-not (Test-Path -LiteralPath $Installer)) { throw 'Inno Setup did not produce the expected installer.' }
if ($CertificateThumbprint) {
    $Certificate = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object Thumbprint -eq $CertificateThumbprint | Select-Object -First 1
    if (-not $Certificate) { throw 'The requested code-signing certificate is not present in CurrentUser/My.' }
    $Signature = Set-AuthenticodeSignature -FilePath $Installer -Certificate $Certificate -TimestampServer $TimestampServer
    if ($Signature.Status -ne 'Valid') { throw "Installer signing failed: $($Signature.StatusMessage)" }
}
$Hash = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath ($Installer + '.sha256') -Value "$Hash  $([IO.Path]::GetFileName($Installer))" -Encoding ascii
Write-Output $Installer
