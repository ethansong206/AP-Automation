"""Table component for invoice data display and manipulation."""
import os
from PyQt5.QtWidgets import (
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QPushButton, QMessageBox, QWidget, QHBoxLayout, QLabel
)
from PyQt5.QtGui import QFont, QColor, QBrush, QIcon
from PyQt5.QtCore import Qt, pyqtSignal

from assets.constants import COLORS
from views.components.status_indicator_delegate import StatusIndicatorDelegate
from views.components.date_selection import DateDelegate

class InvoiceTable(QTableWidget):
    """Enhanced table for displaying and editing invoice data."""
    
    # Define signals for events
    row_deleted = pyqtSignal(int, str)  # row_index, file_path
    vendor_add_clicked = pyqtSignal(int, int)  # row, col
    source_file_clicked = pyqtSignal(str)  # file_path
    manual_entry_clicked = pyqtSignal(int, object)  # row, button
    cell_manually_edited = pyqtSignal(int, int)  # row, col
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_table()
        
        # Data tracking
        self.original_values = {}  # (row, col): value
        self.manually_edited = set()  # Track (row, col) of manually edited cells
        self.auto_calculated = set()  # Track (row, col) of auto-calculated cells
        
    def setup_table(self):
        """Configure table properties and columns."""
        self.setColumnCount(10)
        self.setHorizontalHeaderLabels([
            "Vendor Name", "Invoice Number", "PO Number", "Invoice Date",
            "Discount Terms", "Due Date",
            "Discounted Total", "Total Amount",
            "Manual Entry", "Delete"
        ])
        
        # Set column widths for fixed-width columns
        self.setColumnWidth(0, 140)  # Vendor Name
        self.setColumnWidth(1, 110)  # Invoice Number
        self.setColumnWidth(2, 110)  # PO Number
        self.setColumnWidth(3, 100)  # Invoice Date
        self.setColumnWidth(4, 110)  # Discount Terms
        self.setColumnWidth(5, 100)  # Due Date
        self.setColumnWidth(6, 120)  # Discounted Total
        self.setColumnWidth(7, 100)  # Total Amount
        # Don't set width for column 8 (Manual Entry) - we'll stretch it
        self.setColumnWidth(9, 60)   # Delete

        # Set the resize modes for each column
        header = self.horizontalHeader()
        
        # Fixed width columns
        for col in [0, 1, 2, 3, 4, 5, 6, 7, 9]:
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            
        # Make "Manual Entry" column stretch to fill available space
        header.setSectionResizeMode(8, QHeaderView.Stretch)
        
        # Prevent the last column from stretching automatically
        header.setStretchLastSection(False)
        
        # Set a taller default row height for all rows
        self.verticalHeader().setDefaultSectionSize(42)
    
        # Force consistent row heights - don't allow resizing
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        
        # Rest of your existing setup...
        self.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.cellClicked.connect(self.handle_table_click)
        
        # Create delegates
        self.date_delegate = DateDelegate(self)
        self.indicator_delegate = StatusIndicatorDelegate(self)
        
        # Apply delegates to appropriate columns - this is the key change
        for col in range(self.columnCount()):
            if col == 3 or col == 5:  # Date columns
                self.setItemDelegateForColumn(col, self.date_delegate)
            elif col < 8:  # Regular data columns (not manual entry or delete)
                self.setItemDelegateForColumn(col, self.indicator_delegate)
    
        # Remove this line that was causing the conflict:
        # self.setItemDelegate(self.indicator_delegate)
    
        # Connect cell changed signal
        self.cellChanged.connect(self.handle_cell_changed)
        
        # Row selection behavior
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # Set a taller default row height for all rows
        self.verticalHeader().setDefaultSectionSize(42)  # Increased from 28 to 32
    
        # Force consistent row heights - don't allow resizing
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        
        # Ensure table items don't use the default white background
        self.setStyleSheet("""
            QTableWidget::item {
                background-color: transparent;
            }
        """)
    
    def add_row(self, row_data, file_path, is_no_ocr=False):
        """Add a new row to the table."""
        # Ensure row_data has at least 8 elements (for all columns)
        while len(row_data) < 8:
            row_data.append("")
            
        row_position = self.rowCount()
        self.insertRow(row_position)

        # Add each cell in the row (first 8 columns)
        self.populate_row_cells(row_position, row_data, is_no_ocr)
        
        # Add the Manual Entry cell
        if is_no_ocr:
            # Create a container widget with layout for proper centering
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(2, 0, 2, 0)
            layout.setSpacing(0)
            layout.setAlignment(Qt.AlignCenter)

            # Create the MANUAL ENTRY button with smaller text
            button = QPushButton("MANUAL ENTRY")
            # Store the file path on both the button AND the container
            button.setProperty("file_path", file_path)
            container.setProperty("file_path", file_path)  # Add this line
            button.clicked.connect(lambda _, r=row_position, b=button: 
                                 self.manual_entry_clicked.emit(r, b))

            # Make button shorter
            button.setStyleSheet("""
                QPushButton {
                    background-color: #FFC0CB; 
                    color: black; 
                    font-weight: bold; 
                    font-size: 8pt;  /* Smaller font */
                    padding: 0px 6px;  /* No vertical padding */
                    border-radius: 2px;
                    min-height: 20px;  /* Smaller height */
                    max-height: 20px;
                }
                QPushButton:hover {
                    background-color: #FFB0BB;
                }
            """)

            # Set an even smaller fixed height
            button.setFixedHeight(20)  

            # Add button to the layout
            layout.addWidget(button)
            
            # Set the container as the cell widget
            self.setCellWidget(row_position, 8, container)
        else:
            # Add clickable link for OCR'd rows
            self.add_source_file_cell(row_position, file_path)
    
        # Add delete cell
        self.add_delete_cell(row_position)
        
        # Store original values for tracking changes
        self.store_original_values(row_position, row_data)
        
        # Highlight row based on content
        self.highlight_row(row_position, is_no_ocr)
        
        # Auto-size vendor column
        self.resize_vendor_column()
        
        return row_position

    def populate_row_cells(self, row_position, row_data, is_no_ocr):
        """Populate the cells of a row with data."""
        for col, value in enumerate(row_data):
            if col == 0 and is_no_ocr:
                # Empty vendor name for no OCR rows
                self.setItem(row_position, col, QTableWidgetItem(""))
                
            elif col == 0 and not value:
                # ADD VENDOR placeholder for missing vendor
                item = QTableWidgetItem("ADD VENDOR")
                item.setForeground(QBrush(QColor("blue")))
                item.setBackground(QBrush(QColor(COLORS['RED'])))
                font = QFont()
                font.setBold(True)
                font.setUnderline(True)
                font.setPointSize(font.pointSize() + 2)
                item.setFont(font)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                # Add padding with spaces (will be combined with cell padding below)
                item.setText("    " + "ADD VENDOR")
                self.setItem(row_position, col, item)
                
            else:
                # Normal cell with larger font and padding
                item = QTableWidgetItem("    " + (str(value) if value is not None else ""))
                font = item.font()
                font.setPointSize(font.pointSize() + 2)
                item.setFont(font)
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.setItem(row_position, col, item)

    def add_source_file_cell(self, row_position, file_path):
        """Add the manual entry cell with a clickable link and edit icon."""
        # Create a custom widget with an icon and text label
        cell_widget = QWidget()
        layout = QHBoxLayout(cell_widget)
        
        # Improve vertical spacing with better margins
        layout.setContentsMargins(4, 3, 4, 3)  # Left, Top, Right, Bottom
        layout.setSpacing(4)
        
        # Use a small pencil icon
        icon_label = QLabel("✎")
        icon_label.setStyleSheet("color: #0066cc; font-weight: bold;")
        layout.addWidget(icon_label)
        
        # Add filename label with proper vertical alignment
        if file_path:
            filename = os.path.basename(file_path)
            if len(filename) > 30:
                filename = filename[:27] + "..."
        else:
            filename = "Edit Invoice"
            
        text_label = QLabel(filename)
        text_label.setStyleSheet("color: #0066cc; text-decoration: underline; font-weight: bold;")
        text_label.setToolTip(file_path)
        text_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        layout.addWidget(text_label, 1)  # 1 = stretch factor
    
        # Ensure the widget takes up the whole cell and text is properly aligned
        layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        # CRITICAL: Store file path as property on the widget
        cell_widget.setProperty("file_path", file_path)
        
        # CRITICAL: Add a custom event to handle clicks on the widget
        # This overrides mouseReleaseEvent to emit our signal
        def mouse_release_handler(event):
            self.manual_entry_clicked.emit(row_position, None)
    
        cell_widget.mouseReleaseEvent = mouse_release_handler
    
        # Set cursor to indicate it's clickable
        cell_widget.setCursor(Qt.PointingHandCursor)
        
        # Set the widget in the table cell
        self.setCellWidget(row_position, 8, cell_widget)

    def add_delete_cell(self, row_position):
        """Add the delete cell with a delete icon."""
        delete_item = QTableWidgetItem("❌")
        delete_item.setTextAlignment(Qt.AlignCenter)
        delete_item.setFlags(Qt.ItemIsEnabled)
        delete_item.setBackground(QColor(COLORS['LIGHT_GREY']))
        self.setItem(row_position, 9, delete_item)

    def store_original_values(self, row_position, row_data):
        """Store original values for change tracking."""
        for col, value in enumerate(row_data):
            self.original_values[(row_position, col)] = str(value) if value is not None else ""

    def handle_cell_changed(self, row, col):
        """Handle when a cell's content is changed by the user."""
        # Only handle editable columns (0-7)
        if col > 7:
            return
    
        item = self.item(row, col)
        if not item:
            return

        # Temporarily disconnect to prevent recursion during processing
        self.cellChanged.disconnect(self.handle_cell_changed)

        try:
            # Check if cell was cleared (empty)
            if not item.text().strip():
                # Restore original value
                original_value = self.original_values.get((row, col), "")
                item.setText(original_value)
                # Remove from manually edited if it matches original
                if (row, col) in self.manually_edited:
                    self.manually_edited.remove((row, col))
            else:
                # Check if value is different from original
                original_value = self.original_values.get((row, col), "")
                current_value = item.text().strip()
                
                if current_value != original_value:
                    # Mark as manually edited
                    self.manually_edited.add((row, col))
                    # Emit signal that cell was manually edited
                    self.cell_manually_edited.emit(row, col)
                    
                    # NEW CODE: Check if this is the invoice date column
                    if col == 3:  # Invoice Date column
                        # Check if discount terms are available
                        terms = self.get_cell_text(row, 4).strip()
                        if terms:
                            # Try to calculate due date
                            from extractors.utils import calculate_discount_due_date
                            try:
                                invoice_date = current_value
                                due_date = calculate_discount_due_date(terms, invoice_date)
                                if due_date:
                                    # Update the due date cell
                                    self.update_calculated_field(row, 5, due_date, True)
                            except Exception as e:
                                print(f"[WARN] Could not compute due date: {e}")
                else:
                    # Value matches original, remove from manually edited
                    if (row, col) in self.manually_edited:
                        self.manually_edited.remove((row, col))
                        
            # Let rehighlight_row handle the coloring
            self.rehighlight_row(row)
            
        finally:
            # Reconnect the signal after changes are done
            self.cellChanged.connect(self.handle_cell_changed)

    def handle_table_click(self, row, col):
        """Handle clicking on a cell in the table."""
        header = self.horizontalHeaderItem(col).text()
        file_path = self.get_file_path_for_row(row)
        
        if header == "Manual Entry":
            # Check if we have a cell widget (for custom implementation)
            cell_widget = self.cellWidget(row, col)
            if cell_widget:
                # Custom widget click will be handled by its mouseReleaseEvent
                # But we need a way to handle regular clicks on the widget
                # This is handled by connecting a click signal in the widget
                pass
            else:
                # For regular items
                file_path = self.get_file_path_for_row(row)
                if file_path:
                    self.manual_entry_clicked.emit(row, None)
    
        elif header == "Delete":
            # Only ask for confirmation if row exists
            if row < self.rowCount():
                confirm = QMessageBox.question(
                    self, "Delete Row", f"Are you sure you want to delete row {row + 1}?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if confirm == QMessageBox.Yes:
                    # Ensure we clean up tracking data BEFORE removing the row
                    self.cleanup_row_data(row)
                    self.removeRow(row)
                    self.row_deleted.emit(row, file_path)
        
        elif header == "Vendor Name":
            value = self.item(row, col).text()
            if value.strip().upper() == "ADD VENDOR":
                self.vendor_add_clicked.emit(row, col)

    def get_file_path_for_row(self, row):
        """Get the file path for a row from any type of cell in column 8."""
        file_path = None
        
        # First check if there's a custom widget
        cell_widget = self.cellWidget(row, 8)
        if cell_widget:
            # Try to get file path directly from the container widget first
            file_path = cell_widget.property("file_path")
            
            # If container doesn't have it, check if it's a button
            if not file_path and isinstance(cell_widget, QPushButton):
                file_path = cell_widget.property("file_path")
            
            # For QHBoxLayout containers, find the button inside
            if not file_path:
                for child in cell_widget.children():
                    if isinstance(child, QPushButton):
                        file_path = child.property("file_path")
                        break
    
        # Check for regular QTableWidgetItem as fallback
        if not file_path:
            file_item = self.item(row, 8)
            if file_item:
                file_path = file_item.data(Qt.UserRole)
                if not file_path:
                    file_path = file_item.toolTip()

        # Convert to absolute path if needed
        if file_path:
            file_path = os.path.abspath(file_path)
    
        return file_path

    # --- Additional helper methods (omitted for brevity) ---
    def highlight_row(self, row_position, is_no_ocr):
        """Highlight the row based on its content using left border indicators."""
        # Set colors for each cell using our left border indicator approach
        for col in range(8):
            color = self.determine_cell_color(row_position, col)
            self.set_cell_color(row_position, col, color)

    def resize_vendor_column(self):
        """Auto-resize the vendor column based on content."""
        vendor_col = 0
        self.resizeColumnToContents(vendor_col)
        current_width = self.columnWidth(vendor_col)
        self.setColumnWidth(vendor_col, current_width + 50)
        
    def rehighlight_row(self, row):
        """Rehighlight a row after changes."""
        # Safely disconnect to avoid recursion
        try:
            self.cellChanged.disconnect(self.handle_cell_changed)
            was_connected = True
        except TypeError:
            # Signal was not connected
            was_connected = False
        
        try:
            for col in range(8):
                color = self.determine_cell_color(row, col)
                self.set_cell_color(row, col, color)
        finally:
            # Only reconnect if it was connected before
            if was_connected:
                self.cellChanged.connect(self.handle_cell_changed)
        
        # Force a repaint of the affected cells
        for col in range(8):
            item = self.item(row, col)
            if item:
                item.setSelected(False)  # Toggle selection to force a repaint

    def cleanup_row_data(self, row):
        """Clean up all data associated with a row."""
        # Remove from original_values
        keys_to_remove = [key for key in self.original_values if key[0] == row]
        for key in keys_to_remove:
            del self.original_values[key]
    
        # Remove from manually_edited
        keys_to_remove = [(r, c) for r, c in self.manually_edited if r == row]
        for key in keys_to_remove:
            self.manually_edited.remove(key)
        
        # Remove from auto_calculated
        keys_to_remove = [(r, c) for r, c in self.auto_calculated if r == row]
        for key in keys_to_remove:
            self.auto_calculated.remove(key)
        
        # Also reindex the remaining data for rows after this one
        self.reindex_tracking_data(row)
        
    def reindex_tracking_data(self, deleted_row):
        """Reindex tracking dictionaries after a row is deleted."""
        # Reindex original_values
        new_dict = {}
        for (r, c), value in self.original_values.items():
            if r > deleted_row:
                new_dict[(r-1, c)] = value
            elif r < deleted_row:
                new_dict[(r, c)] = value
        self.original_values = new_dict
        
        # Reindex manually_edited
        new_set = set()
        for r, c in self.manually_edited:
            if r > deleted_row:
                new_set.add((r-1, c))
            elif r < deleted_row:
                new_set.add((r, c))
        self.manually_edited = new_set
        
        # Reindex auto_calculated
        new_set = set()
        for r, c in self.auto_calculated:
            if r > deleted_row:
                new_set.add((r-1, c))
            elif r < deleted_row:
                new_set.add((r, c))
        self.auto_calculated = new_set
        
    def set_cell_color(self, row, col, color):
        """Set the indicator color for a cell."""
        item = self.item(row, col)
        if item:
            # Store the color in the UserRole+2 data
            item.setData(Qt.UserRole + 2, color)
            
            # Special handling for rows with red indicators - use pink background
            if color == COLORS['RED']:
                # Use a more visible pink background for error rows
                item.setBackground(QColor("#FFDDDD"))  # Light pink background
            elif (row, col) in self.auto_calculated:
                # Add a special background for calculated cells - BUT NO BULLET POINTS
                item.setBackground(QColor("#E6F3FF"))  # Light blue background
                
                # REMOVE THIS CODE: 
                # if not item.text().startswith("•"):
                #     item.setText("• " + item.text())
            else:
                # Regular background for normal cells
                light_color = self.get_lighter_shade(color, 0.07)
                item.setBackground(QColor(light_color))
        
    def get_lighter_shade(self, color_code, opacity=0.07):
        """Convert a color to a lighter shade with opacity."""
        color = QColor(color_code)
        # Create a lighter version by blending with white
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {opacity})"

    def determine_cell_color(self, row, col):
        """Determine the appropriate color for a cell based on conditions."""
        # Special cell overrides first (ADD VENDOR cells and discount terms)
        if self.is_add_vendor_cell(row, col):
            return COLORS['RED']
        
        if col == 4:  # Discount Terms column
            cell_text = self.get_cell_text(row, col).upper()
            if "NET" not in cell_text and cell_text:
                return "#FFC0CB"  # Pink
        
        # ROW STATUS DETERMINES COLOR - this is what we're trying to fix
        # Check the row status independent of individual cell edits
        if self.is_row_no_ocr(row):
            return COLORS['RED']
        
        if self.is_row_complete(row):
            return COLORS['GREEN']
            
        # If we get here, the row is incomplete - use YELLOW regardless of cell edits
        return COLORS['YELLOW']
        
        # Remove these individual cell checks - they override the row status
        # if (row, col) in self.manually_edited:
        #     return COLORS['LIGHT_BLUE']
        # elif (row, col) in self.auto_calculated:
        #     return COLORS['LIGHT_BLUE']

    def is_add_vendor_cell(self, row, col):
        """Check if the cell contains an ADD VENDOR placeholder."""
        if col != 0:  # Only vendor name column (0) can have ADD VENDOR
            return False
            
        item = self.item(row, col)
        if not item:
            return False
            
        return item.text().strip().upper() == "ADD VENDOR"

    def is_row_no_ocr(self, row):
        """Check if the row is marked as no-OCR (manual entry only)."""
        # Check if the row has a MANUAL ENTRY button in column 8
        cell_widget = self.cellWidget(row, 8)
        return isinstance(cell_widget, QPushButton) and cell_widget.text() == "MANUAL ENTRY"

    def is_row_complete(self, row):
        """Check if all required fields in the row are filled."""
        # Check first 8 columns (all except Manual Entry and Delete)
        for col in range(8):
            # Skip checking column 2 (PO Number) as it's optional
            if col == 2:
                continue
                
            value = self.get_cell_text(row, col)
            if not value.strip():
                return False
        return True

    def get_cell_text(self, row, col):
        """Safely get the text from a cell."""
        item = self.item(row, col)
        if item:
            return item.text()
        return ""

    def update_calculated_field(self, row, col, value, is_auto_calculated=True):
        """Update a cell with a calculated value."""
        # Create the item with the value
        item = QTableWidgetItem("    " + (str(value) if value is not None else ""))
        
        # Add visual indicators that this is calculated
        font = item.font()
        font.setItalic(True)
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)  # Increase font size
        item.setFont(font)
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    
        # Set the cell value
        self.setItem(row, col, item)
        
        # Mark as auto-calculated in our tracking set
        if is_auto_calculated:
            self.auto_calculated.add((row, col))
        
        # Apply the appropriate color based on row status
        color = self.determine_cell_color(row, col)
        self.set_cell_color(row, col, color)
        
        # Update original values to prevent this being marked as manually edited
        self.original_values[(row, col)] = str(value) if value is not None else ""

    def clear_tracking_data(self):
        """Reset all data tracking mechanisms."""
        # Clear all tracking structures
        self.original_values = {}
        self.manually_edited = set()
        self.auto_calculated = set()