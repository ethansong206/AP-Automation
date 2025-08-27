"""
Custom title bar component for frameless dialogs.
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QToolButton
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont, QIcon, QCursor

# Theme and icon imports
try:
    from views.app_shell import THEME as APP_THEME, _resolve_icon
except Exception:
    try:
        from app_shell import THEME as APP_THEME, _resolve_icon
    except Exception:
        # Safe fallback
        APP_THEME = {
            "outer_bg": "#F2F3F5",
            "content_bg": "#FFFFFF", 
            "text_primary": "#1A1A1A",
            "text_secondary": "#6B7280",
            "border_light": "#E5E7EB",
            "brand_green": "#22C55E",
            "accent_blue": "#3B82F6"
        }
        def _resolve_icon(name):
            return ""

THEME = APP_THEME


class DialogTitleBar(QWidget):
    """Custom titlebar for frameless dialogs.
    
    Features:
    - Reuses SVG icons (minimize/close/maximize) via _resolve_icon
    - Drag anywhere on the left/title area to move the frameless window
    - DPI-aware button sizing
    """
    
    def __init__(self, parent=None, title_text: str = "Manual Entry", titlebar_height: int = 60, dpi_scale: float = 1.0):
        super().__init__(parent)
        self._drag_offset = None
        self.dpi_scale = dpi_scale
        self.setMouseTracking(True)

        # Scale margins and spacing based on titlebar height
        margin_h = max(16, int(titlebar_height * 0.4))
        margin_v = max(12, int(titlebar_height * 0.25))
        spacing = max(8, int(titlebar_height * 0.15))

        row = QHBoxLayout(self)
        row.setContentsMargins(margin_h, margin_v, margin_h//2, margin_v)
        row.setSpacing(spacing)

        # Title label
        self.title = QLabel(title_text, self)
        self.title.setObjectName("DialogBigTitle")
        # Scale font size based on titlebar height
        font_size = max(18, int(titlebar_height * 0.4))
        main_title_font = QFont("Inter", font_size, QFont.Bold)
        self.title.setFont(main_title_font)
        self.title.setStyleSheet(f"color: {THEME['brand_green']}; font-size: {font_size}px; font-weight: bold;")

        # Window control buttons
        self._icon_min = QIcon(_resolve_icon("minimize.svg"))
        self._icon_max = QIcon(_resolve_icon("maximize.svg"))
        self._icon_close = QIcon(_resolve_icon("close.svg"))

        self.btn_min = self._create_window_button(self._icon_min)
        self.btn_max = self._create_window_button(self._icon_max)
        self.btn_close = self._create_window_button(self._icon_close)
        
        # Connect button actions
        self.btn_min.clicked.connect(self.window().showMinimized)
        self.btn_max.clicked.connect(self._toggle_maximize)
        self.btn_close.clicked.connect(self.window().close)

        # Layout
        row.addWidget(self.title)
        row.addStretch()
        row.addWidget(self.btn_min)
        row.addWidget(self.btn_max)
        row.addWidget(self.btn_close)
        self.setStyleSheet("background: transparent;")

    def _create_window_button(self, icon: QIcon) -> QToolButton:
        """Create a styled window control button."""
        button = QToolButton(self)
        button.setObjectName("WinBtn")
        
        # Match main window button sizes with DPI scaling
        btn_width = max(54, int(64 * self.dpi_scale))
        btn_height = max(40, int(48 * self.dpi_scale))
        icon_size = max(45, int(54 * self.dpi_scale))
        
        button.setFixedSize(btn_width, btn_height)
        button.setIcon(icon)
        button.setIconSize(QSize(icon_size, icon_size))
        button.setCursor(Qt.PointingHandCursor)
        button.setFocusPolicy(Qt.NoFocus)
        
        border_radius = max(4, int(6 * self.dpi_scale))
        button.setStyleSheet(
            "QToolButton#WinBtn { background: transparent; border: none; padding: 0; }"
            f"QToolButton#WinBtn:hover {{ background: rgba(0,0,0,0.06); border-radius: {border_radius}px; }}"
        )
        button.setMouseTracking(True)
        return button

    def mousePressEvent(self, e):
        """Handle mouse press for window dragging."""
        if e.button() == Qt.LeftButton and self.childAt(e.pos()) not in (self.btn_min, self.btn_max, self.btn_close):
            self._drag_offset = e.globalPos() - self.window().frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        """Handle mouse move for window dragging."""
        if self._drag_offset and not self.window().isMaximized():
            self.window().move(e.globalPos() - self._drag_offset)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        """Handle mouse release to stop dragging."""
        self._drag_offset = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        """Handle double-click to toggle maximize."""
        self._toggle_maximize()

    def _toggle_maximize(self):
        """Toggle window maximized state."""
        window = self.window()
        if window.isMaximized():
            window.showNormal()
        else:
            window.showMaximized()