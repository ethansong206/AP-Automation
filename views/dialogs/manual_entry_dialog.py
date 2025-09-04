import os
from copy import deepcopy

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QDateEdit,
    QPushButton, QSplitter, QWidget, QFormLayout, QComboBox, QMessageBox,
    QCompleter, QListWidget, QListWidgetItem, QGroupBox,
    QScrollArea, QGridLayout, QFrame, QGraphicsDropShadowEffect, QToolButton,
    QApplication, QSizePolicy, QAbstractSpinBox
)
from PyQt5.QtCore import Qt, QDate, QEvent, QTimer, pyqtSignal, QSize, QPoint, QRect
from PyQt5.QtGui import QBrush, QGuiApplication, QColor, QPainter, QFont, QIcon, QCursor, QPen

# Import Quick Calculator Manager (new inline version)
from .components.quick_calculator_inline import QuickCalculatorManager
# Import styling system
from .styles.manual_entry_styles import ManualEntryStyles

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

DATE_NO_ARROWS_CSS = """
/* Kill spin buttons completely */
QAbstractSpinBox::up-button,
QAbstractSpinBox::down-button { width:0; height:0; border:0; padding:0; margin:0; }

/* Remove any reserved padding/space for those buttons */
QAbstractSpinBox { padding-right: 0; }

/* Also kill any calendar dropdown chrome even if a global style adds it */
QDateEdit::drop-down { width:0 !important; border:none !important; }
QDateEdit::down-arrow { image:none !important; width:0; height:0; }

/* Belt-and-suspenders: make sure QDateEdit itself keeps no extra room */
QDateEdit { padding-right: 0 !important; }
"""

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
    def __init__(self, parent=None, title_text: str = "Manual Entry", titlebar_height: int = 60, dpi_scale: float = 1.0):
        super().__init__(parent)
        self._drag_offset = None
        self.dpi_scale = dpi_scale  # Store DPI scale for button sizing
        self.setMouseTracking(True)

        # Scale margins and spacing based on titlebar height
        margin_h = max(16, int(titlebar_height * 0.4))
        margin_v = max(12, int(titlebar_height * 0.25))
        spacing = max(8, int(titlebar_height * 0.15))

        row = QHBoxLayout(self)
        row.setContentsMargins(margin_h, margin_v, margin_h//2, margin_v)
        row.setSpacing(spacing)

        self.title = QLabel(title_text, self)
        self.title.setObjectName("DialogBigTitle")
        # Scale font size based on titlebar height
        font_size = max(18, int(titlebar_height * 0.4))
        main_title_font = QFont("Inter", font_size, QFont.Bold)
        self.title.setFont(main_title_font)
        self.title.setStyleSheet(parent.styles.get_title_style(font_size) if hasattr(parent, 'styles') else f"color: {THEME['brand_green']}; font-size: {font_size}px; font-weight: bold;")

        # Window control buttons (match main window look)
        self._icon_min = QIcon(_resolve_icon("minimize.svg"))
        self._icon_max = QIcon(_resolve_icon("maximize.svg"))
        self._icon_close = QIcon(_resolve_icon("close.svg"))

        def make_winbtn(icon: QIcon) -> QToolButton:
            b = QToolButton(self)
            b.setObjectName("WinBtn")
            # Match main window button sizes with DPI scaling
            btn_width = max(54, int(64 * self.dpi_scale))   # Scale main window's 64px width
            btn_height = max(40, int(48 * self.dpi_scale))  # Scale main window's 48px height  
            icon_size = max(45, int(54 * self.dpi_scale))   # Scale main window's 54px icon
            b.setFixedSize(btn_width, btn_height)
            b.setIcon(icon)
            b.setIconSize(QSize(icon_size, icon_size))
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            border_radius = max(4, int(6 * self.dpi_scale))  # DPI-scaled border radius
            b.setStyleSheet(parent.styles.get_window_control_button_style() if hasattr(parent, 'styles') else 
                ("QToolButton#WinBtn { background: transparent; border: none; padding: 0; }"
                f"QToolButton#WinBtn:hover {{ background: rgba(0,0,0,0.06); border-radius: {border_radius}px; }}"))
            b.setMouseTracking(True)  # Match main window's mouse tracking
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


class MaskedDateEdit(QDateEdit):
    """
    QDateEdit-based date input (MM/dd/yy) with text-like behavior:
    - First click selects the whole section (MM/DD/YY).
    - Second separate click in the same section places the caret.
    - Switching sections with a click selects the new section.
    - Two-digit typing per section; Tab/Shift+Tab walk sections; Enter or '/' advance.
    - No spin arrows; wheel & Up/Down don't change the value.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDisplayFormat("MM/dd/yy")
        self.setCalendarPopup(False)
        self.setDate(QDate.currentDate())
        self.setFocusPolicy(Qt.StrongFocus)

        # Track last section clicked to implement "first click selects; second click places caret"
        self._last_clicked_section = None

        # Hide spin buttons & disable wheel/spin behavior
        self._hide_spin_buttons_css()
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)

        QTimer.singleShot(0, self._select_current_section)

    # ---- visuals ----
    def _hide_spin_buttons_css(self):
        self.setStyleSheet("""
            QAbstractSpinBox::up-button   { width:0; height:0; border:0; padding:0; margin:0; }
            QAbstractSpinBox::down-button { width:0; height:0; border:0; padding:0; margin:0; }
            QAbstractSpinBox { padding-right: 0; }
            QDateEdit::drop-down { width:0 !important; border:none !important; }
            QDateEdit::down-arrow { image:none !important; width:0; height:0; }
            QDateEdit { padding-right: 0 !important; }
        """)

    # ---- helpers ----
    def _select_current_section(self):
        try:
            self.setSelectedSection(self.currentSection())
        except Exception:
            pass

    def _get_section_from_position(self, pos):
        """
        Calculate which section (MM/DD/YY) was clicked based on pixel position.
        Returns QDateTimeEdit.MonthSection, DaySection, or YearSection.
        """
        try:
            from PyQt5.QtWidgets import QAbstractSpinBox
            
            # Get the widget's content rectangle (excluding margins/borders)
            content_rect = self.contentsRect()
            widget_width = content_rect.width()
            click_x = pos.x() - content_rect.left()
            
            # Calculate approximate character widths for "MM/dd/yy" format
            # Using font metrics for more accurate positioning
            font_metrics = self.fontMetrics()
            
            # Measure actual text widths for each section
            mm_width = font_metrics.horizontalAdvance("MM")
            slash1_width = font_metrics.horizontalAdvance("/")
            dd_width = font_metrics.horizontalAdvance("dd")
            slash2_width = font_metrics.horizontalAdvance("/")
            yy_width = font_metrics.horizontalAdvance("yy")
            
            # Calculate section boundaries
            mm_start = 0
            mm_end = mm_width
            
            slash1_start = mm_end
            slash1_end = slash1_start + slash1_width
            
            dd_start = slash1_end
            dd_end = dd_start + dd_width
            
            slash2_start = dd_end
            slash2_end = slash2_start + slash2_width
            
            yy_start = slash2_end
            yy_end = yy_start + yy_width
            
            # Determine which section was clicked
            if mm_start <= click_x < dd_start:
                return self.MonthSection
            elif dd_start <= click_x < yy_start:
                return self.DaySection
            elif yy_start <= click_x <= yy_end:
                return self.YearSection
            else:
                # Fallback to current section if click is outside bounds
                return self.currentSection()
                
        except Exception as e:
            print(f"[DEBUG] Section detection error: {e}")
            # Fallback to Qt's method if our calculation fails
            try:
                return self.sectionAt(pos)
            except:
                return self.currentSection()

    def _move_section_by(self, step: int):
        idx = self.currentSectionIndex()
        count = self.sectionCount()
        new_idx = max(0, min(count - 1, idx + step))
        if new_idx != idx:
            self.setCurrentSectionIndex(new_idx)
        self._select_current_section()
        # After keyboard navigation, treat the next click as a "first click"
        self._last_clicked_section = None

    def _set_month_safe(self, m: int):
        d0 = self.date()
        y, d = d0.year(), d0.day()
        max_d = QDate(y, m, 1).daysInMonth()
        self.setDate(QDate(y, m, min(d, max_d)))

    def _set_day_safe(self, d: int):
        d0 = self.date()
        y, m = d0.year(), d0.month()
        max_d = QDate(y, m, 1).daysInMonth()
        self.setDate(QDate(y, m, max(1, min(d, max_d))))

    # ---- events ----
    def focusInEvent(self, e):
        super().focusInEvent(e)
        self._last_clicked_section = None
        QTimer.singleShot(0, self._select_current_section)

    def focusOutEvent(self, e):
        self._last_clicked_section = None
        super().focusOutEvent(e)

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return super().mousePressEvent(e)

        # Use pixel-based section detection instead of unreliable sectionAt()
        clicked_section = self._get_section_from_position(e.pos())
        
        if clicked_section is None:
            return super().mousePressEvent(e)

        # If it's the first click in this section (or a different section than last time)…
        if self._last_clicked_section is None or clicked_section != self._last_clicked_section:
            # DO NOT call the base handler here; we own this click.
            e.accept()
            self.setFocus(Qt.MouseFocusReason)
            self.setCurrentSection(clicked_section)
            self.setSelectedSection(clicked_section)
            self._last_clicked_section = clicked_section
            return

        # Otherwise it's a second click in the same section → let Qt place caret
        self._last_clicked_section = None
        return super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        # No special logic needed on release; keep it simple.
        return super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        # Double-click acts like precise edit (caret), not a reselect
        super().mouseDoubleClickEvent(e)
        # Next click should select again
        self._last_clicked_section = None

    def wheelEvent(self, e):
        # Don't let mouse wheel change the date; allow parent views to scroll
        e.ignore()

    def stepBy(self, steps: int):
        # Disable spin behavior entirely
        return

    def keyPressEvent(self, e):
        k = e.key()
        txt = e.text()
        is_digit = bool(txt) and txt.isdigit()

        # Block spin-keys so it behaves like text
        if k in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
            e.ignore()
            return

        # Smart single-digit: '2'..'9' in MM => 02..09 and jump; '4'..'9' in DD => 04..09 and jump
        # BUT only if the current field is empty to avoid interfering with two-digit entry
        if is_digit:
            idx = self.currentSectionIndex()  # 0=MM, 1=DD, 2=YY for "MM/dd/yy"
            dch = txt
            current_text = self.sectionText(self.currentSection()).strip()
            
            if idx == 0 and dch in "23456789" and not current_text:
                self._set_month_safe(int(dch))
                self._move_section_by(+1)
                e.accept()
                return
            if idx == 1 and dch in "456789" and not current_text:
                self._set_day_safe(int(dch))
                self._move_section_by(+1)
                e.accept()
                return

        # Enter or '/' => advance to next section
        if k in (Qt.Key_Return, Qt.Key_Enter) or txt == '/':
            self.interpretText()
            if self.currentSectionIndex() < self.sectionCount() - 1:
                self._move_section_by(+1)
                e.accept()
                return

        # Let base class handle digits, backspace, arrows (L/R), etc.
        super().keyPressEvent(e)

        # After digits, DO NOT reselect (so you can type two digits)
        if is_digit:
            return

        # After non-digit keys, reselect the current section for quick overwrite
        if k not in (Qt.Key_Tab, Qt.Key_Backtab):
            QTimer.singleShot(0, self._select_current_section)

    def focusNextPrevChild(self, next: bool) -> bool:
        """
        Tab / Shift+Tab step MM→DD→YY before leaving the field.
        """
        idx = self.currentSectionIndex()
        last = self.sectionCount() - 1
        self.interpretText()

        if next:
            if idx < last:
                self._move_section_by(+1)
                return True   # keep focus here
            return super().focusNextPrevChild(next)
        else:
            if idx > 0:
                self._move_section_by(-1)
                return True
            return super().focusNextPrevChild(next)


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
        # Set responsive minimum size based on screen dimensions
        screen = QGuiApplication.primaryScreen()
        if screen:
            screen_size = screen.availableGeometry()
            min_width = max(1200, int(screen_size.width() * 0.75))  # 75% of screen width, min 1200
            min_height = max(850, int(screen_size.height() * 0.85))  # 85% of screen height, min 850
            self.setMinimumSize(min_width, min_height)
            
            # Calculate DPI scaling factor for better cross-resolution support
            dpi = screen.logicalDotsPerInch()
            self.dpi_scale = dpi / 96.0  # 96 DPI is standard Windows DPI
        else:
            self.setMinimumSize(1200, 850)  # Fallback for smaller screens
            self.dpi_scale = 1.0
        self.setObjectName("ManualEntryRoot")
        
        # Initialize styling system
        self.styles = ManualEntryStyles(self.dpi_scale, min_width, min_height)

        # Root layout (lets us paint a rounded background in paintEvent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Titlebar - responsive height
        # Scale titlebar height based on screen size (3-4% of screen height, min 50px)
        screen = QGuiApplication.primaryScreen()
        if screen:
            titlebar_height = max(50, int(screen.availableGeometry().height() * 0.035))
        else:
            titlebar_height = 60
        self.titlebar = _DialogTitleBar(self, title_text="Manual Entry", titlebar_height=titlebar_height, dpi_scale=self.dpi_scale)
        self.titlebar.setMouseTracking(True)
        self.titlebar.setFixedHeight(titlebar_height)
        root.addWidget(self.titlebar, 0)  # 0 stretch factor = fixed size

        # Direct gray background area for splitter - this should expand
        gray_area = QVBoxLayout()
        # Scale margins based on screen size
        margin_h = max(16, int(min_width * 0.015))  # 1.5% of width, min 16px
        margin_v = max(8, int(min_height * 0.01))   # 1% of height, min 8px
        spacing = max(8, int(min_height * 0.01))    # 1% of height, min 8px
        gray_area.setContentsMargins(margin_h, margin_v//2, margin_h, margin_v*2)
        gray_area.setSpacing(spacing)
        root.addLayout(gray_area, 1)  # 1 stretch factor = expands

        # ---------- Enhanced dialog UI styling ----------
        # Calculate responsive font sizes and CSS values
        large_font_size = max(16, int(18 * self.dpi_scale))
        
        # Scaled CSS values for consistent proportions (used in highlighting logic)
        self.css_padding_sm = max(6, int(8 * self.dpi_scale))
        self.css_padding_md = max(9, int(12 * self.dpi_scale))
        self.css_font_base = max(13, int(15 * self.dpi_scale))
        self.css_border_radius = max(4, int(6 * self.dpi_scale))
        
        base_style = load_stylesheet(get_style_path('default.qss'))
        self.setStyleSheet(base_style + self.styles.get_base_dialog_styles())
        
        # Removed heavy drop shadow effects that were causing performance issues

        # Data/state
        self.pdf_paths = list(pdf_paths or [])
        # Initialize Quick Calculator Manager
        self.qc_manager = QuickCalculatorManager(self)
        
        self.values_list = values_list or [[""] * 13 for _ in self.pdf_paths]
        # Ensure existing data is expanded to new format
        for values in self.values_list:
            if len(values) < 13:
                values.extend([""] * (13 - len(values)))
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
        left_card.setStyleSheet(self.styles.get_card_style())
        # Removed card shadows for better performance
        left_card_layout = QVBoxLayout(left_card)
        # Scale card margins and spacing
        card_margin = max(8, int(min_width * 0.008))  # 0.8% of width, min 8px
        card_spacing = max(6, int(min_height * 0.008)) # 0.8% of height, min 6px
        left_card_layout.setContentsMargins(card_margin, card_margin, card_margin, card_margin)
        left_card_layout.setSpacing(card_spacing)
        
        # File list title
        file_list_title = QLabel("Files")
        title_font = QFont("Inter", large_font_size, QFont.Bold)
        file_list_title.setFont(title_font)
        file_list_title.setStyleSheet(self.styles.get_title_style(large_font_size) + " margin-bottom: 6px;")
        left_card_layout.addWidget(file_list_title)
        
        self.file_list = QListWidget()
        self.file_list.setObjectName("FileListWidget")
        self.file_list.mousePressEvent = self._file_list_mouse_press
        # Zebra striping and styling
        self.file_list.setStyleSheet(self.styles.get_file_list_style())
        left_card_layout.addWidget(self.file_list)
        
        for i, (path, flagged) in enumerate(zip(self.pdf_paths, self.flag_states)):
            item = QListWidgetItem()
            text = self._get_display_text(i)
            self._update_file_item(item, text, flagged, i)
            self.file_list.addItem(item)

        # ===== Center: manual entry fields (directly on gray background) =====
        center_widget = QWidget()
        center_widget.setMouseTracking(True)
        center_layout = QVBoxLayout(center_widget)
        # Scale center layout margins and spacing - absolutely minimal for title compactness
        center_margin_h = max(12, int(min_width * 0.01))   # 1% of width, min 12px
        center_margin_v = max(1, int(min_height * 0.001))  # 0.1% of height, min 1px (further reduced)
        center_spacing = 0  # Zero spacing between title and form to eliminate gap
        center_layout.setContentsMargins(center_margin_h, center_margin_v, center_margin_h, center_margin_h)
        center_layout.setSpacing(center_spacing)
        
        # Manual entry title with minimal margins - explicit override of all spacing sources
        entry_title = QLabel("Invoice Details")
        entry_title.setObjectName("InvoiceDetailsTitle")  # Unique name for precise CSS targeting
        title_font = QFont("Inter", large_font_size, QFont.Bold)
        entry_title.setFont(title_font)
        # Set fixed height to prevent excessive vertical space usage
        entry_title.setFixedHeight(max(20, large_font_size + 4))  # Font size + minimal padding
        # Apply consolidated title styling (CSS handles all overrides)
        entry_title.setStyleSheet(self.styles.get_title_style(large_font_size))
        center_layout.addWidget(entry_title)
        
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(8)  # Reduced from 10px to 8px for tighter spacing
        form_layout.setHorizontalSpacing(10)
        form_layout.setContentsMargins(0, 0, 0, 0)  # No margins to minimize gap after title

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
        self.fields["Invoice Date"] = MaskedDateEdit()
        self.fields["Invoice Date"].setDate(QDate.currentDate())
        
        form_layout.addRow(QLabel("Invoice Date:"), self.fields["Invoice Date"])

        # Discount Terms
        self.fields["Discount Terms"] = QLineEdit()
        form_layout.addRow(QLabel("Discount Terms:"), self.fields["Discount Terms"])

        # Due Date + Calculate button
        self.fields["Due Date"] = MaskedDateEdit()
        self.fields["Due Date"].setDate(QDate.currentDate())
        
        due_row = QHBoxLayout()
        due_row.addWidget(self.fields["Due Date"], 1)
        due_row.addSpacing(10)
        self.due_calc_btn = QPushButton("Calculate")
        self.due_calc_btn.setToolTip("Compute Due Date from Discount Terms and Invoice Date")
        self.due_calc_btn.clicked.connect(self._on_calculate_due_date)
        due_row.addWidget(self.due_calc_btn)
        form_layout.addRow(QLabel("Due Date:"), due_row)

        # Currency fields removed - now handled by QC inline editing

        # Quick Calculator - managed by QuickCalculatorManager
        self.quick_calc_group = self.qc_manager.create_widget()

        # Button styles - DPI-aware
        primary_btn_css = self.styles.get_primary_button_style()
        for b in (self.vendor_list_btn, self.due_calc_btn):
            b.setStyleSheet(primary_btn_css)

        # Navigation + delete
        self.prev_button = QPushButton("←")
        self.next_button = QPushButton("→")
        nav_css = self.styles.get_navigation_button_style()
        # Scale navigation button size based on screen dimensions
        nav_btn_size = max(50, min(70, int(min_width * 0.04)))  # 4% of min width, between 50-70px
        for b in (self.prev_button, self.next_button):
            b.setStyleSheet(nav_css)
            b.setFixedSize(nav_btn_size, nav_btn_size)
        self.prev_button.clicked.connect(self._on_prev_clicked)
        self.next_button.clicked.connect(self._on_next_clicked)

        self.flag_button = QPushButton("⚑")
        self.flag_button.setStyleSheet(nav_css)
        self.flag_button.setFixedSize(nav_btn_size, nav_btn_size)
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
        self.delete_btn.setStyleSheet(self.styles.get_delete_button_style())
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
        center_layout.addSpacing(6)  # Restore original spacing
        center_layout.addWidget(row_container)

        # Wrap center widget in scroll area
        center_scroll = QScrollArea()
        center_scroll.setWidgetResizable(True)
        center_scroll.setFrameShape(QScrollArea.NoFrame)
        center_scroll.setStyleSheet(self.styles.get_transparent_background_style())
        center_scroll.setWidget(center_widget)

        # ===== Right: PDF viewer card =====
        right_card = QFrame()
        right_card.setObjectName("RightCard")
        right_card.setMouseTracking(True)
        right_card.setStyleSheet(self.styles.get_card_style())
        # Removed card shadows for better performance
        right_card_layout = QVBoxLayout(right_card)
        right_card_layout.setContentsMargins(card_margin, card_margin, card_margin, card_margin)
        right_card_layout.setSpacing(card_spacing)
        
        # PDF viewer title
        pdf_title = QLabel("PDF Preview")
        title_font = QFont("Inter", large_font_size, QFont.Bold)
        pdf_title.setFont(title_font)
        pdf_title.setStyleSheet(self.styles.get_title_style(large_font_size))
        right_card_layout.addWidget(pdf_title)
        
        # Don't create viewer here - let load_invoice handle it
        self.viewer = None

        # ===== Splitter with cards =====
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        # Scale splitter handle width
        handle_width = max(8, int(min_width * 0.008))  # 0.8% of width, min 8px
        self.splitter.setHandleWidth(handle_width)
        self.splitter.setStyleSheet(self.styles.get_splitter_style())
        
        # Set responsive minimum widths for sections - reduce center minimum to allow smaller screens
        left_min_width = max(120, int(min_width * 0.12))    # 12% of width, min 120px
        center_min_width = max(200, int(min_width * 0.20))   # 20% of width, min 200px (reduced from 350px)
        right_min_width = max(180, int(min_width * 0.15))    # 15% of width, min 180px
        left_card.setMinimumWidth(left_min_width)
        center_scroll.setMinimumWidth(center_min_width)
        right_card.setMinimumWidth(right_min_width)
        
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

        # Currency fields we pretty/normalize (now empty - handled by QC)
        self._currency_labels = set()
        for label in self._currency_labels:
            w = self.fields.get(label)
            if w:
                w.installEventFilter(self)

        # Quick calc fields that use pretty/plain toggling (no tax fields now)
        self._calc_currency_fields = self.qc_manager.get_currency_fields()
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
            elif isinstance(widget, (QDateEdit, MaskedDateEdit)):
                widget.dateChanged.connect(lambda _, l=label: self._on_date_changed(l))

        # Apply direct styling to input fields (to override any global styles)
        # Scale padding and sizing based on screen dimensions
        input_padding_v = max(6, int(min_height * 0.008))  # 0.8% of height, min 6px
        input_padding_h = max(8, int(min_width * 0.008))   # 0.8% of width, min 8px
        border_radius = max(4, int(min_width * 0.004))     # 0.4% of width, min 4px
        min_input_height = max(16, int(min_height * 0.02)) # 2% of height, min 16px
        
        input_field_style = self.styles.get_input_field_styles()
        
        focus_style = f"""
            background-color: #FFFFFF;
            color: #000000;
            border: 2px solid {THEME['brand_green']};
            border-radius: {self.css_border_radius}px;
            padding: {max(5, int(7 * self.dpi_scale))}px {max(9, int(11 * self.dpi_scale))}px;
            font-size: {self.css_font_base}px;
            min-height: {max(16, int(20 * self.dpi_scale))}px;
        """
        
        # Apply white background styling directly to all input fields
        for field_name, widget in self.fields.items():
            if isinstance(widget, QLineEdit):
                widget.setStyleSheet(input_field_style)
            elif isinstance(widget, (QDateEdit, MaskedDateEdit)):
                # Apply base field styling AND force-hide any arrows/dropdowns
                widget.setStyleSheet(input_field_style + DATE_NO_ARROWS_CSS)
            elif isinstance(widget, QComboBox):
                # ComboBox styling handled by global CSS - just apply base style
                widget.setStyleSheet(input_field_style)
        
        # Apply to quick calculator fields as well
        self.qc_manager.apply_styles(input_field_style)

        # Wire dirty tracking AFTER fields exist
        self._wire_dirty_tracking()
        
        # Note: Auto-population only happens during initial load via qc_manager
        # No permanent wiring to avoid feedback loops during user input

        # Initial load
        self.load_invoice(self.current_index)

        # Resize to avoid buttons being off-screen, and fit the PDF to width
        QTimer.singleShot(0, self._resize_to_fit_content)
        QTimer.singleShot(0, lambda: self.viewer.fit_width() if self.viewer else None)

        # Guarded file list navigation
        self.file_list.currentRowChanged.connect(self._on_file_list_row_changed)

    def _check_auto_calc_confirmation(self):
        """Check if Quick Calculator has pending auto-calculation confirmation."""
        if hasattr(self, 'qc_manager') and self.qc_manager:
            try:
                self.qc_manager.check_and_show_pending_confirmation()
            except Exception as e:
                print(f"[QC DEBUG] Error showing auto-calc confirmation: {e}")

    # ---------- Frameless outer background (rounded gray with border) ----------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()
        
        # Fill background
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(THEME["outer_bg"]))
        p.drawRoundedRect(r, THEME["radius"], THEME["radius"])
        
        # Add stronger border for better visual separation
        border_color = QColor(THEME["brand_green"])  # Brand green border (#064420)
        border_pen = QPen(border_color, 2)  # 2px border width
        border_pen.setJoinStyle(Qt.RoundJoin)  # Smooth corners
        p.setPen(border_pen)
        p.setBrush(Qt.NoBrush)
        # Draw border slightly inset to avoid clipping
        border_rect = r.adjusted(1, 1, -1, -1)
        p.drawRoundedRect(border_rect, THEME["radius"], THEME["radius"])

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
        # Set responsive target size based on screen dimensions
        target_w = max(1200, min(avail.width() * 0.9, 1800))  # 90% of screen width, between 1200-1800px
        target_h = max(850, min(avail.height() * 0.88, 1250)) # 88% of screen height, between 850-1250px
        self.resize(int(target_w), int(target_h))
        self._apply_splitter_proportions()
        if hasattr(self, "viewer") and self.viewer:
            self.viewer.fit_width()

    # ---------- Keyboard nav ----------
    def keyPressEvent(self, event):
        # Handle Enter key for form navigation
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._entry_field_has_focus():
                self._handle_enter_navigation()
                event.accept()
                return
        
        # Handle Left/Right arrows for file navigation (when not in input fields)
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
        return isinstance(w, (QLineEdit, QComboBox, QDateEdit, MaskedDateEdit))

    def _handle_enter_navigation(self):
        """Handle Enter key to navigate to next field or next file."""
        current_widget = self.focusWidget()
        
        # Define field order for navigation
        field_order = [
            self.vendor_combo,
            self.fields["Invoice Number"],
            self.fields["PO Number"], 
            self.fields["Invoice Date"],
            self.fields["Discount Terms"],
            self.fields["Due Date"]
        ]
        # Add QC fields to navigation order
        field_order = self.qc_manager.add_to_field_order(field_order)
        
        try:
            current_index = field_order.index(current_widget)
            next_index = current_index + 1
            
            if next_index < len(field_order):
                # Move to next field
                field_order[next_index].setFocus()
            else:
                # On last field - navigate to next file with save prompt
                self._navigate_to_next_file_with_save()
        except ValueError:
            # Current widget not in our field order, try to find a reasonable next field
            if hasattr(current_widget, 'parent'):
                # For QC fields or other widgets, just move focus to first main field
                self.vendor_combo.setFocus()

    def _navigate_to_next_file_with_save(self):
        """Navigate to next file with save prompt if changes were made."""
        if self.current_index >= len(self.pdf_paths) - 1:
            # Already on last file, do nothing
            return
            
        def proceed_to_next():
            self._on_next_clicked()
            
        # Use existing unsaved changes logic
        self._confirm_unsaved_then(proceed_to_next)

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
        new_data = self.get_data()
        print(f"[QC DEBUG] save_current_invoice() saving data: {new_data}")
        self.values_list[self.current_index] = new_data

    def _load_values_into_widgets(self, values):
        """Programmatic set (guarded -> doesn't mark dirty)."""
        # Note: _loading should already be True when this is called
        was_loading = self._loading
        self._loading = True
        try:
            # Ensure all values are strings, not None
            vals = [(str(v) if v is not None else "") for v in values] + [""] * (13 - len(values))

            self.vendor_combo.setCurrentText(vals[0])
            self.fields["Invoice Number"].setText(vals[1])
            self.fields["PO Number"].setText(vals[2])

            # Invoice Date
            self.fields["Invoice Date"].setDate(QDate.currentDate())
            inv = vals[3].strip() if vals[3] else ""
            if inv:
                d = self._parse_mmddyy(inv)
                if d.isValid():
                    self.fields["Invoice Date"].setDate(d)

            self.fields["Discount Terms"].setText(vals[4])

            # Due Date
            self.fields["Due Date"].setDate(QDate.currentDate())
            due = vals[5].strip() if vals[5] else ""
            if due:
                d2 = self._parse_mmddyy(due)
                if d2.isValid():
                    self.fields["Due Date"].setDate(d2)

            # Currency fields now handled by QC manager
            # Store original values for QC auto-population
            print(f"[QC DEBUG] Loading invoice values: vals length={len(vals)}")
            print(f"[QC DEBUG] vals[6] (total): '{vals[6] if len(vals) > 6 else 'N/A'}'")
            print(f"[QC DEBUG] vals[7] (shipping): '{vals[7] if len(vals) > 7 else 'N/A'}'")
            self._original_total_amount = vals[6] if len(vals) > 6 else ""    # r.total is at index 6
            self._original_shipping_cost = vals[7] if len(vals) > 7 else ""   # r.shipping is at index 7

            # Highlighting
            self.empty_date_fields = set()
            if not (vals[3] and vals[3].strip()):
                self.empty_date_fields.add("Invoice Date")
            if not (vals[5] and vals[5].strip()):
                self.empty_date_fields.add("Due Date")
            
            # Reset manual edit tracking when loading new data
            self.manually_edited_fields = set()
            
            self._highlight_empty_fields()
        finally:
            # Restore previous loading state (don't force it to False since load_invoice manages it)
            self._loading = was_loading
            # Only reset dirty if we weren't already loading (for backwards compatibility)
            if not was_loading:
                print(f"[DIRTY DEBUG] Setting dirty=False from _load_values_into_widgets (backwards compatibility)")
                self._dirty = False

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

        # Clear Quick Calculator fields when navigating to another file
        self.qc_manager.clear_fields()

        # Load widgets AND QC state (both guarded to prevent dirty)
        self._loading = True
        needs_auto_calc = False
        qc_became_dirty = False
        try:
            self._load_values_into_widgets(self.values_list[index])
            # Load saved QC state OR auto-populate from form data
            needs_auto_calc = self.qc_manager.load_or_populate_from_form(self.values_list, self.current_index, self.fields)
            # Check if QC became dirty during auto-population
            qc_became_dirty = getattr(self.qc_manager, 'is_dirty', False)
        finally:
            print(f"[DIRTY DEBUG] QC became dirty during auto-population: {qc_became_dirty}")
            print(f"[DIRTY DEBUG] Setting dirty={qc_became_dirty} and loading=False from load_invoice")
            self._dirty = qc_became_dirty  # Preserve QC dirty state instead of always clearing
            self._loading = False
            
        # Trigger recalculation AFTER loading is complete if auto-populated
        if needs_auto_calc:
            print(f"[QC DEBUG] Triggering recalculation after loading complete")
            self.qc_manager.recalculate_and_update_fields(during_auto_population=True)

        # Check for pending auto-calculation confirmation after file is loaded
        QTimer.singleShot(50, self._check_auto_calc_confirmation)

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
        
        # Set QC save state (mark as clean)
        self.qc_manager.set_save_state()

        # Snapshot as saved, emit outward, clear dirty
        if self.pdf_paths:
            idx = self.current_index
            self.saved_values_list[idx] = deepcopy(self.values_list[idx])
            self.saved_flag_states[idx] = self.flag_states[idx]
            self.row_saved.emit(self.pdf_paths[idx], self.values_list[idx], self.flag_states[idx])
        print(f"[DIRTY DEBUG] Setting dirty=False from save")
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
        print(f"[DIRTY DEBUG] Setting dirty=True from date update, loading={self._loading}")
        self._dirty = True

    # ---------- Tiny saved toast ----------
    def _flash_saved(self):
        note = QLabel("Saved", self)
        note.setStyleSheet(self.styles.get_success_toast_style())
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
            text = self._get_display_text(index)
            self._update_file_item(item, text, self.flag_states[index], index)

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
            v = (self.values_list[idx][0] or "").strip()
            inv = (self.values_list[idx][1] or "").strip()
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
        self._update_file_item(item, display, self.flag_states[idx], idx)

    # ---------- Flag helpers ----------
    def _update_file_item(self, item, text, flagged, item_index=None):
        icon = "🚩" if flagged else "⚑"
        item.setText(f"{icon} {text}")
        if flagged:
            item.setBackground(QColor(COLORS['LIGHT_RED']))
        else:
            item.setBackground(QBrush())
        
        # Apply viewed state styling (gray text for viewed files)
        if item_index is not None and item_index in self.viewed_files:
            item.setForeground(QBrush(Qt.gray))
        else:
            item.setForeground(QBrush())  # Reset to default color

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
            self._update_file_item(item, text, self.flag_states[idx], idx)
        if idx == self.current_index:
            self._update_flag_button()
        print(f"[DIRTY DEBUG] Setting dirty=True from flag toggle, loading={self._loading}")
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
        current = (self.vendor_combo.currentText() or "").strip()
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
                    # Preserve the user's typed vendor even if not in list
                    self.vendor_combo.setEditText(current)
            else:
                # Keep vendor field blank instead of defaulting to first item
                self.vendor_combo.setCurrentIndex(-1)
                self.vendor_combo.setEditText("")
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
        # Get current screen dimensions for responsive styling
        screen = QGuiApplication.primaryScreen()
        if screen:
            screen_size = screen.availableGeometry()
            min_width = max(1200, int(screen_size.width() * 0.75))
            min_height = max(800, int(screen_size.height() * 0.8))
        else:
            min_width, min_height = 1200, 800
            
        # Calculate responsive values - use DPI-aware scaling
        base_font_size = self.css_font_base  # Use DPI-scaled font size
        input_padding_v = self.css_padding_sm
        input_padding_h = self.css_padding_md
        border_radius = self.css_border_radius
        min_input_height = max(16, int(20 * self.dpi_scale))
        
        # Define base style for input fields
        base_input_style = self.styles.get_input_field_styles()
        
        # Use the same yellow as invoice table for empty fields
        empty_input_style = self.styles.get_empty_field_style()
        
        # Use the same green as invoice table for manually edited fields
        manual_edit_style = self.styles.get_manual_edit_style()
        
        for label, widget in self.fields.items():
                
            if isinstance(widget, QLineEdit):
                empty = not widget.text().strip()
            elif isinstance(widget, QComboBox):
                empty = not widget.currentText().strip()
            elif isinstance(widget, (QDateEdit, MaskedDateEdit)):
                empty = label in getattr(self, "empty_date_fields", set())
            else:
                empty = False
                
            # Determine style based on priority: manual edit > empty > base
            manually_edited = label in getattr(self, "manually_edited_fields", set())
            
            if isinstance(widget, QComboBox):
                # ComboBox styling - keep main field white, only dropdown gets colored background
                if manually_edited:
                    base_style = manual_edit_style
                elif empty:
                    base_style = empty_input_style
                else:
                    base_style = base_input_style
                    
                # Apply base style - global CSS handles dropdown background
                widget.setStyleSheet(base_style)
            elif isinstance(widget, (QDateEdit, MaskedDateEdit)):
                # Always apply arrow-hiding CSS for date widgets
                if manually_edited:
                    widget.setStyleSheet(manual_edit_style + DATE_NO_ARROWS_CSS)
                elif empty:
                    widget.setStyleSheet(empty_input_style + DATE_NO_ARROWS_CSS)
                else:
                    widget.setStyleSheet(base_input_style + DATE_NO_ARROWS_CSS)

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
            "Discount Terms", "Due Date",
        ]:
            w = self.fields[label]
            if isinstance(w, (QDateEdit, MaskedDateEdit)):
                value = w.date().toString("MM/dd/yy")
            elif isinstance(w, QComboBox):
                value = w.currentText().strip()
            else:
                txt = w.text().strip()
                value = self._money_plain(txt) if label in getattr(self, "_currency_labels", set()) else txt
            data.append(value)
        
        # Get financial data from QC manager (Total Amount, Shipping Cost at indices 6,7)
        qc_financial_data = self.qc_manager.get_financial_data_for_form()
        data.extend(qc_financial_data)  # Adds Total Amount, Shipping Cost
        
        # Add QC values (indices 8-11) and flag (index 12) 
        qc_data = self.qc_manager.get_data_for_persistence()
        data.extend(qc_data)
        
        print(f"[QC DEBUG] get_data() returning QC values: {qc_data}")
        return data

    def get_all_data(self):
        self.save_current_invoice()
        return self.values_list

    def get_deleted_files(self):
        return list(self._deleted_files)



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
                print(f"[DIRTY DEBUG] Setting dirty=True from mark_dirty, loading={self._loading}")
                self._dirty = True
        for label, w in self.fields.items():
            if isinstance(w, QLineEdit):
                w.textChanged.connect(mark_dirty)
            elif isinstance(w, QComboBox):
                w.currentTextChanged.connect(mark_dirty)
            elif isinstance(w, (QDateEdit, MaskedDateEdit)):
                w.dateChanged.connect(mark_dirty)
                
        # Wire QC dirty tracking
        def mark_dirty_from_qc(*_):
            if not self._loading:
                print(f"[DIRTY DEBUG] Setting dirty=True from QC changes, loading={self._loading}")
                self._dirty = True
                
        # Connect to all QC field changes
        qc_fields = self.qc_manager.get_currency_fields() + [
            self.qc_manager.discount_pct_field
        ]
        for field in qc_fields:
            if field:  # Safety check
                field.textChanged.connect(mark_dirty_from_qc)

    # Auto-population handled by QuickCalculatorManager

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
    
    def resizeEvent(self, event):
        """Handle window resize to maintain proportions and update responsive elements."""
        super().resizeEvent(event)
        if hasattr(self, 'splitter') and self.splitter:
            QTimer.singleShot(10, self._apply_splitter_proportions)
        
    def closeEvent(self, event):
        """Clean up resize cursor override and guard window-X close."""
        self._restoreOverrideCursor()
        event.ignore()

        def proceed_accept_close():
            self.save_changes = True
            self.setResult(QDialog.Accepted)
            event.accept()

        self._confirm_unsaved_then(proceed_accept_close)
