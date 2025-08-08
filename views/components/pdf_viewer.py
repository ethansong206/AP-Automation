"""Interactive PDF viewer that can display multi-page PDFs with zoom."""
import os
import fitz  # PyMuPDF

from PyQt5.QtWidgets import QScrollArea, QLabel, QAction
from PyQt5.QtGui import QImage, QPixmap, QCursor, QPainter, QTransform
from PyQt5.QtCore import Qt

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

        print(f"Trying to open PDF at: {pdf_path}")
        if not pdf_path:
            self.label.setText("No PDF file specified")
            return
            
        # Try different path formats
        paths_to_try = [
            pdf_path,
            os.path.abspath(pdf_path),
            os.path.normpath(pdf_path)
        ]
        
        for path in paths_to_try:
            print(f"[DEBUG] Trying path: {path}")
            if os.path.isfile(path):
                try:
                    with fitz.open(path) as doc:
                        # Render every page and stack them vertically into one image
                        images = []
                        max_width = 0
                        total_height = 0
                        for page in doc:
                            pix = page.get_pixmap(dpi=100)
                            fmt = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
                            img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
                            img = img.convertToFormat(QImage.Format_RGBA8888)
                            images.append(img)
                            max_width = max(max_width, img.width())
                            total_height += img.height()

                        combined = QImage(max_width, total_height, QImage.Format_RGBA8888)
                        combined.fill(Qt.white)
                        painter = QPainter(combined)
                        y = 0
                        for img in images:
                            painter.drawImage(0, y, img)
                            y += img.height()
                        painter.end()

                    self.original_pixmap = QPixmap.fromImage(combined)
                    
                    self.normal_pixmap = self.original_pixmap.scaledToWidth(500, Qt.SmoothTransformation)
                    self.zoomed_pixmap = self.original_pixmap.scaledToWidth(1000, Qt.SmoothTransformation)
                    self.label.setPixmap(self.normal_pixmap)

                    self.zoom_in_cursor = QCursor(QPixmap("assets/zoom_in_cursor.cur"))
                    self.zoom_out_cursor = QCursor(QPixmap("assets/zoom_out_cursor.cur"))
                    self._update_cursor()
                    self._add_rotation_actions()
                    return  # Successfully loaded, exit the loop
                except Exception as e:
                    print(f"[DEBUG] Failed with path {path}: {e}")
                    continue  # Try next path
        
        # If we get here, all path attempts failed
        self.label.setText(f"Failed to open PDF.\nChecked paths:\n" + "\n".join(paths_to_try))

    def _add_rotation_actions(self):
        self.setContextMenuPolicy(Qt.ActionsContextMenu)
        rotate_cw_action = QAction("Rotate Clockwise", self)
        rotate_cw_action.triggered.connect(self.rotate_clockwise)
        rotate_ccw_action = QAction("Rotate Counterclockwise", self)
        rotate_ccw_action.triggered.connect(self.rotate_counterclockwise)
        self.addAction(rotate_cw_action)
        self.addAction(rotate_ccw_action)

    def rotate_clockwise(self):
        self._rotate(90)

    def rotate_counterclockwise(self):
        self._rotate(-90)

    def _rotate(self, angle):
        if not hasattr(self, "original_pixmap"):
            return
        transform = QTransform().rotate(angle)
        self.original_pixmap = self.original_pixmap.transformed(transform, Qt.SmoothTransformation)
        self._zoomed = False
        self._update_normal_pixmap()
        self.zoomed_pixmap = self.original_pixmap.scaledToWidth(1000, Qt.SmoothTransformation)
        self._update_cursor()
        self.horizontalScrollBar().setValue(0)
        self.verticalScrollBar().setValue(0)

    def _update_normal_pixmap(self):
        if not hasattr(self, "original_pixmap"):
            return
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
            self.setCursor(self.zoom_out_cursor)
        else:
            self.setCursor(self.zoom_in_cursor)

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