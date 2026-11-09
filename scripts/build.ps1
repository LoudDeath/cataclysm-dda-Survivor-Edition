[CmdletBinding()]
param(
    [ValidateSet('Dependencies', 'Game', 'Tests', 'Formatter')]
    [string]$Target = 'Game',
    [ValidateSet('Release')]
    [string]$Configuration = 'Release',
    [string]$ToolchainRoot = 'C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools',
    [ValidateRange(1, 8)]
    [int]$Jobs = 1
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$buildRoot = Join-Path $root '.build'
$toolsRoot = Join-Path $root '.tools'
$logRoot = Join-Path $root 'audits\build'
$vcpkgRoot = Join-Path $toolsRoot 'vcpkg'
$vcpkgExe = Join-Path $vcpkgRoot 'vcpkg.exe'
$msbuild = Join-Path $ToolchainRoot 'MSBuild\Current\Bin\MSBuild.exe'
$vcvars = Join-Path $ToolchainRoot 'VC\Auxiliary\Build\vcvars64.bat'
$cmakeBin = Join-Path $toolsRoot 'cmake-3.31.8-windows-x86_64\bin'
$ninjaBin = Join-Path $ToolchainRoot 'Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja'
$archiveBin = Join-Path $toolsRoot 'vcpkg-downloads\tools\7zip-26.02-windows'
$gitBin = Split-Path -Parent (Get-Command git -ErrorAction Stop).Source
$manifest = Join-Path $root 'msvc-full-features'
$installed = Join-Path $manifest 'vcpkg_installed'

foreach ($required in @($vcpkgExe, $msbuild, $vcvars, (Join-Path $cmakeBin 'cmake.exe'))) {
    if (!(Test-Path -LiteralPath $required)) { throw "Required build tool is missing: $required" }
}
foreach ($directory in @($buildRoot, $logRoot, (Join-Path $toolsRoot 'vcpkg-downloads'),
        (Join-Path $toolsRoot 'vcpkg-binary-cache'), (Join-Path $toolsRoot 'vcpkg-registry'))) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$log = Join-Path $logRoot "$stamp-$Target.log"
$runner = Join-Path $buildRoot "build-$Target.cmd"
$common = @(
    '@echo off',
    'setlocal',
    "call `"$vcvars`"",
    'if errorlevel 1 exit /b %errorlevel%',
    "set `"PATH=$cmakeBin;$ninjaBin;$archiveBin;$gitBin;%PATH%`"",
    "set `"VCPKG_VISUAL_STUDIO_PATH=$ToolchainRoot`"",
    "set `"VCPKG_ROOT=$vcpkgRoot`"",
    "set `"VCPKG_DOWNLOADS=$(Join-Path $toolsRoot 'vcpkg-downloads')`"",
    "set `"VCPKG_DEFAULT_BINARY_CACHE=$(Join-Path $toolsRoot 'vcpkg-binary-cache')`"",
    'set "VCPKG_FORCE_SYSTEM_BINARIES=1"',
    'set "VCPKG_DISABLE_METRICS=1"',
    "set `"VCPKG_MAX_CONCURRENCY=$Jobs`"",
    "set `"_CL_=/MP$Jobs`"",
    "cd /d `"$manifest`""
)

if ($Target -eq 'Dependencies') {
    $command = "`"$vcpkgExe`" install --triplet=x64-windows-static --host-triplet=x64-windows-static --clean-after-build"
    $editionPorts = Join-Path $toolsRoot 'edition-ports'
    if (Test-Path -LiteralPath $editionPorts) {
        $command += " `"--overlay-ports=$editionPorts`""
    }
} else {
    $project = switch ($Target) {
        'Game' { 'Cataclysm-vcpkg-static.vcxproj' }
        'Tests' { 'Cataclysm-test-vcpkg-static.vcxproj' }
        'Formatter' { 'JsonFormatter-vcpkg-static.vcxproj' }
    }
    $props = Join-Path $vcpkgRoot 'scripts\buildsystems\msbuild\vcpkg.props'
    $targets = Join-Path $vcpkgRoot 'scripts\buildsystems\msbuild\vcpkg.targets'
    $vcpkgProperty = $vcpkgRoot.Replace('\', '/') + '/'
    $installedProperty = $installed.Replace('\', '/') + '/'
    $command = "`"$msbuild`" `"$project`" /nologo /m:1 /v:minimal /p:Configuration=$Configuration /p:Platform=x64 /p:PreferredToolArchitecture=x64 /p:CDDA_RELEASE_BUILD=true /p:VcpkgManifestInstall=false `"/p:ForceImportAfterCppProps=$props`" `"/p:ForceImportAfterCppTargets=$targets`" `"/p:VcpkgRoot=$vcpkgProperty`" `"/p:VcpkgInstalledDir=$installedProperty`""
}
$common += $command
$common += 'exit /b %errorlevel%'
[IO.File]::WriteAllLines($runner, $common, [Text.Encoding]::Default)

$started = Get-Date
Write-Host "Target: $Target; x64 $Configuration; log: $log"
Push-Location $root
try {
    & $env:ComSpec /d /c $runner 2>&1 | Tee-Object -FilePath $log
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
$record = [ordered]@{
    target = $Target
    configuration = $Configuration
    architecture = 'x64'
    jobs = $Jobs
    started_at = $started.ToString('o')
    finished_at = (Get-Date).ToString('o')
    exit_code = $code
    toolchain_root = $ToolchainRoot
    log = $log
}
$record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logRoot "latest-$Target.json") -Encoding utf8
if ($code -ne 0) { throw "Build target $Target failed (exit $code). See $log" }
