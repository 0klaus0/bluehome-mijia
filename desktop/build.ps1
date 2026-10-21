param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$web = Join-Path $root 'web'
$server = Join-Path $root 'server/connect_mijia.py'
$dist = Join-Path $root 'dist/windows'
$cache = Join-Path $root '.build/windows'
& $Python -m PyInstaller --noconfirm --clean --onedir --name Bluehome --distpath $dist --workpath (Join-Path $cache 'work') --specpath $cache --paths (Join-Path $root 'server') --add-data "$web;web" $server
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 构建失败' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Bluehome-LAN.cmd') -Destination (Join-Path $dist 'Bluehome/Bluehome-LAN.cmd') -Force
Write-Host "Windows 版本: $(Join-Path $dist 'Bluehome/Bluehome.exe')"
