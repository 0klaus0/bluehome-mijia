param([string]$Sdk = "$env:LOCALAPPDATA\Android\Sdk")
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$tools = Join-Path $Sdk 'build-tools\34.0.0'
$platform = Join-Path $Sdk 'platforms\android-34\android.jar'
$cache = Join-Path $root '.build\android'
$classes = Join-Path $cache 'classes'
$dex = Join-Path $cache 'dex'
$dist = Join-Path $root 'dist\android'
New-Item -ItemType Directory -Force $classes,$dex,$dist | Out-Null
$source = Join-Path $PSScriptRoot 'src\app\bluehome\companion\MainActivity.java'
& javac -encoding UTF-8 -source 8 -target 8 -Xlint:-options -classpath $platform -d $classes $source
if ($LASTEXITCODE -ne 0) { throw 'Java 编译失败' }
$classFiles = @(Get-ChildItem -LiteralPath $classes -Recurse -Filter '*.class' | ForEach-Object FullName)
& (Join-Path $tools 'd8.bat') --lib $platform --min-api 26 --output $dex $classFiles
if ($LASTEXITCODE -ne 0) { throw 'D8 编译失败' }
$unsigned = Join-Path $cache 'unsigned.apk'
& (Join-Path $tools 'aapt2.exe') link -o $unsigned --manifest (Join-Path $PSScriptRoot 'AndroidManifest.xml') -I $platform --min-sdk-version 26 --target-sdk-version 34 --version-code 3 --version-name 0.1.2
if ($LASTEXITCODE -ne 0) { throw 'Android 资源构建失败' }
& jar uf $unsigned -C $dex classes.dex
if ($LASTEXITCODE -ne 0) { throw 'APK 组装失败' }
$aligned = Join-Path $cache 'aligned.apk'
& (Join-Path $tools 'zipalign.exe') -f 4 $unsigned $aligned
if ($LASTEXITCODE -ne 0) { throw 'APK 对齐失败' }
$key = Join-Path $cache 'debug.keystore'
if (-not (Test-Path -LiteralPath $key)) {
    & keytool -genkeypair -keystore $key -storepass android -keypass android -alias androiddebugkey -dname 'CN=Bluehome Debug' -keyalg RSA -keysize 2048 -validity 10000
    if ($LASTEXITCODE -ne 0) { throw '调试签名生成失败' }
}
$apk = Join-Path $dist 'Bluehome-Android-debug.apk'
& (Join-Path $tools 'apksigner.bat') sign --ks $key --ks-pass pass:android --key-pass pass:android --out $apk $aligned
if ($LASTEXITCODE -ne 0) { throw 'APK 签名失败' }
& (Join-Path $tools 'apksigner.bat') verify --verbose $apk
if ($LASTEXITCODE -ne 0) { throw 'APK 签名校验失败' }
Write-Host "Android 版本: $apk"
