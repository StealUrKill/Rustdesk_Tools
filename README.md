# RustDesk Tools

A PyQt6 GUI for managing RustDesk API servers. Provides a single interface for devices, users, groups, address books, strategies, audits, and config generation.

## Features

- **API Tab** - Manage devices, users, user groups, device groups, address books, strategies, and audit logs
- **Custom Tab** - Generate RustDesk config strings and QR codes, apply configs directly
- **Table View** - Sortable columns, per-column filter dropdowns, search, bulk actions (enable/disable/delete)
- **Dark Theme** - Customizable via `style.qss`

## Quick Start

### From Source

```bash
pip install -r requirements.txt
python src/rustdesk_tools.py
```

### Build Standalone Exe

```bash
pip install pyinstaller
python build.py
```

Output: `dist/RustDesk_Tools.exe`

## Project Structure

```
src/
  rustdesk_tools.py               # Main GUI
  devices.py                      # Device management API
  users.py                        # User management API
  user_groups.py                  # User group management API
  device_groups.py                # Device group management API
  ab.py                           # Address book management API
  strategies.py                   # Strategy management API
  audits.py                       # Audit log viewer API
  custom_config_generator.py      # Config string/QR generator
  api_scripts.json                # API module/field definitions
  style.qss                       # GUI stylesheet
  icon.svg                        # App icon (SVG)
  icon.ico                        # App icon (Windows)
windows_src/  
  custom_config_generator.ps1     # PowerShell config generator
  install_rustdesk.bat            # RustDesk installer batch script
  installrustdesknoprinter.ps1    # RustDesk installer (no printer)
```

## Windows PowerShell Scripts

The `windows_src/` folder contains standalone PowerShell/batch scripts that can be run directly without Python.

Run from a PowerShell console:

```powershell
irm https://raw.githubusercontent.com/StealUrKill/Rustdesk_Tools/refs/heads/main/windows_src/custom_config_generator.ps1 | iex
```

```powershell
irm https://raw.githubusercontent.com/StealUrKill/Rustdesk_Tools/refs/heads/main/windows_src/installrustdesknoprinter.ps1 | iex
```

## Requirements

- Python 3.10+
- PyQt6
- requests
