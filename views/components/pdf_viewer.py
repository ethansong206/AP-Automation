"""PDF viewer widget with text selection and zoom support."""
import os
from PyQt5.QtCore import QUrl, Qt
from PyQt5.QtWebEngineWidgets import QWebEngineSettings, QWebEngineView

class InteractivePDFViewer(QWebEngineView):
    """Embed a PDF inside a widget that supports text selection and zoom."""
    def __init__(self, pdf_path: str, parent=None) -> None:
        super().__init__(parent)

        # Enable the built-in PDF viewer provided by QtWebEngine
        self.settings().setAttribute(QWebEngineSettings.PluginsEnabled, True)

        self._zoom_factor = 1.0
        self.setZoomFactor(self._zoom_factor)

        if pdf_path and os.path.isfile(pdf_path):
            url = QUrl.fromLocalFile(os.path.abspath(pdf_path))
            self.load(url)
        else:
            # Show a simple message if the file could not be found
            self.setHtml("<h3>Unable to load PDF</h3>")

    # ------------------------------------------------------------------
    # Zoom handling
    # ------------------------------------------------------------------
    def wheelEvent(self, event):
        """Allow zooming with Ctrl + Mouse Wheel."""
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self._zoom_factor *= 1.25
            else:
                self._zoom_factor /= 1.25
            # Clamp the zoom factor to a sensible range
            self._zoom_factor = max(0.25, min(self._zoom_factor, 5.0))
            self.setZoomFactor(self._zoom_factor)
        else:
            super().wheelEvent(event)
