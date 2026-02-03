$json = '{"host":"yourdomain.com","key":"yourkey","api":"yourapi"}'

$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
$chars = $b64.ToCharArray()
[Array]::Reverse($chars)
$code = -join $chars

# generate qr code for mobile
$qrText  = "config=$json"
$desktop = [Environment]::GetFolderPath("Desktop")
$outFile = Join-Path $desktop "rustdesk_config_qr.png"
$url = "https://api.qrserver.com/v1/create-qr-code/?size=400x400&data=$([uri]::EscapeDataString($qrText))"
Invoke-WebRequest -Uri $url -OutFile $outFile

Write-Host "QR saved to: $outFile"
Write-Host "QR content: $qrText"
Write-Host "Config String: $code"