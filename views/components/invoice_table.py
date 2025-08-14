"""Table component for invoice data display and manipulation."""
import os
from datetime import datetime
from PyQt5.QtWidgets import (
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QPushButton, QMessageBox, QWidget, QHBoxLayout, QLabel,
    QAbstractButton, QDialog
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt, pyqtSignal, QEvent

_SUPERSCRIPT_TRANS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def to_superscript(num: int) -> str:
    """Return ``num`` rendered using Unicode superscript digits."""
    return str(num).translate(_SUPERSCRIPT_TRANS)

from assets.constants import COLORS
from views.components.status_indicator_delegate import StatusIndicatorDelegate
from views.components.date_selection import DateDelegate
from extractors.utils import get_vendor_list
from views.dialogs.vendor_dialog import AddVendorFlow

class SortableTableWidgetItem(QTableWidgetItem):
    """ Table widget item that stores a separate key for sorting. """
    def __init__(self, text: str, sort_key=None):
        super().__init__(text)
        self.sort_key = sort_key
    
    def __lt__(self, other):
        if isinstance(other, SortableTableWidgetItem):
            if self.sort_key is not None and other.sort_key is not None:
                return self.sort_key < other.sort_key
        return super().__lt__(other)

class InvoiceTable(QTableWidget):
    """Enhanced table for displaying and editing invoice data."""
    
    # Define signals for events
    row_deleted = pyqtSignal(int, str)  # row_index, file_path
    source_file_clicked = pyqtSignal(str)  # file_path
    manual_entry_clicked = pyqtSignal(int, object)  # row, button
    cell_manually_edited = pyqtSignal(int, int)  # row, col
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_table()
        
        # Data tracking
        self.manually_edited = set()  # Track (row, col) of manually edited cells
        self.auto_calculated = set()  # Track (row, col) of auto-calculated cells
        
        self._last_duplicate_groups = {}

        self._rehighlighting = False

    # Helper methods for sorting
    def _parse_date(self, text: str):
        """Return a datetime object for consistent date sorting."""
        try:
            dt = datetime.strptime(text, "%m/%d/%y")
            if dt.year < 2000:
                dt = dt.replace(year=dt.year + 100)
            return dt
        except Exception:
            return None

    def _create_item(self, col: int, value, italic: bool = False, bold: bool = False):
        """Create a sortable table item with styling."""
        display_value = str(value) if value is not None else ""
        if col == 1:
            sort_key = display_value.lower()
        elif col in (4, 6):
            sort_key = self._parse_date(display_value)
        else:
            sort_key = display_value
        item = SortableTableWidgetItem(display_value, sort_key)
        font = item.font()
        font.setPointSize(font.pointSize() + 2)
        if italic:
            font.setItalic(True)
        if bold:
            font.setBold(True)
        item.setFont(font)
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        item.setData(Qt.UserRole, display_value)
        return item

    def _update_item_sort_key(self, item, col):
        """Refresh the sort key for an item when its text changes."""
        if not isinstance(item, SortableTableWidgetItem):
            return
        text = item.text().strip()
        if col == 1:
            item.sort_key = text.lower()
        elif col in (4, 6):
            item.sort_key = self._parse_date(text)
        else:
            item.sort_key = text

    def setup_table(self):
        """Configure table properties and columns."""
        self.setColumnCount(11)
        self.setHorizontalHeaderLabels([
            "", "Vendor Name", "Invoice Number", "PO Number", "Invoice Date",
            "Discount Terms", "Due Date",
            "Discounted Total", "Total Amount",
            "Manual Entry", "Delete"
        ])
        
        # Set column widths for fixed-width columns
        self.setColumnWidth(0, 30)   # Flag column
        self.setColumnWidth(1, 140)  # Vendor Name
        self.setColumnWidth(2, 110)  # Invoice Number
        self.setColumnWidth(3, 110)  # PO Number
        self.setColumnWidth(4, 100)  # Invoice Date
        self.setColumnWidth(5, 110)  # Discount Terms
        self.setColumnWidth(6, 100)  # Due Date
        self.setColumnWidth(7, 120)  # Discounted Total
        self.setColumnWidth(8, 100)  # Total Amount
        # Don't set width for column 9 (Manual Entry) - we'll stretch it
        self.setColumnWidth(10, 60)   # Delete

        # Set the resize modes for each column
        header = self.horizontalHeader()
        
        # Fixed width columns
        for col in [0, 1, 2, 3, 4, 5, 6, 7, 8, 10]:
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            
        # Make "Manual Entry" column stretch to fill available space
        header.setSectionResizeMode(9, QHeaderView.Stretch)
        
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
            if col == 4 or col == 6:  # Date columns
                self.setItemDelegateForColumn(col, self.date_delegate)
            elif 1 <= col <= 8:  # Regular data columns (not manual entry or delete)
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
    
        # Track whether the entire table is selected
        self._all_selected = False

        # Store reference to the corner button for select-all toggling
        self._corner_button = self.findChild(QAbstractButton)

        # Update selection state when it changes
        self.itemSelectionChanged.connect(self.update_all_selected_state)

        # Allow toggling select-all via the top-left corner button
        if self._corner_button:
            self._corner_button.installEventFilter(self)

        self.setSortingEnabled(True)

    def delete_row_by_file_path(self, file_path: str, confirm: bool = False) -> bool:
        """Find and delete the first row whose Manual Entry cell matches file_path."""
        if not file_path:
            return False
        abs_target = os.path.abspath(file_path)
        for row in range(self.rowCount()):
            row_path = self.get_file_path_for_row(row)
            if row_path and os.path.abspath(row_path) == abs_target:
                if confirm:
                    ans = QMessageBox.question(
                        self, "Delete Row",
                        f"Delete invoice for file:\n{os.path.basename(abs_target)}?",
                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                    )
                    if ans != QMessageBox.Yes:
                        return False
                # Clean up tracking, remove, and emit
                self.cleanup_row_data(row)
                self.removeRow(row)
                self.row_deleted.emit(row, abs_target)
                self.update_duplicate_invoice_markers()
                return True
        return False

    def update_all_selected_state(self):
        """Update internal flag indicating if the whole table is selected."""
        total_items = self.rowCount() * self.columnCount()
        self._all_selected = (
            total_items > 0 and len(self.selectedIndexes()) == total_items
        )

    def handle_corner_button_click(self):
        """Toggle select-all behaviour when the corner button is clicked."""
        if self._all_selected:
            self.clearSelection()
        else:
            self.selectAll()

    def eventFilter(self, source, event):
        """Intercept corner button clicks to implement toggle behaviour."""
        if source is getattr(self, "_corner_button", None) and event.type() == QEvent.MouseButtonPress:
            self.handle_corner_button_click()
            return True
        return super().eventFilter(source, event)

    def add_row(self, row_data, file_path, is_no_ocr=False):
        """Add a new row to the table."""
        sorting_enabled = self.isSortingEnabled()
        if sorting_enabled:
            header = self.horizontalHeader()
            sort_col = header.sortIndicatorSection()
            sort_order = header.sortIndicatorOrder()
            self.setSortingEnabled(False)
        else:
            sort_col = sort_order = None
        
        # Ensure row_data has at least 8 elements (for all data columns)
        while len(row_data) < 8:
            row_data.append("")
            
        row_position = self.rowCount()
        self.insertRow(row_position)

        # Add flag cell
        self.add_flag_cell(row_position)

        # Add each cell in the row (data columns)
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
            container.setProperty("file_path", file_path)
            # Determine row at click time to support sorting
            button.clicked.connect(
                lambda _, w=container, b=button: self._emit_manual_entry_from_widget(w, b)
            )

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
            self.setCellWidget(row_position, 9, container)
        else:
            # Add clickable link for OCR'd rows
            self.add_source_file_cell(row_position, file_path)
    
        # Add delete cell
        self.add_delete_cell(row_position)
        
        # Highlight row based on content
        self.highlight_row(row_position)
        
        # Auto-size vendor column
        self.resize_vendor_column()

        self.update_duplicate_invoice_markers()

        if sorting_enabled:
            self.setSortingEnabled(True)
            self.sortByColumn(sort_col, sort_order)

        return row_position
    
    def _emit_manual_entry_from_widget(self, widget, button=None):
        """Emit manual entry signal using the widget's current row.

        This determines the row at click time so that sorting the table
        doesn't cause the Manual Entry dialog to open for the wrong file.
        """
        if not widget:
            return
        index = self.indexAt(widget.pos())
        row = index.row()
        self.manual_entry_clicked.emit(row, button)

    def populate_row_cells(self, row_position, row_data, is_no_ocr):
        """Populate the cells of a row with data."""
        for idx, value in enumerate(row_data):
            col = idx + 1 # Offset for flag column
            display_value = str(value) if value is not None else ""
            if col == 1 and is_no_ocr:
                display_value = ""

            item = self._create_item(col, display_value)
            self.setItem(row_position, col, item)

    def add_flag_cell(self, row_position):
        """Add the clickable flag cell."""
        flag_item = QTableWidgetItem("⚑")
        flag_item.setTextAlignment(Qt.AlignCenter)
        flag_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        flag_item.setData(Qt.UserRole, False)
        self.setItem(row_position, 0, flag_item)

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
        # Determine the row at click time so sorting doesn't break selection
        def mouse_release_handler(event, w=cell_widget):
            self._emit_manual_entry_from_widget(w)
    
        cell_widget.mouseReleaseEvent = mouse_release_handler
    
        # Set cursor to indicate it's clickable
        cell_widget.setCursor(Qt.PointingHandCursor)
        
        # Set the widget in the table cell
        self.setCellWidget(row_position, 9, cell_widget)

    def add_delete_cell(self, row_position):
        """Add the delete cell with a delete icon."""
        delete_item = QTableWidgetItem("❌")
        delete_item.setTextAlignment(Qt.AlignCenter)
        delete_item.setFlags(Qt.ItemIsEnabled)
        delete_item.setBackground(QColor(COLORS['LIGHT_GREY']))
        self.setItem(row_position, 10, delete_item)

    def handle_cell_changed(self, row, col):
        """Handle when a cell's content is changed by the user."""
        # Only handle editable columns (0-7)
        if col == 0 or col > 8:
            return
    
        item = self.item(row, col)
        if not item:
            return

        # Temporarily disconnect to prevent recursion during processing
        self.cellChanged.disconnect(self.handle_cell_changed)

        try:
            original_value = item.data(Qt.UserRole) or ""
            current_value = item.text().strip()

            if current_value != original_value:
                # Mark cell as manually edited
                self.manually_edited.add((row, col))
                self.cell_manually_edited.emit(row, col)

                if col == 1:  # Vendor Name column
                    vendors = {v.strip().lower() for v in get_vendor_list()}
                    if current_value and current_value.lower() not in vendors:
                        warn = QMessageBox.warning(
                            self,
                            "Unknown Vendor",
                            (
                                f"‘{current_value}’ isn’t in your vendor list.\n\n"
                                "You’ll need to add it first (Vendor Name → Vendor Number → optional Identifier).\n"
                                "Vendor Number is required; Identifier is optional."
                            ),
                            QMessageBox.Ok | QMessageBox.Cancel,
                            QMessageBox.Ok,
                        )
                        if warn == QMessageBox.Cancel:
                            item.setText(original_value)
                            if (row, col) in self.manually_edited:
                                self.manually_edited.remove((row, col))
                            self._update_item_sort_key(item, col)
                            self.rehighlight_row(row)
                            return
                        pdf_path = self.get_file_path_for_row(row) or ""
                        flow = AddVendorFlow(pdf_path=pdf_path, parent=self, prefill_vendor_name=current_value)
                        if flow.exec_() != QDialog.Accepted:
                            item.setText(original_value)
                            if (row, col) in self.manually_edited:
                                self.manually_edited.remove((row, col))
                            self._update_item_sort_key(item, col)
                            self.rehighlight_row(row)
                            return
                elif col == 4:  # Invoice Date column
                    terms = self.get_cell_text(row, 5).strip()
                    if terms:
                        from extractors.utils import calculate_discount_due_date
                        try:
                            invoice_date = current_value
                            due_date = calculate_discount_due_date(terms, invoice_date)
                            if due_date:
                                self.update_calculated_field(row, 6, due_date, True)
                        except Exception as e:
                            print(f"[WARN] Could not compute due date: {e}")
            else:
                # Remove from tracking if reverted to original
                if (row, col) in self.manually_edited:
                    self.manually_edited.remove((row, col))
            # Reapply coloring after changes
            self._update_item_sort_key(item, col)
            self.rehighlight_row(row)
            
        finally:
            # Reconnect the signal after changes are done
            self.cellChanged.connect(self.handle_cell_changed)
        if col == 2:
            # Update stored clean invoice number and refresh duplicate markers
            item.setData(Qt.UserRole + 20, current_value)
            self.update_duplicate_invoice_markers()

    def handle_table_click(self, row, col):
        """Handle clicking on a cell in the table."""
        if col == 0:
            self.toggle_row_flag(row)
            return
        
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

    def get_file_path_for_row(self, row):
        """Get the file path for a row from any type of cell in column 9."""
        file_path = None
        
        # First check if there's a custom widget
        cell_widget = self.cellWidget(row, 9)
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
            file_item = self.item(row, 9)
            if file_item:
                file_path = file_item.data(Qt.UserRole)
                if not file_path:
                    file_path = file_item.toolTip()

        # Convert to absolute path if needed
        if file_path:
            file_path = os.path.abspath(file_path)
    
        return file_path

    def find_row_by_file_path(self, file_path: str) -> int:
        """Return the row index for the given file path, or -1 if not found."""
        if not file_path:
            return -1
        abs_target = os.path.abspath(file_path)
        for row in range(self.rowCount()):
            row_path = self.get_file_path_for_row(row)
            if row_path and os.path.abspath(row_path) == abs_target:
                return row
        return -1

    def is_row_flagged(self, row):
        """Check if the row is marked for later."""
        item = self.item(row, 0)
        return bool(item and item.data(Qt.UserRole))

    def toggle_row_flag(self, row):
        """Toggle the flag state for a row."""
        item = self.item(row, 0)
        if not item:
            return
        flagged = not bool(item.data(Qt.UserRole))
        item.setData(Qt.UserRole, flagged)
        item.setText("🚩" if flagged else "⚑")

        # Reapply current sorting so the row moves to the correct position
        sort_col = self.horizontalHeader().sortIndicatorSection()
        sort_order = self.horizontalHeader().sortIndicatorOrder()
        self.sortItems(sort_col, sort_order)

        # Rehighlight all rows to ensure stripes match new order
        for r in range(self.rowCount()):
            self.rehighlight_row(r)

    # --- Additional helper methods (omitted for brevity) ---
    def highlight_row(self, row_position):
        """Highlight the row based on its content"""
        for col in range(1, 9):
            background, stripe = self.determine_cell_color(row_position, col)
            self.set_cell_color(row_position, col, background, stripe)

    def resize_vendor_column(self):
        """Auto-resize the vendor column based on content."""
        vendor_col = 1
        self.resizeColumnToContents(vendor_col)
        current_width = self.columnWidth(vendor_col)
        self.setColumnWidth(vendor_col, current_width + 50)
        
    def rehighlight_row(self, row):
        """Rehighlight a row after changes."""
        if self._rehighlighting:
            return
        self._rehighlighting = True
        
        try:
            try:
                self.cellChanged.disconnect(self.handle_cell_changed)
                was_connected = True
            except TypeError:
                was_connected = False
        
            for col in range(1, 9):
                background, stripe = self.determine_cell_color(row, col)
                self.set_cell_color(row, col, background, stripe)

            for col in range(1, 9):
                item = self.item(row, col)
                if item:
                    item.setData(Qt.UserRole + 3, item.data(Qt.UserRole + 3))

        finally:
            if 'was_connected' in locals() and was_connected:
                self.cellChanged.connect(self.handle_cell_changed)
            self._rehighlighting = False

    def cleanup_row_data(self, row):
        """Clean up all data associated with a row."""
        # Remove from manually_edited
        keys_to_remove = [(r, c) for r, c in self.manually_edited if r == row]
        for key in keys_to_remove:
            self.manually_edited.remove(key)
        
        # Remove from auto_calculated
        keys_to_remove = [(r, c) for r, c in self.auto_calculated if r == row]
        for key in keys_to_remove:
            self.auto_calculated.remove(key)
        
        # Reindex the remaining data for rows after this one
        self.reindex_tracking_data(row)

    def reindex_tracking_data(self, deleted_row):
        """Reindex tracking sets after a row is deleted."""
        # Reindex manually_edited
        new_set = set()
        for r, c in self.manually_edited:
            if r > deleted_row:
                new_set.add((r - 1, c))
            elif r < deleted_row:
                new_set.add((r, c))
        self.manually_edited = new_set
        
        # Reindex auto_calculated
        new_set = set()
        for r, c in self.auto_calculated:
            if r > deleted_row:
                new_set.add((r - 1, c))
            elif r < deleted_row:
                new_set.add((r, c))
        self.auto_calculated = new_set
        
    def set_cell_color(self, row, col, background=None, stripe=None):
        """Set the background and stripe color for a cell."""
        item = self.item(row, col)
        if not item:
            return

        # Set stripe color for delegate
        item.setData(Qt.UserRole + 2, stripe)

        # Set background color
        if background:
            item.setBackground(QColor(background))
        else:
            item.setBackground(QColor(COLORS['WHITE']))

    def determine_cell_color(self, row, col):
        """Determine background and stripe colors for a cell."""
        text = self.get_cell_text(row, col).strip()
        text_upper = text.upper()

        row_empty = self.is_row_empty(row)
        row_complete = self.is_row_complete(row)
        vendor_missing = not self.get_cell_text(row, 1).strip()

        background = None
        stripe = None

        if row_empty or vendor_missing:
            background = COLORS['LIGHT_RED']
        else:
            if not text:
                background = COLORS['YELLOW']
            if not row_complete and col == 1:
                stripe = COLORS['YELLOW']

        if (row, col) in self.manually_edited:
            background = COLORS['GREEN']
            stripe = None
        elif self.contains_special_keyword(text_upper):
            background = COLORS['LIGHT_BLUE']
        elif (row, col) in self.auto_calculated:
            background = "#E6F3FF"

        if self.is_row_flagged(row) and col == 1:
            stripe = COLORS['RED']

        return background, stripe

    def contains_special_keyword(self, text):
        """Check if text contains any special keywords."""
        keywords = [
            "CREDIT MEMO", "CREDIT NOTE", "WARRANTY", "RETURN AUTHORIZATION", "DEFECTIVE", "STATEMENT", "NO CHARGE"
        ]
        return any(keyword in text for keyword in keywords)

    def is_cell_empty(self, row, col):
        return not self.get_cell_text(row, col).strip()

    def is_row_empty(self, row):
        """Check if all data cells in the row are empty."""
        for col in range(1, 9):
            if self.get_cell_text(row, col).strip():
                return False
        return True

    def is_row_complete(self, row):
        """Check if all required fields in the row are filled."""
        # Check data columns (all except Manual Entry and Delete)
        for col in range(1, 9):
            # Skip checking column 3 (PO Number) as it's optional
            if col == 3:
                continue
                
            value = self.get_cell_text(row, col)
            if not value.strip():
                return False
        return True

    def get_cell_text(self, row, col):
        """Safely get the text from a cell."""
        item = self.item(row, col)
        if not item:
            return ""
        if col == 2:
            clean = item.data(Qt.UserRole + 20)
            if clean is not None:
                return str(clean)
        return item.text()

    def update_calculated_field(self, row, col, value, is_auto_calculated=True):
        """Update a cell with a calculated value."""
        # Create the item with the value
        item = QTableWidgetItem(str(value) if value is not None else "")
        
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
        elif (row, col) in self.auto_calculated:
            self.auto_calculated.remove((row, col))

        # Store original value on the item
        item.setData(Qt.UserRole, str(value) if value is not None else "")

        # Reapply coloring for the row
        self.rehighlight_row(row)

    def clear_tracking_data(self):
        """Reset all data tracking mechanisms."""
        # Clear all tracking structures
        self.manually_edited = set()
        self.auto_calculated = set()

    def _normalize_invoice_number(self, text: str) -> str:
        """Normalize invoice number for grouping (trim and uppercase)."""
        return (text or "").strip().upper()

    def update_duplicate_invoice_markers(self):
        """Highlight and tag duplicate invoice numbers.

        Duplicate invoice numbers are grouped and each group is assigned a
        superscript index. The invoice number cells are colored light purple
        and the superscript index is appended to the displayed text.
        """
        if self.columnCount() < 2 or self.rowCount() == 0:
            return

        try:
            self.cellChanged.disconnect(self.handle_cell_changed)
            was_connected = True
        except TypeError:
            was_connected = False

        try:
            invoice_col = 2

            # 1) Build groups
            groups = {}
            for row in range(self.rowCount()):
                inv = self.get_cell_text(row, invoice_col)
                norm = self._normalize_invoice_number(inv)
                if not norm:
                    continue
                groups.setdefault(norm, []).append(row)

        # 2) First, restore original text & coloring on all invoice-number cells
            for row in range(self.rowCount()):
                item = self.item(row, invoice_col)
                if not item:
                    continue
                base_text = item.data(Qt.UserRole + 20)
                if base_text is None:
                    base_text = item.text()
                # Always reset the display text to the base/original (no tags)
                item.setText(str(base_text))
                # Reset background/stripe so our normal highlight pipeline can apply later
                item.setBackground(QColor(COLORS['WHITE']))
                item.setData(Qt.UserRole + 2, None)  # clear stripe color
                item.setData(Qt.UserRole + 20, str(base_text))

            # After clearing the invoice-number cells, reapply row-level coloring
            # so that manual/auto highlights remain before we mark duplicates.
            for r in range(self.rowCount()):
                self.rehighlight_row(r)

            # 3) Apply duplicate markings
            dup_norms = [k for k, rows in groups.items() if len(rows) > 1]
            if not dup_norms:
                self._last_duplicate_groups = {}
                return

            # Assign a stable group index for each duplicate set (1..N)
            dup_norms_sorted = sorted(dup_norms)
            group_index_map = {norm: idx + 1 for idx, norm in enumerate(dup_norms_sorted)}

            # Light purple for duplicates (does not rely on COLORS dict)
            dup_bg = QColor("#F5E6FF")

            for norm, rows in groups.items():
                if len(rows) < 2:
                    continue
                gidx = group_index_map[norm]
                tag = to_superscript(gidx)

                for row in rows:
                    item = self.item(row, invoice_col)
                    if not item:
                        continue
                    # Light purple on invoice number cell
                    item.setBackground(dup_bg)

                    # Append superscript group tag to displayed text
                    clean_text = item.data(Qt.UserRole + 20)
                    if clean_text is None:
                        clean_text = item.text()
                    item.setData(Qt.UserRole + 20, str(clean_text))  # ensure cache is set
                    display = f"{clean_text} {tag}"
                    item.setText(display)

            self._last_duplicate_groups = {k: v[:] for k, v in groups.items() if len(v) > 1}

        finally:
            if was_connected:
                self.cellChanged.connect(self.handle_cell_changed)

    def update_row_by_source(self, file_path: str, row_values: list):
        """Update an existing row based on its file path."""
        abs_target = os.path.abspath(file_path)
        for row in range(self.rowCount()):
            row_path = self.get_file_path_for_row(row)
            if row_path and os.path.abspath(row_path) == abs_target:
                for idx, value in enumerate(row_values):
                    col = idx + 1
                    item = self._create_item(col, value)
                    self.setItem(row, col, item)

                self.highlight_row(row)
                return row
            return -1