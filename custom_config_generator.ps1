$rdhost = Read-Host "Enter RustDesk host (example: yourdomain.com)"
Write-Host ""
$rdkey  = Read-Host "Enter RustDesk key"
Write-Host ""
$rdapi  = Read-Host "Enter RustDesk API (example: https://yourdomain.com)"


$json = '{"host":"' + $rdhost + '","key":"' + $rdkey + '","api":"' + $rdapi + '"}'
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
$chars = $b64.ToCharArray()
[Array]::Reverse($chars)
$code = -join $chars


Write-Host ""
$genQR = Read-Host "Generate QR? (y/n)"


if ($genQR -match '^(y|yes)$') {

	$qrText = "config=$json"
	$desktop = [Environment]::GetFolderPath("Desktop")
	$outFile = Join-Path $desktop "rustdesk_config_qr.png"

	$url = "https://api.qrserver.com/v1/create-qr-code/?size=240x240&margin=2&data=$([uri]::EscapeDataString($qrText))"
	Invoke-WebRequest -Uri $url -OutFile $outFile

	Write-Host ""
	Write-Host "QR saved to: $outFile"
	Write-Host ""
	Write-Host "QR content: $qrText"
}


Write-Host ""
Write-Host "Config String:"
Write-Host ""
$code | Set-Clipboard
Write-Host $code
Write-Host ""
Write-Host "(Config copied to clipboard)"
Write-Host ""
$apply = Read-Host "Apply this config to Rustdesk now? (y/n)"


if ($apply -match '^(y|yes)$') {
	$rdExe = "C:\Program Files\RustDesk\rustdesk.exe"

	if (Test-Path $rdExe) {
		Write-Host "Applying config to Rustdesk..."
		& $rdExe --config $code
	}
	else {
		Write-Host ""
		Write-Host "Rustdesk not found at:"
		Write-Host $rdExe
		Write-Host ""

		$customExe = Read-Host "Enter the full path to the Rustdesk executable or press Enter to cancel"

		if ($customExe -and (Test-Path $customExe)) {
			Write-Host "Applying config using custom executable for pro users"
			& $customExe --config $code
		}
		else {
			Write-Host "No valid executable provided. Skipping apply."
		}
	}
}
