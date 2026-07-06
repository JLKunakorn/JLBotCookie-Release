param(
    [string]$Plan = "test1d",
    [int]$DurationDays = 1,
    [int]$DurationMinutes = 0,
    [int]$MaxSeats = 1,
    [string]$Hwid = "TEST-PC",
    [switch]$RevokeAfter
)

$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$AdminPath = Join-Path $Here "admin.local.json"

if (-not (Test-Path -LiteralPath $AdminPath)) {
    throw "Missing admin.local.json. Deploy setup must be completed first."
}

$Admin = Get-Content -LiteralPath $AdminPath -Raw -Encoding UTF8 | ConvertFrom-Json
$BaseUrl = [string]$Admin.worker_url
$BaseUrl = $BaseUrl.TrimEnd("/")
$AdminToken = [string]$Admin.admin_token

if (-not $BaseUrl -or -not $AdminToken) {
    throw "admin.local.json must contain worker_url and admin_token."
}

$AdminHeaders = @{
    "content-type"  = "application/json"
    "x-admin-token" = $AdminToken
}

$JsonHeaders = @{
    "content-type" = "application/json"
}

function ConvertFrom-LicensePayload {
    param($Response)

    $Raw = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Response.payload_b64))
    return $Raw | ConvertFrom-Json
}

Write-Host "Worker:" $BaseUrl
$Root = Invoke-RestMethod -Uri $BaseUrl
Write-Host "Mode:" $Root.mode

$MintBody = @{
    plan          = $Plan
    count         = 1
    max_seats     = $MaxSeats
    note          = "test_flow.ps1"
}
if ($DurationMinutes -gt 0) {
    $MintBody.duration_minutes = $DurationMinutes
} else {
    $MintBody.duration_days = $DurationDays
}
$MintBody = $MintBody | ConvertTo-Json -Compress

$Mint = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/admin/mint" -Headers $AdminHeaders -Body $MintBody
$Key = [string]$Mint.codes[0]
Write-Host "Minted stock key:" $Key

$VerifyBefore = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/verify" -Headers $JsonHeaders -Body (@{
    key  = $Key
    hwid = $Hwid
} | ConvertTo-Json -Compress)
$BeforePayload = ConvertFrom-LicensePayload $VerifyBefore
Write-Host "Before delivery:" "ok=$($BeforePayload.ok)" "msg=$($BeforePayload.msg)"

$OrderId = "TEST-" + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$DeliverBody = @{
    key          = $Key
    order_id     = $OrderId
    customer_ref = "test_flow"
} | ConvertTo-Json -Compress

$Deliver = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/admin/deliver-key" -Headers $AdminHeaders -Body $DeliverBody
Write-Host "Delivered:" "ok=$($Deliver.ok)" "status=$($Deliver.key.status)" "order=$OrderId"

$VerifyAfter = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/verify" -Headers $JsonHeaders -Body (@{
    key  = $Key
    hwid = $Hwid
} | ConvertTo-Json -Compress)
$AfterPayload = ConvertFrom-LicensePayload $VerifyAfter
Write-Host "After delivery:" "ok=$($AfterPayload.ok)" "plan=$($AfterPayload.plan)" "exp=$($AfterPayload.exp)"
Write-Host "Full Payload:" ($AfterPayload | ConvertTo-Json)

if ($RevokeAfter) {
    $Revoke = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/admin/revoke" -Headers $AdminHeaders -Body (@{
        key = $Key
    } | ConvertTo-Json -Compress)
    Write-Host "Revoked:" "ok=$($Revoke.ok)"
}

Write-Host ""
Write-Host "Use this key in GUI:" $Key
