param(
    [string]$PythonArchive,
    [string]$OutputDirectory,
    [switch]$Replace
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$version = [IO.File]::ReadAllText((Join-Path $root 'VERSION')).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'VERSION must contain a semantic release version.' }
$buildNumber = if ($env:GITHUB_RUN_NUMBER -match '^\d+$') { $env:GITHUB_RUN_NUMBER } else { '1' }
$preview = 'preview.'+$buildNumber
$lock = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'python-runtime.lock.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (!$OutputDirectory) { $OutputDirectory = Join-Path $root ('dist\windows-'+$version+'-preview') }
$output = [IO.Path]::GetFullPath($OutputDirectory)
if ($output.TrimEnd('\') -eq $root.TrimEnd('\')) { throw 'Choose a generated output directory outside the source root.' }
$marker = Join-Path $output '.mission-windows-build-output'
$app = Join-Path $output 'app'
$scratch = Join-Path $output 'build-work'
if ((Test-Path -LiteralPath $app) -or (Test-Path -LiteralPath $scratch)) {
    if (!$Replace -or !(Test-Path -LiteralPath $marker) -or (Get-Content -LiteralPath $marker -Raw).Trim() -ne 'CodexMissionManager Windows generated build') {
        throw 'Output already contains a build. Choose another directory, or use -Replace on a marked generated build.'
    }
    foreach ($path in @($app, $scratch)) { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force } }
}
New-Item -ItemType Directory -Path $output -Force | Out-Null
Set-Content -LiteralPath $marker -Value 'CodexMissionManager Windows generated build' -Encoding ASCII
New-Item -ItemType Directory -Path $app,$scratch -Force | Out-Null

if (!$PythonArchive) {
    $PythonArchive = Join-Path $env:TEMP ('mission-python-' + $lock.version + '-embed-amd64.zip')
    $fetch = !(Test-Path -LiteralPath $PythonArchive)
    if (!$fetch) { $fetch = (Get-FileHash -LiteralPath $PythonArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $lock.sha256 }
    if ($fetch) {
        Write-Output ('Downloading pinned Python runtime ' + $lock.version)
        Invoke-WebRequest -UseBasicParsing -Uri $lock.url -OutFile $PythonArchive
    }
}
$PythonArchive = (Resolve-Path -LiteralPath $PythonArchive).Path
$hash = (Get-FileHash -LiteralPath $PythonArchive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($hash -ne $lock.sha256) { throw 'The Python runtime archive does not match the pinned official SHA256.' }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$runtime = Join-Path $app 'runtime\python'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
[IO.Compression.ZipFile]::ExtractToDirectory($PythonArchive,$runtime)
$pth = Get-ChildItem -LiteralPath $runtime -Filter 'python*._pth' | Select-Object -First 1
if (!$pth) { throw 'The embedded Python archive does not contain an isolated path configuration.' }
# All entries are application-relative. No global Python, pip, PATH or user site.
$standardZip = (Get-ChildItem -LiteralPath $runtime -Filter 'python*.zip' | Select-Object -First 1).Name
[IO.File]::WriteAllText($pth.FullName, ($standardZip + "`r`n.`r`n../../backend`r`n"), (New-Object Text.UTF8Encoding($false)))

$backend = Join-Path $app 'backend'
New-Item -ItemType Directory -Path $backend -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $root 'backend') -File | Where-Object { $_.Extension -eq '.py' -or $_.Name -eq 'config.example.json' } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $backend $_.Name)
}
Copy-Item -LiteralPath (Join-Path $root 'third-party') -Destination (Join-Path $app 'third-party') -Recurse
Copy-Item -LiteralPath (Join-Path $root 'VERSION') -Destination (Join-Path $app 'VERSION')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'python-runtime.lock.json') -Destination (Join-Path $app 'python-runtime.lock.json')
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'INSTALL_README.md')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'INSTALL_README.md') -Destination (Join-Path $app 'README.md')
}
if (Test-Path -LiteralPath (Join-Path $root 'docs\USER_GUIDE.md')) {
    Copy-Item -LiteralPath (Join-Path $root 'docs\USER_GUIDE.md') -Destination (Join-Path $app 'USER_GUIDE.md')
}
$defaults = Get-Content -LiteralPath (Join-Path $backend 'config.example.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($defaults.poll_seconds -ne 30 -or $defaults.near_limit_poll_seconds -ne 10) { throw 'Packaged polling defaults must be 30/10 seconds.' }
if ((Test-Path -LiteralPath (Join-Path $backend 'config.json')) -or (Test-Path -LiteralPath (Join-Path $app 'auth.json'))) { throw 'Private runtime data must not be packaged.' }

$framework = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319'
$compiler = Join-Path $framework 'csc.exe'
if (!(Test-Path -LiteralPath $compiler)) { throw 'The Windows .NET Framework x64 C# compiler is unavailable.' }
$wpf = Join-Path $framework 'WPF'
$references = @('System.dll','System.Core.dll','System.Net.Http.dll','System.Web.Extensions.dll','System.Xaml.dll','System.Windows.Forms.dll','System.Drawing.dll') | ForEach-Object { Join-Path $framework $_ }
$references += @('PresentationFramework.dll','PresentationCore.dll','WindowsBase.dll') | ForEach-Object { Join-Path $wpf $_ }
foreach ($reference in $references) { if (!(Test-Path -LiteralPath $reference)) { throw ('Required Windows framework assembly is missing: '+$reference) } }
$icon = Join-Path $scratch 'AppIcon.ico'
$brandIcon = Join-Path $PSScriptRoot 'Assets\AppIcon.ico'
if (!(Test-Path -LiteralPath $brandIcon)) { throw 'The TokenMax brand icon is missing.' }
Copy-Item -LiteralPath $brandIcon -Destination $icon
$appManifest = Join-Path $scratch 'app.manifest'
$manifestSource = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'app.manifest')) -replace '(assemblyIdentity version=")[^"]+', ('${1}'+$version+'.0')
[IO.File]::WriteAllText($appManifest,$manifestSource,(New-Object Text.UTF8Encoding($false)))
$common = @('/nologo','/target:winexe','/platform:x64','/optimize+','/utf8output','/codepage:65001',('/win32manifest:'+$appManifest),('/win32icon:'+$icon))
$versionInfo = Join-Path $scratch 'VersionInfo.cs'
$fileBuild = [Math]::Min(65534,[int]$buildNumber)
$versionSource = '[assembly: System.Reflection.AssemblyVersion("'+$version+'.0")][assembly: System.Reflection.AssemblyFileVersion("'+$version+'.'+$fileBuild+'")][assembly: System.Reflection.AssemblyInformationalVersion("'+$version+'-'+$preview+'")][assembly: System.Reflection.AssemblyProduct("TokenMax")]'
[IO.File]::WriteAllText($versionInfo,$versionSource,(New-Object Text.UTF8Encoding($false)))
$appArgs = $common + @('/out:'+(Join-Path $app 'CodexMissionManager.exe')) + ($references | ForEach-Object { '/reference:'+$_ }) + @((Join-Path $PSScriptRoot 'MissionManager.cs'),(Join-Path $PSScriptRoot 'JuicerLogo.cs'),$versionInfo)
Write-Output 'Compiling native Windows application'
& $compiler @appArgs
if ($LASTEXITCODE -ne 0) { throw 'Native application compilation failed.' }

$python = Join-Path $runtime 'python.exe'
Write-Output 'Checking embedded Python and isolated backend imports'
& $python -X utf8 -I (Join-Path $backend 'app_host.py') --self-test
if ($LASTEXITCODE -ne 0) { throw 'Embedded backend self-test failed.' }
$nativeReceipt = Join-Path $scratch 'native-self-test.json'
$nativeTest = Start-Process -FilePath (Join-Path $app 'CodexMissionManager.exe') -ArgumentList @('--self-test',('"'+$nativeReceipt+'"')) -Wait -PassThru
if ($nativeTest.ExitCode -ne 0 -or !(Test-Path -LiteralPath $nativeReceipt)) { throw 'Native application self-test failed or produced no receipt.' }
$nativeResult = Get-Content -LiteralPath $nativeReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
if (!$nativeResult.native -or $nativeResult.webView -or $nativeResult.hostStarted -or !$nativeResult.brandPresentationChecks) { throw 'Native self-test did not satisfy the no-WebView/no-background-host contract.' }

$manifest = [ordered]@{
    version=$version; preview=$preview; build_number=$buildNumber; platform='windows'; architecture='x64'
    minimum_windows='10.0.19041'; framework='.NET Framework 4.8 or later'; framework_bundled=$false
    ui='WPF'; webview=$false; product='TokenMax'; product_zh=('TOKEN' + [char]0x69A8 + [char]0x6C41 + [char]0x673A); brand_identity_version='1.2.0'; python=$lock.version; python_distribution=$lock.distribution; python_sha256=$lock.sha256
    python_bundled=$true; private_runtime_data_included=$false; signing='unsigned-preview'
    normal_poll_delay_seconds=30; near_limit_or_pending_plan_poll_delay_seconds=10; ui_poll_seconds=5
    configurable_rules=$true; theme_accents=@('green','blue','purple','yellow'); chat_sources=@('codex')
    data_directory='%LOCALAPPDATA%\CodexMissionManager'; install_scope='current-user'
    per_user_uninstaller=$true; uninstall_preserves_private_data=$true
    external_dependency='Compatible installed Codex desktop client and user sign-in'
    source_commit=if ($env:GITHUB_SHA -match '^[0-9a-f]{40}$') { $env:GITHUB_SHA } else { $null }
}
$manifestPath = Join-Path $output 'build-manifest.json'
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $app 'build-manifest.json')

$portableName = 'TokenMax-'+$version+'-windows-x64-preview.zip'
$portable = Join-Path $output $portableName
if (Test-Path -LiteralPath $portable) { Remove-Item -LiteralPath $portable -Force }
[IO.Compression.ZipFile]::CreateFromDirectory($app,$portable,[IO.Compression.CompressionLevel]::Optimal,$false)
$payloadSha = (Get-FileHash -LiteralPath $portable -Algorithm SHA256).Hash.ToLowerInvariant()
$payloadBytes = (Get-Item -LiteralPath $portable).Length
$installerSource = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'Installer.cs') -Raw -Encoding UTF8).Replace('__PAYLOAD_SHA256__',$payloadSha).Replace('__PAYLOAD_BYTES__',$payloadBytes.ToString([Globalization.CultureInfo]::InvariantCulture)).Replace('__PRODUCT_VERSION__',$version).Replace('__PRODUCT_PREVIEW__',$preview)
$installerCs = Join-Path $scratch 'Installer.cs'
[IO.File]::WriteAllText($installerCs,$installerSource,(New-Object Text.UTF8Encoding($false)))
$stub = Join-Path $scratch 'InstallerStub.exe'
$installerRefs = @('System.dll','System.Core.dll','System.Drawing.dll','System.Windows.Forms.dll','System.Web.Extensions.dll','System.IO.Compression.dll','System.IO.Compression.FileSystem.dll') | ForEach-Object { '/reference:'+(Join-Path $framework $_) }
$installerArgs = $common + @('/out:'+$stub) + $installerRefs + @($installerCs,$versionInfo)
& $compiler @installerArgs
if ($LASTEXITCODE -ne 0) { throw 'Native installer compilation failed.' }
$setup = Join-Path $output ('TokenMax-'+$version+'-windows-x64-setup.exe')
Copy-Item -LiteralPath $stub -Destination $setup -Force
$target = [IO.File]::Open($setup,[IO.FileMode]::Append,[IO.FileAccess]::Write,[IO.FileShare]::None)
try {
    $payloadStream = [IO.File]::OpenRead($portable)
    try { $payloadStream.CopyTo($target) } finally { $payloadStream.Dispose() }
    $lengthBytes = [BitConverter]::GetBytes([Int64]$payloadBytes)
    $target.Write($lengthBytes,0,$lengthBytes.Length)
    $magic = [Text.Encoding]::ASCII.GetBytes('CMM-PAYLOAD-0001')
    $target.Write($magic,0,$magic.Length)
} finally { $target.Dispose() }
$installerReceipt = Join-Path $scratch 'installer-self-test.json'
$installerStdout = Join-Path $scratch 'installer-self-test.stdout.log'
$installerStderr = Join-Path $scratch 'installer-self-test.stderr.log'
$installerTest = Start-Process -FilePath $setup -ArgumentList @('--self-test',('"'+$installerReceipt+'"')) -RedirectStandardOutput $installerStdout -RedirectStandardError $installerStderr -Wait -PassThru
if ($installerTest.ExitCode -ne 0 -or !(Test-Path -LiteralPath $installerReceipt)) {
    Write-Output ('Installer self-test exit code: '+$installerTest.ExitCode)
    foreach ($diagnosticPath in @($installerReceipt,$installerStdout,$installerStderr)) {
        if (Test-Path -LiteralPath $diagnosticPath) {
            Write-Output ('Installer diagnostic: '+[IO.Path]::GetFileName($diagnosticPath))
            Get-Content -LiteralPath $diagnosticPath -Raw -Encoding UTF8 | Write-Output
        }
    }
    throw 'Appended installer integrity self-test failed. See isolated fixture diagnostics above.'
}
$installerResult = Get-Content -LiteralPath $installerReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
if ($installerResult.version -ne $version -or $installerResult.preview -ne $preview -or !$installerResult.payload_verified -or !$installerResult.shortcut_migration_checks -or $installerResult.installed -or $installerResult.host_started) { throw 'Installer self-test attempted installation or failed payload validation.' }

$sumLines = @($portable,$setup,$manifestPath) | ForEach-Object {
    (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()+'  '+[IO.Path]::GetFileName($_)
}
[IO.File]::WriteAllText((Join-Path $output 'SHA256SUMS'),(($sumLines -join "`n")+"`n"),(New-Object Text.UTF8Encoding($false)))
Write-Output ('APP_READY '+(Join-Path $app 'CodexMissionManager.exe'))
Write-Output ('SETUP_READY '+$setup)
Write-Output ('PORTABLE_READY '+$portable)
