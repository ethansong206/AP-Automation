import os
from copy import deepcopy
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QDateEdit,
    QPushButton, QSplitter, QWidget, QFormLayout, QComboBox, QMessageBox,
    QCompleter, QListWidget, QListWidgetItem, QGroupBox, QSizePolicy, 
    QScrollArea, QGridLayout
)
from PyQt5.QtCore import Qt, QDate, QEvent, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QGuiApplication, QColor

# Project components
from views.components.pdf_viewer import InteractivePDFViewer
from views.dialogs.vendor_dialog import AddVendorFlow
from extractors.utils import get_vendor_list, calculate_discount_due_date  # <<<< used for Due Date calc
from assets.constants import COLORS


class ManualEntryDialog(QDialog):
    """Dialog for manual entry of invoice fields with PDF viewer and quick calc."""
    file_deleted = pyqtSignal(str)           # emitted when a file is deleted here
    row_saved = pyqtSignal(str, list, bool)        # (file_path, row_values, flagged)

    def __init__(self, pdf_paths, parent=None, values_list=None, flag_states=None, start_index=0):
        super().__init__(parent)
        self.setWindowTitle("Manual Entry")
        self.setMinimumSize(1100, 650)

        # Style tweaks
        self.setStyleSheet("""
            QLabel { font-size: 15px; }
            QLineEdit, QComboBox, QDateEdit { font-size: 15px; padding: 5px; }
            QPushButton { font-size: 15px; padding: 9px 15px; }
            QGroupBox { font-size: 18px; font-weight: bold; margin-top: 15px; }
        """)

        # Data/state
        self.pdf_paths = list(pdf_paths or [])
        self.values_list = values_list or [[""] * 8 for _ in self.pdf_paths]
        self.flag_states = list(flag_states or [False] * len(self.pdf_paths))
        self.saved_flag_states = list(self.flag_states)
        self.saved_values_list = deepcopy(self.values_list)  # last-saved snapshot
        self.current_index = start_index if 0 <= start_index < len(self.pdf_paths) else 0
        self._deleted_files = []
        self._dirty = False
        self._loading = False           # prevents false dirty on programmatic set
        self.save_changes = False
        self.viewed_files = set()

        # ===== Left: file list =====
        self.file_list = QListWidget()
        self.file_list.mousePressEvent = self._file_list_mouse_press
        for path, flagged in zip(self.pdf_paths, self.flag_states):
            text = os.path.basename(path) if path else ""
            item = QListWidgetItem()
            self._update_file_item(item, text, flagged)
            self.file_list.addItem(item)

        # ===== Center: form =====
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(11)
        form_layout.setHorizontalSpacing(10)
        form_layout.setContentsMargins(10, 10, 10, 10)

        self.fields = {}

        # Vendor
        vendor_layout = QHBoxLayout()
        self.vendor_combo = QComboBox()
        self.vendor_combo.setEditable(True)
        self.vendor_combo.setInsertPolicy(QComboBox.NoInsert)
        self.load_vendors()
        comp = self.vendor_combo.completer()
        if comp:
            comp.setCompletionMode(QCompleter.PopupCompletion)
        vendor_layout.addWidget(self.vendor_combo, 1)
        vendor_layout.addSpacing(10)
        self.add_vendor_btn = QPushButton("New Vendor")
        self.add_vendor_btn.clicked.connect(self.add_new_vendor)
        vendor_layout.addWidget(self.add_vendor_btn)
        form_layout.addRow(QLabel("Vendor Name:"), vendor_layout)
        self.fields["Vendor Name"] = self.vendor_combo

        # Core fields
        self.fields["Invoice Number"] = QLineEdit()
        form_layout.addRow(QLabel("Invoice Number:"), self.fields["Invoice Number"])

        self.fields["PO Number"] = QLineEdit()
        form_layout.addRow(QLabel("PO Number:"), self.fields["PO Number"])

        # Invoice Date
        self.fields["Invoice Date"] = QDateEdit()
        self.fields["Invoice Date"].setCalendarPopup(True)
        self.fields["Invoice Date"].setDisplayFormat("MM/dd/yyyy")
        self.fields["Invoice Date"].setDate(QDate.currentDate())
        form_layout.addRow(QLabel("Invoice Date:"), self.fields["Invoice Date"])

        # Discount Terms
        self.fields["Discount Terms"] = QLineEdit()
        form_layout.addRow(QLabel("Discount Terms:"), self.fields["Discount Terms"])

        # Due Date + Calculate button
        self.fields["Due Date"] = QDateEdit()
        self.fields["Due Date"].setCalendarPopup(True)
        self.fields["Due Date"].setDisplayFormat("MM/dd/yyyy")
        self.fields["Due Date"].setDate(QDate.currentDate())
        due_row = QHBoxLayout()
        due_row.addWidget(self.fields["Due Date"], 1)
        due_row.addSpacing(10)
        self.due_calc_btn = QPushButton("Calculate")
        self.due_calc_btn.setToolTip("Compute Due Date from Discount Terms and Invoice Date")
        self.due_calc_btn.clicked.connect(self._on_calculate_due_date)
        due_row.addWidget(self.due_calc_btn)
        form_layout.addRow(QLabel("Due Date:"), due_row)

        # Currency fields
        self.fields["Discounted Total"] = QLineEdit()
        form_layout.addRow(QLabel("Discounted Total:"), self.fields["Discounted Total"])
        self.fields["Total Amount"] = QLineEdit()
        form_layout.addRow(QLabel("Total Amount:"), self.fields["Total Amount"])

        # Quick Calculator (no Tax rows)
        self.quick_calc_group = QGroupBox("Quick Calculator")
        qc = QFormLayout()
        qc.setVerticalSpacing(11)
        qc.setHorizontalSpacing(12)
        qc.setContentsMargins(15, 35, 15, 15)

        def new_lineedit():
            e = QLineEdit()
            e.textChanged.connect(self._recalc_quick_calc)
            return e

        self.qc_subtotal = new_lineedit()
        self.qc_disc_pct = new_lineedit()   # %
        self.qc_disc_amt = new_lineedit()   # $
        self.qc_shipping = new_lineedit()
        self.qc_other = new_lineedit()      # adjustments (+/-)
        self.qc_grand_total = QLabel("$0.00")
        self.qc_grand_total.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.qc_grand_total.setStyleSheet("font-weight: bold;")

        # Buttons to push result back into fields (as plain numbers)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.qc_apply_total = QPushButton("Apply → Total Amount")
        self.qc_apply_discounted = QPushButton("Apply → Discounted Total")
        self.qc_apply_total.clicked.connect(lambda: self._apply_quick_total_to("Total Amount"))
        self.qc_apply_discounted.clicked.connect(lambda: self._apply_quick_total_to("Discounted Total"))
        btn_row.addWidget(self.qc_apply_total)
        btn_row.addWidget(self.qc_apply_discounted)

        qc.addRow(QLabel("Subtotal:"), self.qc_subtotal)
        qc.addRow(QLabel("Discount %:"), self.qc_disc_pct)
        qc.addRow(QLabel("Discount $:"), self.qc_disc_amt)
        qc.addRow(QLabel("Shipping:"), self.qc_shipping)
        qc.addRow(QLabel("Other Adj. (+/-):"), self.qc_other)
        qc.addRow(QLabel("Grand Total:"), self.qc_grand_total)
        qc.addRow(btn_row)
        self.quick_calc_group.setLayout(qc)

        # Button styles
        primary_btn_css = (
            "QPushButton { background-color: #5E6F5E; color: white; border-radius: 4px; "
            "padding: 9px 15; font-weight: bold; } "
            "QPushButton:hover { background-color: #6b7d6b; } "
            "QPushButton:pressed { background-color: #526052; }"
        )
        for b in (self.add_vendor_btn, self.qc_apply_total, self.qc_apply_discounted, self.due_calc_btn):
            b.setStyleSheet(primary_btn_css)

        # Navigation + delete
        self.prev_button = QPushButton("←")
        self.next_button = QPushButton("→")
        nav_css = (
            "QPushButton { background-color: #5E6F5E; color: #f0f0f0; border: 1px solid #3E4F3E; "
            "font-size: 28px; padding: 10px; } "
            "QPushButton:hover { background-color: #546454; } "
            "QPushButton:pressed { background-color: #485848; } "
            "QPushButton:disabled { background-color: #bbbbbb; color: #666666; }"
        )
        for b in (self.prev_button, self.next_button):
            b.setStyleSheet(nav_css)
            b.setFixedSize(60, 60)
        self.prev_button.clicked.connect(self._on_prev_clicked)
        self.next_button.clicked.connect(self._on_next_clicked)

        self.flag_button = QPushButton("⚑")
        self.flag_button.setStyleSheet(nav_css)
        self.flag_button.setFixedSize(60, 60)
        self.flag_button.setToolTip("Toggle follow-up flag for this invoice")
        self.flag_button.clicked.connect(lambda: self.toggle_file_flag(self.current_index))

        arrows = QHBoxLayout()
        arrows.setSpacing(12)
        arrows.setContentsMargins(0, 0, 0, 0)
        arrows.addWidget(self.prev_button)
        arrows.addWidget(self.next_button)

        # Tracker showing current file position
        self.file_tracker_label = QLabel("")
        self.file_tracker_label.setAlignment(Qt.AlignCenter)

        nav_layout = QVBoxLayout()
        nav_layout.setSpacing(4)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.addLayout(arrows)
        nav_layout.addWidget(self.file_tracker_label)

        self.delete_btn = QPushButton("Delete This Invoice")
        self.delete_btn.setToolTip("Remove this invoice from the list and table")
        self.delete_btn.setStyleSheet(
            "QPushButton { background-color: #C0392B; color: white; border-radius: 4px; "
            "padding: 9px 15; font-weight: bold; font-size: 15px; } "
            "QPushButton:hover { background-color: #D3543C; } "
            "QPushButton:pressed { background-color: #A93226; }"
        )
        self.delete_btn.clicked.connect(self._confirm_delete_current)

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.on_save)
        self.save_btn.setStyleSheet(primary_btn_css)

        row_container = QWidget()
        row_grid = QGridLayout(row_container)
        row_grid.setContentsMargins(0, 10, 0, 0)
        row_grid.setHorizontalSpacing(0)
        row_grid.addLayout(nav_layout, 0, 0, alignment=Qt.AlignHCenter | Qt.AlignVCenter)
        row_grid.addWidget(self.delete_btn, 0, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
        row_grid.addWidget(self.flag_button, 0, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        row_grid.addWidget(self.save_btn, 1, 0, alignment=Qt.AlignHCenter | Qt.AlignTop)

        left_layout = QVBoxLayout()
        left_layout.addLayout(form_layout)
        left_layout.addWidget(self.quick_calc_group)
        left_layout.addSpacing(15)
        left_layout.addWidget(row_container)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.NoFrame)
        left_scroll.setWidget(left_widget)

        # ===== Right: PDF viewer =====
        self.viewer = InteractivePDFViewer(self.pdf_paths[self.current_index] if self.pdf_paths else "")

        # ===== Splitter =====
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.file_list.setMinimumWidth(140)
        self.splitter.addWidget(self.file_list)
        self.splitter.addWidget(left_scroll)
        self.splitter.addWidget(self.viewer)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 5)
        self.splitter.setStretchFactor(2, 4)
        QTimer.singleShot(0, self._apply_splitter_proportions)

        # Layout
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.addWidget(self.splitter)
        self.setLayout(content_layout)

        # Currency fields we pretty/normalize
        self._currency_labels = {"Total Amount", "Discounted Total"}
        for label in self._currency_labels:
            w = self.fields.get(label)
            if w:
                w.installEventFilter(self)

        # Quick calc fields that use pretty/plain toggling (no tax fields now)
        self._calc_currency_fields = [
            self.qc_subtotal, self.qc_disc_amt, self.qc_shipping, self.qc_other
        ]
        for w in self._calc_currency_fields:
            w.installEventFilter(self)

        # Highlight on change
        for label, widget in self.fields.items():
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._highlight_empty_fields)
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self._highlight_empty_fields)
            elif isinstance(widget, QDateEdit):
                widget.dateChanged.connect(lambda _, l=label: self._on_date_changed(l))

        # Wire dirty tracking AFTER fields exist
        self._wire_dirty_tracking()

        # Initial load
        self.load_invoice(self.current_index)

        # Resize to avoid buttons being off-screen, and fit the PDF to width
        QTimer.singleShot(0, self._resize_to_fit_content)
        QTimer.singleShot(0, lambda: self.viewer.fit_width())

        # Guarded file list navigation
        self.file_list.currentRowChanged.connect(self._on_file_list_row_changed)

    # ---------- Layout helpers ----------
    def _apply_splitter_proportions(self):
        total = max(1, self.splitter.width())
        sizes = [int(total * 0.10), int(total * 0.50), int(total * 0.40)]
        sizes[2] = max(1, total - sizes[0] - sizes[1])
        self.splitter.setSizes(sizes)

    def _resize_to_fit_content(self):
        screen = self.windowHandle().screen() if self.windowHandle() else QGuiApplication.primaryScreen()
        if not screen:
            return
        avail = screen.availableGeometry()
        target_h = min(900, max(750, avail.height() - 80))
        target_w = min(1400, max(1200, avail.width() - 80))
        self.resize(target_w, target_h)
        self._apply_splitter_proportions()
        if hasattr(self, "viewer") and self.viewer:
            self.viewer.fit_width()

    # ---------- Keyboard nav ----------
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Left, Qt.Key_Right):
            if not self._entry_field_has_focus():
                if event.key() == Qt.Key_Left:
                    self._on_prev_clicked()
                else:
                    self._on_next_clicked()
                event.accept()
                return
        super().keyPressEvent(event)

    def _entry_field_has_focus(self):
        w = self.focusWidget()
        return isinstance(w, (QLineEdit, QComboBox, QDateEdit))

    # ---------- Deletion ----------
    def _confirm_delete_current(self):
        if not self.pdf_paths:
            return
        path = self.pdf_paths[self.current_index]
        fname = os.path.basename(path) if path else "(unknown)"
        confirm = QMessageBox.question(
            self, "Delete Invoice",
            f"Are you sure you want to delete this invoice?\n\n{fname}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self._delete_current_without_prompt()

    def _delete_current_without_prompt(self):
        if not self.pdf_paths:
            return
        idx = self.current_index
        if idx < 0 or idx >= len(self.pdf_paths):
            idx = max(0, min(idx, len(self.pdf_paths) - 1))

        path = self.pdf_paths[idx]
        self.file_list.blockSignals(True)

        # Remove from buffers
        self.pdf_paths.pop(idx)
        self.values_list.pop(idx)
        self.saved_values_list.pop(idx)
        self.flag_states.pop(idx)
        self.saved_flag_states(idx)
        self._deleted_files.append(path)

        # Remove from UI list
        item = self.file_list.takeItem(idx)
        if item:
            del item

        # Tell parent to remove table row
        self.file_deleted.emit(path)

        # No files left: close
        if not self.pdf_paths:
            self.file_list.blockSignals(False)
            QMessageBox.information(self, "All Done", "All invoices were deleted.")
            self.save_changes = True
            self.accept()
            return

        # Go to the next logical file
        new_index = idx if idx < len(self.pdf_paths) else (len(self.pdf_paths) - 1)
        self.file_list.setCurrentRow(new_index)
        self.current_index = new_index
        self.file_list.blockSignals(False)
        self.load_invoice(new_index)

    # ---------- Persistence / navigation ----------
    def save_current_invoice(self):
        if not self.values_list:
            return
        self.values_list[self.current_index] = self.get_data()

    def _load_values_into_widgets(self, values):
        """Programmatic set (guarded -> doesn't mark dirty)."""
        self._loading = True
        try:
            vals = list(values) + [""] * (8 - len(values))

            self.vendor_combo.setCurrentText(vals[0])
            self.fields["Invoice Number"].setText(vals[1])
            self.fields["PO Number"].setText(vals[2])

            # Invoice Date
            self.fields["Invoice Date"].setDate(QDate.currentDate())
            inv = vals[3].strip()
            if inv:
                d = self._parse_mmddyy(inv)
                if d.isValid():
                    self.fields["Invoice Date"].setDate(d)

            self.fields["Discount Terms"].setText(vals[4])

            # Due Date
            self.fields["Due Date"].setDate(QDate.currentDate())
            due = vals[5].strip()
            if due:
                d2 = self._parse_mmddyy(due)
                if d2.isValid():
                    self.fields["Due Date"].setDate(d2)

            # Currency fields
            self.fields["Discounted Total"].setText(vals[6])
            self.fields["Total Amount"].setText(vals[7])
            self._apply_pretty_currency_display()

            # Highlighting
            self.empty_date_fields = set()
            if not vals[3].strip():
                self.empty_date_fields.add("Invoice Date")
            if not vals[5].strip():
                self.empty_date_fields.add("Due Date")
            self._highlight_empty_fields()
        finally:
            # Reset dirty to reflect snapshot equality
            self._dirty = False
            self._loading = False

    def _parse_mmddyy(self, s):
        # Accept MM/DD/YY or MM/DD/YYYY
        parts = s.split("/")
        if len(parts) == 3:
            try:
                m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
                if y < 100:
                    y = 2000 + y
                qd = QDate(y, m, d)
                return qd if qd.isValid() else QDate()
            except Exception:
                return QDate()
        return QDate.fromString(s, "MM/dd/yy")

    def load_invoice(self, index):
        if not self.pdf_paths:
            self.file_tracker_label.setText("0/0")
            return
        index = max(0, min(index, len(self.pdf_paths) - 1))
        self.current_index = index
        self.mark_file_viewed(index)

        #Update tracker label
        self.file_tracker_label.setText(f"{index + 1}/{len(self.pdf_paths)}")

        # Load widgets (guard prevents dirty)
        self._load_values_into_widgets(self.values_list[index])

        # Enable/disable nav
        self.prev_button.setDisabled(index == 0)
        self.next_button.setDisabled(index == len(self.pdf_paths) - 1)
        self._update_flag_button()

        # Sync list selection without triggering guard
        if self.file_list.currentRow() != index:
            self.file_list.blockSignals(True)
            self.file_list.setCurrentRow(index)
            self.file_list.blockSignals(False)

        # Refresh viewer
        new_viewer = InteractivePDFViewer(self.pdf_paths[index])
        i = self.splitter.indexOf(self.viewer)
        self.splitter.replaceWidget(i, new_viewer)
        new_viewer.show()
        self.viewer.deleteLater()
        self.viewer = new_viewer
        self.splitter.setStretchFactor(i, 1)
        QTimer.singleShot(0, self._apply_splitter_proportions)
        QTimer.singleShot(0, lambda: self.viewer.fit_width())

    def _navigate_to_index(self, index):
        if 0 <= index < len(self.pdf_paths):
            self.save_current_invoice()
            self.load_invoice(index)

    def _on_file_list_row_changed(self, index):
        # Only act if actually changing rows
        if index == self.current_index or index < 0 or index >= len(self.pdf_paths):
            return
        self._confirm_unsaved_then(lambda: self._navigate_to_index(index))

    def _on_prev_clicked(self):
        if self.current_index > 0:
            self._confirm_unsaved_then(lambda: self._navigate_to_index(self.current_index - 1))

    def _on_next_clicked(self):
        if self.current_index < len(self.pdf_paths) - 1:
            self._confirm_unsaved_then(lambda: self._navigate_to_index(self.current_index + 1))

    def on_save(self):
        # Normalize currency (plain) before saving
        for label in getattr(self, "_currency_labels", set()):
            w = self.fields.get(label)
            if w:
                w.setText(self._money_plain(w.text()))

        typed_vendor = (self.vendor_combo.currentText() or "").strip()

        current_names = {
            self.vendor_combo.itemText(i).strip().lower()
            for i in range(self.vendor_combo.count())
        }

        if typed_vendor and typed_vendor.lower() not in current_names:
            warn = QMessageBox.warning(
                self,
                "Unknown Vendor",
                (
                    f"‘{typed_vendor}’ isn’t in your vendor list.\n\n"
                    "You’ll need to add it first (Vendor Name → Vendor Number → optional Identifier).\n"
                    "Vendor Number is required; Identifier is optional."
                ),
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Ok
            )
            if warn == QMessageBox.Cancel:
                return  # abort save; let the user decide later

            # Launch the exact same guided flow as the New Vendor button
            current_pdf = (
                self.pdf_paths[self.current_index]
                if (self.pdf_paths and 0 <= self.current_index < len(self.pdf_paths))
                else ""
            )
            flow = AddVendorFlow(pdf_path=current_pdf, parent=self, prefill_vendor_name=typed_vendor)
            if flow.exec_() != QDialog.Accepted:
                return  # user canceled adding the vendor; don't save yet

            # Refresh dropdown and select the new vendor
            self.load_vendors()
            added_vendor = getattr(flow, "get_final_vendor_name", lambda: None)()
            if added_vendor:
                self.vendor_combo.setCurrentText(added_vendor)
            else:
                # Safety: if for some reason we didn't get a name back, bail to avoid saving with unknown vendor
                QMessageBox.warning(self, "Vendor Not Added", "The vendor wasn’t added. Please try again.")
                return

        # Persist into working list
        self.save_current_invoice()

        # Snapshot as saved, emit outward, clear dirty
        if self.pdf_paths:
            idx = self.current_index
            self.saved_values_list[idx] = deepcopy(self.values_list[idx])
            self.saved_flag_states[idx] = self.flag_states[idx]
            self.row_saved.emit(self.pdf_paths[idx], self.values_list[idx], self.flag_states[idx])
        self._dirty = False
        self._flash_saved()

    def closeEvent(self, event):
        """Guard window-X close. Ensure 'No' actually closes."""
        event.ignore()

        def proceed_accept_close():
            # Mark that we should persist changes and accept the close
            self.save_changes = True
            # Ensure dialog returns QDialog.Accepted so caller processes flag updates
            self.setResult(QDialog.Accepted)
            event.accept()

        self._confirm_unsaved_then(proceed_accept_close)

    # ---------- Due Date calculation ----------
    def _on_calculate_due_date(self):
        """Compute Due Date from Discount Terms + Invoice Date using project helper."""
        terms = self.fields["Discount Terms"].text().strip()
        invoice_date_str = self.fields["Invoice Date"].date().toString("MM/dd/yy")
        try:
            due_str = calculate_discount_due_date(terms, invoice_date_str)
        except Exception as e:
            print(f"[WARN] calculate_discount_due_date failed: {e}")
            due_str = None

        if not due_str:
            QMessageBox.warning(
                self, "Cannot Calculate Due Date",
                "I couldn't determine a due date from those Discount Terms.\n"
                "Try formats like 'NET 30', '2%10 NET 30', '8% 75', etc."
            )
            return

        d = self._parse_mmddyy(due_str)
        if not d.isValid():
            QMessageBox.warning(
                self, "Cannot Parse Due Date",
                f"Got '{due_str}', but couldn't parse it as a date."
            )
            return

        self.fields["Due Date"].setDate(d)
        # Mark as modified by the user action
        self._dirty = True

    # ---------- Tiny saved toast ----------
    def _flash_saved(self):
        from PyQt5.QtWidgets import QLabel
        note = QLabel("Saved", self)
        note.setStyleSheet("""
            QLabel {
                background-color: #e7f5e7;
                color: #2f7a2f;
                border: 1px solid #b9e0b9;
                border-radius: 4px;
                padding: 3px 8px;
                font-weight: bold;
            }
        """)
        note.adjustSize()
        note.move(self.width() - note.width() - 60, self.height() - 60)
        note.show()
        QTimer.singleShot(1000, note.deleteLater)

    def mark_file_viewed(self, index):
        if index in self.viewed_files:
            return
        self.viewed_files.add(index)
        item = self.file_list.item(index)
        if item is not None:
            item.setForeground(QBrush(Qt.gray))

    # ---------- Flag helpers ----------
    def _update_file_item(self, item, text, flagged):
        icon = "🚩" if flagged else "⚑"
        item.setText(f"{icon} {text}")
        if flagged:
            item.setBackground(QColor(COLORS['LIGHT_RED']))
        else:
            item.setBackground(QBrush())

    def _update_flag_button(self):
        if not self.flag_states:
            return
        flagged = self.flag_states[self.current_index]
        self.flag_button.setText("🚩" if flagged else "⚑")

    def toggle_file_flag(self, idx):
        if idx < 0 or idx >= len(self.flag_states):
            return
        self.flag_states[idx] = not self.flag_states[idx]
        item = self.file_list.item(idx)
        text = os.path.basename(self.pdf_paths[idx]) if idx < len(self.pdf_paths) else ""
        if item:
            self._update_file_item(item, text, self.flag_states[idx])
        if idx == self.current_index:
            self._update_flag_button()
        self._dirty = True

    def _file_list_mouse_press(self, event):
        item = self.file_list.itemAt(event.pos())
        if item:
            rect = self.file_list.visualItemRect(item)
            if event.pos().x() - rect.x() < 20:
                idx = self.file_list.row(item)
                self.toggle_file_flag(idx)
                return
        QListWidget.mousePressEvent(self.file_list, event)

    def get_flag_states(self):
        return self.flag_states

    # ---------- Vendors ----------
    def load_vendors(self):
        vendors = get_vendor_list()
        if vendors:
            vendors.sort()
            self.vendor_combo.clear()
            self.vendor_combo.addItems(vendors)

    def add_new_vendor(self):
        """Launch the guided flow to add a vendor (Name → Number → optional Identifier)."""
        # Current PDF (for identifier-in-PDF checks inside the flow)
        current_pdf = (
            self.pdf_paths[self.current_index]
            if (self.pdf_paths and 0 <= self.current_index < len(self.pdf_paths))
            else ""
        )

        # Pre-fill with whatever the user already typed into the combo (if any)
        prefill_name = self.vendor_combo.currentText().strip()

        flow = AddVendorFlow(pdf_path=current_pdf, parent=self, prefill_vendor_name=prefill_name)
        if flow.exec_() == QDialog.Accepted:
            # The flow handles writing to vendors.csv (and manual map if identifier provided)
            # Now refresh the dropdown and select the added vendor.
            self.load_vendors()
            added_vendor = getattr(flow, "get_final_vendor_name", lambda: None)()
            if added_vendor:
                self.vendor_combo.setCurrentText(added_vendor)

    def _on_date_changed(self, label):
        self._clear_date_highlight(label)

    # ---------- Highlighting / data extraction ----------
    def _clear_date_highlight(self, label):
        if label in getattr(self, "empty_date_fields", set()):
            self.empty_date_fields.remove(label)
            self._highlight_empty_fields()

    def _highlight_empty_fields(self):
        for label, widget in self.fields.items():
            if isinstance(widget, QLineEdit):
                empty = not widget.text().strip()
            elif isinstance(widget, QComboBox):
                empty = not widget.currentText().strip()
            elif isinstance(widget, QDateEdit):
                empty = label in getattr(self, "empty_date_fields", set())
            else:
                empty = False
            widget.setStyleSheet("background-color: yellow;" if empty else "")

    def get_data(self):
        data = []
        for label in [
            "Vendor Name", "Invoice Number", "PO Number", "Invoice Date",
            "Discount Terms", "Due Date", "Discounted Total", "Total Amount",
        ]:
            w = self.fields[label]
            if isinstance(w, QDateEdit):
                value = w.date().toString("MM/dd/yy")
            elif isinstance(w, QComboBox):
                value = w.currentText().strip()
            else:
                txt = w.text().strip()
                value = self._money_plain(txt) if label in getattr(self, "_currency_labels", set()) else txt
            data.append(value)
        return data

    def get_all_data(self):
        self.save_current_invoice()
        return self.values_list

    def get_deleted_files(self):
        return list(self._deleted_files)

    # ---------- Quick Calculator (no tax) ----------
    def _recalc_quick_calc(self):
        sub = self._money(self.qc_subtotal.text())
        ship = self._money(self.qc_shipping.text())
        other = self._money(self.qc_other.text())

        disc_pct = self._percent(self.qc_disc_pct.text())
        disc_amt_input = self._money(self.qc_disc_amt.text())

        disc_amt = disc_amt_input if disc_amt_input is not None else (
            (sub * disc_pct) if (sub is not None and disc_pct is not None) else 0.0
        )
        if disc_amt is None:
            disc_amt = 0.0

        if sub is None:
            self.qc_grand_total.setText("$0.00")
            return

        total = sub - disc_amt + (ship or 0.0) + (other or 0.0)
        self.qc_grand_total.setText(self._fmt_money(total))

    def _apply_quick_total_to(self, target_label):
        text = self.qc_grand_total.text().strip()
        text = text.replace("***", "").replace("$", "").replace(",", "").strip()
        try:
            val = float(text)
            text = f"{val:.2f}"
        except ValueError:
            pass

        if target_label in self.fields:
            w = self.fields[target_label]
            if isinstance(w, QLineEdit):
                w.setText(text)
                if not w.hasFocus():
                    w.setText(self._money_pretty(w.text()))
                self._highlight_empty_fields()

    # ---------- Currency utils ----------
    def _money(self, s):
        if not s:
            return None
        s = s.strip().replace(",", "")
        neg = False
        if s.startswith("(") and s.endswith(")"):
            neg = True
            s = s[1:-1]
        if s.startswith("$"):
            s = s[1:]
        try:
            val = float(s)
            return -val if neg else val
        except ValueError:
            return None

    def _percent(self, s):
        if not s:
            return None
        s = s.strip()
        try:
            if s.endswith("%"):
                num = float(s[:-1])
                return num / 100.0
            num = float(s)
            return num / 100.0 if num > 1 else num
        except ValueError:
            return None

    def _fmt_money(self, val):
        try:
            return f"${val:,.2f}"
        except Exception:
            return "$0.00"

    def _money_plain(self, s: str) -> str:
        if not s:
            return ""
        t = s.replace("$", "").replace(",", "").strip()
        neg = False
        if t.startswith("(") and t.endswith(")"):
            neg = True
            t = t[1:-1].strip()
        try:
            val = float(t)
            if neg:
                val = -val
            return f"{val:.2f}"
        except ValueError:
            return t

    def _money_pretty(self, s: str) -> str:
        p = self._money_plain(s)
        if p == "":
            return ""
        try:
            return f"${float(p):,.2f}"
        except ValueError:
            return s

    def _apply_pretty_currency_display(self):
        for label in getattr(self, "_currency_labels", set()):
            w = self.fields.get(label)
            if w and not w.hasFocus():
                w.setText(self._money_pretty(w.text()))

    # ---------- Event filter: pretty/plain on focus ----------
    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusIn:
            for label in getattr(self, "_currency_labels", set()):
                if obj is self.fields.get(label):
                    obj.setText(self._money_plain(obj.text()))
                    break
            if obj in getattr(self, "_calc_currency_fields", []):
                obj.setText(self._money_plain(obj.text()))
        elif event.type() == QEvent.FocusOut:
            for label in getattr(self, "_currency_labels", set()):
                if obj is self.fields.get(label):
                    obj.setText(self._money_pretty(obj.text()))
                    break
            if obj in getattr(self, "_calc_currency_fields", []):
                obj.setText(self._money_pretty(obj.text()))
        return super().eventFilter(obj, event)

    # ---------- Dirty tracking + guard ----------
    def _wire_dirty_tracking(self):
        """Mark dialog dirty when user edits a field (but not during programmatic loads)."""
        for w in self.fields.values():
            if hasattr(w, "textChanged"):
                w.textChanged.connect(self._mark_dirty)
            if hasattr(w, "currentIndexChanged"):
                w.currentIndexChanged.connect(self._mark_dirty)
            if isinstance(w, QDateEdit):
                w.dateChanged.connect(self._mark_dirty)

    def _mark_dirty(self, *args):
        if self._loading:
            return
        self._dirty = True

    def _discard_changes_current(self):
        """Revert widgets and working copy to last-saved for the current file."""
        idx = self.current_index
        if 0 <= idx < len(self.saved_values_list):
            snapshot = self.saved_values_list[idx]
            self._load_values_into_widgets(snapshot)   # guarded -> won't mark dirty
            self.values_list[idx] = deepcopy(snapshot)
        self.flag_states = list(self.saved_flag_states)
        for i, path in enumerate(self.pdf_paths):
            item = self.file_list.item(i)
            text = os.path.basename(path) if path else ""
            if item:
                self._update_file_item(item, text, self.flag_states[i])
        self._update_flag_button()
        self._dirty = False

    def _confirm_unsaved_then(self, proceed_action):
        """
        If dirty, ask: Yes / Keep Editing / No
        - Yes: save, then proceed_action()
        - Keep Editing: do nothing
        - No: discard, then proceed_action()
        """
        if not self._dirty:
            proceed_action()
            return

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Unsaved changes")
        box.setText("You have unsaved changes. Do you want to save them before continuing?")
        yes_btn = box.addButton("Yes", QMessageBox.YesRole)
        keep_btn = box.addButton("Keep Editing", QMessageBox.RejectRole)  # your “Make Changes”
        no_btn  = box.addButton("No", QMessageBox.DestructiveRole)
        box.setDefaultButton(yes_btn)
        box.exec_()

        clicked = box.clickedButton()
        if clicked is yes_btn:
            self.on_save()
            proceed_action()
        elif clicked is keep_btn:
            pass  # stay put
        elif clicked is no_btn:
            self._discard_changes_current()
            proceed_action()
