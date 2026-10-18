param(
    [string]$JavaHome = $env:JAVA_HOME,
    [string]$MavenPath,
    [string]$MavenRepository,
    [string]$CodexPath,
    [switch]$CpuOnly,
    [switch]$SkipBuild
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$localRoot = Join-Path $repoRoot '.windows-local'
$support = Join-Path $localRoot 'support'
if (-not $JavaHome) { throw 'Specify -JavaHome with a JDK 21 installation, or set JAVA_HOME.' }
$JavaHome = (Resolve-Path -LiteralPath $JavaHome).Path
foreach ($tool in @('java.exe', 'javac.exe', 'jar.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $JavaHome "bin/$tool"))) { throw "JDK tool missing: $tool" }
}
if (-not $MavenPath) { $MavenPath = (Get-Command mvn.cmd -ErrorAction Stop).Source }
$MavenPath = (Resolve-Path -LiteralPath $MavenPath).Path
if (-not $CpuOnly -and -not $CodexPath) {
    $codexCommand = Get-Command codex -ErrorAction Stop
    if ([IO.Path]::GetExtension($codexCommand.Source) -eq '.exe') {
        $CodexPath = $codexCommand.Source
    } else {
        # Supported npm installation layout; other installations must pass -CodexPath explicitly.
        $CodexPath = Join-Path (Split-Path -Parent $codexCommand.Source) 'node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe'
    }
}
if (-not $CpuOnly) { $CodexPath = (Resolve-Path -LiteralPath $CodexPath).Path }
if (-not $MavenRepository) { $MavenRepository = Join-Path $localRoot 'm2' }
New-Item -ItemType Directory -Force -Path $support, (Join-Path $support 'classes'), (Join-Path $localRoot 'runtime-home'), (Join-Path $localRoot 'player-sandbox'), $MavenRepository | Out-Null
$MavenRepository = (Resolve-Path -LiteralPath $MavenRepository).Path
$env:JAVA_HOME = $JavaHome
$env:PATH = (Join-Path $JavaHome 'bin') + ';' + (Split-Path -Parent $MavenPath) + ';' + $env:PATH
Push-Location $repoRoot
try {
    if (-not $SkipBuild) {
        & uv sync --frozen
        if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
        & $MavenPath "-Dmaven.repo.local=$MavenRepository" '-Dmaven.build.cache.enabled=false' -B -DskipTests -pl Mage.Server,Mage.Client,Mage.Client.Bridge,Mage.Client.Observer -am install
        if ($LASTEXITCODE -ne 0) { throw 'XMage Java build failed.' }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot '.venv/Scripts/python.exe'))) { throw 'Python environment missing; run Setup without -SkipBuild.' }
    $classpathFile = Join-Path $support 'gui-classpath.txt'
    & $MavenPath "-Dmaven.repo.local=$MavenRepository" -q -f Mage.Client.Observer/pom.xml dependency:build-classpath "-Dmdep.outputFile=$classpathFile"
    if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the GUI dependency classpath.' }
    $classpath = [IO.File]::ReadAllText($classpathFile).Trim()
    $classes = Join-Path $support 'classes'
    & (Join-Path $JavaHome 'bin/javac.exe') -proc:none -encoding UTF-8 -cp $classpath -d $classes (Join-Path $PSScriptRoot 'java/IsolatedPreferencesFactory.java') (Join-Path $PSScriptRoot 'java/HumanGui.java') (Join-Path $PSScriptRoot 'java/PreferencesProbe.java')
    if ($LASTEXITCODE -ne 0) { throw 'Windows Java helper compilation failed.' }
    $preferencesJar = Join-Path $support 'isolated-preferences.jar'
    & (Join-Path $JavaHome 'bin/jar.exe') --create --file $preferencesJar -C $classes 'experiment/IsolatedPreferencesFactory.class' -C $classes 'experiment/IsolatedPreferencesFactory$MemoryPreferences.class'
    if ($LASTEXITCODE -ne 0) { throw 'Could not package the isolated preferences helper.' }
    & (Join-Path $JavaHome 'bin/java.exe') "-Xbootclasspath/a:$preferencesJar" '-Djava.util.prefs.PreferencesFactory=experiment.IsolatedPreferencesFactory' -cp $classes PreferencesProbe
    if ($LASTEXITCODE -ne 0) { throw 'The preferences isolation check failed.' }
    $settings = [ordered]@{ java_home=$JavaHome; maven_path=$MavenPath; maven_repository=$MavenRepository; codex_executable=$CodexPath }
    [IO.File]::WriteAllText((Join-Path $localRoot 'settings.json'), ($settings | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
    Write-Output 'Windows setup ready. Runtime files are ignored under .windows-local. No credentials were copied.'
} finally { Pop-Location }
