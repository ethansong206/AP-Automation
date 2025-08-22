import os
from copy import deepcopy

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QDateEdit,
    QPushButton, QSplitter, QWidget, QFormLayout, QComboBox, QMessageBox,
    QCompleter, QListWidget, QListWidgetItem, QGroupBox,
    QScrollArea, QGridLayout, QFrame, QGraphicsDropShadowEffect, QToolButton,
    QApplication, QSizePolicy
)
from PyQt5.QtCore import Qt, QDate, QEvent, QTimer, pyqtSignal, QSize, QPoint, QRect
from PyQt5.QtGui import QBrush, QGuiApplication, QColor, QPainter, QFont, QIcon, QCursor

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

# Icon used for combo box dropdown arrow
ARROW_ICON = _resolve_icon("down_arrow.svg").replace(os.sep, "/")

# Resize margin for edge detection
RESIZE_MARGIN = 14

# Project components (unchanged)
from views.components.pdf_viewer import InteractivePDFViewer
from views.dialogs.vendor_list_dialog import VendorListDialog
from extractors.utils import get_vendor_list, calculate_discount_due_date
from assets.constants import COLORS
from views.helpers.style_loader import load_stylesheet, get_style_path


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
        main_title_font = QFont("Inter", 24, QFont.Bold)
        self.title.setFont(main_title_font)
        self.title.setStyleSheet(f"color: {THEME['brand_green']}; font-size: 24px; font-weight: bold;")

        # Window control buttons (match main window look)
        self._icon_min = QIcon(_resolve_icon("minimize.svg"))
        self._icon_max = QIcon(_resolve_icon("maximize.svg"))
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
        self.btn_max = make_winbtn(self._icon_max)
        self.btn_close = make_winbtn(self._icon_close)
        self.btn_min.clicked.connect(self.window().showMinimized)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(self.window().close)

        row.addWidget(self.title)
        row.addStretch()
        row.addWidget(self.btn_min)
        row.addWidget(self.btn_max)
        row.addWidget(self.btn_close)
        self.setStyleSheet("background: transparent;")

    # drag window
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.childAt(e.pos()) not in (self.btn_min, self.btn_max, self.btn_close):
            self._drag_offset = e.globalPos() - self.window().frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_offset and not self.window().isMaximized():
            self.window().move(e.globalPos() - self._drag_offset)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_offset = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        self._toggle_max()

    def _toggle_max(self):
        w = self.window()
        if w.isMaximized():
            w.showNormal()
        else:
            w.showMaximized()


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
        self.setMinimumSize(1600, 1000)
        self.setObjectName("ManualEntryRoot")

        # Root layout (lets us paint a rounded background in paintEvent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Titlebar - fixed height
        self.titlebar = _DialogTitleBar(self, title_text="Manual Entry")
        self.titlebar.setMouseTracking(True)
        self.titlebar.setFixedHeight(60)  # Set fixed height for titlebar
        root.addWidget(self.titlebar, 0)  # 0 stretch factor = fixed size

        # Direct gray background area for splitter - this should expand
        gray_area = QVBoxLayout()
        gray_area.setContentsMargins(24, 6, 24, 24)
        gray_area.setSpacing(10)
        root.addLayout(gray_area, 1)  # 1 stretch factor = expands

        # ---------- Enhanced dialog UI styling ----------
        base_style = load_stylesheet(get_style_path('default.qss'))
        self.setStyleSheet(base_style + f"""
            QLabel {{ font-size: 15px; }}
            
            /* Input fields with white background - using specific selectors and !important */
            ManualEntryDialog QLineEdit,
            ManualEntryDialog QComboBox,
            ManualEntryDialog QDateEdit {{
                font-size: 15px !important; 
                padding: 8px 12px !important; 
                background-color: #FFFFFF !important;
                color: #000000 !important;
                border: 1px solid {THEME['card_border']} !important;
                border-radius: 6px !important;
                min-height: 20px !important;
                selection-background-color: {THEME['brand_green']} !important;
                selection-color: white !important;
            }}
            
            /* GLOBAL ComboBox dropdown styling to ensure it always appears */
            ManualEntryDialog QComboBox {{
                padding-right: 30px !important;
            }}
            ManualEntryDialog QComboBox::drop-down {{
                subcontrol-origin: padding !important;
                subcontrol-position: top right !important;
                width: 28px !important;
                border-left: 2px solid {THEME['card_border']} !important;
                border-top-right-radius: 6px !important;
                border-bottom-right-radius: 6px !important;
                background-color: #FFFFFF !important;
                padding-right: 8px !important;
                margin: 0 !important;
            }}
            ManualEntryDialog QComboBox::drop-down:hover {{
                background-color: #e0e0e0 !important;
            }}
            ManualEntryDialog QComboBox::drop-down:pressed {{
                background-color: #d0d0d0 !important;
            }}
            ManualEntryDialog QComboBox::down-arrow {{
                image: url({ARROW_ICON}) !important;
                width: 12px !important;
                height: 12px !important;
                subcontrol-origin: padding !important;
                subcontrol-position: center !important;
            }}
            
            /* QDateEdit dropdown styling to match QComboBox */
            ManualEntryDialog QDateEdit::drop-down {{
                subcontrol-origin: padding !important;
                subcontrol-position: top right !important;
                width: 28px !important;
                border-left: 2px solid {THEME['card_border']} !important;
                border-top-right-radius: 6px !important;
                border-bottom-right-radius: 6px !important;
                background-color: #FFFFFF !important;
                padding-right: 8px !important;
                margin: 0 !important;
            }}
            ManualEntryDialog QDateEdit::drop-down:hover {{
                background-color: #e0e0e0 !important;
            }}
            ManualEntryDialog QDateEdit::drop-down:pressed {{
                background-color: #d0d0d0 !important;
            }}
            ManualEntryDialog QDateEdit::down-arrow {{
                image: url({ARROW_ICON}) !important;
                width: 12px !important;
                height: 12px !important;
                subcontrol-origin: padding !important;
                subcontrol-position: center !important;
            }}
            
            /* Additional specific overrides for problematic elements */
            /* Exclude calendar widgets from global styling */
            QWidget QLineEdit:not(QCalendarWidget QLineEdit),
            QWidget QComboBox:not(QCalendarWidget QComboBox), 
            QWidget QDateEdit:not(QCalendarWidget QDateEdit) {{
                background-color: #FFFFFF !important;
                color: #000000 !important;
            }}
            
            /* Ensure calendar widgets are excluded from main styling */
            QCalendarWidget, QCalendarWidget * {{
                font-family: default;
                font-size: 9pt;
                background-color: white;
                color: black;
            }}
            
            ManualEntryDialog QLineEdit:focus, 
            ManualEntryDialog QComboBox:focus, 
            ManualEntryDialog QDateEdit:focus {{
                border-color: {THEME['brand_green']} !important;
                outline: none !important;
                background-color: #FFFFFF !important;
            }}
            
            ManualEntryDialog QComboBox::drop-down {{
                border: none !important;
                padding-right: 8px !important;
                background-color: #FFFFFF !important;
            }}
            

            ManualEntryDialog QComboBox::down-arrow {{
                image: url({ARROW_ICON}) !important;
                width: 12px !important;
                height: 12px !important;
                subcontrol-origin: padding !important;
                subcontrol-position: center !important;
            }}
            
            /* Second QDateEdit dropdown styling block */
            ManualEntryDialog QDateEdit::drop-down {{
                border: none !important;
                padding-right: 8px !important;
                background-color: #FFFFFF !important;
            }}
            ManualEntryDialog QDateEdit::down-arrow {{
                image: url({ARROW_ICON}) !important;
                width: 12px !important;
                height: 12px !important;
                subcontrol-origin: padding !important;
                subcontrol-position: center !important;
            }}
            
            ManualEntryDialog QComboBox QAbstractItemView {{
                background-color: #FFFFFF !important;
                color: #000000 !important;
                border: 1px solid {THEME['card_border']} !important;
                border-radius: 4px !important;
                selection-background-color: {THEME['brand_green']} !important;
                selection-color: white !important;
            }}
            
            QPushButton {{ 
                font-size: 15px; 
                padding: 9px 15px; 
            }}
            
            QGroupBox {{ 
                font-size: 18px; 
                font-weight: bold; 
                margin-top: 15px; 
                background-color: transparent;
                border: 1px solid {THEME['card_border']};
                border-radius: 8px;
                padding-top: 10px;
            }}
            
            QGroupBox::title {{
                color: {THEME['brand_green']};
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                background-color: {THEME['outer_bg']};
            }}
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

        # --- Resize state variables ---
        self._resizing = False
        self._resizeDir = None  # 'l','r','t','b','tl','tr','bl','br'
        self._startGeom = QRect()
        self._startPos = QPoint()
        self._cursorOverridden = False
        
        # Enable mouse tracking for resize functionality
        self.setMouseTracking(True)
        
        # Install event filter to handle resize events
        qapp = QApplication.instance()
        if qapp is not None:
            qapp.installEventFilter(self)

        # ===== Left: file list card =====
        left_card = QFrame()
        left_card.setObjectName("LeftCard")
        left_card.setMouseTracking(True)
        left_card.setStyleSheet(f"""
            QFrame#LeftCard {{
                background: {THEME['card_bg']};
                border: 1px solid {THEME['card_border']};
                border-radius: {THEME['radius']}px;
            }}
        """)
        # Add subtle shadow to left card
        left_shadow = QGraphicsDropShadowEffect(left_card)
        left_shadow.setBlurRadius(12)
        left_shadow.setOffset(0, 2)
        left_shadow.setColor(QColor(0, 0, 0, 15))
        left_card.setGraphicsEffect(left_shadow)
        left_card_layout = QVBoxLayout(left_card)
        left_card_layout.setContentsMargins(12, 12, 12, 12)
        left_card_layout.setSpacing(8)
        
        # File list title
        file_list_title = QLabel("Files")
        title_font = QFont("Inter", 18, QFont.Bold)
        file_list_title.setFont(title_font)
        file_list_title.setStyleSheet(f"color: {THEME['brand_green']}; margin-bottom: 6px; font-size: 18px; font-weight: bold;")
        left_card_layout.addWidget(file_list_title)
        
        self.file_list = QListWidget()
        self.file_list.setObjectName("FileListWidget")
        self.file_list.mousePressEvent = self._file_list_mouse_press
        # Zebra striping and styling
        self.file_list.setStyleSheet("""
            QListWidget#FileListWidget {
                border: none;
                background: transparent;
                selection-background-color: rgba(6, 68, 32, 0.1);
                outline: none;
            }
            QListWidget#FileListWidget::item {
                padding: 8px 12px;
                border-radius: 6px;
                margin: 1px 0px;
            }
            QListWidget#FileListWidget::item:nth-child(even) {
                background-color: #F8F9FA;
            }
            QListWidget#FileListWidget::item:nth-child(odd) {
                background-color: transparent;
            }
            QListWidget#FileListWidget::item:hover {
                background-color: rgba(6, 68, 32, 0.05);
            }
            QListWidget#FileListWidget::item:selected {
                background-color: rgba(6, 68, 32, 0.1);
                border: 1px solid rgba(6, 68, 32, 0.2);
            }
        """)
        left_card_layout.addWidget(self.file_list)
        
        for i, (path, flagged) in enumerate(zip(self.pdf_paths, self.flag_states)):
            item = QListWidgetItem()
            text = self._get_display_text(i)
            self._update_file_item(item, text, flagged)
            self.file_list.addItem(item)

        # ===== Center: manual entry fields (directly on gray background) =====
        center_widget = QWidget()
        center_widget.setMouseTracking(True)
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(16, 4, 16, 16)  # Reduced top margin from 8 to 4
        center_layout.setSpacing(3)  # Reduced spacing from 6 to 3
        
        # Manual entry title with reduced margins - use !important to override global QDialog QLabel styles
        entry_title = QLabel("Invoice Details")
        entry_title.setObjectName("InvoiceDetailsTitle")  # Give it a specific ID
        title_font = QFont("Inter", 18, QFont.Bold)
        entry_title.setFont(title_font)
        entry_title.setStyleSheet(f"""
            QLabel#InvoiceDetailsTitle {{
                color: {THEME['brand_green']} !important;
                font-size: 18px !important;
                font-weight: bold !important;
                margin: 0px !important;
                padding: 0px !important;
                margin-top: 0px !important;
                margin-bottom: 0px !important;
            }}
        """)
        center_layout.addWidget(entry_title)
        
        # Add explicit small spacing after title
        center_layout.addSpacing(2)
        
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(10)
        form_layout.setHorizontalSpacing(10)
        form_layout.setContentsMargins(0, 0, 0, 0)

        self.fields = {}

        # Vendor
        vendor_layout = QHBoxLayout()
        self.vendor_combo = QComboBox()
        self.vendor_combo.setEditable(True)
        self.vendor_combo.setInsertPolicy(QComboBox.NoInsert)
        self.vendor_combo.setMaxVisibleItems(20)

        # Ensure the dropdown uses a view with a scroll bar that can actually scroll
        combo_view = self.vendor_combo.view()
        combo_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        comp = self.vendor_combo.completer()
        if comp:
            comp.setCompletionMode(QCompleter.PopupCompletion)
            # The completer's popup is a separate view; make sure it also scrolls
            comp.popup().setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.load_vendors()
        self.vendor_combo.currentTextChanged.connect(self._on_display_fields_changed)
        vendor_layout.addWidget(self.vendor_combo, 1)
        vendor_layout.addSpacing(10)
        self.vendor_list_btn = QPushButton("Vendor List")
        self.vendor_list_btn.clicked.connect(self.open_vendor_list)
        vendor_layout.addWidget(self.vendor_list_btn)
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
        
        # Configure calendar to be large enough and look default
        calendar = self.fields["Invoice Date"].calendarWidget()
        if calendar:
            calendar.setMinimumSize(380, 240)  # Ensure calendar is wide enough for all 7 days
            # Remove any inherited styling to make it look default
            calendar.setStyleSheet("""
                QCalendarWidget {
                    font-family: default !important;
                    font-size: 9pt !important;
                    background-color: white !important;
                    alternate-background-color: #f0f0f0 !important;
                }
                QCalendarWidget QTableView {
                    selection-background-color: #3399ff !important;
                    selection-color: white !important;
                    font-size: 9pt !important;
                }
                QCalendarWidget QWidget {
                    color: black !important;
                    background-color: white !important;
                }
            """)
        
        form_layout.addRow(QLabel("Invoice Date:"), self.fields["Invoice Date"])

        # Discount Terms
        self.fields["Discount Terms"] = QLineEdit()
        form_layout.addRow(QLabel("Discount Terms:"), self.fields["Discount Terms"])

        # Due Date + Calculate button
        self.fields["Due Date"] = QDateEdit()
        self.fields["Due Date"].setCalendarPopup(True)
        self.fields["Due Date"].setDisplayFormat("MM/dd/yyyy")
        self.fields["Due Date"].setDate(QDate.currentDate())
        
        # Configure Due Date calendar to be large enough and look default
        due_calendar = self.fields["Due Date"].calendarWidget()
        if due_calendar:
            due_calendar.setMinimumSize(380, 240)  # Ensure calendar is wide enough for all 7 days
            # Remove any inherited styling to make it look default
            due_calendar.setStyleSheet("""
                QCalendarWidget {
                    font-family: default !important;
                    font-size: 9pt !important;
                    background-color: white !important;
                    alternate-background-color: #f0f0f0 !important;
                }
                QCalendarWidget QTableView {
                    selection-background-color: #3399ff !important;
                    selection-color: white !important;
                    font-size: 9pt !important;
                }
                QCalendarWidget QWidget {
                    color: black !important;
                    background-color: white !important;
                }
            """)
        
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
        qc.setVerticalSpacing(10)
        qc.setHorizontalSpacing(12)
        qc.setContentsMargins(15, 10, 15, 15)

        def new_lineedit():
            e = QLineEdit()
            e.textChanged.connect(self._recalc_quick_calc)
            return e

        self.qc_subtotal = new_lineedit()
        self.qc_disc_pct = new_lineedit()   # %
        self.qc_disc_amt = new_lineedit()   # $
        self.qc_shipping = new_lineedit()
        self.qc_total_wo_shipping = QLabel("$0.00")
        self.qc_total_wo_shipping.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.qc_grand_total = QLabel("$0.00")
        self.qc_grand_total.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.qc_grand_total.setStyleSheet("font-weight: bold;")

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.qc_push_shipping = QPushButton("Push to Shipping Cost")
        self.qc_push_total = QPushButton("Push to Total Amount")
        self.qc_push_shipping.clicked.connect(self._push_shipping_from_qc)
        self.qc_push_total.clicked.connect(lambda: self._apply_quick_total_to("Total Amount", self.qc_total_wo_shipping))
        btn_row.addWidget(self.qc_push_shipping)
        btn_row.addWidget(self.qc_push_total)

        qc.addRow(QLabel("Subtotal:"), self.qc_subtotal)
        qc.addRow(QLabel("Discount %:"), self.qc_disc_pct)
        qc.addRow(QLabel("Discount $:"), self.qc_disc_amt)
        qc.addRow(QLabel("Shipping:"), self.qc_shipping)
        qc.addRow(QLabel("Total without Shipping:"), self.qc_total_wo_shipping)
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
        for b in (self.vendor_list_btn, self.qc_push_shipping, self.qc_push_total, self.due_calc_btn):
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

        # Add form and other content to center widget
        center_layout.addLayout(form_layout)
        center_layout.addWidget(self.quick_calc_group)
        center_layout.addSpacing(6)
        center_layout.addWidget(row_container)

        # Wrap center widget in scroll area
        center_scroll = QScrollArea()
        center_scroll.setWidgetResizable(True)
        center_scroll.setFrameShape(QScrollArea.NoFrame)
        center_scroll.setStyleSheet("background: transparent;")
        center_scroll.setWidget(center_widget)

        # ===== Right: PDF viewer card =====
        right_card = QFrame()
        right_card.setObjectName("RightCard")
        right_card.setMouseTracking(True)
        right_card.setStyleSheet(f"""
            QFrame#RightCard {{
                background: {THEME['card_bg']};
                border: 1px solid {THEME['card_border']};
                border-radius: {THEME['radius']}px;
            }}
        """)
        # Add subtle shadow to right card
        right_shadow = QGraphicsDropShadowEffect(right_card)
        right_shadow.setBlurRadius(12)
        right_shadow.setOffset(0, 2)
        right_shadow.setColor(QColor(0, 0, 0, 15))
        right_card.setGraphicsEffect(right_shadow)
        right_card_layout = QVBoxLayout(right_card)
        right_card_layout.setContentsMargins(12, 12, 12, 12)
        right_card_layout.setSpacing(8)
        
        # PDF viewer title
        pdf_title = QLabel("PDF Preview")
        title_font = QFont("Inter", 18, QFont.Bold)
        pdf_title.setFont(title_font)
        pdf_title.setStyleSheet(f"color: {THEME['brand_green']}; margin-bottom: 6px; font-size: 18px; font-weight: bold;")
        right_card_layout.addWidget(pdf_title)
        
        # Don't create viewer here - let load_invoice handle it
        self.viewer = None

        # ===== Splitter with cards =====
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(12)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background: transparent;
                margin: 6px;
            }
            QSplitter::handle:horizontal {
                width: 12px;
            }
        """)
        
        # Set minimum widths for sections
        left_card.setMinimumWidth(180)
        center_scroll.setMinimumWidth(400)
        right_card.setMinimumWidth(300)
        
        self.splitter.addWidget(left_card)
        self.splitter.addWidget(center_scroll)
        self.splitter.addWidget(right_card)
        
        # Set stretch factors (equal for middle and right)
        self.splitter.setStretchFactor(0, 1)  # Left card: minimal stretch
        self.splitter.setStretchFactor(1, 4)  # Center section: equal stretch
        self.splitter.setStretchFactor(2, 4)  # Right card: equal stretch
        
        QTimer.singleShot(0, self._apply_splitter_proportions)

        # Set size policies for proper vertical scaling
        left_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        center_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding) 
        right_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        
        # Put the content directly into gray area
        gray_area.addWidget(self.splitter)

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

        # Track manually edited fields
        self.manually_edited_fields = set()
        
        # Highlight on change
        for label, widget in self.fields.items():
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(lambda _, l=label: self._on_field_changed(l))
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(lambda _, l=label: self._on_field_changed(l))
            elif isinstance(widget, QDateEdit):
                widget.dateChanged.connect(lambda _, l=label: self._on_date_changed(l))

        # Apply direct styling to input fields (to override any global styles)
        input_field_style = f"""
            background-color: #FFFFFF;
            color: #000000;
            border: 1px solid {THEME['card_border']};
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 15px;
            min-height: 20px;
        """
        
        focus_style = f"""
            background-color: #FFFFFF;
            color: #000000;
            border: 2px solid {THEME['brand_green']};
            border-radius: 6px;
            padding: 7px 11px;
            font-size: 15px;
            min-height: 20px;
        """
        
        # Apply white background styling directly to all input fields
        for field_name, widget in self.fields.items():
            if isinstance(widget, QLineEdit):
                widget.setStyleSheet(input_field_style)
            elif isinstance(widget, QDateEdit):
                # QDateEdit now uses global ManualEntryDialog styles with SVG arrow
                # Just apply basic field styling - dropdown handled by global styles
                widget.setStyleSheet(input_field_style)
            elif isinstance(widget, QComboBox):
                # Special handling for vendor dropdown with enhanced visibility
                enhanced_combo_style = input_field_style + f"""
                    QComboBox {{
                        padding-right: 30px;
                    }}
                    QComboBox::drop-down {{
                        subcontrol-origin: padding;
                        subcontrol-position: top right;
                        width: 28px;
                        border-left: 2px solid {THEME['card_border']};
                        border-top-right-radius: 6px;
                        border-bottom-right-radius: 6px;
                        background-color: #f0f0f0;
                        margin-top: 1px;
                        margin-bottom: 1px;
                        margin-right: 1px;
                    }}
                    QComboBox::drop-down:hover {{
                        background-color: #e0e0e0;
                    }}
                    QComboBox::drop-down:pressed {{
                        background-color: #d0d0d0;
                    }}
                    QComboBox::down-arrow {{
                        image: none;
                        background-color: transparent;
                        width: 16px;
                        height: 16px;
                        border: 2px solid #333333;
                        border-left: transparent;
                        border-right: transparent;
                        border-bottom: transparent;
                        border-top: 8px solid #333333;
                        margin-top: 4px;
                    }}
                    QComboBox QAbstractItemView {{
                        background-color: #FFFFFF;
                        color: #000000;
                        border: 2px solid {THEME['card_border']};
                        border-radius: 4px;
                        selection-background-color: {THEME['brand_green']};
                        selection-color: white;
                        outline: none;
                        show-decoration-selected: 1;
                        min-height: 20px;
                    }}
                    QComboBox QAbstractItemView::item {{
                        min-height: 25px;
                        padding: 4px;
                    }}
                    QComboBox QAbstractItemView QScrollBar:vertical {{
                        background-color: #f0f0f0;
                        width: 16px;
                        border: 1px solid {THEME['card_border']};
                        border-radius: 8px;
                    }}
                    QComboBox QAbstractItemView QScrollBar::handle:vertical {{
                        background-color: #c0c0c0;
                        border-radius: 6px;
                        min-height: 20px;
                    }}
                    QComboBox QAbstractItemView QScrollBar::handle:vertical:hover {{
                        background-color: #a0a0a0;
                    }}
                """
                widget.setStyleSheet(enhanced_combo_style)
        
        # Apply to quick calculator fields as well
        for qc_field in [self.qc_subtotal, self.qc_disc_pct, self.qc_disc_amt, self.qc_shipping]:
            qc_field.setStyleSheet(input_field_style)

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
        # Equal middle and right sections, keep left file list narrow
        sizes = [int(total * 0.15), int(total * 0.46), int(total * 0.39)]
        sizes[2] = max(1, total - sizes[0] - sizes[1])
        self.splitter.setSizes(sizes)

    def _resize_to_fit_content(self):
        screen = self.windowHandle().screen() if self.windowHandle() else QGuiApplication.primaryScreen()
        if not screen:
            return
        avail = screen.availableGeometry()
        # Set fixed size of 1600x1050 as requested
        target_w = 1600
        target_h = 1050
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
            
            # Reset manual edit tracking when loading new data
            self.manually_edited_fields = set()
            
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

    def _clear_quick_calculator(self):
        """Clear all Quick Calculator fields when navigating to another file."""
        self.qc_subtotal.clear()
        self.qc_disc_pct.clear()
        self.qc_disc_amt.clear()
        self.qc_shipping.clear()
        # Also clear the calculated totals
        self.qc_total_wo_shipping.setText("$0.00")
        self.qc_grand_total.setText("$0.00")

    def load_invoice(self, index):
        if not self.pdf_paths:
            self.file_tracker_label.setText("0/0")
            return
        index = max(0, min(index, len(self.pdf_paths) - 1))
        self.current_index = index
        self.mark_file_viewed(index)

        #Update tracker label
        self.file_tracker_label.setText(f"{index + 1}/{len(self.pdf_paths)}")

        # Clear Quick Calculator fields when navigating to another file
        self._clear_quick_calculator()

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

        # Refresh viewer (now inside right card)
        new_viewer = InteractivePDFViewer(self.pdf_paths[index])
        # Find the right card and its layout
        right_card = self.splitter.widget(2)  # Right card is the 3rd widget
        if right_card and hasattr(right_card, 'layout') and right_card.layout():
            layout = right_card.layout()
            # Remove any existing viewers (clean slate approach)
            items_to_remove = []
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    # Check if it's a PDF viewer (has doc attribute or is InteractivePDFViewer)
                    if (hasattr(widget, 'doc') or 
                        widget.__class__.__name__ == 'InteractivePDFViewer'):
                        items_to_remove.append(widget)
            
            for widget in items_to_remove:
                layout.removeWidget(widget)
                widget.deleteLater()
            
            # Add the new viewer
            layout.addWidget(new_viewer)
            self.viewer = new_viewer
            QTimer.singleShot(0, lambda: self.viewer.fit_width() if self.viewer else None)

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
            warn = QMessageBox.question(
                self,
                "Unknown Vendor",
                f"‘{typed_vendor}’ isn’t in your vendor list. Open Vendor List to add it?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if warn == QMessageBox.Cancel:
                return False # abort save; let the user decide later

            dlg = VendorListDialog(self)
            dlg.exec_()
            self.load_vendors()
            current_names = {
                self.vendor_combo.itemText(i).strip().lower()
                for i in range(self.vendor_combo.count())
            }
            if typed_vendor.lower() in current_names:
                self.vendor_combo.setCurrentText(typed_vendor)
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
        current = self.vendor_combo.currentText()
        if vendors:
            vendors.sort()
            self.vendor_combo.blockSignals(True)
            self.vendor_combo.clear()
            self.vendor_combo.addItems(vendors)
            if current:
                idx = self.vendor_combo.findText(current)
                if idx >= 0:
                    self.vendor_combo.setCurrentIndex(idx)
                else:
                    self.vendor_combo.setEditText(current)
            self.vendor_combo.blockSignals(False)

    def open_vendor_list(self):
        """Open the editable vendor list dialog and refresh the combo after closing."""
        dlg = VendorListDialog(self)
        dlg.vendor_list_updated.connect(self._on_vendor_list_updated)
        dlg.exec_()
        self.load_vendors()

    def _on_vendor_list_updated(self):
        """Handle vendor list updates by re-extracting vendor names for empty cells."""
        from extractors import vendor_name
        vendor_name.reload_vendor_cache()
        self._reextract_empty_vendor_names()

    def _reextract_empty_vendor_names(self):
        """Re-extract vendor names for all empty vendor name cells in the invoice table."""
        # Get the parent application through parent chain
        parent_app = self.parent()
        if not hasattr(parent_app, 'table'):
            return
        
        invoice_table = parent_app.table
        
        # Import vendor extraction function
        from extractors.vendor_name import extract_vendor_name
        
        # Track updates made
        updates_made = 0
        
        # Iterate through all rows in the invoice table
        for row in range(invoice_table.rowCount()):
            # Check if vendor name is empty (column 1)
            vendor_name = invoice_table.get_cell_text(row, 1).strip()
            if not vendor_name:
                # Get the file path for this row to extract words
                file_path = invoice_table.get_file_path_for_row(row)
                if file_path and os.path.exists(file_path):
                    try:
                        # Extract text from the PDF and attempt vendor extraction
                        import fitz  # PyMuPDF
                        doc = fitz.open(file_path)
                        
                        # Extract all words from all pages
                        words = []
                        for page_num in range(len(doc)):
                            page = doc[page_num]
                            word_list = page.get_text("words")
                            for w in word_list:
                                words.append({"text": w[4]})  # w[4] is the text content
                        doc.close()
                        
                        # Try to extract vendor name
                        print(f"[DEBUG] Re-extracting vendor for file: {file_path}")
                        extracted_vendor = extract_vendor_name(words)
                        if extracted_vendor.strip():
                            print(f"[DEBUG] Re-extraction successful: '{extracted_vendor}' for file: {file_path}")
                            # Update the table with the new vendor name using the model
                            # Convert view row to source row
                            src_row = invoice_table._view_to_source_row(row)
                            if src_row >= 0:
                                model_index = invoice_table._model.index(src_row, 1)  # Column 1 is vendor
                                invoice_table._model.setData(model_index, extracted_vendor, Qt.EditRole)
                                updates_made += 1
                        else:
                            print(f"[DEBUG] Re-extraction failed: No vendor found for file: {file_path}")
                            
                    except Exception as e:
                        print(f"[ERROR] Failed to re-extract vendor for row {row}, file: {file_path}: {e}")
                        continue
        
        # Update all values_list entries to stay in sync with the table
        if updates_made > 0:
            # Update all entries in values_list to match the updated table
            for i in range(min(len(self.values_list), invoice_table.rowCount())):
                updated_vendor = invoice_table.get_cell_text(i, 1)
                if self.values_list[i][0] != updated_vendor:
                    self.values_list[i][0] = updated_vendor
            
            # Update the current dialog display if we're viewing an affected row
            current_index = getattr(self, 'current_index', 0)
            if (current_index < len(self.values_list) and 
                current_index < invoice_table.rowCount()):
                updated_vendor = invoice_table.get_cell_text(current_index, 1)
                if not self._loading:
                    self.vendor_combo.setCurrentText(updated_vendor)
            
            print(f"[INFO] Re-extracted vendor names for {updates_made} empty cells")

    def _on_field_changed(self, label):
        if not self._loading:
            self.manually_edited_fields.add(label)
        self._highlight_empty_fields()
    
    def _on_date_changed(self, label):
        self._clear_date_highlight(label)
        if not self._loading:
            self.manually_edited_fields.add(label)
        # Immediately update highlighting when date changes
        self._highlight_empty_fields()

    # ---------- Highlighting / data extraction ----------
    def _clear_date_highlight(self, label):
        if label in getattr(self, "empty_date_fields", set()):
            self.empty_date_fields.remove(label)
            self._highlight_empty_fields()

    def _highlight_empty_fields(self):
        # Define base style for input fields
        base_input_style = f"""
            background-color: #FFFFFF;
            color: #000000;
            border: 1px solid {THEME['card_border']};
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 15px;
            min-height: 20px;
        """
        
        # Use the same yellow as invoice table for empty fields
        empty_input_style = f"""
            background-color: #FFF1A6;
            color: #000000;
            border: 1px solid {THEME['card_border']};
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 15px;
            min-height: 20px;
        """
        
        # Use the same green as invoice table for manually edited fields
        manual_edit_style = f"""
            background-color: #DCFCE7;
            color: #000000;
            border: 1px solid {THEME['card_border']};
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 15px;
            min-height: 20px;
        """
        
        for label, widget in self.fields.items():
            # Skip highlighting for Shipping Cost field entirely
            if label == "Shipping Cost":
                # Apply base style for shipping cost field
                widget.setStyleSheet(base_input_style)
                continue
                
            if isinstance(widget, QLineEdit):
                empty = not widget.text().strip()
            elif isinstance(widget, QComboBox):
                empty = not widget.currentText().strip()
            elif isinstance(widget, QDateEdit):
                empty = label in getattr(self, "empty_date_fields", set())
            else:
                empty = False
                
            # Determine style based on priority: manual edit > empty > base
            manually_edited = label in getattr(self, "manually_edited_fields", set())
            
            if isinstance(widget, QComboBox):
                # ComboBox needs special handling
                if manually_edited:
                    base_style = manual_edit_style
                    dropdown_bg = "#dcfce7"
                elif empty:
                    base_style = empty_input_style
                    dropdown_bg = "#FFF1A6"
                else:
                    base_style = base_input_style
                    dropdown_bg = "#f0f0f0"
                    
                widget.setStyleSheet(base_style + f"""
                    QComboBox {{
                        padding-right: 30px;
                    }}
                    QComboBox::drop-down {{
                        subcontrol-origin: padding;
                        subcontrol-position: top right;
                        width: 28px;
                        border-left: 2px solid {THEME['card_border']};
                        border-top-right-radius: 6px;
                        border-bottom-right-radius: 6px;
                        background-color: {dropdown_bg};
                        margin-top: 1px;
                        margin-bottom: 1px;
                        margin-right: 1px;
                    }}
                    QComboBox::drop-down:hover {{
                        background-color: #e0e0e0;
                    }}
                    QComboBox::drop-down:pressed {{
                        background-color: #d0d0d0;
                    }}
                    QComboBox::down-arrow {{
                        image: none;
                        background-color: transparent;
                        width: 16px;
                        height: 16px;
                        border: 2px solid #333333;
                        border-left: transparent;
                        border-right: transparent;
                        border-bottom: transparent;
                        border-top: 8px solid #333333;
                        margin-top: 4px;
                    }}
                    QComboBox QAbstractItemView {{
                        background-color: #FFFFFF;
                        color: #000000;
                        border: 2px solid {THEME['card_border']};
                        border-radius: 4px;
                        selection-background-color: {THEME['brand_green']};
                        selection-color: white;
                        outline: none;
                        show-decoration-selected: 1;
                        min-height: 20px;
                    }}
                    QComboBox QAbstractItemView::item {{
                        min-height: 25px;
                        padding: 4px;
                    }}
                    QComboBox QAbstractItemView QScrollBar:vertical {{
                        background-color: #f0f0f0;
                        width: 16px;
                        border: 1px solid {THEME['card_border']};
                        border-radius: 8px;
                    }}
                    QComboBox QAbstractItemView QScrollBar::handle:vertical {{
                        background-color: #c0c0c0;
                        border-radius: 6px;
                        min-height: 20px;
                    }}
                    QComboBox QAbstractItemView QScrollBar::handle:vertical:hover {{
                        background-color: #a0a0a0;
                    }}
                """)
            elif isinstance(widget, QDateEdit):
                # QDateEdit uses global ManualEntryDialog styles for dropdown arrow
                # Only apply field background highlighting - dropdown handled globally
                if manually_edited:
                    widget.setStyleSheet(manual_edit_style)
                elif empty:
                    widget.setStyleSheet(empty_input_style)
                else:
                    widget.setStyleSheet(base_input_style)
            else:
                # QLineEdit
                if manually_edited:
                    widget.setStyleSheet(manual_edit_style)
                elif empty:
                    widget.setStyleSheet(empty_input_style)
                else:
                    widget.setStyleSheet(base_input_style)

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
            self.qc_total_wo_shipping.setText("$0.00")
            self.qc_grand_total.setText("$0.00")
            return

        total_wo_shipping = sub - disc_amt
        self.qc_total_wo_shipping.setText(self._fmt_money(total_wo_shipping))

        total = total_wo_shipping + (ship or 0.0)
        self.qc_grand_total.setText(self._fmt_money(total))

    def _apply_quick_total_to(self, target_label, source_label=None):
        label = source_label or self.qc_grand_total
        text = label.text().strip()
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

    # ---------- Event filter: currency formatting + resize handling ----------
    def eventFilter(self, obj, event):
        et = event.type()

        # Pretty/plain formatting for currency fields
        if et == QEvent.FocusIn:
            for label in getattr(self, "_currency_labels", set()):
                w = self.fields.get(label)
                if w is obj:
                    w.setText(self._money_plain(w.text()))
        elif et == QEvent.FocusOut:
            for label in getattr(self, "_currency_labels", set()):
                w = self.fields.get(label)
                if w is obj and not w.hasFocus():
                    w.setText(self._money_pretty(w.text()))

        # Only handle resize events for the dialog itself
        if obj != self:
            return super().eventFilter(obj, event)
        
        # Disable resize functionality when maximized
        if self.isMaximized():
            if not self._resizing:
                self._restoreOverrideCursor()
            return super().eventFilter(obj, event)
            
        if et in (QEvent.MouseMove, QEvent.HoverMove):
            self._updateResizeCursor()
            if self._resizing:
                self._performResize()
                return True
            return False
        if et == QEvent.MouseButtonPress:
            if getattr(event, "button", lambda: None)() == Qt.LeftButton:
                if self._beginResize():
                    return True
            return False
        if et == QEvent.MouseButtonRelease:
            if self._resizing:
                self._resizing = False
                self._resizeDir = None
                self._restoreOverrideCursor()
                return True
            return False
        if et == QEvent.Leave:
            if not self._resizing:
                self._restoreOverrideCursor()
        return super().eventFilter(obj, event)

    def _winPos(self):
        gp = QCursor.pos()
        return self.mapFromGlobal(gp), gp

    def _edgeAt(self, pos: QPoint):
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        m = RESIZE_MARGIN
        # corners first
        if x <= m and y <= m: return 'tl'
        if x >= w - m and y <= m: return 'tr'
        if x <= m and y >= h - m: return 'bl'
        if x >= w - m and y >= h - m: return 'br'
        # edges
        if x <= m: return 'l'
        if x >= w - m: return 'r'
        if y <= m: return 't'
        if y >= h - m: return 'b'
        return None

    def _setOverrideCursorForEdge(self, edge):
        cursors = {
            'l': Qt.SizeHorCursor, 'r': Qt.SizeHorCursor,
            't': Qt.SizeVerCursor, 'b': Qt.SizeVerCursor,
            'tl': Qt.SizeFDiagCursor, 'br': Qt.SizeFDiagCursor,
            'tr': Qt.SizeBDiagCursor, 'bl': Qt.SizeBDiagCursor,
        }
        if edge:
            if not self._cursorOverridden:
                QApplication.setOverrideCursor(QCursor(cursors[edge]))
                self._cursorOverridden = True
            else:
                if QApplication.overrideCursor() and QApplication.overrideCursor().shape() != cursors[edge]:
                    QApplication.changeOverrideCursor(QCursor(cursors[edge]))
        else:
            self._restoreOverrideCursor()

    def _restoreOverrideCursor(self):
        if self._cursorOverridden:
            QApplication.restoreOverrideCursor()
            self._cursorOverridden = False

    def _updateResizeCursor(self):
        pos, _ = self._winPos()
        edge = self._edgeAt(pos)
        self._setOverrideCursorForEdge(edge)

    def _beginResize(self):
        pos, gp = self._winPos()
        edge = self._edgeAt(pos)
        if edge:
            self._resizing = True
            self._resizeDir = edge
            self._startGeom = QRect(self.geometry())
            self._startPos = QPoint(gp)
            return True
        return False

    def _performResize(self):
        # Don't resize if maximized
        if self.isMaximized():
            return
            
        gp = QCursor.pos()
        dx = gp.x() - self._startPos.x()
        dy = gp.y() - self._startPos.y()
        g = QRect(self._startGeom)
        
        min_w = self.minimumWidth()
        min_h = self.minimumHeight()

        # Handle horizontal resizing
        if 'l' in self._resizeDir:
            new_left = g.left() + dx
            # Clamp to minimum width constraint
            max_left = g.right() - min_w
            new_left = min(new_left, max_left)
            g.setLeft(new_left)
        elif 'r' in self._resizeDir:
            new_right = g.right() + dx
            # Clamp to minimum width constraint
            min_right = g.left() + min_w
            new_right = max(new_right, min_right)
            g.setRight(new_right)

        # Handle vertical resizing
        if 't' in self._resizeDir:
            new_top = g.top() + dy
            # Clamp to minimum height constraint
            max_top = g.bottom() - min_h
            new_top = min(new_top, max_top)
            g.setTop(new_top)
        elif 'b' in self._resizeDir:
            new_bottom = g.bottom() + dy
            # Clamp to minimum height constraint
            min_bottom = g.top() + min_h
            new_bottom = max(new_bottom, min_bottom)
            g.setBottom(new_bottom)

        self.setGeometry(g)
        
    def closeEvent(self, event):
        """Clean up resize cursor override and guard window-X close."""
        self._restoreOverrideCursor()
        event.ignore()

        def proceed_accept_close():
            self.save_changes = True
            self.setResult(QDialog.Accepted)
            event.accept()

        self._confirm_unsaved_then(proceed_accept_close)
