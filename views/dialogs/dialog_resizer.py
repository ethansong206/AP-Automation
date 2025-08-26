"""
Dialog resizer mixin for adding resize functionality to frameless dialogs.
"""

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QPoint, QRect
from PyQt5.QtGui import QCursor

RESIZE_MARGIN = 14


class DialogResizerMixin:
    """Mixin class that adds resize functionality to frameless dialogs.
    
    Provides edge/corner resize handles with appropriate cursor changes.
    Should be mixed into a QDialog or QWidget class.
    """
    
    def __init__(self):
        # Initialize resize state variables
        self._resizing = False
        self._resizeDir = None  # 'l','r','t','b','tl','tr','bl','br'
        self._cursorOverridden = False
        self._startGeom = None
        self._startPos = None
        
    def _winPos(self):
        """Get current cursor position relative to widget and global."""
        global_pos = QCursor.pos()
        local_pos = self.mapFromGlobal(global_pos)
        return local_pos, global_pos

    def _edgeAt(self, pos: QPoint):
        """Determine which edge/corner the position is at."""
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        m = RESIZE_MARGIN
        
        # Check corners first
        if x <= m and y <= m: 
            return 'tl'  # top-left
        if x >= w - m and y <= m: 
            return 'tr'  # top-right
        if x <= m and y >= h - m: 
            return 'bl'  # bottom-left
        if x >= w - m and y >= h - m: 
            return 'br'  # bottom-right
        
        # Check edges
        if x <= m: 
            return 'l'  # left
        if x >= w - m: 
            return 'r'  # right
        if y <= m: 
            return 't'  # top
        if y >= h - m: 
            return 'b'  # bottom
        
        return None

    def _setOverrideCursorForEdge(self, edge):
        """Set the appropriate cursor for the given edge."""
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
                current_cursor = QApplication.overrideCursor()
                if current_cursor and current_cursor.shape() != cursors[edge]:
                    QApplication.changeOverrideCursor(QCursor(cursors[edge]))
        else:
            self._restoreOverrideCursor()

    def _restoreOverrideCursor(self):
        """Restore the original cursor."""
        if self._cursorOverridden:
            QApplication.restoreOverrideCursor()
            self._cursorOverridden = False

    def _updateResizeCursor(self):
        """Update cursor based on current mouse position."""
        pos, _ = self._winPos()
        edge = self._edgeAt(pos)
        self._setOverrideCursorForEdge(edge)

    def _beginResize(self):
        """Begin resize operation if cursor is at an edge."""
        pos, global_pos = self._winPos()
        edge = self._edgeAt(pos)
        
        if edge:
            self._resizing = True
            self._resizeDir = edge
            self._startGeom = QRect(self.geometry())
            self._startPos = QPoint(global_pos)
            return True
        return False

    def _performResize(self):
        """Perform the resize operation based on mouse movement."""
        # Don't resize if maximized
        if self.isMaximized():
            return
            
        global_pos = QCursor.pos()
        dx = global_pos.x() - self._startPos.x()
        dy = global_pos.y() - self._startPos.y()
        geometry = QRect(self._startGeom)
        
        min_w = self.minimumWidth()
        min_h = self.minimumHeight()

        # Handle horizontal resizing
        if 'l' in self._resizeDir:
            new_left = geometry.left() + dx
            max_left = geometry.right() - min_w
            new_left = min(new_left, max_left)
            geometry.setLeft(new_left)
        elif 'r' in self._resizeDir:
            new_right = geometry.right() + dx
            min_right = geometry.left() + min_w
            new_right = max(new_right, min_right)
            geometry.setRight(new_right)

        # Handle vertical resizing
        if 't' in self._resizeDir:
            new_top = geometry.top() + dy
            max_top = geometry.bottom() - min_h
            new_top = min(new_top, max_top)
            geometry.setTop(new_top)
        elif 'b' in self._resizeDir:
            new_bottom = geometry.bottom() + dy
            min_bottom = geometry.top() + min_h
            new_bottom = max(new_bottom, min_bottom)
            geometry.setBottom(new_bottom)

        self.setGeometry(geometry)

    def _endResize(self):
        """End resize operation."""
        self._resizing = False
        self._resizeDir = None
        self._restoreOverrideCursor()

    def _isResizing(self) -> bool:
        """Check if currently in resize mode."""
        return self._resizing

    def _cleanupResize(self):
        """Cleanup resize state and cursor override."""
        self._restoreOverrideCursor()
        self._resizing = False
        self._resizeDir = None