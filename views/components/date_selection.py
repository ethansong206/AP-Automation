"""Date handling components for the invoice application."""
from PyQt5.QtWidgets import QItemDelegate, QDateEdit, QStyleOptionViewItem
from PyQt5.QtCore import QDate, Qt, QRect
from PyQt5.QtGui import QPainter, QColor, QBrush

class DateDelegate(QItemDelegate):
    """Delegate for date fields in the table."""
    
    def createEditor(self, parent, option, index):
        """Create a date editor widget."""
        editor = QDateEdit(parent)
        editor.setCalendarPopup(True)
        editor.setDisplayFormat("MM/dd/yy")
        editor.setDate(QDate.currentDate())
        return editor

    def setEditorData(self, editor, index):
        """Set the editor data from the model."""
        text = index.model().data(index, Qt.EditRole)
        try:
            # Parse the date from the table
            date_obj = QDate.fromString(text, "MM/dd/yy")
            
            # Fix the century issue - if year < 2000, assume it's a 21st century date
            if date_obj.isValid() and date_obj.year() < 2000:
                # Extract components
                day = date_obj.day()
                month = date_obj.month()
                year = date_obj.year() % 100  # Get just the 2-digit year
                
                # Create a new date in the 21st century
                corrected_date = QDate(2000 + year, month, day)
                editor.setDate(corrected_date)
            elif date_obj.isValid():
                editor.setDate(date_obj)
            else:
                editor.setDate(QDate.currentDate())
        except Exception:
            editor.setDate(QDate.currentDate())

    def setModelData(self, editor, model, index):
        """Update the model with data from the editor."""
        date = editor.date()
        model.setData(index, date.toString("MM/dd/yy"), Qt.EditRole)

    def paint(self, painter, option, index):
        """Custom painting to handle both date display and status indicators."""
        # Save painter state
        painter.save()
        
        # Create a copy of the option with QStyleOptionViewItem
        opt = QStyleOptionViewItem(option)
        
        # Get the status color from the model data
        color_data = index.data(Qt.UserRole + 2)
        
        # First draw the cell background - either default or our custom light background
        if color_data:
            # Use very light background based on indicator color
            base_color = QColor(color_data)
            light_color = QColor(base_color)
            light_color.setAlpha(20)  # Very light
            painter.fillRect(opt.rect, light_color)
        
        # Now draw the text using standard ItemDelegate methods
        # This ensures the text is drawn with proper alignment and formatting
        self.drawDisplay(painter, opt, opt.rect, index.data(Qt.DisplayRole))
        
        # Finally draw the indicator stripe if color is provided
        if color_data:
            stripe_rect = QRect(opt.rect.left(), opt.rect.top(), 
                             10, opt.rect.height())
            painter.fillRect(stripe_rect, QColor(color_data))
        
        # Restore painter state
        painter.restore()