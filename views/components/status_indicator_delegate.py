"""Delegate for drawing status indicators in table cells."""
from PyQt5.QtWidgets import QStyledItemDelegate, QStyle
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtCore import Qt, QRect

class StatusIndicatorDelegate(QStyledItemDelegate):
    """Delegate that draws a status indicator stripe on the left side of cells."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.stripe_width = 5  # Width of the indicator stripe
        
    def paint(self, painter, option, index):
        """Paint the cell with an indicator stripe on the left."""
        # Determine background and text colors based on selection state
        if option.state & QStyle.State_Selected:
            background_color = option.palette.highlight().color()
            text_color = option.palette.highlightedText().color()
        else:
            bg_data = index.data(Qt.BackgroundRole)
            if bg_data:
                background_color = bg_data.color() if hasattr(bg_data, "color") else QColor(bg_data)
            else:
                background_color = option.palette.base().color()
            text_color = option.palette.color(QPalette.Text)

        # Fill the cell background
        painter.save()
        painter.fillRect(option.rect, background_color)

        # Draw the indicator stripe if a color is provided
        color_data = index.data(Qt.UserRole + 2)  # Use UserRole+2 for status color

        if color_data:
            stripe_rect = QRect(option.rect.left(), option.rect.top(),
                                 self.stripe_width, option.rect.height())
            painter.fillRect(stripe_rect, QColor(color_data))
        
        # Determine padding for the Vendor Name column (column 1)
        padding = 12 if index.column() == 1 else 6

        # Draw the cell text with the appropriate padding
        text = index.data(Qt.DisplayRole)
        if text is not None:
            painter.setPen(QColor(text_color))
            painter.setFont(option.font)
            text_rect = option.rect.adjusted(padding, 0, 0, 0)
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, str(text))

        painter.restore()