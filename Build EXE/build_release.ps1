$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Name = "JLmain_V1.0.2_Premium"
$Stage = Join-Path $Root "release_stage"
$Obf = Join-Path $Stage "obf"
$Out = Join-Path $Root "dist"
$ZipStage = Join-Path $Stage "zip"
$Exe = Join-Path $Out "$Name.exe"
$Zip = Join-Path $Out "$Name.zip"
$Guide = Get-ChildItem -LiteralPath $Root -File -Filter "*JLmain_V1.0_Premium.txt" | Select-Object -First 1

Set-Location $Root

Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $Exe -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $Zip -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $Stage, $Obf, $ZipStage | Out-Null

python -m py_compile bot.py JLmain.py license_core.py run.py

Copy-Item -LiteralPath (Join-Path $Root "assets") -Destination (Join-Path $Obf "assets") -Recurse
Copy-Item -LiteralPath (Join-Path $Root "templates") -Destination (Join-Path $Obf "templates") -Recurse
Copy-Item -LiteralPath (Join-Path $Root "adb_bundle") -Destination (Join-Path $Obf "adb_bundle") -Recurse
Copy-Item -LiteralPath (Join-Path $Root "license_config.json") -Destination (Join-Path $Obf "license_config.json")

pyinstaller --noconfirm --clean --onefile --windowed --optimize 2 --name $Name `
  --icon (Join-Path $Root "assets\app.ico") `
  --collect-all customtkinter `
  --collect-all darkdetect `
  --add-data "$($Obf)\license_config.json;." `
  --add-data "$($Obf)\assets;assets" `
  --add-data "$($Obf)\templates;templates" `
  --add-data "$($Obf)\adb_bundle;adb_bundle" `
  --distpath $Out `
  --workpath (Join-Path $Stage "build") `
  --specpath $Stage `
  (Join-Path $Root "run.py")

Copy-Item -LiteralPath $Exe -Destination (Join-Path $ZipStage "$Name.exe")
Copy-Item -LiteralPath $Guide.FullName -Destination (Join-Path $ZipStage "วิธีใช้งาน_JLmain_V1.0.2_Premium.txt")
Compress-Archive -Path (Join-Path $ZipStage "*") -DestinationPath $Zip -Force

Get-FileHash -Algorithm SHA256 $Exe, $Zip | Format-Table -AutoSize
