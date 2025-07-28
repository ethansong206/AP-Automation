import os
import subprocess
import fitz  # PyMuPDF
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox,
    QHBoxLayout, QComboBox, QDialog, QDialogButtonBox, QSplitter, QScrollArea, QLineEdit
)
from PyQt5.QtGui import QFont, QColor, QBrush, QCursor, QPixmap, QImage
from PyQt5.QtCore import Qt
from pdf_reader import extract_text_data_from_pdfs
from extractor import extract_fields
from utils import validate_row_data, write_to_csv
from extractors.utils import get_vendor_list, load_manual_mapping
from extractors.vendor_name import save_manual_mapping

class InteractivePDFViewer(QScrollArea):
    def __init__(self, pdf_path, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignTop)

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignTop)
        self.setWidget(self.label)

        self._zoomed = False
        self._dragging = False
        self._drag_start_pos = None
        self._dragged = False

        if os.path.isfile(pdf_path):
            try:
                doc = fitz.open(pdf_path)
                page = doc.load_page(0)
                pix = page.get_pixmap(dpi=100)
                fmt = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
                self.original_pixmap = QPixmap.fromImage(img)

                self.normal_pixmap = self.original_pixmap.scaledToWidth(500, Qt.SmoothTransformation)
                self.zoomed_pixmap = self.original_pixmap.scaledToWidth(1000, Qt.SmoothTransformation)
                self.label.setPixmap(self.normal_pixmap)

                self.zoom_in_cursor = QCursor(QPixmap("assets/zoom_in_cursor.cur"))
                self.zoom_out_cursor = QCursor(QPixmap("assets/zoom_out_cursor.cur"))
                self._update_cursor()

            except Exception as e:
                self.label.setText(f"Failed to render PDF:\n{e}")
        else:
            self.label.setText("[Error] PDF file not found")

    def _update_normal_pixmap(self):
        container_width = self.viewport().width()
        target_width = min(container_width, self.original_pixmap.width())
        # Only rescale if width changes by more than 20px
        if (
            hasattr(self, "normal_pixmap")
            and abs(self.normal_pixmap.width() - target_width) < 20
        ):
            return
        self.normal_pixmap = self.original_pixmap.scaledToWidth(target_width, Qt.SmoothTransformation)
        if not self._zoomed:
            self.label.setPixmap(self.normal_pixmap)

    def resizeEvent(self, event):
        self._update_normal_pixmap()
        super().resizeEvent(event)

    def _update_cursor(self):
        if self._zoomed:
            self.setCursor(self.zoom_in_cursor)
        else:
            self.setCursor(self.zoom_out_cursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragged = False
            self._drag_start_pos = event.pos()
            if not self._zoomed:
                self._zoomed = True
                self._center_on_click(event.pos())
                self._update_cursor()
            else:
                self._dragging = True
                self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._zoomed:
            delta = self._drag_start_pos - event.pos()
            if delta.manhattanLength() > 2:
                self._dragged = True
                self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + delta.x())
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() + delta.y())
                self._drag_start_pos = event.pos()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._dragging:
                self._dragging = False
                if not self._dragged:
                    self.label.setPixmap(self.normal_pixmap)
                    self._zoomed = False
                    self._update_cursor()
                else:
                    self._update_cursor()
        super().mouseReleaseEvent(event)

    def _center_on_click(self, pos):
        # Map the click position from viewport to label coordinates
        click_pos = self.label.mapFrom(self.viewport(), pos)

        # Clamp click_pos to the pixmap area
        x = max(0, min(click_pos.x(), self.normal_pixmap.width() - 1))
        y = max(0, min(click_pos.y(), self.normal_pixmap.height() - 1))

        # Calculate the ratio of the click position within the normal pixmap
        x_ratio = x / self.normal_pixmap.width()
        y_ratio = y / self.normal_pixmap.height()

        # Set the zoomed pixmap
        self.label.setPixmap(self.zoomed_pixmap)
        self.label.resize(self.zoomed_pixmap.size())

        # Calculate the target scroll positions so the clicked point is centered
        h_target = int(self.zoomed_pixmap.width() * x_ratio - self.viewport().width() / 2)
        v_target = int(self.zoomed_pixmap.height() * y_ratio - self.viewport().height() / 2)

        # Clamp scroll values to valid range
        h_target = max(0, min(h_target, self.horizontalScrollBar().maximum()))
        v_target = max(0, min(v_target, self.verticalScrollBar().maximum()))

        self.horizontalScrollBar().setValue(h_target)
        self.verticalScrollBar().setValue(v_target)


class VendorSelectDialog(QDialog):
    def __init__(self, pdf_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Vendor")
        self.setMinimumSize(800, 600)
        self.pdf_path = pdf_path  # Save PDF path for identifier validation later

        # --- Vendor Dropdown Setup ---
        csv_vendors = get_vendor_list()
        manual_vendors = list(load_manual_mapping().values())
        combined = sorted(set(csv_vendors + manual_vendors), key=str.lower)

        self.combo = QComboBox()
        self.combo.addItems(combined)

        self.new_vendor_btn = QPushButton("Create New Vendor")
        self.new_vendor_btn.clicked.connect(self.add_new_vendor)

        # --- Identifier Entry ---
        self.identifier_input = QLineEdit()
        self.identifier_input.setPlaceholderText("Enter unique identifier (e.g. email address, customer #, etc.)")

        self.identifier_confirm = QLineEdit()
        self.identifier_confirm.setPlaceholderText("Confirm unique identifier")
        self.identifier_confirm.textChanged.connect(self.check_identifiers_match)

        self.identifier_error_label = QLabel("")
        self.identifier_error_label.setStyleSheet("color: red;")
        self.identifier_error_label.setVisible(False)

        # --- Save & Cancel ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.save)
        self.button_box.rejected.connect(self.reject)

        # --- Left Panel Layout ---
        left_layout = QVBoxLayout()

        left_font = QFont()
        left_font.setPointSize(left_font.pointSize() + 2)

        label_select = QLabel("Select a vendor from the list:")
        label_select.setFont(left_font)
        left_layout.addWidget(label_select)

        self.combo.setFont(left_font)
        left_layout.addWidget(self.combo)

        or_label = QLabel("--- OR ---")
        or_label.setAlignment(Qt.AlignCenter)
        or_label.setFont(left_font)
        left_layout.addWidget(or_label)

        self.new_vendor_btn.setFont(left_font)
        left_layout.addWidget(self.new_vendor_btn)

        left_layout.addSpacing(20)
        sep_label = QLabel("--------------------------------------------------")
        sep_label.setAlignment(Qt.AlignCenter)
        sep_label.setFont(left_font)
        left_layout.addWidget(sep_label)
        left_layout.addSpacing(20)

        label_unique = QLabel("Unique Identifier:")
        label_unique.setFont(left_font)
        left_layout.addWidget(label_unique)

        self.identifier_input.setFont(left_font)
        left_layout.addWidget(self.identifier_input)

        label_confirm = QLabel("Confirm Identifier:")
        label_confirm.setFont(left_font)
        left_layout.addWidget(label_confirm)

        self.identifier_confirm.setFont(left_font)
        left_layout.addWidget(self.identifier_confirm)

        self.identifier_error_label.setFont(left_font)
        left_layout.addWidget(self.identifier_error_label)

        left_layout.addStretch()
        self.button_box.setFont(left_font)
        left_layout.addWidget(self.button_box)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        # --- PDF Viewer ---
        viewer = InteractivePDFViewer(pdf_path)

        splitter = QSplitter()
        splitter.addWidget(left_widget)
        splitter.addWidget(viewer)
        splitter.setSizes([300, 500])

        main_layout = QVBoxLayout()
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

    def add_new_vendor(self):
        class VendorDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("Create New Vendor")
                layout = QVBoxLayout(self)

                self.name_input = QLineEdit()
                self.name_input.setPlaceholderText("Enter new vendor name")
                self.confirm_input = QLineEdit()
                self.confirm_input.setPlaceholderText("Confirm new vendor name")

                self.error_label = QLabel("")
                self.error_label.setStyleSheet("color: red;")
                self.error_label.setVisible(False)

                layout.addWidget(QLabel("Vendor Name:"))
                layout.addWidget(self.name_input)
                layout.addWidget(QLabel("Confirm Vendor Name:"))
                layout.addWidget(self.confirm_input)
                layout.addWidget(self.error_label)

                self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
                self.button_box.accepted.connect(self.accept)
                self.button_box.rejected.connect(self.reject)
                layout.addWidget(self.button_box)

                self.name_input.textChanged.connect(self.validate)
                self.confirm_input.textChanged.connect(self.validate)
                self.validate()

            def validate(self):
                name = self.name_input.text().strip()
                confirm = self.confirm_input.text().strip()
                save_btn = self.button_box.button(QDialogButtonBox.Save)
                if not name or not confirm:
                    self.error_label.setVisible(False)
                    save_btn.setEnabled(False)
                elif name != confirm:
                    self.error_label.setText("Names do not match.")
                    self.error_label.setVisible(True)
                    save_btn.setEnabled(False)
                else:
                    self.error_label.setVisible(False)
                    save_btn.setEnabled(True)

            def get_name(self):
                return self.name_input.text().strip()

        dialog = VendorDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            name = dialog.get_name()
            # Check for duplicates (case-insensitive)
            existing_names = [self.combo.itemText(i).strip().lower() for i in range(self.combo.count())]
            if name.lower() in existing_names:
                QMessageBox.critical(self, "Duplicate Vendor",
                    f"The vendor '{name}' already exists.\nPlease check the drop-down menu.")
                return
            self.combo.addItem(name)
            self.combo.setCurrentText(name)

    def check_identifiers_match(self):
        id1 = self.identifier_input.text().strip()
        id2 = self.identifier_confirm.text().strip()
        if id1 and id2 and id1 != id2:
            self.identifier_error_label.setText("Identifiers do not match.")
            self.identifier_error_label.setVisible(True)
        else:
            self.identifier_error_label.setVisible(False)

    def save(self):
        vendor = self.combo.currentText().strip()
        id1 = self.identifier_input.text().strip()
        id2 = self.identifier_confirm.text().strip()

        if not vendor:
            QMessageBox.critical(self, "Missing Vendor", "Please select or enter a vendor.")
            return

        if not id1 or not id2:
            QMessageBox.critical(self, "Missing Identifier", "Please enter and confirm the identifier.")
            return

        if id1 != id2:
            QMessageBox.critical(self, "Mismatch", "The identifiers do not match.")
            return

        # --- Validate Identifier in PDF ---
        try:
            doc = fitz.open(self.pdf_path)
            full_text = "\n".join(page.get_text() for page in doc)
            if id1.lower() not in full_text.lower():
                QMessageBox.critical(self, "Identifier Not Found",
                    f"The string '{id1}' does not appear in the PDF.\n"
                    "Please double-check for typos or try a different identifier.")
                return
        except Exception as e:
            QMessageBox.critical(self, "PDF Read Error", f"Unable to read PDF:\n{e}")
            return

        # Confirm save
        confirm = QMessageBox.question(
            self, "Confirm Save",
            f"Are you sure you want to map:\n\nVendor: {vendor}\nIdentifier: {id1}",
            QMessageBox.Yes | QMessageBox.Cancel
        )
        if confirm != QMessageBox.Yes:
            return

        # --- Save Mapping ---
        save_manual_mapping(id1.lower(), vendor)
        QMessageBox.information(
            self, "Mapping Saved",
            f"Future invoices containing '{id1}' will map to '{vendor}'."
        )
        self.accept()

    def selected_vendor(self):
        return self.combo.currentText().strip()

    def get_identifier(self):
        return self.identifier_input.text().strip()

class InvoiceApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Invoice Extraction App")
        self.setGeometry(100, 100, 1200, 600)

        # --- Main layout setup ---
        self.layout = QVBoxLayout()
        self.label = QLabel("Drop PDF files here or click 'Browse Files'")
        self.label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.label)

        self.browse_button = QPushButton("Browse Files")
        self.browse_button.clicked.connect(self.browse_files)
        self.layout.addWidget(self.browse_button)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Vendor Name", "Invoice Number", "Invoice Date",
            "Discount Terms", "Discount Due Date",
            "Discounted Total", "Total Amount",
            "Source File", "Delete"
        ])
        self.table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.table.cellClicked.connect(self.handle_table_click)
        self.layout.addWidget(self.table)

        self.export_button = QPushButton("Export to CSV")
        self.export_button.clicked.connect(self.export_to_csv)
        self.layout.addWidget(self.export_button)

        self.setLayout(self.layout)
        self.setAcceptDrops(True)
        self.loaded_files = set()

    # --- File browsing ---
    def browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select PDF files", "", "PDF Files (*.pdf)")
        if files:
            self.process_files(files)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        pdf_files = [f for f in files if f.lower().endswith(".pdf")]
        if pdf_files:
            self.process_files(pdf_files)

    # --- Main PDF processing logic ---
    def process_files(self, pdf_paths):
        new_files = [f for f in pdf_paths if f not in self.loaded_files]
        if not new_files:
            print("[INFO] No new files to process.")
            return

        print(f"[INFO] Processing {len(new_files)} new files...")
        self.loaded_files.update(new_files)

        text_blocks = extract_text_data_from_pdfs(new_files)
        extracted_data = extract_fields(text_blocks)

        for row_data, file_path in zip(extracted_data, new_files):
            self.add_row(row_data, file_path)

    # --- Populate table row ---
    def add_row(self, row_data, file_path):
        row_position = self.table.rowCount()
        self.table.insertRow(row_position)

        for col, value in enumerate(row_data):
            if col == 0 and not value:
                item = QTableWidgetItem("Add Vendor")
                item.setForeground(QBrush(QColor("white")))
                item.setBackground(QBrush(QColor("red")))
                font = QFont()
                font.setBold(True)
                item.setFont(font)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            else:
                item = QTableWidgetItem(str(value) if value is not None else "")
            self.table.setItem(row_position, col, item)

        # --- Source File clickable link ---
        file_item = QTableWidgetItem(os.path.basename(file_path))
        file_item.setToolTip(file_path)
        file_item.setData(Qt.UserRole, file_path)
        file_item.setFlags(file_item.flags() ^ Qt.ItemIsEditable)
        file_item.setForeground(QColor("blue"))
        file_item.setBackground(QColor(230, 230, 230))  # light grey
        font = QFont()
        font.setUnderline(True)
        file_item.setFont(font)
        self.table.setItem(row_position, 7, file_item)

        # --- Delete button ---
        delete_item = QTableWidgetItem("❌")
        delete_item.setTextAlignment(Qt.AlignCenter)
        delete_item.setFlags(Qt.ItemIsEnabled)
        delete_item.setBackground(QColor(230, 230, 230))  # light grey
        self.table.setItem(row_position, 8, delete_item)

        # --- Highlight incomplete rows ---
        empty_count = sum(
            1 for col in range(7)
            if not self.table.item(row_position, col).text().strip()
            or self.table.item(row_position, col).text() == "Add Vendor"
        )

        for col in range(7):
            current_item = self.table.item(row_position, col)
            if current_item.text() != "Add Vendor":
                if empty_count >= 4:
                    current_item.setBackground(Qt.yellow)
                else:
                    current_item.setBackground(QColor(220, 255, 220))  # light green

        if empty_count >= 4:
            print(f"[WARN] Row {row_position + 1} flagged for having {empty_count} empty fields.")

        # --- Auto-size Vendor column ---
        vendor_col = 0
        self.table.resizeColumnToContents(vendor_col)
        current_width = self.table.columnWidth(vendor_col)
        self.table.setColumnWidth(vendor_col, current_width + 50)

    # --- Cell click handling ---
    def handle_table_click(self, row, col):
        header = self.table.horizontalHeaderItem(col).text()

        if header == "Source File":
            file_item = self.table.item(row, col)
            file_path = file_item.toolTip()
            if not os.path.isfile(file_path):
                QMessageBox.warning(self, "File Not Found", f"The file does not exist:\n{file_path}")
                return
            try:
                if os.name == 'nt':
                    os.startfile(file_path)
                elif os.name == 'posix':
                    subprocess.call(('open', file_path))
                else:
                    subprocess.call(('xdg-open', file_path))
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open file:\n{e}")

        elif header == "Delete":
            file_item = self.table.item(row, 7)
            file_path = file_item.data(Qt.UserRole) if file_item else None
            confirm = QMessageBox.question(
                self, "Delete Row", f"Are you sure you want to delete row {row + 1}?",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                self.table.removeRow(row)
                if file_path in self.loaded_files:
                    self.loaded_files.remove(file_path)
                    print(f"[DEBUG] Removed '{file_path}' from loaded_files.")

        elif header == "Vendor Name":
            value = self.table.item(row, col).text()
            if value == "Add Vendor":
                self.open_vendor_dialog(row, col)

    # --- Vendor input dialog ---
    def open_vendor_dialog(self, row, col):
        file_item = self.table.item(row, 7)
        file_path = file_item.toolTip() if file_item else ""

        dialog = VendorSelectDialog(file_path, self)
        if dialog.exec_() == QDialog.Accepted:
            vendor_name = dialog.selected_vendor().strip()
            item = QTableWidgetItem(vendor_name)
            self.table.setItem(row, col, item)

    # --- Export to CSV ---
    def export_to_csv(self):
        rows_to_export = []

        for row in range(self.table.rowCount()):
            row_data = []
            for col in range(7):
                item = self.table.item(row, col)
                row_data.append(item.text() if item else "")
            rows_to_export.append(row_data)

        try:
            write_to_csv("invoice_data.csv", rows_to_export)
            QMessageBox.information(self, "Export Successful", "Data exported to invoice_data.csv")
            print(f"[INFO] Exported {len(rows_to_export)} rows to invoice_data.csv")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Error: {e}")
            print(f"[ERROR] Failed to export: {e}")