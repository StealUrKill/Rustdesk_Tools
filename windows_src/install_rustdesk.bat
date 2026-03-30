@echo off
:: BatchGotAdmin
::-------------------------------------
REM  --> Check for permissions
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"

REM --> If error flag set, we do not have admin.
if '%errorlevel%' NEQ '0' (
    echo Requesting administrative privileges...
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    set params = %*:"="
    echo UAC.ShellExecute "cmd.exe", "/c %~s0 %params%", "", "runas", 1 >> "%temp%\getadmin.vbs"

    "%temp%\getadmin.vbs"
    del "%temp%\getadmin.vbs"
    exit /B

:gotAdmin
    pushd "%CD%"
    CD /D "%~dp0"
::--------------------------------------

::ENTER YOUR CODE BELOW:

@echo off

CD /D "%~dp0"
CLS
del "%~dp0rustdesk.ps1"
IF NOT EXIST "%~dp0\rustdesk.ps1" GOTO COPYRUSTDESK

:START
CLS
setlocal EnableExtensions

REM     ONLY MODIFY FROM HERE
set "RUSTDESK_URL=https://github.com/rustdesk/rustdesk/releases/download/1.4.5/rustdesk-1.4.5-x86_64.exe"
set "RUSTDESK_SERVER=192.168.20.200"
set "RUSTDESK_KEY=NEW_PUBLIC_KEY_HERE"
set "USE_PERM_PASSWORD=Y"
set "SET_PASSWORD=Y"
set "PASSWORD=ChangePasswordIfSetToYAbove"
REM     TO HERE FOR MODIFICATIONS

set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "SCRIPT=%~dp0rustdesk.ps1"

if /I "%USE_PERM_PASSWORD%"=="Y" (
  if /I "%SET_PASSWORD%"=="Y" (
    "%PS%" -NoProfile -ExecutionPolicy Bypass ^
      -File "%SCRIPT%" ^
      -Url "%RUSTDESK_URL%" ^
      -Server "%RUSTDESK_SERVER%" ^
      -Key "%RUSTDESK_KEY%" ^
      -UsePermanentPassword ^
      -SetPassword ^
      -Password "%PASSWORD%"
  ) else (
    "%PS%" -NoProfile -ExecutionPolicy Bypass ^
      -File "%SCRIPT%" ^
      -Url "%RUSTDESK_URL%" ^
      -Server "%RUSTDESK_SERVER%" ^
      -Key "%RUSTDESK_KEY%" ^
      -UsePermanentPassword
  )
) else (
  if /I "%SET_PASSWORD%"=="Y" (
    "%PS%" -NoProfile -ExecutionPolicy Bypass ^
      -File "%SCRIPT%" ^
      -Url "%RUSTDESK_URL%" ^
      -Server "%RUSTDESK_SERVER%" ^
      -Key "%RUSTDESK_KEY%" ^
      -SetPassword ^
      -Password "%PASSWORD%"
  ) else (
    "%PS%" -NoProfile -ExecutionPolicy Bypass ^
      -File "%SCRIPT%" ^
      -Url "%RUSTDESK_URL%" ^
      -Server "%RUSTDESK_SERVER%" ^
      -Key "%RUSTDESK_KEY%"
  )
)

ping 127.0.0.1 -n 10 >nul
del "%~dp0rustdesk.ps1"
exit /b %errorlevel%


:COPYRUSTDESK
@echo off
cls
setlocal EnableExtensions DisableDelayedExpansion

set "out=%~dp0rustdesk.ps1"
set "line="

for /f "delims=:" %%N in ('findstr /n ":::BeginText" "%~f0"') do set "line=%%N"

if not defined line (
  echo ERROR: Marker :::BeginText not found.
  echo Showing matches containing BeginText for debugging:
  findstr /n /c:"BeginText" "%~f0"
  pause
  exit /b 1
)

set /a line=line+1

more +%line% "%~f0" > "%out%"

echo Wrote: "%out%"
powershell -NoProfile -Command "Get-Content -Path '%out%' -TotalCount 5"
goto START

:::BeginText

param(
    [Parameter(Mandatory=$true)]
    [string]$Url,

    [Parameter(Mandatory=$true)]
    [string]$Server,

    [Parameter(Mandatory=$true)]
    [string]$Key,

    [switch]$UsePermanentPassword,

    [switch]$SetPassword,

    [string]$Password
)

$TmpExe  = Join-Path $env:TEMP (Split-Path $Url -Leaf)
$ExePath = "$env:ProgramFiles\RustDesk\rustdesk.exe"

#Write-Host "Downloading RustDesk from $Url"
#Invoke-WebRequest -Uri $Url -OutFile $TmpExe -UseBasicParsing
#Start-BitsTransfer -Source $Url -Destination $TmpExe -Priority Foreground

$os = [Environment]::OSVersion.Version
if ($os.Major -eq 6) {
	# Force TLS 1.2 on older Windows
    Write-Host "Windows 7/8 detected - using WebClient (TLS 1.2 forced)..."
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    } catch {
        [Net.ServicePointManager]::SecurityProtocol = 3072
    }
    (New-Object Net.WebClient).DownloadFile($Url, $TmpExe)

}
else {

    Write-Host "Windows 10/11 detected - using BITS transfer..."
    Start-BitsTransfer -Source $Url -Destination $TmpExe -Priority Foreground

}

Write-Host "Installing RustDesk silently..."
Start-Process -FilePath $TmpExe -ArgumentList "--silent-install"

Start-Sleep -Seconds 5

Write-Host "Installing RustDesk service..."
Start-Process -FilePath $ExePath -ArgumentList "--install-service"
Start-Sleep -Seconds 5

Write-Host "Stopping RustDesk process..."
Get-Process rustdesk -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "Stopping RustDesk service..."
Get-Service | Where-Object { $_.Name -like "*rustdesk*" } |
    Where-Object { $_.Status -ne "Stopped" } |
    Stop-Service -Force

Start-Sleep -Seconds 5

$cfg = Join-Path $env:APPDATA 'rustdesk\config\rustdesk2.toml'

$timeout = 10
while (!(Test-Path $cfg) -and $timeout-- -gt 0) {
    Start-Sleep -Seconds 1
}

if (!(Test-Path $cfg)) {
    Write-Error "RustDesk config not found: $cfg"
    exit 1
}

$content = Get-Content $cfg -Raw


if ($content -notmatch '(?m)^\[options\]') {
    $content += "`n[options]"
}


if ($content -match '(?m)^custom-rendezvous-server\s*=') {
    $content = $content -replace `
        '(?m)^custom-rendezvous-server\s*=\s*''.*?''', `
        "custom-rendezvous-server = '$Server'"
}
else {
    $content = $content -replace `
        '(?m)^\[options\]', `
        "[options]`ncustom-rendezvous-server = '$Server'"
}


if ($content -match '(?m)^key\s*=') {
    $content = $content -replace `
        '(?m)^key\s*=\s*''.*?''', `
        "key = '$Key'"
}
else {
    $content = $content -replace `
        '(?m)^\[options\]', `
        "[options]`nkey = '$Key'"
}

if ($UsePermanentPassword) {
    $line = "verification-method = 'use-permanent-password'"

    if ($content -match '(?m)^verification-method\s*=') {
        $content = $content -replace `
            "(?m)^verification-method\s*=\s*'.*?'", `
            $line
    } else {
        $content = $content -replace `
            "(?m)^\[options\]", `
            "[options]`n$line"
    }
}


Set-Content -Path $cfg -Value $content -Encoding UTF8

Write-Host "RustDesk options updated successfully"

Write-Host "Starting RustDesk service..."
$svc = Get-Service | Where-Object { $_.Name -like "*rustdesk*" }

if ($svc) {
    if ($svc.Status -ne 'Running') {
        Start-Service -Name $svc.Name
    }
} else {
    Write-Warning "RustDesk service not found"
}

Write-Host "Starting RustDesk (detached via explorer.exe)..."
Start-Sleep -Seconds 5
Start-Process -FilePath "$env:WINDIR\explorer.exe" -ArgumentList "`"$ExePath`""
Start-Sleep -Seconds 5


if ($SetPassword) {
    if ([string]::IsNullOrWhiteSpace($Password)) {
        Write-Warning "SetPassword was requested but -Password is empty; skipping."
    } else {
        Write-Host "Setting RustDesk permanent password..."

		$wd = Split-Path $ExePath
		Push-Location $wd
		try {
			& $ExePath --password $Password 2>&1 | Out-Host -Paging
			$code = $LASTEXITCODE
		}
		finally {
			Pop-Location
		}		
    }
}
