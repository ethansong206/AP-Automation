"""
Redesigned Quick Calculator with inline editing for manual entry dialog.
Provides professional financial summary with editable fields and smart calculation logic.
"""

from copy import deepcopy
from collections import deque
from PyQt5.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QLineEdit,
                             QLabel, QFrame, QWidget, QMessageBox, QPushButton)
from PyQt5.QtCore import pyqtSignal, Qt, QTimer
from logging_config import get_logger

logger = get_logger(__name__)
from PyQt5.QtGui import QFont, QColor, QPalette
from ..utils.currency_utils import CurrencyUtils


class QuickCalculatorInline(QGroupBox):
    """Inline editing Quick Calculator with smart calculation logic.
    
    Features:
    - Professional summary display with inline input fields
    - Priority-based calculation (last 2 changed drives the third)
    - Real-time discount field synchronization
    - Visual feedback for recently changed fields
    """
    
    # Signal emitted when calculations change
    calculation_changed = pyqtSignal(dict)
    
    def __init__(self, parent=None, dialog_ref=None):
        super().__init__("", parent)  # Empty title since we have header
        self.currency = CurrencyUtils()
        
        # Store direct reference to dialog (in case parent gets changed by Qt layouts)
        self.dialog_ref = dialog_ref or parent
        
        # Track original subtotal and saved inventory for highlighting logic
        self._original_subtotal = 0  # The initial auto-populated subtotal value
        self._saved_inventory = 0    # The last saved inventory value for comparison
        
        # Calculate responsive sizes based on screen DPI
        from PyQt5.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            dpi = screen.logicalDotsPerInch()
            self.dpi_scale = dpi / 96.0  # 96 DPI is standard Windows DPI
        else:
            self.dpi_scale = 1.0
            
        # Calculate responsive field widths
        self.label_width = max(140, int(140 * self.dpi_scale))
        self.currency_field_width = max(100, int(100 * self.dpi_scale))
        self.pct_field_width = max(75, int(75 * self.dpi_scale))
        self.display_width = max(100, int(100 * self.dpi_scale))
        self.indicator_width = max(20, int(20 * self.dpi_scale))
        self.pct_label_width = max(15, int(15 * self.dpi_scale))
        
        # Priority queue for tracking field changes
        self.recently_changed = deque(maxlen=2)  # Most recent at index 0

        # Track which discount input (pct or amt) was last edited
        self._last_discount_source = None

        
        # Track when auto-calculation was accepted by user
        self._auto_calc_accepted = False

        # Store pending confirmation data
        self._pending_confirmation = None

        # Track current credit memo status for toggle functionality
        self._is_currently_credit = False

        # Toggle button reference
        self.credit_toggle_button = None

        
        # Field references
        self.subtotal_field = None
        self.discount_pct_field = None
        self.discount_amt_field = None
        self.shipping_field = None
        self.grand_total_field = None
        
        # Display labels
        self.subtotal_display = None
        self.discount_display = None
        self.inventory_display = None
        self.shipping_display = None
        self.grand_total_display = None
        
        # Visual feedback indicators
        self.field_indicators = {}
        
        # Save state tracking for dirty detection
        self.saved_state = {}
        self.is_dirty = False
        
        self._setup_ui()
        self._connect_signals()

        # Initialize credit memo status to false - will be set during load_or_populate_from_form
        self._is_currently_credit = False

        # Initialize toggle button state after UI is created
        self.credit_toggle_button.setChecked(self._is_currently_credit)
        self._update_toggle_button_state()
        
    def _setup_ui(self):
        """Create the inline editing summary UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 15)
        layout.setSpacing(8)

        # Add header with credit toggle button
        self._add_header_with_toggle(layout)
        
        # Subtotal row
        self._add_editable_row(layout, "Subtotal", "subtotal")
        
        # Discount row (with both % and $ fields)
        self._add_discount_row(layout)
        
        # Separator line
        self._add_separator_line(layout)
        
        # Inventory row (calculated, not editable)
        self._add_calculated_row(layout, "Inventory (140-000)", "inventory")
        
        # Shipping row  
        self._add_editable_row(layout, "Shipping (520-004)", "shipping")
        
        # Separator line
        self._add_separator_line(layout)
        
        # Grand Total row
        self._add_editable_row(layout, "Grand Total", "grand_total")
        
        # Final separator (thick black line)
        self._add_thick_separator(layout)
        
        self.setLayout(layout)

    def _add_header_with_toggle(self, layout):
        """Add header row with credit memo toggle button."""
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 5)

        # Title label
        title_label = QLabel("Quick Calculator")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")

        # Credit toggle button with +/- design
        self.credit_toggle_button = QPushButton("+")
        self.credit_toggle_button.setCheckable(True)
        self.credit_toggle_button.setFixedSize(max(50, int(50 * self.dpi_scale)), max(28, int(28 * self.dpi_scale)))
        self.credit_toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #e8f5e8;
                border: 2px solid #4CAF50;
                border-radius: 14px;
                font-size: 16px;
                font-weight: bold;
                color: #2E7D32;
            }
            QPushButton:checked {
                background-color: #ffebee;
                border-color: #f44336;
                color: #c62828;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
                border-width: 3px;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
        """)
        self.credit_toggle_button.clicked.connect(self._on_credit_toggle_clicked)

        header_row.addWidget(title_label)
        header_row.addStretch()  # Push button to the right
        header_row.addWidget(self.credit_toggle_button)

        layout.addLayout(header_row)

    def _on_credit_toggle_clicked(self):
        """Handle credit memo toggle button click."""
        self._is_currently_credit = self.credit_toggle_button.isChecked()
        logger.debug(f"Credit toggle clicked: {self._is_currently_credit}")

        # Update button appearance and recalculate displays
        self._update_toggle_button_state()
        self._recalculate()

    def _update_toggle_button_state(self):
        """Update toggle button appearance based on current state."""
        if self._is_currently_credit:
            self.credit_toggle_button.setText("−")  # Minus symbol for credit memo
            self.credit_toggle_button.setToolTip("Credit Memo Mode - Click to switch to regular invoice")
        else:
            self.credit_toggle_button.setText("+")  # Plus symbol for regular invoice
            self.credit_toggle_button.setToolTip("Regular Invoice Mode - Click to switch to credit memo")

    def _detect_credit_memo_early(self):
        """Early detection of credit memo status before loading values."""
        try:
            # Check dialog reference for discount terms or original extracted values
            if hasattr(self, 'dialog_ref') and self.dialog_ref:
                logger.debug(f"Starting early credit detection...")

                # Method 1: Check current discount terms field (fields dict)
                if hasattr(self.dialog_ref, 'fields') and "Discount Terms" in self.dialog_ref.fields:
                    terms_text = self.dialog_ref.fields["Discount Terms"].text().strip().upper()
                    logger.debug(f"Found discount terms field with text: '{terms_text}'")
                    credit_indicators = [
                        "CREDIT MEMO", "CREDIT NOTE", "PRODUCT RETURN",
                        "RETURN AUTHORIZATION", "DEFECTIVE", "RA FOR CREDIT"
                    ]
                    for indicator in credit_indicators:
                        if indicator in terms_text:
                            logger.debug(f"Early credit detection: Found '{indicator}' in discount terms field")
                            return True

                # Method 2: Check total amount field for negative values
                if hasattr(self.dialog_ref, 'fields') and "Total Amount" in self.dialog_ref.fields:
                    total_text = self.dialog_ref.fields["Total Amount"].text().strip()
                    logger.debug(f"Found total amount field with text: '{total_text}'")
                    if total_text.startswith('-') or total_text.startswith('('):
                        logger.debug(f"Early credit detection: Negative total amount detected")
                        return True
                    # Also try parsing as number
                    try:
                        total_value = float(total_text.replace('$', '').replace(',', '').replace('(', '-').replace(')', ''))
                        if total_value < 0:
                            logger.debug(f" Early credit detection: Parsed negative total amount: {total_value}")
                            return True
                    except ValueError:
                        pass

                logger.debug(f"No credit indicators found, defaulting to regular invoice")

        except Exception as e:
            logger.debug(f"Error in early credit detection: {e}")

        return False

    def _detect_credit_memo_from_data(self, vals, form_fields):
        """Detect credit memo status from row data and form fields (called during load)."""
        try:
            logger.debug(f" Starting credit detection with populated fields...")
            logger.debug(f" Row data - vals[4] (discount terms): '{vals[4] if len(vals) > 4 else 'N/A'}'")
            logger.debug(f" Row data - vals[6] (total amount): '{vals[6] if len(vals) > 6 else 'N/A'}'")

            # Method 1: Check row data discount terms (vals[4])
            if len(vals) > 4 and vals[4]:
                terms_text = vals[4].strip().upper()
                logger.debug(f" Checking row discount terms: '{terms_text}'")
                credit_indicators = [
                    "CREDIT MEMO", "CREDIT NOTE", "PRODUCT RETURN",
                    "RETURN AUTHORIZATION", "DEFECTIVE", "RA FOR CREDIT",
                    "WARRANTY", "WARRANTY CLAIM", "WARRANTY RETURN",
                    "RMA", "RETURN MERCHANDISE", "RETURNED GOODS",
                    "DAMAGE", "DAMAGED GOODS", "REFUND", "CHARGEBACK"
                ]
                for indicator in credit_indicators:
                    if indicator in terms_text:
                        logger.debug(f" Found credit indicator '{indicator}' in row data")
                        return True

            # Method 2: Check populated form fields
            if form_fields and "Discount Terms" in form_fields:
                terms_text = form_fields["Discount Terms"].text().strip().upper()
                logger.debug(f" Checking form discount terms: '{terms_text}'")
                credit_indicators = [
                    "CREDIT MEMO", "CREDIT NOTE", "PRODUCT RETURN",
                    "RETURN AUTHORIZATION", "DEFECTIVE", "RA FOR CREDIT",
                    "WARRANTY", "WARRANTY CLAIM", "WARRANTY RETURN",
                    "RMA", "RETURN MERCHANDISE", "RETURNED GOODS",
                    "DAMAGE", "DAMAGED GOODS", "REFUND", "CHARGEBACK"
                ]
                for indicator in credit_indicators:
                    if indicator in terms_text:
                        logger.debug(f" Found credit indicator '{indicator}' in form fields")
                        return True

            # Method 3: Check for negative total amount in row data (vals[6])
            if len(vals) > 6 and vals[6]:
                total_text = vals[6].strip()
                logger.debug(f" Checking row total amount: '{total_text}'")
                if total_text.startswith('-') or total_text.startswith('('):
                    logger.debug(f" Found negative total amount in row data")
                    return True
                # Parse as number
                try:
                    total_value = float(total_text.replace('$', '').replace(',', '').replace('(', '-').replace(')', ''))
                    if total_value < 0:
                        logger.debug(f" Parsed negative total amount: {total_value}")
                        return True
                except ValueError:
                    pass

            # Method 4: Check populated Total Amount field
            if form_fields and "Total Amount" in form_fields:
                total_text = form_fields["Total Amount"].text().strip()
                logger.debug(f" Checking form total amount: '{total_text}'")
                if total_text.startswith('-') or total_text.startswith('('):
                    logger.debug(f" Found negative total amount in form field")
                    return True

            logger.debug(f" No credit indicators found")

        except Exception as e:
            logger.debug(f" Error in credit detection from data: {e}")

        return False

    def _add_editable_row(self, layout, label_text, field_name):
        """Add a row with label, input field, and display value."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 4, 0, 4)
        
        # Label with consistent width
        label = QLabel(label_text)
        label.setFixedWidth(self.label_width)
        
        # Input field sized for $99,999.99
        input_field = QLineEdit()
        input_field.setFixedWidth(self.currency_field_width)
        input_field.setPlaceholderText("0.00")
        input_field.setStyleSheet("""
            QLineEdit {
                padding: 4px 6px;
                border: 2px solid #E5E7EB;
                border-radius: 4px;
                background: white;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #22C55E;
                outline: none;
            }
        """)
        
        # Add single-click select all functionality
        self._add_select_all_on_click(input_field)
        
        # Visual indicator
        indicator = QLabel("●")
        indicator.setFixedWidth(self.indicator_width)
        indicator.setVisible(False)
        indicator.setStyleSheet("color: #22C55E; font-weight: bold; font-size: 12px;")
        self.field_indicators[field_name] = indicator
        
        # Flexible space with dots
        dots_container = QWidget()
        dots_container.setSizePolicy(dots_container.sizePolicy().Expanding, dots_container.sizePolicy().Fixed)
        dots_layout = QHBoxLayout(dots_container)
        dots_layout.setContentsMargins(5, 0, 5, 0)
        
        dots = QLabel()
        dots.setText("." * 50)  # More dots, will get truncated as needed
        dots.setAlignment(Qt.AlignCenter)
        dots.setStyleSheet("color: #cccccc; font-size: 10px;")
        dots_layout.addWidget(dots)
        
        # Display value - locked to right with consistent width
        display = QLabel("$0.00")
        display.setFixedWidth(self.display_width)
        display.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        display.setStyleSheet("font-weight: bold; font-size: 13px;")
        
        # Store references
        setattr(self, f"{field_name}_field", input_field)
        setattr(self, f"{field_name}_display", display)
        
        # Layout - right-aligned display values
        row.addWidget(label)
        row.addWidget(input_field)
        row.addWidget(indicator)
        row.addWidget(dots_container)  # This expands to fill space
        row.addWidget(display)
        
        layout.addLayout(row)
        
    def _add_discount_row(self, layout):
        """Add discount row with both % and $ input fields."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 4, 0, 4)
        
        # Label with consistent width
        label = QLabel("Discount")
        label.setFixedWidth(self.label_width)
        
        # Percentage field (3 digits: 0-100)
        self.discount_pct_field = QLineEdit()
        self.discount_pct_field.setFixedWidth(self.pct_field_width)
        self.discount_pct_field.setPlaceholderText("0")
        self.discount_pct_field.setStyleSheet("""
            QLineEdit {
                padding: 4px 6px;
                border: 2px solid #E5E7EB;
                border-radius: 4px;
                background: white;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #22C55E;
                outline: none;
            }
        """)
        
        # Add single-click select all functionality
        self._add_select_all_on_click(self.discount_pct_field)
        
        pct_label = QLabel("%")
        pct_label.setFixedWidth(self.pct_label_width)
        
        # Dollar field (for $99,999.99)
        self.discount_amt_field = QLineEdit()
        self.discount_amt_field.setFixedWidth(self.currency_field_width)
        self.discount_amt_field.setPlaceholderText("0.00")
        self.discount_amt_field.setStyleSheet("""
            QLineEdit {
                padding: 4px 6px;
                border: 2px solid #E5E7EB;
                border-radius: 4px;
                background: white;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #22C55E;
                outline: none;
            }
        """)
        
        # Add single-click select all functionality
        self._add_select_all_on_click(self.discount_amt_field)
        
        # Visual indicator
        indicator = QLabel("●")
        indicator.setFixedWidth(self.indicator_width)
        indicator.setVisible(False)
        indicator.setStyleSheet("color: #22C55E; font-weight: bold; font-size: 12px;")
        self.field_indicators["discount"] = indicator
        
        # Flexible space with dots
        dots_container = QWidget()
        dots_container.setSizePolicy(dots_container.sizePolicy().Expanding, dots_container.sizePolicy().Fixed)
        dots_layout = QHBoxLayout(dots_container)
        dots_layout.setContentsMargins(5, 0, 5, 0)
        
        dots = QLabel()
        dots.setText("." * 50)  # More dots, will get truncated as needed
        dots.setAlignment(Qt.AlignCenter)
        dots.setStyleSheet("color: #cccccc; font-size: 10px;")
        dots_layout.addWidget(dots)
        
        # Display value - locked to right with consistent width
        self.discount_display = QLabel("$0.00")
        self.discount_display.setFixedWidth(self.display_width)
        self.discount_display.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.discount_display.setStyleSheet("font-weight: bold; font-size: 13px;")
        
        # Layout - right-aligned display values
        row.addWidget(label)
        row.addWidget(self.discount_pct_field)
        row.addWidget(pct_label)
        row.addWidget(self.discount_amt_field)
        row.addWidget(indicator)
        row.addWidget(dots_container)  # This expands to fill space
        row.addWidget(self.discount_display)
        
        layout.addLayout(row)
        
    def _add_calculated_row(self, layout, label_text, field_name):
        """Add a calculated row (not editable)."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 4, 0, 4)
        
        # Label with consistent width
        label = QLabel(label_text)
        label.setFixedWidth(self.label_width)
        
        # Empty space to align with input fields (no input field here)
        spacer_widget = QWidget()
        spacer_widget.setFixedWidth(self.currency_field_width + self.indicator_width)  # Match total width of input fields + indicator
        
        # Flexible space with dots
        dots_container = QWidget()
        dots_container.setSizePolicy(dots_container.sizePolicy().Expanding, dots_container.sizePolicy().Fixed)
        dots_layout = QHBoxLayout(dots_container)
        dots_layout.setContentsMargins(5, 0, 5, 0)
        
        dots = QLabel()
        dots.setText("." * 50)  # More dots, will get truncated as needed
        dots.setAlignment(Qt.AlignCenter)
        dots.setStyleSheet("color: #cccccc; font-size: 10px;")
        dots_layout.addWidget(dots)
        
        # Display value - locked to right with consistent width
        display = QLabel("$0.00")
        display.setFixedWidth(self.display_width)
        display.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        display.setStyleSheet("font-weight: bold; color: #064420; font-size: 13px;")  # Brand green
        
        # Store reference
        setattr(self, f"{field_name}_display", display)
        
        # Layout - right-aligned display values
        row.addWidget(label)
        row.addWidget(spacer_widget)  # Empty space to match input field layout
        row.addWidget(dots_container)  # This expands to fill space
        row.addWidget(display)
        
        layout.addLayout(row)
        
    def _add_separator_line(self, layout):
        """Add a thin separator line."""
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        line.setStyleSheet("color: #cccccc; background-color: #cccccc; height: 1px;")
        line.setFixedHeight(1)
        layout.addWidget(line)
        
    def _add_thick_separator(self, layout):
        """Add a thick black separator line."""
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        line.setStyleSheet("color: #000000; background-color: #000000; height: 3px;")
        line.setFixedHeight(3)
        layout.addWidget(line)
        
    def _add_select_all_on_click(self, line_edit):
        """Add single-click select all functionality to a QLineEdit."""
        def mousePressEvent(event):
            # Call the original mousePressEvent
            QLineEdit.mousePressEvent(line_edit, event)
            # Then select all text if there's any content
            if line_edit.text():
                line_edit.selectAll()
        
        # Override the mousePressEvent
        line_edit.mousePressEvent = mousePressEvent
    
    def _show_auto_calculation_confirmation(self, original_total, calculated_inventory, subtotal, discount_pct):
        """Show confirmation dialog when auto-calculation results in different inventory amount."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Auto-Calculation Found")
        msg.setIcon(QMessageBox.Question)
        
        # Fix styling - set proper background and text colors
        msg.setStyleSheet("""
            QMessageBox {
                background-color: white;
                color: black;
                border: 1px solid #ccc;
                border-radius: 8px;
            }
            QMessageBox QLabel {
                background-color: transparent;
                color: black;
                padding: 10px;
            }
            QMessageBox QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 8px 16px;
                color: black;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #e0e0e0;
                border-color: #999;
            }
            QMessageBox QPushButton:pressed {
                background-color: #d0d0d0;
            }
            QMessageBox QPushButton:default {
                background-color: #0078d4;
                color: white;
                border-color: #005a9e;
            }
            QMessageBox QPushButton:default:hover {
                background-color: #106ebe;
            }
        """)
        
        # Format the message
        original_formatted = self.currency.format_money(original_total)
        inventory_formatted = self.currency.format_money(calculated_inventory)
        discount_text = f"{discount_pct}%" if discount_pct else "0%"
        
        msg.setText("Quick Calculator found a discount and calculated a new inventory amount.")
        msg.setInformativeText(
            f"Original Total Amount: {original_formatted}\n"
            f"Calculated Inventory (after {discount_text} discount): {inventory_formatted}\n\n"
            f"Would you like to apply this auto-calculation?"
        )
        
        # Custom buttons
        accept_btn = msg.addButton("Apply Calculation", QMessageBox.AcceptRole)
        deny_btn = msg.addButton("Keep Original (Clear Discount)", QMessageBox.RejectRole)
        msg.setDefaultButton(accept_btn)
        
        # Show dialog
        msg.exec_()
        clicked_btn = msg.clickedButton()
        
        return clicked_btn == accept_btn
    
    def check_and_show_pending_confirmation(self):
        """Legacy method - auto-calculations now apply immediately without confirmation."""
        return False  # No confirmation dialogs needed
    
    def _trigger_auto_save(self):
        """Trigger save to persist auto-calculation changes to the invoice table."""
        if self.dialog_ref and hasattr(self.dialog_ref, 'save_current_invoice'):
            try:
                
                # Call the dialog's save methods directly
                self.dialog_ref.save_current_invoice()  # Updates internal values_list
                self.set_save_state()  # Mark QC as clean
                
                # Emit the signal to update the main invoice table
                if (hasattr(self.dialog_ref, 'pdf_paths') and 
                    hasattr(self.dialog_ref, 'values_list') and 
                    hasattr(self.dialog_ref, 'flag_states') and
                    hasattr(self.dialog_ref, 'current_index') and
                    hasattr(self.dialog_ref, 'row_saved')):
                    
                    idx = self.dialog_ref.current_index
                    if (0 <= idx < len(self.dialog_ref.pdf_paths) and
                        0 <= idx < len(self.dialog_ref.values_list) and
                        0 <= idx < len(self.dialog_ref.flag_states)):
                        
                        # Update saved snapshots  
                        if hasattr(self.dialog_ref, 'saved_values_list'):
                            self.dialog_ref.saved_values_list[idx] = deepcopy(self.dialog_ref.values_list[idx])
                        if hasattr(self.dialog_ref, 'saved_flag_states'):
                            self.dialog_ref.saved_flag_states[idx] = self.dialog_ref.flag_states[idx]
                        
                        # Emit signal to update main invoice table
                        self.dialog_ref.row_saved.emit(
                            self.dialog_ref.pdf_paths[idx], 
                            self.dialog_ref.values_list[idx], 
                            self.dialog_ref.flag_states[idx]
                        )
                
            except Exception as e:
                logger.error(f"QC auto-save failed: {e}")
    
    def _block_all_signals(self, block):
        """Block or unblock signals on all QC input fields."""
        fields = [
            self.subtotal_field, self.discount_pct_field,
            self.discount_amt_field, self.shipping_field, self.grand_total_field
        ]
        for field in fields:
            if field:
                field.blockSignals(block)
        
    def _connect_signals(self):
        # Subtotal should tell us it changed, so we can resync discounts
        self.subtotal_field.textChanged.connect(lambda: self._on_field_changed('subtotal'))

        self.discount_pct_field.textChanged.connect(lambda: self._on_field_changed('discount_pct'))
        self.discount_amt_field.textChanged.connect(lambda: self._on_field_changed('discount_amt'))
        self.shipping_field.textChanged.connect(lambda: self._on_field_changed('shipping'))
        self.grand_total_field.textChanged.connect(lambda: self._on_field_changed('grand_total'))


    def _on_field_changed(self, field_name):
        # Record the last discount source to decide which value stays 'authoritative'
        if field_name in ['discount_pct', 'discount_amt']:
            self._last_discount_source = field_name

            # Debounced sync for discount fields themselves
            if hasattr(self, '_sync_timer') and self._sync_timer.isActive():
                self._sync_timer.stop()
            original_field_name = field_name
            self._sync_timer = QTimer()
            self._sync_timer.setSingleShot(True)
            self._sync_timer.timeout.connect(lambda: self._sync_discount_fields(original_field_name))
            self._sync_timer.start(500)

            # For priority queue, both discount inputs map to 'inventory'
            mapped_for_priority = 'inventory'

        elif field_name == 'subtotal':
            # When subtotal changes, re-sync discount based on last_discount_source
            if hasattr(self, '_sync_timer') and self._sync_timer.isActive():
                self._sync_timer.stop()
            original_field_name = field_name
            self._sync_timer = QTimer()
            self._sync_timer.setSingleShot(True)
            self._sync_timer.timeout.connect(lambda: self._sync_discount_fields(original_field_name))
            self._sync_timer.start(500)

            # For priority logic, subtotal affects inventory
            mapped_for_priority = 'inventory'
        else:
            mapped_for_priority = field_name

        # Update priority queue with the final mapped field name
        self._mark_field_changed(mapped_for_priority)

        # Dirty + indicator
        self.is_dirty = True
        self._show_field_indicator(mapped_for_priority)

        # Debounced recalculation for smoother UX
        if hasattr(self, '_calc_timer') and self._calc_timer.isActive():
            self._calc_timer.stop()
        self._calc_timer = QTimer()
        self._calc_timer.setSingleShot(True)
        self._calc_timer.timeout.connect(self._recalculate)
        self._calc_timer.start(100)

        
    def _mark_field_changed(self, field_name):
        """Add field to front of priority queue."""
        if field_name in self.recently_changed:
            self.recently_changed.remove(field_name)
        self.recently_changed.appendleft(field_name)

        logger.debug(f" Field '{field_name}' marked as changed. Priority queue: {list(self.recently_changed)}")
            
    def _show_field_indicator(self, field_name):
        """Show visual indicator for recently changed field."""
        # Map discount fields to single indicator
        indicator_name = 'discount' if field_name in ['discount_pct', 'discount_amt'] else field_name
        
        # Hide all indicators
        for indicator in self.field_indicators.values():
            indicator.setVisible(False)
            
        # Show current field indicator
        if indicator_name in self.field_indicators:
            self.field_indicators[indicator_name].setVisible(True)
            
    def _sync_discount_fields(self, changed_field):
        """Synchronize discount % and $ fields."""
        try:
            subtotal_value = self.currency.parse_money(self.subtotal_field.text()) or 0

            # Temporarily block signals to prevent circular updates
            self.discount_pct_field.blockSignals(True)
            self.discount_amt_field.blockSignals(True)

            if changed_field == 'discount_pct' and subtotal_value > 0:
                # Update $ field based on % field
                pct_text = self.discount_pct_field.text().strip()
                if pct_text:
                    try:
                        pct_value = float(pct_text) / 100
                        amt_value = subtotal_value * pct_value
                        self.discount_amt_field.setText(f"{amt_value:.2f}")
                    except ValueError:
                        pass

            elif changed_field == 'discount_amt':
                # Update % field based on $ field
                amt_text = self.discount_amt_field.text().strip()
                amt_value = self.currency.parse_money(amt_text) or 0
                amt_value = abs(amt_value)
                if subtotal_value > 0:
                    pct_value = (amt_value / subtotal_value) * 100
                    self.discount_pct_field.setText(f"{pct_value:.1f}")

            elif changed_field == 'subtotal':
                # Decide which discount input is authoritative
                last = getattr(self, '_last_discount_source', None)

                if last == 'discount_amt':
                    # Keep $ fixed, recompute % from $
                    amt_text = self.discount_amt_field.text().strip()
                    if amt_text:
                        amt_value = self.currency.parse_money(amt_text) or 0
                        amt_value = abs(amt_value)
                        if subtotal_value > 0:
                            pct_value = (amt_value / subtotal_value) * 100.0
                            self.discount_pct_field.setText(f"{pct_value:.1f}")
                        else:
                            # If subtotal is 0, percent is undefined—clear it
                            self.discount_pct_field.clear()
                    # If $ is blank, do nothing
                else:
                    # Default: keep % fixed, recompute $ from %
                    pct_text = self.discount_pct_field.text().strip()
                    if pct_text:
                        try:
                            pct_value = float(pct_text) / 100.0
                            amt_value = subtotal_value * pct_value
                            self.discount_amt_field.setText(f"{amt_value:.2f}")
                        except ValueError:
                            pass
                    # If % is blank, do nothing

        except (ValueError, ZeroDivisionError):
            pass
        finally:
            # Always restore signals
            self.discount_pct_field.blockSignals(False)
            self.discount_amt_field.blockSignals(False)
            
            # Update displays immediately after sync to reflect changes
            values = self._get_current_values()
            calculated_values = self._calculate_based_on_priority(values)
            self._update_displays(calculated_values)
            
    def _recalculate(self):
        """Recalculate values based on priority queue logic."""
        # Get current values
        values = self._get_current_values()
        
        # Apply priority-based calculation logic
        calculated_values = self._calculate_based_on_priority(values)
        
        # Update displays
        self._update_displays(calculated_values)
        
        # Emit signal for external listeners
        self.calculation_changed.emit(calculated_values)
        
    def _get_current_values(self):
        """Get current field values as floats."""
        # Always use absolute value for discount (subtract positive amount)
        discount_value = self.currency.parse_money(self.discount_amt_field.text()) or 0
        values = {
            'subtotal': self.currency.parse_money(self.subtotal_field.text()) or 0,
            'discount': abs(discount_value),  # Always positive for subtraction
            'shipping': self.currency.parse_money(self.shipping_field.text()) or 0,
            'grand_total': self.currency.parse_money(self.grand_total_field.text()) or 0
        }
        logger.debug(f" _get_current_values: discount_amt_field='{self.discount_amt_field.text()}', discount_pct_field='{self.discount_pct_field.text()}', calculated_discount={values['discount']}")
        return values
        
    def _calculate_based_on_priority(self, values):
        """Apply priority-based calculation logic for three-way relationship."""
        # Three components: inventory, shipping, grand_total
        # Rule: Last 2 changed determine the third

        recent_changes = list(self.recently_changed)  # Convert deque to list

        # Always calculate inventory first (this ensures the key exists)
        values['inventory'] = values['subtotal'] - values['discount']

        logger.debug(f" Priority calculation: recent_changes={recent_changes}, values={values}")

        if len(recent_changes) >= 2:
            changed_set = set(recent_changes)
            logger.debug(f" Changed set: {changed_set}")

            if changed_set == {'grand_total', 'shipping'}:
                logger.debug(f" Case: grand_total + shipping -> calculate inventory")
                logger.debug(f" Before calc: GT={values['grand_total']}, Shipping={values['shipping']}")
                # Calculate inventory = grand_total - shipping
                inventory_calc = values['grand_total'] - values['shipping']
                logger.debug(f" Calculated inventory: {inventory_calc}")
                # Update subtotal and clear discounts to achieve this inventory
                values['subtotal'] = inventory_calc
                values['discount'] = 0
                values['inventory'] = inventory_calc
                logger.debug(f" After update: subtotal={values['subtotal']}, discount={values['discount']}")
                # Update UI fields
                self.subtotal_field.blockSignals(True)
                self.discount_pct_field.blockSignals(True)
                self.discount_amt_field.blockSignals(True)
                self.subtotal_field.setText(f"{inventory_calc:.2f}")
                self.discount_pct_field.setText("")
                self.discount_amt_field.setText("")
                self.subtotal_field.blockSignals(False)
                self.discount_pct_field.blockSignals(False)
                self.discount_amt_field.blockSignals(False)
                
            elif changed_set == {'grand_total', 'inventory'}:
                # Calculate shipping = grand_total - inventory
                values['shipping'] = values['grand_total'] - values['inventory']
                self.shipping_field.blockSignals(True)
                self.shipping_field.setText(f"{values['shipping']:.2f}")
                self.shipping_field.blockSignals(False)
                
            elif changed_set == {'inventory', 'shipping'}:
                # Calculate grand_total = inventory + shipping
                # Only if grand_total isn't the most recently changed field
                if self.recently_changed[0] != 'grand_total':
                    values['grand_total'] = values['inventory'] + values['shipping']
                    self.grand_total_field.blockSignals(True)
                    self.grand_total_field.setText(f"{values['grand_total']:.2f}")
                    self.grand_total_field.blockSignals(False)
        # No else block - only calculate when 2 fields have changed
        
        # Apply GT override rules after all priority-based calculations
        values = self._apply_override_rules(values)
        
        return values

    def _is_credit_memo(self):
        """Check if this is a credit memo based on discount terms."""
        try:
            # Get discount terms from the dialog
            if hasattr(self, 'dialog_ref') and self.dialog_ref:
                # Check if there's a discount terms field
                if hasattr(self.dialog_ref, 'discount_terms_field'):
                    discount_terms = self.dialog_ref.discount_terms_field.text().strip().upper()
                elif hasattr(self.dialog_ref, 'form_fields') and 'Discount Terms' in self.dialog_ref.form_fields:
                    discount_terms = self.dialog_ref.form_fields['Discount Terms'].text().strip().upper()
                else:
                    return False

                # Check for credit memo indicators
                credit_indicators = [
                    "CREDIT MEMO", "CREDIT NOTE", "PRODUCT RETURN",
                    "RETURN AUTHORIZATION", "DEFECTIVE", "RA FOR CREDIT",
                    "WARRANTY", "WARRANTY CLAIM", "WARRANTY RETURN",
                    "RMA", "RETURN MERCHANDISE", "RETURNED GOODS",
                    "DAMAGE", "DAMAGED GOODS", "REFUND", "CHARGEBACK"
                ]

                for indicator in credit_indicators:
                    if indicator in discount_terms:
                        return True

        except Exception:
            pass

        return False

    def _original_is_credit_memo(self):
        """Check if this appears to be a credit memo based on the original total amount."""
        try:
            # Check if the original total amount (from extraction) is negative
            # This indicates it was detected as a credit memo
            if hasattr(self, 'dialog_ref') and self.dialog_ref:
                # Get the original extracted total amount from the dialog
                total_amount_text = self.dialog_ref.total_amount_field.text() if hasattr(self.dialog_ref, 'total_amount_field') else ""
                if total_amount_text.strip():
                    # Remove currency formatting and check if negative
                    cleaned_amount = total_amount_text.replace('$', '').replace(',', '').strip()
                    if cleaned_amount.startswith('-') or cleaned_amount.startswith('('):
                        return True
                    try:
                        amount_value = float(cleaned_amount)
                        if amount_value < 0:
                            return True
                    except ValueError:
                        pass
        except Exception:
            pass
        
        return False
        
    def _apply_override_rules(self, values):
        """Apply override rules to prevent negative inventory, negative shipping, or impossible math."""
        is_credit = self._is_currently_credit

        logger.debug(f" Override rules: is_credit={is_credit}, values before={values}")

        # Rule 1: Inventory cannot be negative (now applies to both regular and credit memos)
        if values['inventory'] < 0:
            logger.debug(f" Rule 1 triggered: inventory {values['inventory']} < 0")
            # Cap discount at subtotal amount to make inventory = 0
            values['discount'] = values['subtotal']
            values['inventory'] = 0

            # Update discount amount field
            self.discount_amt_field.blockSignals(True)
            self.discount_amt_field.setText(f"{values['discount']:.2f}")
            self.discount_amt_field.blockSignals(False)

            # Update discount percentage field if subtotal > 0
            if values['subtotal'] > 0:
                pct_value = (values['discount'] / values['subtotal']) * 100
                self.discount_pct_field.blockSignals(True)
                self.discount_pct_field.setText(f"{pct_value:.1f}")
                self.discount_pct_field.blockSignals(False)

        # Rule 2: Shipping should never be negative (only for regular invoices)
        # Note: Credit memos use absolute values in input fields now, so negative shipping shouldn't occur
        if not is_credit and values['shipping'] < 0:
            logger.debug(f" Rule 2 triggered: shipping {values['shipping']} < 0, setting to 0")
            values['shipping'] = 0
            self.shipping_field.blockSignals(True)
            self.shipping_field.setText("0.00")
            self.shipping_field.blockSignals(False)

        logger.debug(f" Override rules complete: values after={values}")
        return values
        
    def _update_displays(self, values):
        """Update all display labels with calculated values."""
        # Use toggle state for credit memo formatting
        multiplier = -1 if self._is_currently_credit else 1

        # Apply negative formatting for credit memos while keeping input fields positive
        self.subtotal_display.setText(self.currency.format_money(values['subtotal'] * multiplier))
        self.discount_display.setText(self.currency.format_money(values['discount'] * multiplier))
        self.inventory_display.setText(self.currency.format_money(values['inventory'] * multiplier))
        self.shipping_display.setText(self.currency.format_money(values['shipping'] * multiplier))
        self.grand_total_display.setText(self.currency.format_money(values['grand_total'] * multiplier))
        
        # Apply inventory highlighting based on comparison with saved value
        current_inventory = values['inventory']
        should_highlight = abs(current_inventory - self._saved_inventory) > 0.01
        
        if should_highlight:
            # More visible green background to indicate changed inventory
            self.inventory_display.setStyleSheet("""
                font-weight: bold; 
                font-size: 13px; 
                background-color: #D4F4D4; 
                padding: 2px 4px; 
                border-radius: 3px;
                border: 1px solid #A8D8A8;
            """)
            self.inventory_display.setToolTip(f"Inventory changed from saved value (${self._saved_inventory:.2f})")
        else:
            # Reset to default styling
            self.inventory_display.setStyleSheet("font-weight: bold; font-size: 13px;")
            self.inventory_display.setToolTip("")
        
    def get_financial_data_for_form(self):
        """Return [Total Amount, Shipping Cost] for form data compatibility."""
        values = self._get_current_values()
        calculated_values = self._calculate_based_on_priority(values)

        # Apply negative multiplier for credit memos
        multiplier = -1 if self._is_currently_credit else 1

        return [
            self.currency.format_money(calculated_values['inventory'] * multiplier),  # Total Amount = Inventory
            self.currency.format_money(calculated_values['shipping'] * multiplier)    # Shipping Cost
        ]
        
    def get_inventory_for_invoice_table(self):
        """Return current inventory value for updating the invoice table Total column."""
        values = self._get_current_values()
        calculated_values = self._calculate_based_on_priority(values)

        # Apply negative multiplier for credit memos
        multiplier = -1 if self._is_currently_credit else 1

        return calculated_values['inventory'] * multiplier
        
    def get_data_for_persistence(self):
        """Return QC data for session persistence [subtotal, disc_pct, disc_amt, shipping, flag, save_state]."""
        values = self._get_current_values()
        calculated_values = self._calculate_based_on_priority(values)

        # Apply negative multiplier for credit memos
        multiplier = -1 if self._is_currently_credit else 1

        # Get discount percentage
        disc_pct = self.discount_pct_field.text().strip()

        # Get save state as JSON string
        import json
        save_state_json = json.dumps(self.get_save_state())

        # Determine if QC was actually used (either manually or via auto-calc acceptance)
        qc_was_used = self._auto_calc_accepted or self.is_dirty

        return [
            self.currency.format_money(calculated_values['subtotal'] * multiplier),
            disc_pct,
            self.currency.format_money(calculated_values['discount'] * multiplier),
            self.currency.format_money(calculated_values['shipping'] * multiplier),
            "true" if qc_was_used else "false",  # QC used flag
            save_state_json,  # Save state field
            self.currency.format_money(self._original_subtotal * multiplier),  # Original subtotal
            self.currency.format_money(calculated_values['inventory'] * multiplier)  # Current inventory (for invoice table Total)
        ]
        
    def load_or_populate_from_form(self, values_list, current_index, form_fields):
        """Load saved QC state OR auto-populate from form data."""
        if current_index < 0 or current_index >= len(values_list):
            return False

        vals = values_list[current_index]
        if len(vals) < 13:
            return False

        # NOW detect credit memo status - fields should be populated by this point
        previous_credit_status = self._is_currently_credit
        self._is_currently_credit = self._detect_credit_memo_from_data(vals, form_fields)

        # Update toggle button if status changed
        if previous_credit_status != self._is_currently_credit:
            self.credit_toggle_button.setChecked(self._is_currently_credit)
            self._update_toggle_button_state()
            logger.debug(f" Credit status updated during load: {previous_credit_status} -> {self._is_currently_credit}")

        qc_used = vals[12].lower() == "true" if len(vals) > 12 else False
        
        # Load original subtotal and saved inventory if available (new format)
        # Backward compatibility: these fields may not exist in old save states
        if len(vals) > 14:  # New format with original subtotal
            try:
                self._original_subtotal = self.currency.parse_money(vals[14]) or 0
                logger.debug(f" Loaded original_subtotal from vals[14]: {vals[14]}")
            except (IndexError, ValueError) as e:
                self._original_subtotal = 0
                logger.debug(f" Could not load original_subtotal, using 0: {e}")
        else:
            self._original_subtotal = 0
            logger.debug(f" vals length {len(vals)} < 15, no original_subtotal available")

        if len(vals) > 15:  # New format with saved inventory
            try:
                self._saved_inventory = self.currency.parse_money(vals[15]) or 0
                logger.debug(f" Loaded saved_inventory from vals[15]: {vals[15]}")
            except (IndexError, ValueError) as e:
                self._saved_inventory = 0
                logger.debug(f" Could not load saved_inventory, using 0: {e}")
        else:
            self._saved_inventory = 0
            logger.debug(f" vals length {len(vals)} < 16, no saved_inventory available")
        
        # Block signals during auto-population to prevent interference
        self._block_all_signals(True)
        
        if qc_used:
            # Check for new save state format (includes deque)
            if len(vals) > 13 and vals[13]:  # New format with save state
                try:
                    import json
                    save_state = json.loads(vals[13])
                    self.load_from_state(save_state)
                    return True  # Force recalculation to update displays
                except (json.JSONDecodeError, IndexError):
                    pass  # Fall back to legacy format
            
            # Restore legacy saved QC state (use absolute values for credit memos)
            subtotal_val = self.currency.parse_money(vals[8]) or 0
            discount_amt_val = self.currency.parse_money(vals[10]) or 0
            shipping_val = self.currency.parse_money(vals[11]) or 0

            if self._is_currently_credit:
                # For credit memos, use absolute values in input fields
                self.subtotal_field.setText(f"{abs(subtotal_val):.2f}")
                self.discount_amt_field.setText(f"{abs(discount_amt_val):.2f}")
                self.shipping_field.setText(f"{abs(shipping_val):.2f}")
                logger.debug(f" Loading credit memo with absolute values: subtotal={abs(subtotal_val)}, shipping={abs(shipping_val)}")
            else:
                # For regular invoices, use values as-is
                self.subtotal_field.setText(vals[8])
                self.discount_amt_field.setText(vals[10])
                self.shipping_field.setText(vals[11])

            self.discount_pct_field.setText(vals[9])

            # Calculate and set grand total
            values = self._get_current_values()
            grand_total = values['subtotal'] - values['discount'] + values['shipping']
            self.grand_total_field.setText(f"{grand_total:.2f}")
            # Set as saved state for new tracking
            self.set_save_state()
            needs_recalc = True  # Force recalculation to update displays
        else:
            # Auto-populate from form fields
            
            # Get dialog reference to access original values
            dialog = self.dialog_ref
            auto_populated = False
            
            # 1. Enhanced auto-population using extractor calculation data
            enhanced_data = None
            total_value = None
            discount_percentage = None
            discount_dollar = None
            extraction_handled_discount = False
            enhanced_data_used = False

            # Try to get enhanced total amount data by re-extracting from the document
            enhanced_data = None
            try:
                # Get the file path for the current invoice
                if hasattr(dialog, 'pdf_paths') and hasattr(dialog, 'current_index'):
                    current_file = dialog.pdf_paths[dialog.current_index]

                    # Re-extract the document to get enhanced data
                    from pdf_reader import extract_text_data_from_pdfs
                    from extractors.total_amount import extract_total_amount

                    text_blocks = extract_text_data_from_pdfs([current_file])
                    if text_blocks and len(text_blocks) > 0:
                        words = text_blocks[0]["words"]
                        # Get vendor name from the dialog
                        vendor_name = ""
                        if hasattr(dialog, 'vendor_combo') and dialog.vendor_combo:
                            vendor_name = dialog.vendor_combo.currentText().strip()
                        enhanced_data = extract_total_amount(words, vendor_name)
                        logger.debug(f" Re-extracted enhanced data for QC: {enhanced_data}")
            except Exception as e:
                logger.debug(f" Failed to re-extract enhanced data: {e}")
                enhanced_data = None

            # If enhanced data is available, use it for intelligent population
            if enhanced_data and isinstance(enhanced_data, dict):
                total_amount = enhanced_data.get('total_amount', '')
                calculation_method = enhanced_data.get('calculation_method', 'none')
                discount_type = enhanced_data.get('discount_type', 'none')
                discount_value = enhanced_data.get('discount_value')
                pre_discount_amount = enhanced_data.get('pre_discount_amount')
                has_calculation = enhanced_data.get('has_calculation', False)

                logger.debug(f" Using enhanced extraction data: method={calculation_method}, discount_type={discount_type}, has_calculation={has_calculation}")

                if total_amount:
                    total_value = self.currency.parse_money(total_amount)
                    enhanced_data_used = True

                    # If extractor already handled discount calculations, use those results
                    if has_calculation and discount_type == 'percentage' and discount_value:
                        discount_percentage = float(discount_value)
                        # total_value is the final post-discount amount (inventory)
                        extraction_handled_discount = True
                        logger.debug(f" Extractor handled percentage discount: {discount_percentage}%")
                    elif has_calculation and discount_type == 'dollar' and discount_value:
                        discount_dollar = self.currency.parse_money(discount_value)
                        # total_value is the final post-discount amount (inventory)
                        extraction_handled_discount = True
                        logger.debug(f" Extractor handled dollar discount: ${discount_dollar}")
                    else:
                        # Extractor did not handle discounts, total_value is pre-discount subtotal
                        extraction_handled_discount = False
                        logger.debug(f" Extractor did not handle discounts, total_value is subtotal")

            # Do NOT extract discount information from form fields
            # Only use discount information from enhanced total data
            # The discount terms field is for reference only and doesn't indicate
            # whether discounts should be applied to calculations

            # Fallback to old method if enhanced data not available
            if total_value is None:
                # First try row data vals[6] (Total Amount)
                if len(vals) > 6 and vals[6]:
                    total_text = vals[6].strip()
                    logger.debug(f" Auto-populating from row data vals[6]: '{total_text}'")
                    if total_text:
                        total_value = self.currency.parse_money(total_text)

                # Fallback to dialog's original total amount if row data not available
                if total_value is None and hasattr(dialog, '_original_total_amount') and dialog._original_total_amount:
                    total_text = dialog._original_total_amount.strip()
                    logger.debug(f" Auto-populating from dialog original: '{total_text}'")
                    if total_text:
                        total_value = self.currency.parse_money(total_text)

            # Populate QC fields using appropriate calculation approach
            if total_value is not None and total_value != 0:
                # Use absolute value for all calculations and displays
                abs_total_value = abs(total_value)

                if discount_percentage:
                    if extraction_handled_discount:
                        # Backward calculation: use enhanced data directly
                        # We have: pre_discount_amount (subtotal) and final inventory amount
                        if enhanced_data and enhanced_data.get('pre_discount_amount'):
                            # Use the pre-discount amount as subtotal from enhanced data
                            subtotal_from_enhanced = self.currency.parse_money(enhanced_data.get('pre_discount_amount'))
                            discount_dollar_amount = subtotal_from_enhanced - abs_total_value

                            self.subtotal_field.setText(f"{subtotal_from_enhanced:.2f}")
                            self.discount_pct_field.setText(f"{discount_percentage:.1f}")
                            self.discount_amt_field.setText(f"{discount_dollar_amount:.2f}")
                            logger.debug(f" Enhanced backward calculation: subtotal=${subtotal_from_enhanced:.2f}, discount={discount_percentage}%=${discount_dollar_amount:.2f}, inventory=${abs_total_value:.2f}")

                            self._original_subtotal = subtotal_from_enhanced
                            self._saved_inventory = abs_total_value
                        else:
                            # Fallback: calculate subtotal from inventory and discount rate
                            discount_rate = discount_percentage / 100.0
                            calculated_subtotal = abs_total_value / (1.0 - discount_rate)
                            discount_dollar_amount = calculated_subtotal - abs_total_value

                            self.subtotal_field.setText(f"{calculated_subtotal:.2f}")
                            self.discount_pct_field.setText(f"{discount_percentage:.1f}")
                            self.discount_amt_field.setText(f"{discount_dollar_amount:.2f}")
                            logger.debug(f" Calculated backward calculation: inventory=${abs_total_value:.2f}, discount={discount_percentage}%=${discount_dollar_amount:.2f}, subtotal=${calculated_subtotal:.2f}")

                            self._original_subtotal = calculated_subtotal
                            self._saved_inventory = abs_total_value
                    else:
                        # Forward calculation: total_value is subtotal, apply discount to get inventory
                        # subtotal = total_value, inventory = subtotal * (1 - discount_rate)
                        discount_rate = discount_percentage / 100.0
                        calculated_inventory = abs_total_value * (1.0 - discount_rate)

                        self.subtotal_field.setText(f"{abs_total_value:.2f}")
                        self.discount_pct_field.setText(f"{discount_percentage:.1f}")
                        logger.debug(f" Forward calculation: subtotal=${abs_total_value:.2f}, discount={discount_percentage}%, inventory=${calculated_inventory:.2f}")

                        self._original_subtotal = abs_total_value
                        self._saved_inventory = calculated_inventory

                elif discount_dollar:
                    if extraction_handled_discount:
                        # Backward calculation: total_value is final inventory
                        # subtotal = inventory + discount_dollar
                        calculated_subtotal = abs_total_value + discount_dollar

                        self.subtotal_field.setText(f"{calculated_subtotal:.2f}")
                        self.discount_amt_field.setText(f"{discount_dollar:.2f}")
                        logger.debug(f" Backward dollar discount: inventory=${abs_total_value:.2f}, discount=${discount_dollar:.2f}, subtotal=${calculated_subtotal:.2f}")

                        self._original_subtotal = calculated_subtotal
                        self._saved_inventory = abs_total_value
                    else:
                        # Forward calculation: total_value is subtotal
                        # inventory = subtotal - discount_dollar
                        calculated_inventory = abs_total_value - discount_dollar

                        self.subtotal_field.setText(f"{abs_total_value:.2f}")
                        self.discount_amt_field.setText(f"{discount_dollar:.2f}")
                        logger.debug(f" Forward dollar discount: subtotal=${abs_total_value:.2f}, discount=${discount_dollar:.2f}, inventory=${calculated_inventory:.2f}")

                        self._original_subtotal = abs_total_value
                        self._saved_inventory = calculated_inventory

                else:
                    # No discount found: subtotal = total_value, clear all discount fields
                    self.subtotal_field.setText(f"{abs_total_value:.2f}")

                    # Stop any running sync timers
                    if hasattr(self, '_sync_timer') and self._sync_timer.isActive():
                        self._sync_timer.stop()
                        logger.debug(f" Stopped running sync timer")

                    # Clear discount fields with signals blocked to prevent sync
                    self.discount_pct_field.blockSignals(True)
                    self.discount_amt_field.blockSignals(True)
                    self.discount_pct_field.setText("")
                    self.discount_amt_field.setText("")
                    self.discount_pct_field.blockSignals(False)
                    self.discount_amt_field.blockSignals(False)

                    # Clear the last discount source to prevent any sync mechanisms
                    self._last_discount_source = None

                    logger.debug(f" No discount: subtotal=${abs_total_value:.2f}, cleared discount fields and sync source")
                    logger.debug(f" After clearing - discount_amt_field='{self.discount_amt_field.text()}', discount_pct_field='{self.discount_pct_field.text()}'")

                    self._original_subtotal = abs_total_value
                    self._saved_inventory = abs_total_value

                auto_populated = True
            
            # 2. Auto-populate Shipping from row data or dialog's original shipping cost
            shipping_value = None

            # First try row data vals[7] (Shipping Cost)
            if len(vals) > 7 and vals[7]:
                shipping_text = vals[7].strip()
                logger.debug(f" Auto-populating shipping from row data vals[7]: '{shipping_text}'")
                if shipping_text:
                    shipping_value = self.currency.parse_money(shipping_text)

            # Fallback to dialog's original shipping cost
            if shipping_value is None and hasattr(dialog, '_original_shipping_cost') and dialog._original_shipping_cost:
                shipping_text = dialog._original_shipping_cost.strip()
                logger.debug(f" Auto-populating shipping from dialog original: '{shipping_text}'")
                if shipping_text:
                    shipping_value = self.currency.parse_money(shipping_text)

            # Populate shipping field (use absolute value for display)
            if shipping_value is not None:
                display_value = abs(shipping_value)
                self.shipping_field.setText(f"{display_value:.2f}")
                auto_populated = True
                logger.debug(f" Populated shipping field with {display_value:.2f} (original was {shipping_value})")
                
            # 3. Discount Terms field -> Discount % (only if enhanced data wasn't used)
            if not enhanced_data_used:
                discount_terms = form_fields.get("Discount Terms")
                if discount_terms:
                    terms_text = discount_terms.text().strip()
                    if terms_text:
                        terms = terms_text.lower()
                        import re
                        pct_match = re.search(r'(\d+(?:\.\d+)?)%', terms)
                        if pct_match:
                            discount_pct = pct_match.group(1)
                            self.discount_pct_field.setText(discount_pct)

                            # Auto-calculate discount $ amount based on subtotal and %
                            if hasattr(dialog, '_original_total_amount') and dialog._original_total_amount:
                                subtotal_val = self.currency.parse_money(dialog._original_total_amount) or 0
                                if subtotal_val > 0:
                                    discount_amt = subtotal_val * (float(discount_pct) / 100)
                                    self.discount_amt_field.setText(f"{discount_amt:.2f}")
                                    auto_populated = True
                                    logger.debug(f" Fallback auto-populated discount: {discount_pct}% = ${discount_amt:.2f}")
            else:
                logger.debug(f" Skipping fallback discount auto-population - enhanced data was used")
            
            # Add auto-populated fields to priority queue for immediate calculation
            if auto_populated:
                # Add fields to priority queue based on what was auto-populated
                # This will trigger two-field calculation when signals are restored

                logger.debug(f" Auto-population occurred, setting up priority queue...")

                # Check what was auto-populated and add to priority queue
                # Add inventory first so it gets pushed down when GT is manually entered
                if total_value is not None and total_value != 0:
                    self._mark_field_changed('inventory')  # subtotal maps to inventory
                    logger.debug(f" Added 'inventory' to priority queue due to subtotal auto-population")

                if shipping_value is not None:
                    self._mark_field_changed('shipping')
                    logger.debug(f" Added 'shipping' to priority queue due to shipping auto-population")

                logger.debug(f" Priority queue after auto-population: {list(self.recently_changed)}")

                # Check if discount was auto-calculated
                current_values = self._get_current_values()
                if current_values['discount'] > 0:
                    # Auto-calculation occurred, mark as accepted and trigger dirty state
                    self._auto_calc_accepted = True
                    self.is_dirty = True
                else:
                    # Only auto-population occurred (no calculations), can set clean state
                    self.set_save_state()

            # No confirmation popup needed
            self._pending_confirmation = None
            needs_recalc = True
            
        # Always restore signals at the end
        self._block_all_signals(False)
        
        # Force a recalculation if we auto-populated to ensure displays update
        if needs_recalc:
            self._recalculate()
        
        return needs_recalc
            
    def _recalculate(self):
        """Perform recalculation and update displays."""
        values = self._get_current_values()
        calculated_values = self._calculate_based_on_priority(values)
        self._update_displays(calculated_values)
        
    def recalculate_and_update_fields(self, during_auto_population=False):
        """Trigger recalculation."""
        self._recalculate()
        
    def clear_fields(self):
        """Clear all input fields."""
        self.subtotal_field.clear()
        self.discount_pct_field.clear()
        self.discount_amt_field.clear()
        self.shipping_field.clear()
        self.grand_total_field.clear()
        
        # Hide all indicators
        for indicator in self.field_indicators.values():
            indicator.setVisible(False)
            
        # Clear priority queue
        self.recently_changed.clear()
        
        # Reset auto-calc accepted flag and pending confirmation
        self._auto_calc_accepted = False
        self._pending_confirmation = None
        
        # Reset tracking values
        self._original_subtotal = 0
        self._saved_inventory = 0
        
        # Reset displays
        self._update_displays({
            'subtotal': 0, 'discount': 0, 'inventory': 0, 
            'shipping': 0, 'grand_total': 0
        })
        
    def add_to_field_order(self, field_order):
        """Add QC fields to navigation order."""
        qc_fields = [
            self.subtotal_field,
            self.discount_pct_field,
            self.discount_amt_field, 
            self.shipping_field,
            self.grand_total_field
        ]
        return field_order + qc_fields
        
    def apply_styles(self, input_field_style):
        """Apply consistent styling to input fields."""
        qc_fields = [
            self.subtotal_field, self.discount_pct_field, 
            self.discount_amt_field, self.shipping_field, self.grand_total_field
        ]
        for field in qc_fields:
            field.setStyleSheet(input_field_style)
            
    def get_currency_fields(self):
        """Return QC currency fields for formatting."""
        return [
            self.subtotal_field, self.discount_amt_field, 
            self.shipping_field, self.grand_total_field
        ]
    
    def get_save_state(self):
        """Get current state for save tracking."""
        state = {
            # Version for future compatibility
            'version': '1.1',

            # Field values
            'subtotal': self.subtotal_field.text(),
            'discount_pct': self.discount_pct_field.text(),
            'discount_amt': self.discount_amt_field.text(),
            'shipping': self.shipping_field.text(),
            'grand_total': self.grand_total_field.text(),

            # Internal state
            'recently_changed': list(self.recently_changed),  # Convert deque to list for JSON serialization
            'auto_calc_accepted': self._auto_calc_accepted,
            'is_currently_credit': getattr(self, '_is_currently_credit', False),

            # Metadata for debugging/future use
            'saved_timestamp': __import__('time').time(),
            'original_subtotal': getattr(self, '_original_subtotal', 0),
            'saved_inventory': getattr(self, '_saved_inventory', 0)
        }
        logger.debug(f" Saving priority queue to state: {list(self.recently_changed)}")
        logger.debug(f" Saving state version: {state['version']} with credit status: {state['is_currently_credit']}")
        return state
    
    def set_save_state(self, state=None):
        """Set the saved state for dirty tracking."""
        if state is None:
            state = self.get_save_state()
        # Ensure recently_changed is stored as list for consistency
        if 'recently_changed' in state and not isinstance(state['recently_changed'], list):
            state = state.copy()
            state['recently_changed'] = list(state['recently_changed'])
        self.saved_state = state
        self.is_dirty = False
        
        # Update saved inventory to current value (highlighting will disappear)
        current_values = self._get_current_values()
        calculated_values = self._calculate_based_on_priority(current_values)
        self._saved_inventory = calculated_values['inventory']
    
    def check_if_dirty(self):
        """Check if current state differs from saved state."""
        current_state = self.get_save_state()
        # Compare without the recently_changed queue for basic dirty check
        current_values = {k: v for k, v in current_state.items() if k != 'recently_changed'}
        saved_values = {k: v for k, v in self.saved_state.items() if k != 'recently_changed'}
        return current_values != saved_values
    
    def load_from_state(self, state):
        """Load QC from saved state including deque."""
        if not state:
            return

        # Check version for compatibility
        version = state.get('version', '1.0')  # Default to 1.0 for old states
        logger.debug(f" Loading save state version: {version}")

        
        # Load field values (use absolute values for credit memos)
        subtotal_text = state.get('subtotal', '')
        discount_amt_text = state.get('discount_amt', '')
        shipping_text = state.get('shipping', '')
        grand_total_text = state.get('grand_total', '')

        # Handle credit memo loading with backward compatibility
        is_credit_from_state = state.get('is_currently_credit', None)
        current_is_credit = self._is_currently_credit

        # For backward compatibility: if old state doesn't have credit flag, use current detection
        is_credit = is_credit_from_state if is_credit_from_state is not None else current_is_credit

        if is_credit:
            # For credit memos, use absolute values in input fields
            subtotal_val = self.currency.parse_money(subtotal_text) or 0
            discount_amt_val = self.currency.parse_money(discount_amt_text) or 0
            shipping_val = self.currency.parse_money(shipping_text) or 0
            grand_total_val = self.currency.parse_money(grand_total_text) or 0

            self.subtotal_field.setText(f"{abs(subtotal_val):.2f}" if subtotal_val != 0 else "")
            self.discount_amt_field.setText(f"{abs(discount_amt_val):.2f}" if discount_amt_val != 0 else "")
            self.shipping_field.setText(f"{abs(shipping_val):.2f}" if shipping_val != 0 else "")
            self.grand_total_field.setText(f"{abs(grand_total_val):.2f}" if grand_total_val != 0 else "")
            logger.debug(f" Loading credit memo state with absolute values: subtotal={abs(subtotal_val)}, shipping={abs(shipping_val)}")
        else:
            # For regular invoices, use values as-is
            self.subtotal_field.setText(subtotal_text)
            self.discount_amt_field.setText(discount_amt_text)
            self.shipping_field.setText(shipping_text)
            self.grand_total_field.setText(grand_total_text)

        self.discount_pct_field.setText(state.get('discount_pct', ''))
        
        # Restore priority queue and auto-calc flag with backward compatibility
        recently_changed_list = state.get('recently_changed', [])
        self.recently_changed = deque(recently_changed_list, maxlen=2)  # Convert list back to deque
        self._auto_calc_accepted = state.get('auto_calc_accepted', False)

        # Backward compatibility: old save states won't have is_currently_credit
        if 'is_currently_credit' in state:
            self._is_currently_credit = state.get('is_currently_credit', False)
        # If not in state, keep the current detected value (don't overwrite)

        logger.debug(f" Restored priority queue from state: {list(self.recently_changed)}")
        logger.debug(f" Credit status from state: {state.get('is_currently_credit', 'NOT_IN_STATE')} (current: {self._is_currently_credit})")
        
        # Update displays with current values
        values = self._get_current_values()
        calculated_values = self._calculate_based_on_priority(values)
        self._update_displays(calculated_values)
        
        # Set as saved state and mark clean
        self.set_save_state(state)


# Manager class for compatibility with existing code
class QuickCalculatorManager:
    """Manager class that creates and manages the inline QC widget."""
    
    def __init__(self, parent):
        self.parent = parent
        self.widget = None
        
    def create_widget(self):
        """Create and return the QC widget."""
        self.widget = QuickCalculatorInline(self.parent, dialog_ref=self.parent)
        return self.widget
        
    def __getattr__(self, name):
        """Delegate all other calls to the widget."""
        if self.widget:
            return getattr(self.widget, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")