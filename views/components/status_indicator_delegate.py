"""Delegate for drawing status indicators in table cells."""
from PyQt5.QtWidgets import QStyledItemDelegate
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtCore import Qt, QRect

class StatusIndicatorDelegate(QStyledItemDelegate):
    """Delegate that draws a status indicator stripe on the left side of cells."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.stripe_width = 10  # Width of the indicator stripe
        
    def paint(self, painter, option, index):
        """Paint the cell with an indicator stripe on the left."""
        # Get the status color from the model data
        color_data = index.data(Qt.UserRole + 2)  # Use UserRole+2 for status color
        
        # First let the standard delegate draw the cell
        super().paint(painter, option, index)
        
        # Then draw our indicator stripe if color is provided
        if color_data:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Create a rectangle for the left stripe
            stripe_rect = QRect(option.rect.left(), option.rect.top(), 
                              self.stripe_width, option.rect.height())
            
            # Draw the indicator stripe
            painter.fillRect(stripe_rect, QColor(color_data))
            painter.restore()