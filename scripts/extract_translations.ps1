[CmdletBinding()]
param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$gettext = Join-Path $root '.tools\gettext-1.0\bin'
$report = Join-Path $root 'audits\localization'
$work = Join-Path $root '.build\localization'
foreach ($name in @('xgettext.exe', 'msguniq.exe')) {
    if (!(Test-Path -LiteralPath (Join-Path $gettext $name))) { throw "Missing gettext tool: $name; restore edition/gettext.lock.json" }
}
New-Item -ItemType Directory -Path $report,$work -Force | Out-Null
$sourceList = Join-Path $work 'cpp-sources.txt'
$files = Get-ChildItem -LiteralPath (Join-Path $root 'src') -File |
    Where-Object { $_.Extension -in @('.cpp', '.h') } |
    Sort-Object Name | ForEach-Object { 'src/' + $_.Name }
[IO.File]::WriteAllLines($sourceList, [string[]]$files, [Text.UTF8Encoding]::new($false))
$cppPot = Join-Path $report 'cpp-source.pot'
$combinedPot = Join-Path $work 'combined-source.pot'
$finalPot = Join-Path $report 'current-source.pot'
$pendingPot = Join-Path $work 'current-source.pending.pot'
$xgettextArgs = @('--default-domain=cataclysm-dda', '--add-comments=~', '--sort-by-file',
    '--from-code=UTF-8', '--keyword=_', '--keyword=pgettext:1c,2', '--keyword=n_gettext:1,2',
    '--keyword=npgettext:1c,2,3', '--keyword=translate_marker', '--keyword=translate_marker_context:1c,2',
    '--keyword=to_translation:1,1t', '--keyword=to_translation:1c,2,2t', '--keyword=pl_translation:1,2,2t',
    '--keyword=pl_translation:1c,2,3,3t', "--files-from=$sourceList", "--output=$cppPot")
$jsonArgs = @('lang/extract_json_strings.py', '-i', 'data', '-i', 'data/json', '-i', 'data/mods',
    '-x', 'data/mods/TEST_DATA', '-X', 'data/json/furniture_and_terrain/terrain-regional-pseudo.json',
    '-X', 'data/json/furniture_and_terrain/furniture-regional-pseudo.json',
    '-X', 'data/json/items/book/abstract.json', '-X', 'data/json/npcs/TALK_TEST.json',
    '-X', 'data/core/sentinels.json', '-X', 'data/raw/color_templates/no_bright_background.json',
    '-X', 'data/mods/Magiclysm/Spells/debug.json', '-n', 'Cataclysm-DDA 0.I Survivor Edition', '-r', $combinedPot)
$oldPythonPath = $env:PYTHONPATH
$oldEpoch = $env:SOURCE_DATE_EPOCH
Push-Location $root
try {
    $env:PYTHONPATH = Join-Path $root '.tools\python-packages'
    $env:SOURCE_DATE_EPOCH = (& git show -s --format=%ct 27939e29b8b4ddc081490d9f51de59a459c88df6)
    & (Join-Path $gettext 'xgettext.exe') @xgettextArgs 2> (Join-Path $report 'xgettext-stderr.log')
    if ($LASTEXITCODE -ne 0) { throw 'C++ string extraction failed; see xgettext-stderr.log' }
    Copy-Item -LiteralPath $cppPot -Destination $combinedPot -Force
    & $Python @jsonArgs
    if ($LASTEXITCODE -ne 0) { throw 'Upstream JSON string extraction failed' }
    & (Join-Path $gettext 'msguniq.exe') '--output' $pendingPot $combinedPot
    if ($LASTEXITCODE -ne 0) { throw 'POT unification failed' }
    & $Python lang/unicode_check.py $pendingPot
    if ($LASTEXITCODE -ne 0) { throw 'POT Unicode validation failed' }
    [IO.File]::Move($pendingPot, $finalPot, $true)
    [ordered]@{
        upstream_commit = '27939e29b8b4ddc081490d9f51de59a459c88df6'
        cpp_files = $files.Count
        scope = 'Exact lang/update_pot.sh keywords and JSON exclusions; src root .cpp/.h'
        gettext_version = '1.0'
        pot = 'audits/localization/current-source.pot'
        sha256 = (Get-FileHash -LiteralPath $finalPot -Algorithm SHA256).Hash.ToLowerInvariant()
        extraction = 'PASS'
        runtime = 'UNKNOWN'
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $report 'extraction.json') -Encoding utf8
} finally {
    $env:PYTHONPATH = $oldPythonPath
    $env:SOURCE_DATE_EPOCH = $oldEpoch
    Pop-Location
}
Write-Host "Extracted current source strings: $finalPot"
