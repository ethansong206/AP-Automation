import os
from copy import deepcopy

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QDateEdit,
    QPushButton, QSplitter, QWidget, QFormLayout, QComboBox, QMessageBox,
    QCompleter, QListWidget, QListWidgetItem, QGroupBox,
    QScrollArea, QGridLayout, QFrame, QGraphicsDropShadowEffect, QToolButton
)
from PyQt5.QtCore import Qt, QDate, QEvent, QTimer, pyqtSignal, QSize
from PyQt5.QtGui import QBrush, QGuiApplication, QColor, QPainter, QFont, QIcon

# ---------- THEME & ICONS: reuse from app_shell when available ----------
try:
    # Typical project path
    from views.app_shell import THEME as APP_THEME, _resolve_icon
except Exception:
    try:
        # Alternate import if views/ prefix isn't used
        from app_shell import THEME as APP_THEME, _resolve_icon
    except Exception:
        # Safe fallback so this dialog still runs in isolation
        APP_THEME = {
            "outer_bg": "#F2F3F5",
            "card_bg": "#FFFFFF",
            "card_border": "#E1E4E8",
            "brand_green": "#064420",
            "radius": 12,
        }
        def _resolve_icon(name: str) -> str:
            # Fallback path guess; replace if your assets live elsewhere
            return os.path.join("assets", "icons", name)

THEME = APP_THEME

# Project components (unchanged)
from views.components.pdf_viewer import InteractivePDFViewer
from views.dialogs.vendor_dialog import AddVendorFlow
from extractors.utils import get_vendor_list, calculate_discount_due_date
from assets.constants import COLORS


class _DialogTitleBar(QWidget):
    """Custom titlebar:
    - Reuses your SVG icons (minimize/close) via _resolve_icon
    - Drag anywhere on the left/title area to move the frameless window
    """
    def __init__(self, parent=None, title_text: str = "Manual Entry"):
        super().__init__(parent)
        self._drag_offset = None
        self.setMouseTracking(True)

        row = QHBoxLayout(self)
        row.setContentsMargins(24, 16, 12, 16)
        row.setSpacing(10)

        self.title = QLabel(title_text, self)
        self.title.setObjectName("DialogBigTitle")
        self.title.setFont(QFont("Inter", 20, QFont.Bold))
        self.title.setStyleSheet(f"color: {THEME['brand_green']};")

        # Window control buttons (match main window look)
        self._icon_min = QIcon(_resolve_icon("minimize.svg"))
        self._icon_close = QIcon(_resolve_icon("close.svg"))

        def make_winbtn(icon: QIcon) -> QToolButton:
            b = QToolButton(self)
            b.setObjectName("WinBtn")
            b.setFixedSize(48, 36)
            b.setIcon(icon)
            b.setIconSize(QSize(36, 36))
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setStyleSheet(
                "QToolButton#WinBtn { background: transparent; border: none; padding: 0; }"
                "QToolButton#WinBtn:hover { background: rgba(0,0,0,0.06); border-radius: 6px; }"
            )
            return b

        self.btn_min = make_winbtn(self._icon_min)
        self.btn_close = make_winbtn(self._icon_close)
        self.btn_min.clicked.connect(self.window().showMinimized)
        self.btn_close.clicked.connect(self.window().close)

        row.addWidget(self.title)
        row.addStretch()
        row.addWidget(self.btn_min)
        row.addWidget(self.btn_close)
        self.setStyleSheet("background: transparent;")

    # drag window
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.childAt(e.pos()) not in (self.btn_min, self.btn_close):
            self._drag_offset = e.globalPos() - self.window().frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_offset:
            self.window().move(e.globalPos() - self._drag_offset)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_offset = None
        super().mouseReleaseEvent(e)


class ManualEntryDialog(QDialog):
    """Manual Entry dialog wrapped in a frameless, rounded-card shell.

    Fixes:
      • Behaves as a true top‑level window (no clipping, full interactivity outside main window)
      • Application‑modal to prevent main window edge‑resize from engaging while dragging dialog
      • Reuses the main window's SVG buttons for consistent look
    """

    file_deleted = pyqtSignal(str)
    row_saved = pyqtSignal(str, list, bool)  # (file_path, row_values, flagged)

    def __init__(self, pdf_paths, parent=None, values_list=None, flag_states=None, start_index=0):
        super().__init__(parent)

        # ---- Frameless top-level setup ----
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowTitle("Manual Entry")
        self.setMinimumSize(1100, 650)
        self.setObjectName("ManualEntryRoot")

        # Root layout (lets us paint a rounded background in paintEvent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Titlebar
        self.titlebar = _DialogTitleBar(self, title_text="Manual Entry")
        root.addWidget(self.titlebar)

        # Padding around the inner card
        pad = QVBoxLayout()
        pad.setContentsMargins(24, 6, 24, 24)
        pad.setSpacing(10)
        root.addLayout(pad)

        # Inner white card with shadow
        self.card = QFrame(self)
        self.card.setObjectName("Card")
        self.card.setStyleSheet(
            f"QFrame#Card {{ background: {THEME['card_bg']};"
            f"  border: 1px solid {THEME['card_border']};"
            f"  border-radius: {THEME['radius']}px; }}"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 45))
        self.card.setGraphicsEffect(shadow)
        pad.addWidget(self.card)

        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(20, 20, 20, 20)
        card_lay.setSpacing(12)

        # ---------- Original dialog UI (unchanged logic) ----------
        self.setStyleSheet(self.styleSheet() + """
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
        self.saved_values_list = deepcopy(self.values_list)
        self.current_index = start_index if 0 <= start_index < len(self.pdf_paths) else 0
        self._deleted_files = []
        self._dirty = False
        self._loading = False
        self.save_changes = False
        self.viewed_files = set()

        # ===== Left: file list =====
        self.file_list = QListWidget()
        self.file_list.mousePressEvent = self._file_list_mouse_press
        for i, (path, flagged) in enumerate(zip(self.pdf_paths, self.flag_states)):
            item = QListWidgetItem()
            text = self._get_display_text(i)
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
        self.vendor_combo.currentTextChanged.connect(self._on_display_fields_changed)
        vendor_layout.addWidget(self.vendor_combo, 1)
        vendor_layout.addSpacing(10)
        self.add_vendor_btn = QPushButton("New Vendor")
        self.add_vendor_btn.clicked.connect(self.add_new_vendor)
        vendor_layout.addWidget(self.add_vendor_btn)
        form_layout.addRow(QLabel("Vendor Name:"), vendor_layout)
        self.fields["Vendor Name"] = self.vendor_combo

        # Core fields
        self.fields["Invoice Number"] = QLineEdit()
        self.fields["Invoice Number"].textChanged.connect(self._on_display_fields_changed)
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
        self.fields["Shipping Cost"] = QLineEdit()
        form_layout.addRow(QLabel("Shipping Cost:"), self.fields["Shipping Cost"])
        self.fields["Total Amount"] = QLineEdit()
        form_layout.addRow(QLabel("Total Amount:"), self.fields["Total Amount"])

        # Quick Calculator (no tax rows)
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
        self.qc_grand_total = QLabel("$0.00")
        self.qc_grand_total.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.qc_grand_total.setStyleSheet("font-weight: bold;")

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.qc_push_shipping = QPushButton("Push to Shipping Cost")
        self.qc_push_total = QPushButton("Push to Total Amount")
        self.qc_push_shipping.clicked.connect(self._push_shipping_from_qc)
        self.qc_push_total.clicked.connect(lambda: self._apply_quick_total_to("Total Amount"))
        btn_row.addWidget(self.qc_push_shipping)
        btn_row.addWidget(self.qc_push_total)

        qc.addRow(QLabel("Subtotal:"), self.qc_subtotal)
        qc.addRow(QLabel("Discount %:"), self.qc_disc_pct)
        qc.addRow(QLabel("Discount $:"), self.qc_disc_amt)
        qc.addRow(QLabel("Shipping:"), self.qc_shipping)
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
        for b in (self.add_vendor_btn, self.qc_push_shipping, self.qc_push_total, self.due_calc_btn):
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

        # Put the content into the card
        card_lay.addWidget(self.splitter)

        # Currency fields we pretty/normalize
        self._currency_labels = {"Total Amount", "Shipping Cost"}
        for label in self._currency_labels:
            w = self.fields.get(label)
            if w:
                w.installEventFilter(self)

        # Quick calc fields that use pretty/plain toggling (no tax fields now)
        self._calc_currency_fields = [
            self.qc_subtotal, self.qc_disc_amt, self.qc_shipping
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

    # ---------- Frameless outer background (rounded gray) ----------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(THEME["outer_bg"]))
        p.drawRoundedRect(r, THEME["radius"], THEME["radius"])

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
            f"Are you sure you want to delete this invoice? {fname}",
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
        self.saved_flag_states.pop(idx)
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
            self.fields["Shipping Cost"].setText("")
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
                    f"‘{typed_vendor}’ isn’t in your vendor list."
                    "You’ll need to add it first (Vendor Name → Vendor Number → optional Identifier)."
                    "Vendor Number is required; Identifier is optional."
                ),
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Ok
            )
            if warn == QMessageBox.Cancel:
                return False # abort save; let the user decide later

            # Launch the guided flow used by the New Vendor button
            current_pdf = (
                self.pdf_paths[self.current_index]
                if (self.pdf_paths and 0 <= self.current_index < len(self.pdf_paths))
                else ""
            )
            flow = AddVendorFlow(pdf_path=current_pdf, parent=self, prefill_vendor_name=typed_vendor)
            if flow.exec_() != QDialog.Accepted:
                return False # user canceled adding the vendor; don't save yet

            # Refresh dropdown and select the new vendor
            self.load_vendors()
            added_vendor = getattr(flow, "get_final_vendor_name", lambda: None)()
            if added_vendor:
                self.vendor_combo.setCurrentText(added_vendor)
            else:
                QMessageBox.warning(self, "Vendor Not Added", "The vendor wasn’t added. Please try again.")
                return False

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
        return True

    def closeEvent(self, event):
        """Guard window-X close. Ensure 'No' actually closes if chosen."""
        event.ignore()

        def proceed_accept_close():
            self.save_changes = True
            self.setResult(QDialog.Accepted)
            event.accept()

        self._confirm_unsaved_then(proceed_accept_close)

    # ---------- Due Date calculation ----------
    def _on_calculate_due_date(self):
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
                "I couldn't determine a due date from those Discount Terms."
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
        note = QLabel("Saved", self)
        note.setStyleSheet(
            """
            QLabel {
                background-color: #e7f5e7;
                color: #2f7a2f;
                border: 1px solid #b9e0b9;
                border-radius: 4px;
                padding: 3px 8px;
                font-weight: bold;
            }
            """
        )
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

    def _get_display_text(self, idx):
        """Return "Vendor_Invoice" for index if available; otherwise use filename."""
        if idx == self.current_index and hasattr(self, "fields") and "Invoice Number" in self.fields:
            vendor = getattr(self, "vendor_combo", None)
            v = vendor.currentText().strip() if vendor else ""
            inv = self.fields["Invoice Number"].text().strip()
            display = f"{v}_{inv}" if v and inv else (v or inv)
            if display:
                return display
            use_saved = False
        else:
            use_saved = True
        if use_saved and 0 <= idx < len(self.values_list):
            v = self.values_list[idx][0].strip()
            inv = self.values_list[idx][1].strip()
            display = f"{v}_{inv}" if v and inv else (v or inv)
            if display:
                return display
        path = self.pdf_paths[idx] if 0 <= idx < len(self.pdf_paths) else ""
        return os.path.basename(path) if path else ""

    def _on_display_fields_changed(self, *args):
        idx = self.current_index
        item = self.file_list.item(idx)
        if not item:
            return
        display = self._get_display_text(idx)
        self._update_file_item(item, display, self.flag_states[idx])

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
        text = self._get_display_text(idx)
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
        # Fallback to default behavior
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
        current_pdf = (
            self.pdf_paths[self.current_index]
            if (self.pdf_paths and 0 <= self.current_index < len(self.pdf_paths))
            else ""
        )
        prefill_name = self.vendor_combo.currentText().strip()
        flow = AddVendorFlow(pdf_path=current_pdf, parent=self, prefill_vendor_name=prefill_name)
        if flow.exec_() == QDialog.Accepted:
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
            "Discount Terms", "Due Date", "Shipping Cost", "Total Amount",
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

        total = sub - disc_amt + (ship or 0.0)
        self.qc_grand_total.setText(self._fmt_money(total))

    def _apply_quick_total_to(self, target_label):
        text = self.qc_grand_total.text().strip()
        text = text.replace("$", "").replace(",", "").strip()
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

    def _push_shipping_from_qc(self):
        w = self.fields.get("Shipping Cost")
        if w:
            w.setText(self.qc_shipping.text())
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
                w = self.fields.get(label)
                if w is obj:
                    w.setText(self._money_plain(w.text()))
        elif event.type() == QEvent.FocusOut:
            for label in getattr(self, "_currency_labels", set()):
                w = self.fields.get(label)
                if w is obj:
                    if not w.hasFocus():
                        w.setText(self._money_pretty(w.text()))
        return super().eventFilter(obj, event)

    # ---------- Dirty tracking + unsaved guard ----------
    def _wire_dirty_tracking(self):
        def mark_dirty(*_):
            if not self._loading:
                self._dirty = True
        for label, w in self.fields.items():
            if isinstance(w, QLineEdit):
                w.textChanged.connect(mark_dirty)
            elif isinstance(w, QComboBox):
                w.currentTextChanged.connect(mark_dirty)
            elif isinstance(w, QDateEdit):
                w.dateChanged.connect(mark_dirty)

    def _confirm_unsaved_then(self, proceed_fn):
        if not self._dirty:
            proceed_fn()
            return
        ans = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Save them before continuing?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes,
        )
        if ans == QMessageBox.Cancel:
            return
        if ans == QMessageBox.Yes:
            if not self.on_save():
                return  # save aborted (e.g., vendor add canceled)
        # at this point either saved or user chose No
        proceed_fn()
