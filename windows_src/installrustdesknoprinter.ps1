$ErrorActionPreference = "Stop"

$msiUrl = "https://github.com/rustdesk/rustdesk/releases/download/1.4.5/rustdesk-1.4.5-x86_64.msi"
$msiFile = "$env:TEMP\rustdesk.msi"

Write-Host "[+] Downloading RustDesk MSI..."
Invoke-RestMethod $msiUrl -OutFile $msiFile

Write-Host "[+] Installing RustDesk silently (no printer)..."

Start-Process msiexec.exe -Wait -ArgumentList @(
    "/i `"$msiFile`"",
    "/qn",
    "CREATESTARTMENUSHORTCUTS=Y",
    "CREATEDESKTOPSHORTCUTS=Y",
    "INSTALLPRINTER=N"
)

Write-Host "[+] RustDesk installed successfully."
