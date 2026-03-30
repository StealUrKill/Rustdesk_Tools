#!/usr/bin/env python3

import ast
import sys
import os
import io
import json
import contextlib
import threading
import importlib
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QComboBox, QPushButton, QTextEdit,
    QFormLayout, QGroupBox, QCheckBox, QFileDialog, QSpinBox, QScrollArea,
    QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView, QStackedWidget,
    QMessageBox,
)
from PyQt6.QtCore import pyqtSignal, QObject, Qt
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon


# When frozen (PyInstaller exe), bundled data is in sys._MEIPASS
# Scripts are bundled there too, so SCRIPT_DIR points to the temp extract folder
if getattr(sys, "frozen", False):
    SCRIPT_DIR = sys._MEIPASS
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Config file always lives next to the exe (or script) so it persists between runs
CONFIG_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else SCRIPT_DIR
CONFIG_FILE = os.path.join(CONFIG_DIR, "rustdesk_tools_config.json")

# ---------------------------------------------------------------------------
# SCRIPT IMPORTS AND IN-PROCESS RUNNER
# ---------------------------------------------------------------------------

from script_error import ScriptError

import devices
import users
import ab
import audits
import strategies
import custom_config_generator
device_groups = importlib.import_module("device_groups")
user_groups = importlib.import_module("user_groups")

SCRIPT_MODULES = {
    "devices.py": devices,
    "users.py": users,
    "ab.py": ab,
    "audits.py": audits,
    "strategies.py": strategies,
    "custom_config_generator.py": custom_config_generator,
    "device_groups.py": device_groups,
    "user_groups.py": user_groups,
}

_script_lock = threading.Lock()


def run_script(script_filename, args_list, output_signal):
    """Run a script's main() in-process, capturing print output."""
    module = SCRIPT_MODULES.get(os.path.basename(script_filename))
    if module is None:
        output_signal.text.emit(f"Error: Unknown script {script_filename}\n")
        return

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    with _script_lock:
        try:
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                module.main(args_list)
        except ScriptError as e:
            stderr_buf.write(str(e) + "\n")
        except SystemExit as e:
            if e.code and e.code != 0:
                stderr_buf.write(f"Script exited with code {e.code}\n")
        except Exception as e:
            stderr_buf.write(f"Error: {e}\n")

    out = stdout_buf.getvalue()
    err = stderr_buf.getvalue()
    if out:
        output_signal.text.emit(out)
    if err:
        output_signal.text.emit(err)


# ---------------------------------------------------------------------------
# API SCRIPT DEFINITIONS: SCRIPT >> SUBCOMMANDS >> FIELDS
# Each field: (flag, label, type)  type: "text", "int", "choice:a,b,c"
# ---------------------------------------------------------------------------

def load_api_scripts():
    json_path = os.path.join(SCRIPT_DIR, "api_scripts.json")
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


API_SCRIPTS = load_api_scripts()


# -------------------------------------
# SIGNAL HELPER FOR THREAD-SAFE OUTPUT
# -------------------------------------

class OutputSignal(QObject):
    text = pyqtSignal(str)
    finished = pyqtSignal()
    clear = pyqtSignal()


# -------------------------------------
# CONFIG PERSISTENCE
# -------------------------------------

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


# -------------------------------------
# DYNAMIC FORM BUILDER
# -------------------------------------

class DynamicForm(QWidget):
    """A form that rebuilds its fields based on the selected subcommand."""

    def __init__(self):
        super().__init__()
        self.layout = QFormLayout(self)
        self.layout.setContentsMargins(10, 5, 10, 5)
        self.fields = {}  # flag >> widget

    def set_fields(self, field_defs):
        """Rebuild form with given field definitions."""
        # Clear existing
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.fields.clear()

        for flag, label, ftype in field_defs:
            if ftype == "int":
                widget = QSpinBox()
                widget.setRange(0, 999999)
                widget.setSpecialValueText("")
                widget.setValue(0)
            elif ftype.startswith("choice:"):
                widget = QComboBox()
                widget.addItem("")  # blank = not set
                choices = ftype[7:].split(",")
                for c in choices:
                    widget.addItem(c.strip())
            elif ftype == "file":
                widget = self._file_picker()
            elif ftype == "dir":
                widget = self._dir_picker()
            else:
                widget = QLineEdit()

            self.fields[flag] = widget
            self.layout.addRow(label + ":", widget)

    def _file_picker(self):
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        line = QLineEdit()
        btn = QPushButton("Browse...")
        btn.clicked.connect(lambda: self._browse_file(line))
        h.addWidget(line)
        h.addWidget(btn)
        container._line = line
        return container

    def _dir_picker(self):
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        line = QLineEdit()
        btn = QPushButton("Browse...")
        btn.clicked.connect(lambda: self._browse_dir(line))
        h.addWidget(line)
        h.addWidget(btn)
        container._line = line
        return container

    def _browse_file(self, line_edit):
        path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if path:
            line_edit.setText(path)

    def _browse_dir(self, line_edit):
        path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if path:
            line_edit.setText(path)

    def get_values(self):
        """Return list of command-line args from the form values."""
        args = []
        for flag, widget in self.fields.items():
            val = ""
            if isinstance(widget, QLineEdit):
                val = widget.text().strip()
            elif isinstance(widget, QSpinBox):
                if widget.value() > 0:
                    val = str(widget.value())
            elif isinstance(widget, QComboBox):
                val = widget.currentText().strip()
                # For choices like "0 - Remote Desktop", extract just the number
                if val and " - " in val:
                    val = val.split(" - ")[0].strip()
            elif hasattr(widget, "_line"):
                val = widget._line.text().strip()

            if not val:
                continue

            if flag.startswith("--"):
                args.extend([flag, val])
            else:
                # Positional argument
                args.append(val)

        return args


# -------------------------------------
# API TAB
# -------------------------------------

class APITab(QWidget):
    def __init__(self, url_edit, token_edit, output_signal):
        super().__init__()
        self.url_edit = url_edit
        self.token_edit = token_edit
        self.output_signal = output_signal

        layout = QVBoxLayout(self)

        # Script selector
        top = QHBoxLayout()
        top.addWidget(QLabel("Module:"))
        self.script_combo = QComboBox()
        self.script_combo.addItems(API_SCRIPTS.keys())
        self.script_combo.currentTextChanged.connect(self.on_script_changed)
        top.addWidget(self.script_combo)

        top.addWidget(QLabel("Action:"))
        self.sub_combo = QComboBox()
        self.sub_combo.currentTextChanged.connect(self.on_subcommand_changed)
        top.addWidget(self.sub_combo)
        top.addStretch()
        layout.addLayout(top)

        # Dynamic form in a scroll area
        self.form = DynamicForm()
        scroll = QScrollArea()
        scroll.setWidget(self.form)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(250)
        layout.addWidget(scroll)

        # Run button
        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("Run")
        self.run_btn.clicked.connect(self.run_command)
        btn_row.addWidget(self.run_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Initialize
        self.on_script_changed(self.script_combo.currentText())

    def on_script_changed(self, name):
        if not name or name not in API_SCRIPTS:
            return
        self.sub_combo.blockSignals(True)
        self.sub_combo.clear()
        subs = list(API_SCRIPTS[name]["subcommands"].keys())
        self.sub_combo.addItems(subs)
        self.sub_combo.blockSignals(False)
        if subs:
            self.on_subcommand_changed(subs[0])

    def on_subcommand_changed(self, name):
        script_name = self.script_combo.currentText()
        if not script_name or not name:
            return
        fields = API_SCRIPTS[script_name]["subcommands"].get(name, [])
        self.form.set_fields(fields)

    def run_command(self):
        script_name = self.script_combo.currentText()
        sub = self.sub_combo.currentText()
        if not script_name or not sub:
            return

        self.output_signal.clear.emit()

        info = API_SCRIPTS[script_name]
        url = self.url_edit.text().strip()
        token = self.token_edit.text().strip()

        args_list = ["--url", url, "--token", token, sub] + self.form.get_values()

        self.run_btn.setEnabled(False)
        self.output_signal.text.emit(f"> {info['script']} {' '.join(args_list)}\n")
        self._run_in_thread(info["script"], args_list)

    def _run_in_thread(self, script_filename, args_list):
        def worker():
            try:
                run_script(script_filename, args_list, self.output_signal)
            except Exception as e:
                self.output_signal.text.emit(f"Error: {e}\n")
            finally:
                self.output_signal.finished.emit()

        t = threading.Thread(target=worker, daemon=True)
        t.start()


# -------------------------------------
# CUSTOM TAB (CONFIG GENERATOR)
# -------------------------------------

class CustomTab(QWidget):
    def __init__(self, output_signal):
        super().__init__()
        self.output_signal = output_signal

        layout = QVBoxLayout(self)

        group = QGroupBox("Config Generator")
        form = QFormLayout(group)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("yourdomain.com")
        form.addRow("RustDesk Host:", self.host_edit)

        self.key_edit = QLineEdit()
        form.addRow("RustDesk Key:", self.key_edit)

        self.api_edit = QLineEdit()
        self.api_edit.setPlaceholderText("https://yourdomain.com")
        form.addRow("RustDesk API:", self.api_edit)

        self.gen_qr = QCheckBox("Generate QR Code")
        form.addRow(self.gen_qr)

        self.qr_output = QLineEdit()
        self.qr_output.setPlaceholderText("Default: Desktop/rustdesk_config_qr.png")
        form.addRow("QR Output Path:", self.qr_output)

        self.apply_config = QCheckBox("Apply Config to RustDesk")
        form.addRow(self.apply_config)

        self.exe_path = QLineEdit()
        self.exe_path.setPlaceholderText("Default: C:\\Program Files\\RustDesk\\rustdesk.exe")
        form.addRow("RustDesk Exe Path:", self.exe_path)

        self.no_clipboard = QCheckBox("Skip Clipboard Copy")
        form.addRow(self.no_clipboard)

        self.run_btn = QPushButton("Generate")
        self.run_btn.clicked.connect(self.run_generator)
        form.addRow(self.run_btn)

        layout.addWidget(group)
        layout.addStretch()

    def run_generator(self):
        self.output_signal.clear.emit()
        host = self.host_edit.text().strip()
        key = self.key_edit.text().strip()
        api = self.api_edit.text().strip()

        if not host or not key or not api:
            self.output_signal.text.emit("Error: Host, Key, and API are all required.\n")
            return

        args_list = ["--host", host, "--key", key, "--api", api]

        if self.gen_qr.isChecked():
            args_list.append("--qr")
            qr_path = self.qr_output.text().strip()
            if qr_path:
                args_list.extend(["--qr-output", qr_path])

        if self.apply_config.isChecked():
            args_list.append("--apply")
            exe = self.exe_path.text().strip()
            if exe:
                args_list.extend(["--exe", exe])

        if self.no_clipboard.isChecked():
            args_list.append("--no-clipboard")

        self.run_btn.setEnabled(False)
        self.output_signal.text.emit(f"> custom_config_generator.py {' '.join(args_list)}\n")

        def worker():
            try:
                run_script("custom_config_generator.py", args_list, self.output_signal)
            except Exception as e:
                self.output_signal.text.emit(f"Error: {e}\n")
            finally:
                self.output_signal.finished.emit()

        t = threading.Thread(target=worker, daemon=True)
        t.start()


# -------------------------------------
# MAIN WINDOW
# -------------------------------------

class RustDeskTools(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RustDesk Tools")
        # Prefer .ico (works better on Windows taskbar), fall back to .svg
        icon_path = os.path.join(SCRIPT_DIR, "icon.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(SCRIPT_DIR, "icon.svg")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.setMinimumSize(1200, 900)

        self.output_signal = OutputSignal()
        self.output_signal.text.connect(self.append_output)
        self.output_signal.clear.connect(self.clear_output)
        self.output_signal.finished.connect(self.on_command_finished)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # --- Server connection bar ---
        conn_group = QGroupBox("API Connection")
        conn_layout = QHBoxLayout(conn_group)

        conn_layout.addWidget(QLabel("Server URL:"))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://your-rustdesk-server.com")
        conn_layout.addWidget(self.url_edit)

        conn_layout.addWidget(QLabel("Token:"))
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText("Bearer token")
        conn_layout.addWidget(self.token_edit)

        self.show_token = QCheckBox("Show")
        self.show_token.toggled.connect(
            lambda checked: self.token_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        conn_layout.addWidget(self.show_token)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_connection)
        conn_layout.addWidget(save_btn)

        conn_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        main_layout.addWidget(conn_group)

        # --- Tabs ---
        self.tabs = QTabWidget()

        self.api_tab = APITab(self.url_edit, self.token_edit, self.output_signal)

        self.custom_tab = CustomTab(self.output_signal)

        self.tabs.addTab(self.api_tab, "API")

        self.tabs.addTab(self.custom_tab, "Custom")

        self.tabs.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        main_layout.addWidget(self.tabs)

        # --- Output panel ---
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)

        # Toggle buttons
        view_row = QHBoxLayout()
        self.raw_btn = QPushButton("Raw")
        self.raw_btn.setCheckable(True)
        self.raw_btn.setChecked(True)
        self.raw_btn.clicked.connect(lambda: self.set_output_view("raw"))
        view_row.addWidget(self.raw_btn)

        self.table_btn = QPushButton("Table")
        self.table_btn.setCheckable(True)
        self.table_btn.clicked.connect(lambda: self.set_output_view("table"))
        view_row.addWidget(self.table_btn)

        view_row.addStretch()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search / Filter...")
        self.search_edit.setMaximumWidth(250)
        self.search_edit.textChanged.connect(self.apply_filter)
        view_row.addWidget(self.search_edit)

        clear_btn = QPushButton("Clear Output")
        clear_btn.clicked.connect(self.clear_output)
        view_row.addWidget(clear_btn)

        output_layout.addLayout(view_row)

        # Stacked widget: raw text vs table
        self.output_stack = QStackedWidget()

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Consolas", 9))
        self.output_stack.addWidget(self.output)  # index 0

        # Table view container (filters + table + actions)
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)

        # Column filter row (scrollable)
        self.filter_scroll = QScrollArea()
        self.filter_scroll.setWidgetResizable(True)
        self.filter_scroll.setFixedHeight(54)
        self.filter_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.filter_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.filter_widget = QWidget()
        self.filter_layout = QHBoxLayout(self.filter_widget)
        self.filter_layout.setContentsMargins(6, 8, 6, 8)
        self.filter_layout.setSpacing(6)
        self.filter_scroll.setWidget(self.filter_widget)
        self.filter_combos = []
        table_layout.addWidget(self.filter_scroll)

        self.table = QTableWidget()
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table_layout.addWidget(self.table)

        # Bulk action bar
        action_row = QHBoxLayout()
        self.visible_count_label = QLabel("")
        action_row.addWidget(self.visible_count_label)
        action_row.addStretch()

        self.bulk_disable_btn = QPushButton("Disable Visible")
        self.bulk_disable_btn.clicked.connect(lambda: self.bulk_action("disable"))
        action_row.addWidget(self.bulk_disable_btn)

        self.bulk_enable_btn = QPushButton("Enable Visible")
        self.bulk_enable_btn.clicked.connect(lambda: self.bulk_action("enable"))
        action_row.addWidget(self.bulk_enable_btn)

        self.bulk_delete_btn = QPushButton("Delete Visible")
        self.bulk_delete_btn.setStyleSheet("QPushButton { background-color: #8b2020; } QPushButton:hover { background-color: #a52a2a; }")
        self.bulk_delete_btn.clicked.connect(lambda: self.bulk_action("delete"))
        action_row.addWidget(self.bulk_delete_btn)

        table_layout.addLayout(action_row)

        self.output_stack.addWidget(table_container)  # index 1

        output_layout.addWidget(self.output_stack)

        main_layout.addWidget(output_group, stretch=1)

        # Store raw output and parsed records for bulk actions
        self._raw_output = ""
        self._table_records = []  # original parsed records (with guid)
        self._table_columns = []

        # Load saved config
        self.load_connection()

        # Track all run buttons for re-enabling
        self.run_buttons = [
            self.api_tab.run_btn,
            self.custom_tab.run_btn,
        ]

    def append_output(self, text):
        self._raw_output += text
        self.output.moveCursor(self.output.textCursor().MoveOperation.End)
        self.output.insertPlainText(text)
        self.output.moveCursor(self.output.textCursor().MoveOperation.End)

    def on_command_finished(self):
        self.output.insertPlainText("\n")
        self._try_populate_table()
        for btn in self.run_buttons:
            btn.setEnabled(True)

    def set_output_view(self, mode):
        if mode == "raw":
            self.output_stack.setCurrentIndex(0)
            self.raw_btn.setChecked(True)
            self.table_btn.setChecked(False)
        else:
            self.output_stack.setCurrentIndex(1)
            self.raw_btn.setChecked(False)
            self.table_btn.setChecked(True)

    def clear_output(self):
        self.output.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self._raw_output = ""
        self._table_records = []
        self._table_columns = []
        self.search_edit.clear()
        self.visible_count_label.setText("")
        for combo in self.filter_combos:
            combo.deleteLater()
        self.filter_combos.clear()

    def apply_filter(self, text):
        """Filter both raw output and table rows by search text."""
        query = text.strip().lower()

        # Filter raw view | show only matching lines
        if self.output_stack.currentIndex() == 0:
            if not query:
                self.output.setPlainText(self._raw_output)
            else:
                filtered = [
                    line for line in self._raw_output.splitlines()
                    if query in line.lower()
                ]
                self.output.setPlainText("\n".join(filtered))

        # Filter table rows
        for row in range(self.table.rowCount()):
            if not query:
                self.table.setRowHidden(row, False)
                continue
            match = False
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item and query in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(row, not match)
        self._update_visible_count()

    def _try_populate_table(self):
        """Try to parse raw output as JSON records and populate the table."""
        records = []

        # Strip the leading "> command" line(s)
        lines = self._raw_output.strip().splitlines()
        data_lines = [l for l in lines if not l.strip().startswith(">")]
        data_text = "\n".join(data_lines).strip()

        if not data_text:
            return

        # First, try parsing the whole block as JSON (handles multi-line JSON arrays)
        parsed = False
        try:
            obj = json.loads(data_text)
            if isinstance(obj, list):
                for item in obj:
                    if isinstance(item, dict):
                        records.append(item)
                parsed = True
            elif isinstance(obj, dict):
                # Check for wrapper format: {"data": [...], "total": ...}
                if "data" in obj and isinstance(obj["data"], list):
                    for item in obj["data"]:
                        if isinstance(item, dict):
                            records.append(item)
                else:
                    records.append(obj)
                parsed = True
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: try each line individually (handles one-dict-per-line Python repr)
        if not parsed:
            for line in data_lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    try:
                        obj = ast.literal_eval(line)
                    except (ValueError, SyntaxError):
                        continue

                if isinstance(obj, dict):
                    records.append(obj)
                elif isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, dict):
                            records.append(item)

        if not records:
            return

        # Flatten nested dicts, JSON strings, and summarize nested arrays
        flat_records = []
        tooltip_records = []
        for rec in records:
            flat = {}
            tips = {}
            for k, v in rec.items():
                # Try to parse JSON strings into dicts
                if isinstance(v, str) and v.startswith("{"):
                    try:
                        v = json.loads(v)
                    except (json.JSONDecodeError, ValueError):
                        pass

                if isinstance(v, dict):
                    for k2, v2 in v.items():
                        if isinstance(v2, dict):
                            # Flatten second level (e.g. info.device_info.name)
                            for k3, v3 in v2.items():
                                flat[f"{k}.{k2}.{k3}"] = str(v3) if v3 is not None else ""
                        elif isinstance(v2, list):
                            # Flatten nested arrays (e.g. files: [["path", size]])
                            parts = []
                            for entry in v2:
                                if isinstance(entry, list) and len(entry) >= 1:
                                    parts.append(str(entry[0]))
                                else:
                                    parts.append(str(entry))
                            flat[f"{k}.{k2}"] = ", ".join(parts)
                        else:
                            flat[f"{k}.{k2}"] = str(v2) if v2 is not None else ""
                elif isinstance(v, list):
                    if not v:
                        flat[k] = ""
                    elif all(isinstance(item, str) for item in v):
                        # Simple string list (e.g. admin_roles: ["Managers"])
                        flat[k] = ", ".join(v)
                    else:
                        # List of dicts | summarize by 'name' field
                        names = []
                        for item in v:
                            if isinstance(item, dict) and "name" in item:
                                names.append(item["name"])
                        if names:
                            count = len(names)
                            preview = ", ".join(names[:5])
                            if count > 5:
                                flat[k] = f"{preview} ... ({count} total)"
                            else:
                                flat[k] = preview
                            tips[k] = "\n".join(names)
                        else:
                            flat[k] = f"[{len(v)} items]"
                else:
                    flat[k] = str(v) if v is not None else ""
            flat_records.append(flat)
            tooltip_records.append(tips)

        # Collect all columns
        columns = []
        seen = set()
        for rec in flat_records:
            for k in rec:
                if k not in seen:
                    columns.append(k)
                    seen.add(k)

        # Store for bulk actions
        self._table_records = records
        self._table_columns = columns
        self._flat_records = flat_records

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(flat_records))
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)

        for row, rec in enumerate(flat_records):
            tips = tooltip_records[row]
            for col, key in enumerate(columns):
                val = rec.get(key, "")
                item = QTableWidgetItem(val)
                if key in tips:
                    item.setToolTip(tips[key])
                self.table.setItem(row, col, item)

        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()

        # Build column filter dropdowns
        self._build_column_filters(columns, flat_records)
        self._update_visible_count()

    def _build_column_filters(self, columns, flat_records):
        """Create a dropdown filter for each column with unique values."""
        # Clear old filters
        for combo in self.filter_combos:
            combo.deleteLater()
        self.filter_combos.clear()

        for col, key in enumerate(columns):
            combo = QComboBox()
            combo.setMinimumWidth(100)
            combo.setMaximumWidth(180)
            combo.addItem(f"▼ {key}")  # header/default = no filter

            # Collect unique values for this column
            values = set()
            has_blank = False
            for rec in flat_records:
                val = rec.get(key, "")
                if val:
                    values.add(val)
                else:
                    has_blank = True

            if has_blank:
                combo.addItem("(blank)", "")

            for val in sorted(values):
                display = val if len(val) <= 40 else val[:37] + "..."
                combo.addItem(display, val)

            combo.currentIndexChanged.connect(self._apply_column_filters)
            self.filter_layout.addWidget(combo)
            self.filter_combos.append(combo)

        self.filter_layout.addStretch()

    def _apply_column_filters(self):
        """Hide rows that don't match ALL active column filters, then refresh other dropdowns."""
        # First pass: determine visibility based on all active filters
        for row in range(self.table.rowCount()):
            visible = True
            for col, combo in enumerate(self.filter_combos):
                if combo.currentIndex() == 0:
                    continue  # no filter on this column
                filter_val = combo.currentData()
                if filter_val is None:
                    filter_val = combo.currentText()
                item = self.table.item(row, col)
                cell_val = item.text() if item else ""
                if cell_val != filter_val:
                    visible = False
                    break
            self.table.setRowHidden(row, not visible)

        # Second pass: update each dropdown to only show values present in rows
        # that pass ALL OTHER filters (excluding that column's own filter)
        for target_col, target_combo in enumerate(self.filter_combos):
            # Collect values from rows that pass all filters EXCEPT this column
            available = set()
            has_blank = False
            for row in range(self.table.rowCount()):
                passes = True
                for col, combo in enumerate(self.filter_combos):
                    if col == target_col:
                        continue  # skip this column's own filter
                    if combo.currentIndex() == 0:
                        continue
                    fval = combo.currentData()
                    if fval is None:
                        fval = combo.currentText()
                    item = self.table.item(row, col)
                    cell_val = item.text() if item else ""
                    if cell_val != fval:
                        passes = False
                        break
                if passes:
                    item = self.table.item(row, target_col)
                    val = item.text() if item else ""
                    if val:
                        available.add(val)
                    else:
                        has_blank = True

            # Remember current selection
            current_data = target_combo.currentData()
            current_idx = target_combo.currentIndex()

            # Rebuild dropdown without triggering filters
            target_combo.blockSignals(True)
            key = self._table_columns[target_col] if target_col < len(self._table_columns) else ""
            target_combo.clear()
            target_combo.addItem(f"▼ {key}")

            if has_blank:
                target_combo.addItem("(blank)", "")

            for val in sorted(available):
                display = val if len(val) <= 40 else val[:37] + "..."
                target_combo.addItem(display, val)

            # Restore selection
            if current_idx > 0 and current_data is not None:
                for i in range(1, target_combo.count()):
                    if target_combo.itemData(i) == current_data:
                        target_combo.setCurrentIndex(i)
                        break
                else:
                    target_combo.setCurrentIndex(0)  # value no longer available

            target_combo.blockSignals(False)

        self._update_visible_count()

    def _update_visible_count(self):
        """Update the visible row count label."""
        total = self.table.rowCount()
        visible = sum(1 for r in range(total) if not self.table.isRowHidden(r))
        if total > 0:
            self.visible_count_label.setText(f"Showing {visible} of {total}")
        else:
            self.visible_count_label.setText("")

    def _get_visible_records(self):
        """Get the original records for all visible (non-hidden) table rows."""
        visible = []
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                # Match back to original record by guid or row data
                guid_col = None
                for col, key in enumerate(self._table_columns):
                    if key == "guid":
                        guid_col = col
                        break
                if guid_col is not None:
                    guid_item = self.table.item(row, guid_col)
                    if guid_item:
                        guid = guid_item.text()
                        for rec in self._table_records:
                            if rec.get("guid") == guid:
                                visible.append(rec)
                                break
        return visible

    def bulk_action(self, action):
        """Run a bulk action (disable/enable/delete) on all visible records."""
        records = self._get_visible_records()
        if not records:
            QMessageBox.information(self, "No Records", "No visible records to act on.")
            return

        # Get identifiers for display
        ids = []
        for rec in records:
            name = rec.get("id") or rec.get("name") or rec.get("guid", "?")
            ids.append(str(name))

        preview = ", ".join(ids[:10])
        if len(ids) > 10:
            preview += f" ... ({len(ids)} total)"

        reply = QMessageBox.warning(
            self,
            f"Confirm {action.title()}",
            f"Are you sure you want to {action} {len(records)} record(s)?\n\n{preview}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Determine which script to use from the current API tab selection
        script_name = self.api_tab.script_combo.currentText()
        if script_name not in API_SCRIPTS:
            self.output_signal.text.emit(f"Error: Cannot determine script for bulk {action}.\n")
            return

        info = API_SCRIPTS[script_name]
        url = self.url_edit.text().strip()
        token = self.token_edit.text().strip()

        self.output_signal.text.emit(f"\n--- Bulk {action} on {len(records)} records ---\n")

        def worker():
            module = SCRIPT_MODULES.get(info["script"])
            for rec in records:
                rec_id = rec.get("id") or rec.get("name") or rec.get("guid", "?")
                self.output_signal.text.emit(f"  {action}: {rec_id}...")
                try:
                    stdout_buf = io.StringIO()
                    with contextlib.redirect_stdout(stdout_buf):
                        func = getattr(module, action.replace("-", "_"), None)
                        if func and "id" in rec:
                            func(url, token, rec.get("guid", ""), rec["id"])
                        elif func and "name" in rec:
                            func(url, token, rec.get("guid", ""), rec["name"])
                        else:
                            # Fall back to main() with args
                            args_list = ["--url", url, "--token", token, action]
                            if "id" in rec:
                                args_list.extend(["--id", str(rec["id"])])
                            elif "name" in rec:
                                args_list.extend(["--name", str(rec["name"])])
                            module.main(args_list)
                    out = stdout_buf.getvalue().strip()
                    if out:
                        self.output_signal.text.emit(f" {out}\n")
                    else:
                        self.output_signal.text.emit(" done\n")
                except ScriptError as e:
                    self.output_signal.text.emit(f" ERROR: {e}\n")
                except Exception as e:
                    self.output_signal.text.emit(f" ERROR: {e}\n")
            self.output_signal.text.emit(f"--- Bulk {action} complete ---\n")
            self.output_signal.finished.emit()

        for btn in self.run_buttons:
            btn.setEnabled(False)
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def save_connection(self):
        config = load_config()
        config["url"] = self.url_edit.text().strip()
        config["token"] = self.token_edit.text().strip()
        save_config(config)
        self.output_signal.text.emit("Connection settings saved.\n")

    def load_connection(self):
        config = load_config()
        self.url_edit.setText(config.get("url", ""))
        self.token_edit.setText(config.get("token", ""))


# -------------------------------------
# ENTRY POINT
# -------------------------------------

def load_stylesheet():
    qss_path = os.path.join(SCRIPT_DIR, "style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(load_stylesheet())
    window = RustDeskTools()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
