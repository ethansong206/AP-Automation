# views/app_shell.py
import os
from PyQt5.QtCore import Qt, QSize, QEvent, QPoint, QRect
from PyQt5.QtGui import QColor, QPainter, QBrush, QFont, QIcon, QPixmap, QCursor
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QToolButton, QFrame, QGraphicsDropShadowEffect,
    QPushButton, QSizePolicy, QApplication, QMessageBox
)
from version import APP_VERSION

APP_TITLE = "Invoice App"

THEME = {
    "outer_bg": "#F2F3F5",
    "card_bg":  "#FFFFFF",
    "card_border": "#E1E4E8",
    "brand_green": "#064420",
    "radius": 12,
}

RESIZE_MARGIN = 14  # easier corner hit area

# ---------- asset helpers ----------
def _resolve_asset(path_parts):
    here = os.path.dirname(__file__)
    candidates = [
        os.path.join(here, *path_parts),
        os.path.join(os.path.dirname(here), *path_parts),
        os.path.join(os.getcwd(), *path_parts),
        os.path.join(*path_parts),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[-1]

def _resolve_icon(filename: str) -> str:
    return _resolve_asset(["assets", "icons", filename])

def _resolve_logo(filename: str) -> str:
    return _resolve_asset(["assets", filename])


# ---------------- Titlebar: Title (left) + absolutely centered Logo + SVG icons (right) ----------------
class _TitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag = None
        self.setMouseTracking(True)

        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(24, 16, 12, 16)  # equal top/bottom for vertical centering
        self._row.setSpacing(10)

        # Left: Big title
        self.title = QLabel("GOPC Invoice App", self)
        self.title.setObjectName("BigAppTitle")
        self.title.setFont(QFont("Inter", 22, QFont.Bold))
        self.title.setStyleSheet(f"color: {THEME['brand_green']};")

        # Right: window controls
        self._icon_min = QIcon(_resolve_icon("minimize.svg"))
        self._icon_max = QIcon(_resolve_icon("maximize.svg"))
        self._icon_close = QIcon(_resolve_icon("close.svg"))

        def make_winbtn(icon: QIcon) -> QToolButton:
            b = QToolButton(self)
            b.setObjectName("WinBtn")
            b.setFixedSize(64, 48)
            b.setIcon(icon)
            b.setIconSize(QSize(54, 54))
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setStyleSheet("QToolButton#WinBtn { background: transparent; border: none; padding: 0; }")
            b.setMouseTracking(True)
            return b

        self.btn_min = make_winbtn(self._icon_min)
        self.btn_max = make_winbtn(self._icon_max)
        self.btn_close = make_winbtn(self._icon_close)

        # Base flow row: title (left), stretch, buttons (right)
        self._row.addWidget(self.title)
        self._row.addStretch()
        self._row.addWidget(self.btn_min)
        self._row.addWidget(self.btn_max)
        self._row.addWidget(self.btn_close)

        # Centered logo as overlay (absolute center)
        logo_path = _resolve_logo("GOPCLogo.png")
        self.centerLogo = QLabel(self)
        self.centerLogo.setObjectName("GopcLogo")
        self.centerLogo.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        desired_h = 54  # adjust as needed
        pm = QPixmap(logo_path)
        if not pm.isNull():
            scaled = pm.scaledToHeight(desired_h, Qt.SmoothTransformation)
            self.centerLogo.setPixmap(scaled)
            self.centerLogo.resize(scaled.size())

        # Wire up
        self.btn_min.clicked.connect(self.window().showMinimized)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(self.window().close)

        self.setStyleSheet("background: transparent;")

    def resizeEvent(self, e):
        # keep logo absolutely centered
        if self.centerLogo.pixmap():
            w = self.centerLogo.pixmap().width()
            h = self.centerLogo.pixmap().height()
            x = (self.width() - w) // 2
            m = self._row.contentsMargins()
            y = (m.top() + (self.height() - m.bottom()) - h) // 2
            self.centerLogo.move(x, y)
        super().resizeEvent(e)

    def _toggle_max(self):
        w = self.window()
        if w.isMaximized():
            w.showNormal()
        else:
            w.showMaximized()

    # drag window
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self.childAt(e.pos()) in (self.btn_min, self.btn_max, self.btn_close):
                return
            self._drag = e.globalPos() - self.window().frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if self._drag and not self.window().isMaximized():
            self.window().move(e.globalPos() - self._drag)
    def mouseReleaseEvent(self, e):
        self._drag = None
    def mouseDoubleClickEvent(self, e):
        self._toggle_max()


# --------------------------- App Shell (frameless + resize + wiring) ----------------------------
class AppShell(QMainWindow):
    """
    Frameless, rounded outer window that hosts your existing main widget.
    Call with AppShell(InvoiceApp).

    Inside the white card header row, exposes:
      - Upload, Search, Filter (moved from middle row)
    """
    def __init__(self, widget_factory):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.resize(1400, 1000)
        self.setMinimumSize(900, 600)
        self.setObjectName("RootShell")

        # --- resize state ---
        self._resizing = False
        self._resizeDir = None  # 'l','r','t','b','tl','tr','bl','br'
        self._startGeom = QRect()
        self._startPos = QPoint()
        self._cursorOverridden = False

        self.setMouseTracking(True)
        qapp = QApplication.instance()
        if qapp is not None:
            qapp.installEventFilter(self)

        container = QWidget(self)
        container.setMouseTracking(True)
        self.setCentralWidget(container)
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top gray: titlebar (title left + centered logo + icons right)
        self.titlebar = _TitleBar(self)
        self.titlebar.setMouseTracking(True)
        root.addWidget(self.titlebar)

        # Gray padding around white card
        pad = QVBoxLayout()
        pad.setContentsMargins(24, 6, 24, 24)
        pad.setSpacing(10)
        root.addLayout(pad)

        # White rounded card
        self.card = QFrame()
        self.card.setObjectName("Card")
        self.card.setMouseTracking(True)
        self.card.setStyleSheet(f"""
            QFrame#Card {{
                background: {THEME['card_bg']};
                border: 1px solid {THEME['card_border']};
                border-radius: {THEME['radius']}px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28); shadow.setOffset(0, 8); shadow.setColor(QColor(0, 0, 0, 45))
        self.card.setGraphicsEffect(shadow)
        pad.addWidget(self.card)

        # Card layout
        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(20, 20, 20, 20)
        card_lay.setSpacing(12)

        # Your existing app widget
        app_widget = widget_factory()
        if hasattr(app_widget, "title_label"):
            app_widget.title_label.setVisible(False)  # avoid duplicate inner title
        app_widget.setMouseTracking(True)

        # Card header row: "Invoices" (left) + Search Bar + Filter (right)
        header_row = QHBoxLayout(); header_row.setContentsMargins(0, 0, 0, 0); header_row.setSpacing(10)

        title_left = QLabel("Invoices")
        title_left.setObjectName("CardTitle")
        title_left.setFont(QFont("Inter", 18, QFont.Bold))
        title_left.setStyleSheet(f"color: {THEME['brand_green']};")
        header_row.addWidget(title_left)
        header_row.addStretch()

        # Add the search and filter controls from app_widget to header
        if hasattr(app_widget, 'search_edit'):
            header_row.addWidget(app_widget.search_edit)
        if hasattr(app_widget, 'btn_filter'):
            header_row.addWidget(app_widget.btn_filter)

        card_lay.addLayout(header_row)
        card_lay.addWidget(app_widget)

        # Small application version label at bottom-right of gray area
        self.version_label = QLabel(f"v{APP_VERSION}")
        version_font = QFont()
        version_font.setPointSize(8)
        self.version_label.setFont(version_font)
        pad.addWidget(self.version_label, alignment=Qt.AlignRight)

        # Button colors and control styles
        self.setStyleSheet(f"""
            QPushButton#BtnCsv    {{ background: #2E7D32; color: #FFFFFF; border: none; border-radius: 8px; padding: 8px 14px; }}
            QPushButton#BtnFolder {{ background: #FBC02D; color: #263238; border: none; border-radius: 8px; padding: 8px 14px; }}
            
            /* Upload button styling - Primary action */
            QPushButton#importButton {{
                background-color: {THEME['brand_green']};
                color: white;
                border-radius: 8px;
                padding: 8px 15px;
                font-weight: bold;
                font-size: 12pt;
                min-height: 20px;
                min-width: 120px;
            }}
            QPushButton#importButton:hover {{
                background-color: #053318;
            }}
            QPushButton#importButton:pressed {{
                background-color: #042712;
            }}
            
            /* Search bar styling - with constrained width */
            QLineEdit#searchEdit {{
                border: 2px solid #E0E0E0;
                border-radius: 15px;
                padding: 6px 12px;
                background-color: white;
                font-size: 12pt;
                min-height: 20px;
                max-width: 300px;
                min-width: 150px;
            }}
            QLineEdit#searchEdit:focus {{
                border-color: {THEME['brand_green']};
            }}
            
            /* Filter button styling - Darker gray, proper sizing */
            QPushButton#filterButton {{
                background-color: #757575;
                color: white;
                border-radius: 8px;
                padding: 8px 12px;
                font-weight: bold;
                font-size: 12pt;
                min-height: 20px;
                min-width: 100px;
            }}
            QPushButton#filterButton:hover {{
                background-color: #616161;
            }}
            QPushButton#filterButton:pressed {{
                background-color: #424242;
            }}
            QPushButton#filterButton::menu-indicator {{
                image: none;
                width: 0;
            }}
        """)

    # ---- rounded gray background ----
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform, True)
        r = self.rect().adjusted(8, 8, -8, -8)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(THEME["outer_bg"])))
        p.drawRoundedRect(r, THEME["radius"], THEME["radius"])

    # ---------------- frameless resize (edges + corners with cursor) ----------------
    def eventFilter(self, obj, event):
        # Check if there's an active modal dialog - if so, don't process resize events
        qapp = QApplication.instance()
        if qapp and qapp.activeModalWidget():
            # Ensure resize cursor is cleared when modal dialog is active
            if not self._resizing:
                self._restoreOverrideCursor()
            return False
            
        et = event.type()
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
        return False

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
                QApplication.setOverrideCursor(QCursor(cursors[edge])); self._cursorOverridden = True
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
        gp = QCursor.pos()
        dx = gp.x() - self._startPos.x()
        dy = gp.y() - self._startPos.y()
        g = QRect(self._startGeom)

        if 'l' in self._resizeDir:
            new_left = g.left() + dx
            if g.right() - new_left >= self.minimumWidth(): g.setLeft(new_left)
        if 'r' in self._resizeDir:
            new_right = g.right() + dx
            if new_right - g.left() >= self.minimumWidth(): g.setRight(new_right)
        if 't' in self._resizeDir:
            new_top = g.top() + dy
            if g.bottom() - new_top >= self.minimumHeight(): g.setTop(new_top)
        if 'b' in self._resizeDir:
            new_bottom = g.bottom() + dy
            if new_bottom - g.top() >= self.minimumHeight(): g.setBottom(new_bottom)

        self.setGeometry(g)