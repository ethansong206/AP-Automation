"""Date handling components for the invoice application."""
from PyQt5.QtWidgets import QItemDelegate, QDateEdit
from PyQt5.QtCore import QDate, Qt

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
            date = QDate.fromString(text, "MM/dd/yy")
            if not date.isValid():
                date = QDate.currentDate()
        except Exception:
            date = QDate.currentDate()
        editor.setDate(date)

    def setModelData(self, editor, model, index):
        """Update the model with data from the editor."""
        date = editor.date()
        model.setData(index, date.toString("MM/dd/yy"), Qt.EditRole)