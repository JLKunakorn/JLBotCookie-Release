$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Name = "JLmain_V2.0.3_Premium"
$Stage = Join-Path $Root "release_stage"
$Obf = Join-Path $Stage "obf"
$Out = Join-Path $Root "dist"
$ZipStage = Join-Path $Stage "zip"
$Exe = Join-Path $Out "$Name.exe"
$Zip = Join-Path $Out "$Name.zip"
$Guide = Get-ChildItem -LiteralPath $Root -File -Filter "*JLmain_V1.0_Premium.txt" | Select-Object -First 1
if (-not $Guide) {
  throw "Premium user guide was not found."
}

Set-Location $Root

Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $Exe -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $Zip -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $Stage, $Obf, $ZipStage | Out-Null

python -m py_compile `
  bot.py `
  JLmain.py `
  license_core.py `
  run.py `
  treasure_extract_roi.py `
  adb_core.py `
  notification_settings.py `
  premium_multi.py `
  premium_notifier.py `
  premium_ocr.py `
  premium_runtime.py `
  premium_worker.py `
  screen_license_store.py `
  ClaimItems\MailLives\mail_lives_bot.py `
  ClaimItems\RelicClaim\relic_claim_bot.py

Copy-Item -LiteralPath (Join-Path $Root "assets") -Destination (Join-Path $Obf "assets") -Recurse
Copy-Item -LiteralPath (Join-Path $Root "templates") -Destination (Join-Path $Obf "templates") -Recurse
Copy-Item -LiteralPath (Join-Path $Root "treasure_extract_roi") -Destination (Join-Path $Obf "treasure_extract_roi") -Recurse
Copy-Item -LiteralPath (Join-Path $Root "adb_bundle") -Destination (Join-Path $Obf "adb_bundle") -Recurse
Copy-Item -LiteralPath (Join-Path $Root "license_config.json") -Destination (Join-Path $Obf "license_config.json")

pyinstaller --noconfirm --clean --onefile --windowed --optimize 2 --name $Name `
  --icon (Join-Path $Root "assets\app.ico") `
  --collect-all customtkinter `
  --collect-all darkdetect `
  --add-data "$($Obf)\license_config.json;." `
  --add-data "$($Obf)\assets;assets" `
  --add-data "$($Obf)\templates;templates" `
  --add-data "$($Root)\ClaimItems\MailLives\rules.json;ClaimItems\MailLives" `
  --add-data "$($Root)\ClaimItems\MailLives\templates;ClaimItems\MailLives\templates" `
  --add-data "$($Root)\ClaimItems\RelicClaim\rules.json;ClaimItems\RelicClaim" `
  --add-data "$($Root)\ClaimItems\RelicClaim\templates;ClaimItems\RelicClaim\templates" `
  --add-data "$($Obf)\treasure_extract_roi;treasure_extract_roi" `
  --add-data "$($Obf)\adb_bundle;adb_bundle" `
  --distpath $Out `
  --workpath (Join-Path $Stage "build") `
  --specpath $Stage `
  (Join-Path $Root "run.py")

Copy-Item -LiteralPath $Exe -Destination (Join-Path $ZipStage "$Name.exe")
Copy-Item -LiteralPath $Guide.FullName -Destination (Join-Path $ZipStage "How_to_use_JLmain_V2.0.3_Premium.txt")
Compress-Archive -Path (Join-Path $ZipStage "*") -DestinationPath $Zip -Force

Get-FileHash -Algorithm SHA256 $Exe, $Zip | Format-Table -AutoSize
