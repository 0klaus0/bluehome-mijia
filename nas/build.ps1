param([string]$Fnpack = 'fnpack')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$package = Join-Path $PSScriptRoot 'bluehome-mijia'
$target = Join-Path $package 'app/bluehome'
Copy-Item -LiteralPath (Join-Path $root 'LICENSE') -Destination (Join-Path $package 'LICENSE') -Force
New-Item -ItemType Directory -Force -Path (Join-Path $target 'server'), (Join-Path $target 'web') | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'server/requirements.txt') -Destination (Join-Path $target 'server/requirements.txt') -Force
Get-ChildItem -LiteralPath (Join-Path $root 'server') -Filter '*.py' |
  Where-Object { $_.Name -notlike 'test_*' } |
  Copy-Item -Destination (Join-Path $target 'server') -Force
Get-ChildItem -LiteralPath (Join-Path $root 'web') -File |
  Copy-Item -Destination (Join-Path $target 'web') -Force
$main = Join-Path $package 'cmd/main'
$normalized = [IO.File]::ReadAllText($main).Replace("`r`n", "`n").TrimEnd([char[]]@("`r", "`n")) + "`n"
[IO.File]::WriteAllText($main, $normalized, [Text.UTF8Encoding]::new($false))
Push-Location $package
try {
  & $Fnpack build
  if ($LASTEXITCODE -ne 0) { throw 'fnpack 打包失败' }
} finally { Pop-Location }
$fpk = Join-Path $package 'bluehome-mijia.fpk'
if (-not (Test-Path -LiteralPath $fpk)) { throw '未找到 fnpack 产物' }
Copy-Item -LiteralPath $fpk -Destination (Join-Path $root 'dist/bluehome-mijia-1.0.2.fpk') -Force
Write-Host "飞牛安装包: $(Join-Path $root 'dist/bluehome-mijia-1.0.2.fpk')"
