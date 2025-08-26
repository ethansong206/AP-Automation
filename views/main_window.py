"""Main application window for invoice processing."""
import os
import re
import shutil
import json
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QHBoxLayout, QDialog, QTableWidgetItem, QLineEdit, QMenu
)
from PyQt5.QtGui import QFont, QFontMetrics, QDragEnterEvent, QDropEvent, QIcon
from PyQt5.QtCore import Qt, QStandardPaths, QTimer, QSize

try:
    from views.app_shell import _resolve_icon
except Exception:  # pragma: no cover - fallback for isolated runs
    def _resolve_icon(name: str) -> str:
        return os.path.join("assets", "icons", name)

from views.components.invoice_table import InvoiceTable
from views.helpers.style_loader import load_stylesheet, get_style_path
from views.dialogs.manual_entry_dialog import ManualEntryDialog

from controllers.file_controller import FileController
from controllers.invoice_controller import InvoiceController
from models.invoice import Invoice
from views.app_shell import _resolve_icon
from utils import get_vendor_csv_path

class InvoiceApp(QWidget):
    """Main application window for invoice processing."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Invoice Extraction App")
        self.setGeometry(100, 100, 1300, 650)

        # Apply stylesheet
        stylesheet = load_stylesheet(get_style_path('default.qss'))
        if stylesheet:
            self.setStyleSheet(stylesheet)

        # Controllers
        self.file_controller = FileController(self)
        self.invoice_controller = InvoiceController(self)

        # Session
        self.session_file = self._get_session_file()
        self._loading_session = False

        # UI
        self.setup_ui()

        # Full-window drag & drop
        self.setAcceptDrops(True)

        # Autosave/restore
        self.setup_autosave()
        self.load_session()
        
        # Initialize vendor data (merge if needed)
        self.initialize_vendor_data()

    # ---------------- UI ----------------
    def setup_ui(self):
        self.layout = QVBoxLayout()

        # Title (hidden by AppShell, but fine if run standalone)
        self.title_label = QLabel("GOPC\nInvoice App")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("""
            font-family: 'Montserrat', Arial, sans-serif;
            font-size: 28px;
            font-weight: bold;
            color: #5E6F5E;
            padding: 10px;
            margin-bottom: 8px;
            line-height: 1;
        """)
        self.layout.addWidget(self.title_label)

        # --- Second row with Upload (left) and Flag Selected (right) ---
        second_row = QHBoxLayout()
        
        self.btn_import = QPushButton("Upload")
        self.btn_import.setObjectName("importButton")
        self.btn_import.setIcon(QIcon(_resolve_icon("upload.svg")))
        self.btn_import.setIconSize(QSize(20, 20))  # Increased from 16,16 to 20,20
        self.btn_import.clicked.connect(self.browse_files)
        second_row.addWidget(self.btn_import)
        
        second_row.addStretch()
        
        self.flag_selected_button = QPushButton("Flag Selected")
        self.flag_selected_button.setObjectName("flagSelectedButton")
        self.flag_selected_button.clicked.connect(self.flag_selected_rows)
        second_row.addWidget(self.flag_selected_button)
        
        self.layout.addLayout(second_row)

        # Table
        self.table = InvoiceTable()
        self.setup_table_connections()
        self.layout.addWidget(self.table)

        # Bottom row: (left) Clear/Delete, (middle) Total Count, (right) Export Files, Export CSV
        button_row = QHBoxLayout()

        # Left group: Clear All and Delete Selected
        left_button_group = QHBoxLayout()
        self.clear_all_button = QPushButton("Clear All")
        self.clear_all_button.setObjectName("clearAllButton")
        self.clear_all_button.clicked.connect(self.clear_all_rows)
        left_button_group.addWidget(self.clear_all_button)

        self.delete_selected_button = QPushButton("Delete Selected")
        self.delete_selected_button.setObjectName("deleteSelectedButton")
        self.delete_selected_button.clicked.connect(self.delete_selected_rows)
        left_button_group.addWidget(self.delete_selected_button)
        button_row.addLayout(left_button_group)

        button_row.addStretch()

        #Middle: Total Number of Invoices + Filtered Count
        count_layout = QVBoxLayout()
        count_layout.setContentsMargins(0, 0, 0, 0)
        count_layout.setSpacing(0)

        self.invoice_count_label = QLabel("Total Number of Invoices: 0")
        self.invoice_count_label.setObjectName("totalLabel")
        self.invoice_count_label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        count_font = QFont()
        count_font.setBold(True)
        count_font.setPointSize(12)
        self.invoice_count_label.setFont(count_font)
        self.invoice_count_label.setContentsMargins(0, 0, 0, 0)
        # Remove bottom padding so the stacked labels sit closer together
        self.invoice_count_label.setStyleSheet("padding: 10px 5px 0px 5px;")
        count_layout.addWidget(self.invoice_count_label)

        self.filtered_count_label = QLabel("")
        self.filtered_count_label.setObjectName("totalLabel")
        self.filtered_count_label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.filtered_count_label.setFont(QFont(count_font))
        self.filtered_count_label.setContentsMargins(0, 0, 0, 0)
        # Remove top/bottom padding and reserve space so the table doesn't shift
        self.filtered_count_label.setStyleSheet("padding: 0px 5px 0px 5px;")
        self.filtered_count_label.setFixedHeight(QFontMetrics(count_font).height())
        count_layout.addWidget(self.filtered_count_label)

        button_row.addLayout(count_layout)

        button_row.addStretch()

        # Right group: Export Files and Export CSV
        right_button_group = QHBoxLayout()
        self.export_files_button = QPushButton("Export Files to Folder")
        self.export_files_button.setObjectName("exportFilesButton")
        self.export_files_button.clicked.connect(self.export_files_to_folder)
        right_button_group.addWidget(self.export_files_button)

        self.export_button = QPushButton("Export to CSV")
        self.export_button.setObjectName("exportButton")
        self.export_button.clicked.connect(self.export_to_csv)
        right_button_group.addWidget(self.export_button)
        button_row.addLayout(right_button_group)

        self.layout.addLayout(button_row)
        self.setLayout(self.layout)

        # Create controls for the header (to be used by AppShell)
        self._create_header_controls()

    def _create_header_controls(self):
        """Create the controls that will be moved to the header by AppShell"""
        # These will be accessed by AppShell, so we create them as instance variables
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search invoices…")
        self.search_edit.textChanged.connect(self._on_search_text)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setObjectName("searchEdit")

        self.btn_filter = QPushButton("Filter")
        self.btn_filter.setObjectName("filterButton")
        self.btn_filter.setIcon(QIcon(_resolve_icon("filter.svg")))
        self.btn_filter.setIconSize(QSize(16, 16))

        # Set consistent sizing - shortened search bar
        base_w = self.export_button.sizeHint().width()
        self.btn_filter.setMinimumWidth(base_w)
        self.search_edit.setMinimumWidth(int(base_w * 1.5))  # Shortened from base_w * 2 to base_w * 1.5
        self.search_edit.setMaximumWidth(int(base_w * 1.5))  # Also set max width to prevent expansion

        # Filter menu (checkable)
        self.filter_menu = QMenu(self)
        self.act_flagged_only = self.filter_menu.addAction("Flagged only")
        self.act_flagged_only.setCheckable(True)
        self.act_incomplete_only = self.filter_menu.addAction("Rows with empty cells")
        self.act_incomplete_only.setCheckable(True)
        self.btn_filter.setMenu(self.filter_menu)

        self.act_flagged_only.toggled.connect(self._apply_filters)
        self.act_incomplete_only.toggled.connect(self._apply_filters)

    def setup_table_connections(self):
        self.table.row_deleted.connect(self.handle_row_deleted)
        self.table.row_deleted.connect(lambda *_: self.save_session())
        self.table.source_file_clicked.connect(self.open_file)
        self.table.manual_entry_clicked.connect(self.open_manual_entry_dialog)
        self.table.cell_manually_edited.connect(self.handle_cell_edited)
        self.table.cellChanged.connect(lambda *_: self.save_session())

    # ---------------- Drag & Drop (full window) ----------------
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            # Accept if any PDF present
            for u in event.mimeData().urls():
                if u.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        pdfs = [f for f in files if f.lower().endswith(".pdf")]
        if pdfs:
            self.process_files(pdfs)
            event.acceptProposedAction()
        else:
            event.ignore()

    # ---------------- File selection ----------------
    def browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select PDF files", "", "PDF Files (*.pdf)")
        if files:
            self.process_files(files)

    # ---------------- Processing ----------------
    def process_files(self, pdf_paths):
        data = self.file_controller.process_files(pdf_paths)
        if not data:
            return
        for extracted_data, file_path in data:
            invoice = Invoice.from_extracted_data(extracted_data, file_path)
            self.table.add_row(invoice.to_row_data(), file_path, invoice.is_no_ocr)
        self.update_invoice_count()
        self.save_session()

    # ---------------- Events/handlers ----------------
    def handle_row_deleted(self, row, file_path):
        self.file_controller.remove_file(file_path)
        self.update_invoice_count()
        self.save_session()

    def handle_cell_edited(self, row, col):
        if col == 5:
            self.invoice_controller.recalculate_dependent_fields(row)

    def open_file(self, file_path):
        self.file_controller.open_file(file_path)

    def open_manual_entry_dialog(self, row, button=None):
        file_paths, values_list, flag_states = [], [], []
        for r in range(self.table.rowCount()):
            file_paths.append(self.table.get_file_path_for_row(r))
            row_values = self.table.get_row_values(r)  # Get all 13 values including QC
            print(f"[QC DEBUG] Loading row {r} values for dialog: {row_values}")
            values_list.append(row_values)
            flag_states.append(self.table.is_row_flagged(r))

        dialog = ManualEntryDialog(file_paths, self, values_list, flag_states, start_index=row)
        dialog.file_deleted.connect(self._on_dialog_deleted_file)
        dialog.row_saved.connect(self.on_manual_row_saved)

        if dialog.exec_() == QDialog.Accepted and dialog.save_changes:
            new_flag_states = dialog.get_flag_states()
            for path, flagged in zip(file_paths, new_flag_states):
                row_idx = self.table.find_row_by_file_path(path)
                if row_idx >= 0 and self.table.is_row_flagged(row_idx) != flagged:
                    self.table.toggle_row_flag(row_idx)
            self.update_invoice_count()
            self.save_session()

    def clear_all_rows(self):
        if self.table.rowCount() == 0:
            return
        confirm = QMessageBox.question(
            self, "Clear All", "Are you sure you want to delete all rows?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.table.setRowCount(0) if hasattr(self.table, "setRowCount") else None
            self.table.clear_tracking_data() if hasattr(self.table, "clear_tracking_data") else None
            self.file_controller.clear_all_files()
            self.update_invoice_count()
            self.remove_session_file()

    def delete_selected_rows(self):
        selected_rows = sorted(self.table.get_checked_rows(), reverse=True)
        if not selected_rows:
            return
        confirm = QMessageBox.question(
            self, "Delete Selected Rows", "Are you sure you want to delete the selected rows?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            for vrow in selected_rows:
                file_path = self.table.get_file_path_for_row(vrow)
                # use helper to delete by file path to keep controllers in sync
                self.table.delete_row_by_file_path(file_path, confirm=False)
                self.file_controller.remove_file(file_path)
            self.update_invoice_count()
            self.save_session()

    def flag_selected_rows(self):
        selected_rows = self.table.get_checked_rows()
        if not selected_rows:
            return

        # Count how many in the selection are already flagged
        flagged_states = [self.table.is_row_flagged(r) for r in selected_rows]
        any_flagged = any(flagged_states)
        all_flagged = all(flagged_states)

        if not any_flagged:
            # Case 1: none flagged -> flag all in selection
            for r in selected_rows:
                if not self.table.is_row_flagged(r):
                    self.table.toggle_row_flag(r)

        elif not all_flagged:
            # Case 2: some flagged (but not all) -> flag all non-flagged
            for r in selected_rows:
                if not self.table.is_row_flagged(r):
                    self.table.toggle_row_flag(r)

        else:
            # Case 3: all flagged -> unflag all
            for r in selected_rows:
                if self.table.is_row_flagged(r):
                    self.table.toggle_row_flag(r)

        self.save_session()
    
    def update_invoice_count(self):
        total = self.table.total_row_count()
        self.invoice_count_label.setText(f"Total Number of Invoices: {total}")
        visible = self.table.rowCount()
        if self.table.is_filtered():
            self.filtered_count_label.setText(f"Showing {visible} of {total} rows")
        else:
            self.filtered_count_label.setText("")

    def _on_dialog_deleted_file(self, file_path: str):
        if not file_path:
            return
        self.table.delete_row_by_file_path(file_path, confirm=False)

    def on_manual_row_saved(self, file_path: str, row_values: list, flagged: bool):
        self.table.update_row_by_source(file_path, row_values)
        row = self.table.find_row_by_file_path(file_path)
        if row >= 0 and self.table.is_row_flagged(row) != flagged:
            self.table.toggle_row_flag(row)
        self.update_invoice_count()
        self.save_session()

    # ---------------- Export ----------------
    def export_to_csv(self):
        if self.table.total_row_count() == 0:
            QMessageBox.warning(self, "No Data", "There is no data to export.")
            return
        options = QFileDialog.Options() | QFileDialog.DontConfirmOverwrite
        default_name = "accounting_import.csv"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export to CSV", default_name,
            "CSV Files (*.csv);;All Files (*)", options=options
        )
        if not filename:
            return
        if not filename.lower().endswith('.csv'):
            filename += '.csv'
        success, message = self.invoice_controller.export_to_csv(filename)
        if success:
            QMessageBox.information(self, "Export Successful", message)
            self.remove_session_file()
        else:
            QMessageBox.critical(self, "Export Failed", f"Error: {message}")

    def export_files_to_folder(self):
        if self.table.total_row_count() == 0:
            QMessageBox.warning(self, "No Files", "There are no files to export.")
            return
        target_dir = QFileDialog.getExistingDirectory(self, "Select Export Folder")
        if not target_dir:
            return
        month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        month_dirs = []
        for i, name in enumerate(month_names, 1):
            p = os.path.join(target_dir, f"{i:02d} - {name}")
            os.makedirs(p, exist_ok=True)
            month_dirs.append(p)

        model = getattr(self.table, "_model", None)
        total_rows = model.rowCount() if model else self.table.rowCount()
        for src_row in range(total_rows):
            file_path = model.get_file_path(src_row) if model else self.table.get_file_path_for_row(src_row)
            if not file_path or not os.path.isfile(file_path):
                continue
            if model:
                vals = model.row_values(src_row)
                vendor = self._sanitize_filename(vals[0]) or "UNKNOWN"
                po_number = self._sanitize_filename(vals[2]) or "PO"
                invoice_number = self._sanitize_filename(vals[1]) or "INV"
                date_str = vals[3]
            else:
                vendor = self._sanitize_filename(self.table.get_cell_text(src_row, 1)) or "UNKNOWN"
                po_number = self._sanitize_filename(self.table.get_cell_text(src_row, 3)) or "PO"
                invoice_number = self._sanitize_filename(self.table.get_cell_text(src_row, 2)) or "INV"
                date_str = self.table.get_cell_text(src_row, 4)
            new_name = f"{vendor}_{po_number}_{invoice_number}.pdf"
            date_obj = self._parse_invoice_date(date_str)
            dest_dir = month_dirs[date_obj.month - 1] if date_obj else target_dir
            dest_path = os.path.join(dest_dir, new_name)
            if os.path.exists(dest_path):
                continue
            try:
                shutil.copy2(file_path, dest_path)
                src_dir = os.path.dirname(file_path)
                new_src_path = os.path.join(src_dir, new_name)
                if (
                    os.path.normpath(file_path) != os.path.normpath(new_src_path)
                    and not os.path.exists(new_src_path)
                ):
                    os.rename(file_path, new_src_path)
                    if model:
                        model.set_file_path(src_row, new_src_path)
                    else:
                        self.table.set_file_path_for_row(src_row, new_src_path)
                    old_norm = os.path.normpath(file_path)
                    new_norm = os.path.normpath(new_src_path)
                    if old_norm in self.file_controller.loaded_files:
                        self.file_controller.loaded_files.remove(old_norm)
                        self.file_controller.loaded_files.add(new_norm)
            except Exception as e:
                print(f"[ERROR] Failed to copy '{file_path}' to '{dest_path}': {e}")
        QMessageBox.information(self, "Export Complete", f"Files exported to:\n{target_dir}")

    # ---------------- Search / Filter helpers ----------------
    def _on_search_text(self, text: str):
        self.table.set_search_text(text)
        self.update_invoice_count()

    def _apply_filters(self):
        self.table.set_flagged_only(self.act_flagged_only.isChecked())
        self.table.set_incomplete_only(self.act_incomplete_only.isChecked())
        self.update_invoice_count()

    # ---------------- Session ----------------
    def _get_session_file(self):
        base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        if not os.path.exists(base):
            os.makedirs(base, exist_ok=True)
        return os.path.join(base, "session.json")

    def setup_autosave(self):
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(60000)
        self.autosave_timer.timeout.connect(self.save_session)
        self.autosave_timer.start()

    def save_session(self):
        if self._loading_session:
            return
        if self.table.rowCount() == 0:
            self.remove_session_file()
            return
        rows = []
        for row in range(self.table.rowCount()):
            # Get all 13 values including QC data (not just the first 8 visible columns)
            values = self.table.get_row_values(row)  
            rows.append({
                "values": values,
                "flagged": self.table.is_row_flagged(row),
                "file_path": self.table.get_file_path_for_row(row)
            })
        payload = {
            "rows": rows,
            "loaded_files": list(self.file_controller.loaded_files),
            "timestamp": datetime.now().isoformat(),
        }
        try:
            with open(self.session_file, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
        except Exception as e:
            print(f"[ERROR] Failed to save session: {e}")

    def load_session(self):
        if not os.path.exists(self.session_file):
            return
        try:
            with open(self.session_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as e:
            print(f"[ERROR] Failed to load session: {e}")
            return
        rows = data.get("rows", [])
        if not rows:
            return

        # Ask the user if they want to restore the previous session
        timestamp = data.get("timestamp")
        msg = "A previous session was found. Restore it?"
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                msg = (
                    "Restore session from "
                    f"{dt.strftime('%Y-%m-%d %H:%M')}?"
                )
            except Exception:
                pass
        resp = QMessageBox.question(
            self,
            "Restore Session",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if resp != QMessageBox.Yes:
            return

        self._loading_session = True
        # start with a clean table/model
        if hasattr(self.table, "_model") and hasattr(self.table._model, "clear"):
            self.table._model.clear()
        self.table.clear_tracking_data() if hasattr(self.table, "clear_tracking_data") else None

        for row in rows:
            values = row.get("values", [""] * 13)  # Default to 13 values including QC data
            file_path = row.get("file_path", "")
            flagged = row.get("flagged", False)
            self.table.add_row(values, file_path)
            if flagged:
                self.table.toggle_row_flag(self.table.rowCount() - 1)

        self.file_controller.load_saved_files(data.get("loaded_files", []))
        self.update_invoice_count()
        self._loading_session = False

    # ----------- small utils -----------
    def _sanitize_filename(self, s):
        return re.sub(r'[\\/*?:"<>|]+', "_", (s or "").strip())

    def _parse_invoice_date(self, text):
        try:
            m, d, y = re.split(r"[/\-]", text.strip())
            y = int(y); y = y + 2000 if y < 100 else y
            return datetime(int(y), int(m), int(d))
        except Exception:
            return None

    def remove_session_file(self):
        try:
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
        except Exception:
            pass
    
    def initialize_vendor_data(self):
        """Initialize vendor data on app startup - triggers merge if needed."""
        try:
            # This call will trigger the merge process if there are conflicts
            get_vendor_csv_path()
        except Exception as e:
            print(f"[WARN] Failed to initialize vendor data: {e}")