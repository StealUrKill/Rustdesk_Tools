#!/usr/bin/env python3
"""
Build script for RustDesk Tools
Creates a standalone executable using PyInstaller

Usage:
    pip install pyinstaller
    python build.py
"""

import os
import subprocess
import sys
import tempfile

SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
ICON_FILE = os.path.join(SRC_DIR, "icon.ico")

VERSION = "1.0.0"

# Hidden imports that PyInstaller might miss (imported via importlib)
HIDDEN_IMPORTS = [
    "device_groups",
    "user_groups",
]

# Data files (non-python) to bundle
DATA_FILES = [
    "style.qss",
    "api_scripts.json",
    "icon.svg",
    "icon.ico",
]


def make_version_file():
    """Create a temporary PyInstaller version-info file."""
    parts = VERSION.split(".")
    while len(parts) < 4:
        parts.append("0")
    p = [int(x) for x in parts[:4]]
    file_version = ".".join(str(x) for x in p)

    content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({p[0]}, {p[1]}, {p[2]}, {p[3]}),
    prodvers=({p[0]}, {p[1]}, {p[2]}, {p[3]}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('CompanyName', 'RustDesk Tools'),
            StringStruct('FileDescription', 'RustDesk Tools'),
            StringStruct('FileVersion', '{file_version}'),
            StringStruct('ProductName', 'RustDesk Tools'),
            StringStruct('ProductVersion', '{VERSION}'),
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, prefix="ver_")
    tmp.write(content)
    tmp.close()
    return tmp.name


def build():
    entry = os.path.join(SRC_DIR, "rustdesk_tools.py")

    if not os.path.exists(entry):
        print(f"Error: Entry point not found: {entry}")
        sys.exit(1)

    ver_file = make_version_file()

    try:
        # Build --add-data and --hidden-import args
        add_data = []
        sep = ";"  # Windows

        for mod in HIDDEN_IMPORTS:
            add_data.extend(["--hidden-import", mod])

        for data in DATA_FILES:
            path = os.path.join(SRC_DIR, data)
            if os.path.exists(path):
                add_data.extend(["--add-data", f"{path}{sep}."])
            else:
                print(f"Warning: Data file not found, skipping: {path}")

        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--windowed",
            "--name", "RustDesk_Tools",
            "--noconfirm",
            "--version-file", ver_file,
            # Optimizations
            "--noupx",                       # UPX often triggers antivirus false positives
            "--optimize", "2",               # Python -OO bytecode (drops docstrings + asserts)
            "--exclude-module", "tkinter",   # Not used, saves ~5MB
            "--exclude-module", "unittest",
            "--exclude-module", "test",
            "--exclude-module", "distutils",
            "--exclude-module", "setuptools",
            "--exclude-module", "pkg_resources",
            "--exclude-module", "xmlrpc",
            "--exclude-module", "pydoc",
            "--exclude-module", "doctest",
            "--exclude-module", "sqlite3",
            "--exclude-module", "multiprocessing",
            "--paths", SRC_DIR,              # So PyInstaller finds our script modules
            "--hidden-import", "PyQt6",
            "--hidden-import", "PyQt6.QtWidgets",
            "--hidden-import", "PyQt6.QtCore",
            "--hidden-import", "PyQt6.QtGui",
        ]

        if os.path.isfile(ICON_FILE):
            cmd.extend(["--icon", ICON_FILE])
            print(f"Using icon: {ICON_FILE}")
        else:
            print("Warning: icon.ico not found, building without icon.")

        cmd.extend(add_data)
        cmd.append(entry)

        print(f"\n{'='*50}")
        print(f"  Building RustDesk Tools v{VERSION}")
        print(f"{'='*50}\n")

        result = subprocess.run(cmd)

        if result.returncode == 0:
            print(f"\nBuild successful!")
            print(f"Output: dist/RustDesk_Tools.exe")
            print(f"\nNote: The config file (rustdesk_tools_config.json) will be")
            print(f"created next to the exe on first run.")
        else:
            print(f"\nBuild failed with return code {result.returncode}")
            sys.exit(1)
    finally:
        os.unlink(ver_file)


if __name__ == "__main__":
    build()
