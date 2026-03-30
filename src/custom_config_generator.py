#!/usr/bin/env python3

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

from script_error import ScriptError


def generate_config_string(host, key, api):
    """Generate a RustDesk config string (reversed base64 of JSON)."""
    config = json.dumps({"host": host, "key": key, "api": api}, separators=(",", ":"))
    b64 = base64.b64encode(config.encode("utf-8")).decode("utf-8").rstrip("=")
    return b64[::-1]


def generate_qr(config_json, output_path):
    """Generate a QR code PNG via the qrserver.com API."""
    qr_text = f"config={config_json}"
    url = f"https://api.qrserver.com/v1/create-qr-code/?size=240x240&margin=2&data={urllib.parse.quote(qr_text)}"

    try:
        urllib.request.urlretrieve(url, output_path)
        print(f"\nQR saved to: {output_path}")
        print(f"QR content: {qr_text}")
    except Exception as e:
        raise ScriptError(f"Error: generating QR code: {e}")


def apply_config(code, exe_path=None):
    """Apply config to RustDesk by running the executable with --config."""
    if exe_path is None:
        exe_path = r"C:\Program Files\RustDesk\rustdesk.exe"

    if not os.path.exists(exe_path):
        raise ScriptError(f"Error: RustDesk not found at: {exe_path}")

    print(f"\nApplying config to RustDesk...")
    subprocess.run([exe_path, "--config", code])


def main(argv=None):
    parser = argparse.ArgumentParser(description="RustDesk custom config generator")
    parser.add_argument("--host", help="RustDesk host (e.g. yourdomain.com)")
    parser.add_argument("--key", help="RustDesk key")
    parser.add_argument("--api", help="RustDesk API URL (e.g. https://yourdomain.com)")
    parser.add_argument("--qr", action="store_true", help="Generate QR code image")
    parser.add_argument("--qr-output", default=None, help="QR output path (default: Desktop/rustdesk_config_qr.png)")
    parser.add_argument("--apply", action="store_true", help="Apply config to RustDesk immediately")
    parser.add_argument("--exe", default=None, help="Custom RustDesk executable path")
    parser.add_argument("--no-clipboard", action="store_true", help="Skip copying to clipboard")

    args = parser.parse_args(argv)

    host = args.host or input("Enter RustDesk host (e.g. yourdomain.com): ").strip()
    key = args.key or input("Enter RustDesk key: ").strip()
    api = args.api or input("Enter RustDesk API (e.g. https://yourdomain.com): ").strip()

    config_json = json.dumps({"host": host, "key": key, "api": api}, separators=(",", ":"))
    code = generate_config_string(host, key, api)

    # QR code
    if args.qr:
        qr_output = args.qr_output
        if qr_output is None:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            qr_output = os.path.join(desktop, "rustdesk_config_qr.png")
        generate_qr(config_json, qr_output)

    print("\nConfig String:\n")
    print(code)

    if not args.no_clipboard:
        try:
            subprocess.run(["clip"], input=code.encode("utf-8"), check=True)
            print("\n(Config copied to clipboard)")
        except Exception:
            print("\n(Could not copy to clipboard)")

    if args.apply:
        apply_config(code, args.exe)
    else:
        apply = input("\nApply this config to RustDesk now? (y/n): ").strip().lower()
        if apply in ("y", "yes"):
            apply_config(code, args.exe)


if __name__ == "__main__":
    try:
        main()
    except ScriptError as e:
        print(e)
        sys.exit(1)
