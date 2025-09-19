import os
from PyQt5.QtCore import Qt, QRect, QRectF, QPoint, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage, QKeySequence, QGuiApplication
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGraphicsView,
    QGraphicsScene, QGraphicsPixmapItem, QSizePolicy, QSpacerItem, QShortcut, QRubberBand
)

try:
    import fitz  # PyMuPDF
except Exception as e:
    raise RuntimeError("PyMuPDF (fitz) is required for this viewer. Install with: pip install PyMuPDF") from e


class _PDFGraphicsView(QGraphicsView):
    """Graphics view that supports Ctrl+wheel zoom, rectangle selection (left-drag),
    and panning with either Space (hold) or right-drag."""
    selectionMade = pyqtSignal(QRectF)  # scene rect (pixels in rendered image coords)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragMode(QGraphicsView.ScrollHandDrag)  # used during Spacebar pan only
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setRenderHints(self.renderHints())

        # Disable default context menu so right-drag is clean
        self.setContextMenuPolicy(Qt.NoContextMenu)

        # Rubber-band selection (left-drag)
        self._rubber = QRubberBand(QRubberBand.Rectangle, self)
        self._origin = None

        # Spacebar panning override (uses built-in hand drag)
        self._panning_override = False

        # Right-button manual panning
        self._rb_pan_active = False
        self._rb_last_pos = None

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            event.accept()
            p = self.parent()
            if hasattr(p, "_on_ctrl_wheel"):
                p._on_ctrl_wheel(event.angleDelta().y())
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self._panning_override = True
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.viewport().setCursor(Qt.ClosedHandCursor)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space:
            self._panning_override = False
            self.setDragMode(QGraphicsView.NoDrag)
            self.viewport().unsetCursor()
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        # --- Right-button manual panning ---
        if event.button() == Qt.RightButton:
            self._rb_pan_active = True
            self._rb_last_pos = event.pos()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        # --- Left-button rectangle selection (unless in spacebar pan) ---
        if event.button() == Qt.LeftButton and not self._panning_override and not self._rb_pan_active:
            self._origin = event.pos()
            self._rubber.setGeometry(QRect(self._origin, self._origin))
            self._rubber.show()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Active right-button pan: move scrollbars by mouse delta
        if self._rb_pan_active and self._rb_last_pos is not None:
            delta = event.pos() - self._rb_last_pos
            self._rb_last_pos = event.pos()
            h = self.horizontalScrollBar()
            v = self.verticalScrollBar()
            h.setValue(h.value() - delta.x())
            v.setValue(v.value() - delta.y())
            event.accept()
            return

        # Resize selection rectangle while dragging with left button
        if self._rubber.isVisible() and self._origin is not None:
            rect = QRect(self._origin, event.pos()).normalized()
            self._rubber.setGeometry(rect)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # End right-button pan
        if event.button() == Qt.RightButton and self._rb_pan_active:
            self._rb_pan_active = False
            self._rb_last_pos = None
            self.viewport().unsetCursor()
            event.accept()
            return

        # Finish left-button selection drag
        if self._rubber.isVisible() and self._origin is not None:
            self._rubber.hide()
            view_rect = QRect(self._origin, event.pos()).normalized()
            self._origin = None
            top_left = self.mapToScene(view_rect.topLeft())
            bottom_right = self.mapToScene(view_rect.bottomRight())
            scene_rect = QRectF(top_left, bottom_right).normalized()
            if scene_rect.width() > 4 and scene_rect.height() > 4:
                self.selectionMade.emit(scene_rect)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class InteractivePDFViewer(QWidget):
    """Drop-in replacement viewer for your app, but powered by PyMuPDF."""

    # Emitted after a rectangle selection; provides extracted text (already in clipboard too)
    selectionText = pyqtSignal(str)

    def __init__(self, pdf_path: str, parent=None) -> None:
        super().__init__(parent)

        # ---- State ----
        self.doc = None
        self.page_index = 0
        self.scale = 1.25  # render scale relative to 72dpi points → pixels (1.0 = 72 dpi)
        self.rotation = 0
        self._pix_item = None

        # ---- Top toolbar ----
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)

        self.btn_prev = QPushButton("Prev")
        self.btn_next = QPushButton("Next")
        self.lbl_page = QLabel("Page 1/1")
        self._mk_btn(self.btn_prev, "Go to previous page")
        self._mk_btn(self.btn_next, "Go to next page")
        self.lbl_page.setStyleSheet("padding: 4px;")
        top.addWidget(self.btn_prev)
        top.addWidget(self.btn_next)
        top.addWidget(self.lbl_page)

        top.addItem(QSpacerItem(20, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.btn_fitw = QPushButton("Fit Width")
        self.btn_fitp = QPushButton("Fit Page")
        self.btn_zoomin = QPushButton("+")
        self.btn_zoomout = QPushButton("-")
        self.btn_reset = QPushButton("Reset")
        self.btn_rotate = QPushButton("Rotate")
        for b, tip in [
            (self.btn_fitw, "Scale to fit width (W)"),
            (self.btn_fitp, "Scale to fit page (P)"),
            (self.btn_zoomin, "Zoom In (Ctrl+=)"),
            (self.btn_zoomout, "Zoom Out (Ctrl+-)"),
            (self.btn_reset, "Reset Zoom (Ctrl+0)"),
            (self.btn_rotate, "Rotate 90° clockwise (R)"),
        ]:
            self._mk_btn(b, tip)
            top.addWidget(b)

        # ---- Graphics view / scene ----
        self.scene = QGraphicsScene(self)
        self.view = _PDFGraphicsView(self)
        self.view.setScene(self.scene)
        self.view.setDragMode(QGraphicsView.NoDrag)  # enable rectangle selection by default
        self.view.selectionMade.connect(self._on_selection_rect)

        # ---- Layout ----
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addLayout(top)
        root.addWidget(self.view)
        self.setLayout(root)

        # ---- Shortcuts ----
        QShortcut(QKeySequence.ZoomIn, self, activated=self.zoom_in)     # Ctrl+= / Ctrl++
        QShortcut(QKeySequence.ZoomOut, self, activated=self.zoom_out)   # Ctrl+-
        QShortcut(QKeySequence("Ctrl+0"), self, activated=self.reset_zoom)
        QShortcut(QKeySequence("W"), self, activated=self.fit_width)
        QShortcut(QKeySequence("P"), self, activated=self.fit_page)
        QShortcut(QKeySequence.MoveToPreviousPage, self, activated=self.prev_page)
        QShortcut(QKeySequence.MoveToNextPage, self, activated=self.next_page)
        QShortcut(QKeySequence("R"), self, activated=self.rotate_clockwise)

        # ---- Signals ----
        self.btn_prev.clicked.connect(self.prev_page)
        self.btn_next.clicked.connect(self.next_page)
        self.btn_fitw.clicked.connect(self.fit_width)
        self.btn_fitp.clicked.connect(self.fit_page)
        self.btn_zoomin.clicked.connect(self.zoom_in)
        self.btn_zoomout.clicked.connect(self.zoom_out)
        self.btn_reset.clicked.connect(self.reset_zoom)
        self.btn_rotate.clicked.connect(self.rotate_clockwise)

        # ---- Load initial PDF ----
        self.load_pdf(pdf_path)

    def __del__(self):
        """Ensure PDF document is properly closed when viewer is destroyed."""
        self.close_document()

    def close_document(self):
        """Explicitly close the PDF document to release file handles."""
        if self.doc:
            try:
                self.doc.close()
            except:
                pass  # Ignore errors during cleanup
            self.doc = None

    # -----------------------------
    # UI helpers
    # -----------------------------
    def _mk_btn(self, btn: QPushButton, tip: str):
        btn.setToolTip(tip)
        btn.setFixedHeight(28)
        btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #5E6F5E;"
            "  color: white;"
            "  border: none;"
            "  padding: 4px 8px;"
            "  border-radius: 4px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #6b7d6b;"
            "}"
            "QPushButton:pressed {"
            "  background-color: #526052;"
            "}"
    )

    # -----------------------------
    # Loading / rendering
    # -----------------------------
    def load_pdf(self, pdf_path: str):
        """Open a PDF file and render the current page."""
        # Close any existing document first
        self.close_document()

        self.scene.clear()
        self._pix_item = None
        self.page_index = 0
        self.rotation = 0
        if not pdf_path or not os.path.isfile(pdf_path):
            self.scene.addText("Unable to load PDF").setDefaultTextColor(Qt.red)
            self._update_page_label()
            return

        try:
            self.doc = fitz.open(pdf_path)
        except Exception as e:
            self.scene.addText(f"Failed to open PDF:\n{e}").setDefaultTextColor(Qt.red)
            self._update_page_label()
            return

        self._render_page()
        self._update_page_label()

    def _render_page(self):
        if not self.doc:
            return
        page = self.doc.load_page(self.page_index)
        # Render at current scale (points * scale = pixels)
        mat = fitz.Matrix(self.scale, self.scale).prerotate(self.rotation)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        # Keep a deep copy (PyMuPDF buffer goes out of scope)
        img = img.copy()
        pixmap = QPixmap.fromImage(img)

        if self._pix_item is None:
            self._pix_item = QGraphicsPixmapItem(pixmap)
            self.scene.addItem(self._pix_item)
            self.scene.setSceneRect(QRectF(0, 0, pixmap.width(), pixmap.height()))
        else:
            self._pix_item.setPixmap(pixmap)
            self.scene.setSceneRect(QRectF(0, 0, pixmap.width(), pixmap.height()))

    def _update_page_label(self):
        total = self.doc.page_count if self.doc else 1
        self.lbl_page.setText(f"Page {self.page_index + 1}/{total}")

    # -----------------------------
    # Zoom controls
    # -----------------------------
    def zoom_in(self):
        self._set_scale(self.scale * 1.25)

    def zoom_out(self):
        self._set_scale(self.scale / 1.25)

    def reset_zoom(self):
        self._set_scale(1.25)

    def _set_scale(self, new_scale: float):
        # Clamp to reasonable range
        new_scale = max(0.5, min(new_scale, 6.0))
        if abs(new_scale - self.scale) < 1e-4:
            return
        self.scale = new_scale
        old_center = self.view.mapToScene(self.view.viewport().rect().center())
        self._render_page()
        # keep view centered
        self.view.centerOn(old_center)

    def fit_width(self):
        """Scale so that the page width fits the viewport width."""
        if not self.doc or self.view.viewport().width() <= 0:
            return
        page = self.doc.load_page(self.page_index)
        target = max(1, self.view.viewport().width() - 24)  # minus a bit for scrollbars
        width = page.rect.height if self.rotation in (90, 270) else page.rect.width
        scale = target / width
        self._set_scale(scale)

    def fit_page(self):
        """Scale so that the whole page fits inside the viewport."""
        if not self.doc:
            return
        vp = self.view.viewport().rect()
        if vp.width() <= 0 or vp.height() <= 0:
            return
        page = self.doc.load_page(self.page_index)
        if self.rotation in (90, 270):
            page_w, page_h = page.rect.height, page.rect.width
        else:
            page_w, page_h = page.rect.width, page.rect.height
        scale_w = (vp.width() - 24) / page_w
        scale_h = (vp.height() - 24) / page_h
        self._set_scale(min(scale_w, scale_h))

    # Called by the child view to handle ctrl+wheel centrally
    def _on_ctrl_wheel(self, delta_y: int):
        if delta_y > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    # -----------------------------
    # Page navigation
    # -----------------------------
    def next_page(self):
        if not self.doc:
            return
        if self.page_index < self.doc.page_count - 1:
            self.page_index += 1
            self._render_page()
            self._update_page_label()

    def prev_page(self):
        if not self.doc:
            return
        if self.page_index > 0:
            self.page_index -= 1
            self._render_page()
            self._update_page_label()

    def rotate_clockwise(self):
        """Rotate the current page 90 degrees clockwise."""
        if not self.doc:
            return
        self.rotation = (self.rotation + 90) % 360
        self._render_page()

    # -----------------------------
    # Selection → text extraction
    # -----------------------------
    def _on_selection_rect(self, scene_rect: QRectF):
        """Map the drawn rectangle to page coordinates (points) and extract text."""
        if not self.doc or self._pix_item is None:
            return

        # scene_rect is in rendered pixels; convert back to page points
        # pixels = points * scale  →  points = pixels / scale
        page_rect = fitz.Rect(
            scene_rect.left() / self.scale,
            scene_rect.top() / self.scale,
            scene_rect.right() / self.scale,
            scene_rect.bottom() / self.scale,
        )

        page = self.doc.load_page(self.page_index)
        try:
            # Use clip to get text only from that rectangle
            text = page.get_text("text", clip=page_rect) or ""
        except Exception:
            # Fallback to a simpler extractor
            text = page.get_textbox(page_rect) or ""

        text = text.strip()
        if text:
            # Copy to clipboard for quick paste into fields
            QGuiApplication.clipboard().setText(text)
            # Tooltip confirmation
            self._toast(f"Copied selection to clipboard:\n{text[:120]}{'…' if len(text) > 120 else ''}")
            self.selectionText.emit(text)
        else:
            self._toast("No text found in selection.")

    def _toast(self, msg: str):
        # Lightweight feedback using a QLabel overlay
        label = QLabel(msg, self)
        label.setStyleSheet(
            "background: rgba(60,60,60,0.9); color: white; padding: 8px 10px; "
            "border-radius: 6px; font-size: 12px;"
        )
        label.adjustSize()
        # bottom-right corner
        m = 12
        label.move(self.width() - label.width() - m, self.height() - label.height() - m)
        label.show()
        # auto-hide
        label.setWindowOpacity(0.95)
        label.raise_()
        # simple timerless fade via single-shot deleteLater
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(1700, label.deleteLater)

    # (Optional) expose a convenience for external reloading with same path
    def reload(self):
        if self.doc:
            path = self.doc.name
            self.load_pdf(path)
