import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QDateEdit,
    QPushButton, QDialogButtonBox, QSplitter, QWidget, QFormLayout,
    QComboBox, QMessageBox, QCompleter, QListWidget, QGroupBox,
    QSizePolicy, QScrollArea
)
from PyQt5.QtCore import Qt, QDate, QEvent, QTimer
from PyQt5.QtGui import QBrush, QGuiApplication

from views.components.pdf_viewer import InteractivePDFViewer
from views.dialogs.vendor_dialog import VendorDialog
from extractors.utils import get_vendor_list  # removed calculate_* deps


class ManualEntryDialog(QDialog):
    """Dialog for manual entry of invoice fields with PDF viewer and a Quick Calculator."""

    def __init__(self, pdf_paths, parent=None, values_list=None, start_index=0):
        super().__init__(parent)
        self.setWindowTitle("Manual Entry")
        self.setMinimumSize(1100, 650)

        # Global readability tweaks
        self.setStyleSheet("""
            QLabel { font-size: 13px; }
            QLineEdit, QComboBox, QDateEdit { font-size: 13px; padding: 4px; }
            QPushButton { font-size: 13px; padding: 6px 12px; }
            QGroupBox { font-size: 14px; font-weight: bold; margin-top: 12px; }
        """)

        # Store paths and values for all files
        self.pdf_paths = pdf_paths
        self.values_list = values_list or [[""] * 8 for _ in pdf_paths]
        self.current_index = start_index
        self.save_changes = False

        # --- File list on the far left ---
        self.file_list = QListWidget()
        for path in pdf_paths:
            self.file_list.addItem(os.path.basename(path) if path else "")
        self.file_list.currentRowChanged.connect(self.switch_to_index)
        self.viewed_files = set()

        # --- Form fields ---
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(10)
        form_layout.setHorizontalSpacing(8)
        form_layout.setContentsMargins(8, 8, 8, 8)

        self.fields = {}

        # 1) Vendor dropdown + New Vendor button
        vendor_layout = QHBoxLayout()
        self.vendor_combo = QComboBox()
        self.vendor_combo.setEditable(True)
        self.vendor_combo.setInsertPolicy(QComboBox.NoInsert)
        self.load_vendors()
        completer = self.vendor_combo.completer()
        if completer:
            completer.setCompletionMode(QCompleter.PopupCompletion)
        vendor_layout.addWidget(self.vendor_combo, 1)

        self.add_vendor_btn = QPushButton("New Vendor")
        self.add_vendor_btn.clicked.connect(self.add_new_vendor)
        vendor_layout.addWidget(self.add_vendor_btn)

        form_layout.addRow(QLabel("Vendor Name:"), vendor_layout)
        self.fields["Vendor Name"] = self.vendor_combo

        # 2) Core fields
        self.fields["Invoice Number"] = QLineEdit()
        form_layout.addRow(QLabel("Invoice Number:"), self.fields["Invoice Number"])

        self.fields["PO Number"] = QLineEdit()
        form_layout.addRow(QLabel("PO Number:"), self.fields["PO Number"])

        # 3) Dates
        self.fields["Invoice Date"] = QDateEdit()
        self.fields["Invoice Date"].setCalendarPopup(True)
        self.fields["Invoice Date"].setDisplayFormat("MM/dd/yyyy")
        self.fields["Invoice Date"].setDate(QDate.currentDate())
        form_layout.addRow(QLabel("Invoice Date:"), self.fields["Invoice Date"])

        self.fields["Discount Terms"] = QLineEdit()
        form_layout.addRow(QLabel("Discount Terms:"), self.fields["Discount Terms"])

        # 4) Due Date (fully manual now)
        self.fields["Due Date"] = QDateEdit()
        self.fields["Due Date"].setCalendarPopup(True)
        self.fields["Due Date"].setDisplayFormat("MM/dd/yyyy")
        self.fields["Due Date"].setDate(QDate.currentDate())
        form_layout.addRow(QLabel("Due Date:"), self.fields["Due Date"])

        # 5) Discounted Total (manual)
        self.fields["Discounted Total"] = QLineEdit()
        form_layout.addRow(QLabel("Discounted Total:"), self.fields["Discounted Total"])

        # 6) Total Amount (manual)
        self.fields["Total Amount"] = QLineEdit()
        form_layout.addRow(QLabel("Total Amount:"), self.fields["Total Amount"])

        # --- Quick Calculator (subtotal/discount/shipping/tax/adjust) ---
        self.quick_calc_group = QGroupBox("Quick Calculator")
        qc = QFormLayout()
        qc.setVerticalSpacing(10)
        qc.setHorizontalSpacing(10)
        qc.setContentsMargins(12, 12, 12, 12)

        # Groupbox styling and spacing for title
        self.quick_calc_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #C9C9C9;
                border-radius: 6px;
                margin-top: 16px;
                padding-top: 16px;
                background: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 6px;
                background: #ffffff;
            }
        """)
        self.quick_calc_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        # Inputs
        self.qc_subtotal = QLineEdit()
        self.qc_disc_pct = QLineEdit()     # as %
        self.qc_disc_amt = QLineEdit()     # as $
        self.qc_shipping = QLineEdit()
        self.qc_tax_pct = QLineEdit()      # as %
        self.qc_tax_amt = QLineEdit()      # as $
        self.qc_other = QLineEdit()        # adjustments (+/-)

        # Output
        self.qc_grand_total = QLabel("$0.00")
        self.qc_grand_total.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.qc_grand_total.setStyleSheet("font-weight: bold;")

        # Wire up live recalculation
        for w in (
            self.qc_subtotal, self.qc_disc_pct, self.qc_disc_amt,
            self.qc_shipping, self.qc_tax_pct, self.qc_tax_amt, self.qc_other
        ):
            w.textChanged.connect(self._recalc_quick_calc)

        # Buttons to push result back into fields (as PLAIN numbers)
        buttons_row = QHBoxLayout()
        self.qc_apply_total = QPushButton("Apply → Total Amount")
        self.qc_apply_discounted = QPushButton("Apply → Discounted Total")
        self.qc_apply_total.setMinimumHeight(32)
        self.qc_apply_discounted.setMinimumHeight(32)
        self.qc_apply_total.clicked.connect(lambda: self._apply_quick_total_to("Total Amount"))
        self.qc_apply_discounted.clicked.connect(lambda: self._apply_quick_total_to("Discounted Total"))
        buttons_row.addWidget(self.qc_apply_total)
        buttons_row.addWidget(self.qc_apply_discounted)

        # Layout the calculator
        qc.addRow(QLabel("Subtotal:"), self.qc_subtotal)
        qc.addRow(QLabel("Discount %:"), self.qc_disc_pct)
        qc.addRow(QLabel("Discount $:"), self.qc_disc_amt)
        qc.addRow(QLabel("Shipping:"), self.qc_shipping)
        qc.addRow(QLabel("Tax %:"), self.qc_tax_pct)
        qc.addRow(QLabel("Tax $:"), self.qc_tax_amt)
        qc.addRow(QLabel("Other Adj. (+/−):"), self.qc_other)
        qc.addRow(QLabel("Grand Total:"), self.qc_grand_total)
        qc.addRow(buttons_row)
        self.quick_calc_group.setLayout(qc)

        # Standard button styling for action buttons
        primary_button_style = (
            "QPushButton {"
            "background-color: #5E6F5E;"
            "color: white;"
            "border-radius: 4px;"
            "padding: 6px 12px;"
            "font-weight: bold;"
            "}"
            "QPushButton:hover { background-color: #6b7d6b; }"
            "QPushButton:pressed { background-color: #526052; }"
        )
        for btn in (
            self.add_vendor_btn, self.qc_apply_total, self.qc_apply_discounted
        ):
            btn.setStyleSheet(primary_button_style)

        # --- Navigation Buttons ---
        arrow_layout = QHBoxLayout()
        arrow_layout.addStretch()

        self.prev_button = QPushButton("←")
        self.next_button = QPushButton("→")

        button_style = (
            "QPushButton {"
            "background-color: #5E6F5E;"
            "color: #f0f0f0;"
            "border: 1px solid #3E4F3E;"
            "font-size: 28px;"
            "padding: 10px;"
            "}"
            "QPushButton:hover { background-color: #546454; }"
            "QPushButton:pressed { background-color: #485848; }"
            "QPushButton:disabled { background-color: #bbbbbb; color: #666666; }"
        )
        self.prev_button.setStyleSheet(button_style)
        self.next_button.setStyleSheet(button_style)
        size = 60
        self.prev_button.setFixedSize(size, size)
        self.next_button.setFixedSize(size, size)
        self.prev_button.clicked.connect(self.show_prev)
        self.next_button.clicked.connect(self.show_next)
        arrow_layout.addWidget(self.prev_button)
        arrow_layout.addWidget(self.next_button)
        arrow_layout.addStretch()

        # Combine the form + calculator + navigation on the left
        left_layout = QVBoxLayout()
        left_layout.addLayout(form_layout)
        left_layout.addWidget(self.quick_calc_group)
        left_layout.addSpacing(16)
        left_layout.addLayout(arrow_layout)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        # Make the whole left column scrollable so nothing gets clipped
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.NoFrame)
        left_scroll.setWidget(left_widget)

        # --- Right: PDF Viewer ---
        self.viewer = InteractivePDFViewer(self.pdf_paths[self.current_index])

        # --- Splitter Layout ---
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        # Keep the file list readable but allow shrinking a bit
        self.file_list.setMinimumWidth(140)

        self.splitter.addWidget(self.file_list)
        self.splitter.addWidget(left_scroll)   # scrollable center pane
        self.splitter.addWidget(self.viewer)

        # Ratios: 10% : 50% : 40%
        self.splitter.setStretchFactor(0, 1)   # list
        self.splitter.setStretchFactor(1, 5)   # entry fields (largest)
        self.splitter.setStretchFactor(2, 4)   # pdf viewer

        # Apply initial absolute sizes after layout
        QTimer.singleShot(0, self._apply_splitter_proportions)

        # --- Dialog Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.on_save)
        button_box.rejected.connect(self.reject)
        for btn in button_box.buttons():
            btn.setStyleSheet(primary_button_style)

        # --- Content Layout ---
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.addWidget(self.splitter)
        content_layout.addWidget(button_box)
        self.setLayout(content_layout)

        # Currency fields that display pretty but store plain
        self._currency_labels = {"Total Amount", "Discounted Total"}
        for label in self._currency_labels:
            w = self.fields.get(label)
            if w:
                w.installEventFilter(self)

        # Also pretty/plain toggle for $-based calculator inputs
        self._calc_currency_fields = [
            self.qc_subtotal, self.qc_disc_amt, self.qc_shipping, self.qc_tax_amt, self.qc_other
        ]
        for w in self._calc_currency_fields:
            w.installEventFilter(self)

        # Load first invoice data
        self.load_invoice(self.current_index)

        # Highlight empty fields initially and update on change
        for label, widget in self.fields.items():
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._highlight_empty_fields)
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self._highlight_empty_fields)
            elif isinstance(widget, QDateEdit):
                widget.dateChanged.connect(lambda _, l=label: self._on_date_changed(l))

        # Make the window taller on open (within screen bounds) so buttons are visible
        QTimer.singleShot(0, self._resize_to_fit_content)
        # Ensure PDF starts as fit-to-width after initial layout
        QTimer.singleShot(0, lambda: self.viewer.fit_width())

    # -----------------------------
    # Apply initial splitter proportions
    # -----------------------------
    def _apply_splitter_proportions(self):
        """Set initial splitter sizes to ~10% / 50% / 40% of current width."""
        total = max(1, self.splitter.width())
        sizes = [int(total * 0.10), int(total * 0.50), int(total * 0.40)]
        sizes[2] = max(1, total - sizes[0] - sizes[1])  # exact fill
        self.splitter.setSizes(sizes)

    # -----------------------------
    # Resize dialog on open to avoid scrolling to actions
    # -----------------------------
    def _resize_to_fit_content(self):
        """Resize the dialog so calculator buttons are visible w/o scrolling,
        but never exceed the available screen area."""
        screen = self.windowHandle().screen() if self.windowHandle() else QGuiApplication.primaryScreen()
        if not screen:
            return
        avail = screen.availableGeometry()
        # Aim for a comfortably tall, wide window; cap to screen with a margin
        target_h = min(900, max(750, avail.height() - 80))
        target_w = min(1400, max(1200, avail.width() - 80))
        self.resize(target_w, target_h)
        # Re-apply the 10/50/40 splitter proportions after resize
        self._apply_splitter_proportions()
        # After resize, keep PDF fit-to-width
        if hasattr(self, "viewer") and self.viewer:
            self.viewer.fit_width()

    # -----------------------------
    # Keyboard: arrow navigation when no field is focused
    # -----------------------------
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Left, Qt.Key_Right):
            # If an entry control has focus, let it handle arrows (e.g., caret move).
            if not self._entry_field_has_focus():
                if event.key() == Qt.Key_Left:
                    self.show_prev()
                else:
                    self.show_next()
                event.accept()
                return
        super().keyPressEvent(event)

    def _entry_field_has_focus(self):
        """Return True if a text-entry-like widget currently has focus."""
        w = self.focusWidget()
        return isinstance(w, (QLineEdit, QComboBox, QDateEdit))

    # -----------------------------
    # Persistence / Navigation
    # -----------------------------
    def save_current_invoice(self):
        if not self.values_list:
            return
        self.values_list[self.current_index] = self.get_data()

    def load_invoice(self, index):
        self.current_index = index
        self.mark_file_viewed(index)
        values = self.values_list[index]

        self.vendor_combo.setCurrentText(values[0])
        self.fields["Invoice Number"].setText(values[1])
        self.fields["PO Number"].setText(values[2])

        # Invoice Date
        self.fields["Invoice Date"].setDate(QDate.currentDate())
        invoice_date = values[3]
        try:
            date_obj = QDate.fromString(invoice_date, "MM/dd/yy")
            if date_obj.isValid() and date_obj.year() < 2000:
                year = date_obj.year() % 100
                date_obj = QDate(2000 + year, date_obj.month(), date_obj.day())
            if date_obj.isValid():
                self.fields["Invoice Date"].setDate(date_obj)
        except Exception as e:
            print(f"Error parsing invoice date: {e}")

        self.fields["Discount Terms"].setText(values[4])

        # Due Date
        self.fields["Due Date"].setDate(QDate.currentDate())
        due_date = values[5]
        if due_date.strip():
            try:
                new_date = QDate()
                if '/' in due_date:
                    parts = due_date.split('/')
                    if len(parts) == 3:
                        month = int(parts[0])
                        day = int(parts[1])
                        year = int(parts[2])
                        if year < 100:
                            year = 2000 + year
                        new_date = QDate(year, month, day)

                if not new_date.isValid():
                    date_obj = QDate.fromString(due_date, "MM/dd/yy")
                    if date_obj.isValid():
                        correct_year = 2000 + (date_obj.year() % 100)
                        new_date = QDate(correct_year, date_obj.month(), date_obj.day())
                if new_date.isValid():
                    self.fields["Due Date"].setDate(new_date)
            except Exception as e:
                print(f"Error parsing due date '{due_date}': {e}")

        # Currency fields: set text from values and apply pretty display
        self.fields["Discounted Total"].setText(values[6])
        self.fields["Total Amount"].setText(values[7])
        self._apply_pretty_currency_display()

        # Track empty date fields for highlighting
        self.empty_date_fields = set()
        if not values[3].strip():
            self.empty_date_fields.add("Invoice Date")
        if not values[5].strip():
            self.empty_date_fields.add("Due Date")

        self._highlight_empty_fields()

        # Update navigation buttons and list selection
        self.prev_button.setDisabled(index == 0)
        self.next_button.setDisabled(index == len(self.pdf_paths) - 1)
        if self.file_list.currentRow() != index:
            self.file_list.blockSignals(True)
            self.file_list.setCurrentRow(index)
            self.file_list.blockSignals(False)

        # Replace PDF viewer
        new_viewer = InteractivePDFViewer(self.pdf_paths[index])
        index_in_splitter = self.splitter.indexOf(self.viewer)
        self.splitter.replaceWidget(index_in_splitter, new_viewer)
        new_viewer.show()
        self.viewer.deleteLater()
        self.viewer = new_viewer
        self.splitter.setStretchFactor(index_in_splitter, 1)
        # keep proportions on swap
        QTimer.singleShot(0, self._apply_splitter_proportions)
        # ensure new viewer is fit-to-width after layout
        QTimer.singleShot(0, lambda: self.viewer.fit_width())

    def switch_to_index(self, index):
        if index < 0 or index >= len(self.pdf_paths):
            return
        if index == self.current_index:
            return
        self.save_current_invoice()
        self.load_invoice(index)

    def show_prev(self):
        if self.current_index > 0:
            self.save_current_invoice()
            self.load_invoice(self.current_index - 1)

    def show_next(self):
        if self.current_index < len(self.pdf_paths) - 1:
            self.save_current_invoice()
            self.load_invoice(self.current_index + 1)

    def on_save(self):
        # Ensure currency fields are stored canonically
        for label in self._currency_labels:
            w = self.fields.get(label)
            if w:
                w.setText(self._money_plain(w.text()))
        self.save_current_invoice()
        self.save_changes = True
        self.accept()

    def mark_file_viewed(self, index):
        if index in self.viewed_files:
            return
        self.viewed_files.add(index)
        item = self.file_list.item(index)
        if item is not None:
            item.setForeground(QBrush(Qt.gray))

    # -----------------------------
    # Vendors / Helpers
    # -----------------------------
    def _on_date_changed(self, label):
        self._clear_date_highlight(label)

    def load_vendors(self):
        vendors = get_vendor_list()
        if vendors:
            vendors.sort()
            self.vendor_combo.clear()
            self.vendor_combo.addItems(vendors)

    def add_new_vendor(self):
        dialog = VendorDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            new_vendor = dialog.get_name()
            if new_vendor:
                self.vendor_combo.addItem(new_vendor)
                self.vendor_combo.setCurrentText(new_vendor)

    # -----------------------------
    # Highlighting / Data extraction
    # -----------------------------
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
            widget = self.fields[label]
            if isinstance(widget, QDateEdit):
                value = widget.date().toString("MM/dd/yy")
            elif isinstance(widget, QComboBox):
                value = widget.currentText().strip()
            else:
                txt = widget.text().strip()
                if label in getattr(self, "_currency_labels", set()):
                    # store canonically
                    value = self._money_plain(txt)
                else:
                    value = txt
            data.append(value)
        return data

    def get_all_data(self):
        self.save_current_invoice()
        return self.values_list

    # -----------------------------
    # Quick Calculator logic
    # -----------------------------
    def _recalc_quick_calc(self):
        """Live-recalculate Grand Total from the calculator inputs."""
        sub = self._money(self.qc_subtotal.text())
        ship = self._money(self.qc_shipping.text())
        other = self._money(self.qc_other.text())

        disc_pct = self._percent(self.qc_disc_pct.text())
        disc_amt_input = self._money(self.qc_disc_amt.text())

        tax_pct = self._percent(self.qc_tax_pct.text())
        tax_amt_input = self._money(self.qc_tax_amt.text())

        # Derive discount amount: prefer explicit $ if entered; else use %
        disc_amt = disc_amt_input if disc_amt_input is not None else (
            (sub * disc_pct) if (sub is not None and disc_pct is not None) else 0.0
        )
        if disc_amt is None:
            disc_amt = 0.0

        # Tax base is (subtotal - discount) + shipping (common AP convention; tweak if needed)
        tax_base = None
        if sub is not None:
            tax_base = sub - disc_amt
            if ship is not None:
                tax_base += ship

        # Derive tax amount: prefer explicit $ if entered; else use %
        tax_amt = tax_amt_input if tax_amt_input is not None else (
            (tax_base * tax_pct) if (tax_base is not None and tax_pct is not None) else 0.0
        )
        if tax_amt is None:
            tax_amt = 0.0

        # Grand total = subtotal - discount + shipping + tax + other adjustments
        if sub is None:
            self.qc_grand_total.setText("$0.00")
            return

        total = sub - disc_amt + (ship or 0.0) + tax_amt + (other or 0.0)
        self.qc_grand_total.setText(self._fmt_money(total))

    def _apply_quick_total_to(self, target_label):
        """Copy the calculator’s grand total into a target field as plain numeric (no $ or commas)."""
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
                # Immediately pretty-display it if the field is not focused
                if not w.hasFocus():
                    w.setText(self._money_pretty(w.text()))
                self._highlight_empty_fields()

    # -----------------------------
    # Currency helpers / formatting
    # -----------------------------
    def _money(self, s):
        """Parse a money string like '$1,234.56' or '1234.56'. Returns float or None."""
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
        """Parse percent like '2', '2%', or '0.02' → fraction (0.02) or None."""
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
        """Format a float as currency with $ and 2 decimals."""
        try:
            return f"${val:,.2f}"
        except Exception:
            return "$0.00"

    def _money_plain(self, s: str) -> str:
        """Return plain numeric string with 2 decimals, no $/commas; empty -> ''."""
        if not s:
            return ""
        t = s.replace("$", "").replace(",", "").strip()
        # handle parentheses negatives
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
            return t  # leave as-is for user to fix

    def _money_pretty(self, s: str) -> str:
        """Return pretty currency like $2,500.68 from a raw string; empty -> ''."""
        p = self._money_plain(s)
        if p == "":
            return ""
        try:
            return f"${float(p):,.2f}"
        except ValueError:
            return s

    def _apply_pretty_currency_display(self):
        """Pretty-format any currency field currently showing plain numbers."""
        for label in self._currency_labels:
            w = self.fields.get(label)
            if w and not w.hasFocus():
                w.setText(self._money_pretty(w.text()))

    # -----------------------------
    # Focus-based pretty/plain toggle
    # -----------------------------
    def eventFilter(self, obj, event):
        # Fields on the main form
        if event.type() == QEvent.FocusIn:
            for label in getattr(self, "_currency_labels", set()):
                if obj is self.fields.get(label):
                    obj.setText(self._money_plain(obj.text()))
                    break
            # Calculator currency inputs
            if obj in getattr(self, "_calc_currency_fields", []):
                obj.setText(self._money_plain(obj.text()))
        elif event.type() == QEvent.FocusOut:
            for label in getattr(self, "_currency_labels", set()):
                if obj is self.fields.get(label):
                    obj.setText(self._money_pretty(obj.text()))
                    break
            # Calculator currency inputs
            if obj in getattr(self, "_calc_currency_fields", []):
                obj.setText(self._money_pretty(obj.text()))
        return super().eventFilter(obj, event)