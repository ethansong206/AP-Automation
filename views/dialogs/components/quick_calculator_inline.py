"""
Redesigned Quick Calculator with inline editing for manual entry dialog.
Provides professional financial summary with editable fields and smart calculation logic.
"""

from copy import deepcopy
from collections import deque
from PyQt5.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QLineEdit,
                             QLabel, QFrame, QWidget, QMessageBox)
from PyQt5.QtCore import pyqtSignal, Qt, QTimer
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
        super().__init__("Quick Calculator", parent)
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
        
    def _setup_ui(self):
        """Create the inline editing summary UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 15)
        layout.setSpacing(8)
        
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
                print(f"[ERROR] QC auto-save failed: {e}")
    
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

        print(f"[DEBUG] Field '{field_name}' marked as changed. Priority queue: {list(self.recently_changed)}")
            
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
        return {
            'subtotal': self.currency.parse_money(self.subtotal_field.text()) or 0,
            'discount': abs(discount_value),  # Always positive for subtraction
            'shipping': self.currency.parse_money(self.shipping_field.text()) or 0,
            'grand_total': self.currency.parse_money(self.grand_total_field.text()) or 0
        }
        
    def _calculate_based_on_priority(self, values):
        """Apply priority-based calculation logic for three-way relationship."""
        # Three components: inventory, shipping, grand_total
        # Rule: Last 2 changed determine the third

        recent_changes = list(self.recently_changed)  # Convert deque to list

        # Always calculate inventory first (this ensures the key exists)
        values['inventory'] = values['subtotal'] - values['discount']

        print(f"[DEBUG] Priority calculation: recent_changes={recent_changes}, values={values}")

        if len(recent_changes) >= 2:
            changed_set = set(recent_changes)
            print(f"[DEBUG] Changed set: {changed_set}")

            if changed_set == {'grand_total', 'shipping'}:
                print(f"[DEBUG] Case: grand_total + shipping -> calculate inventory")
                print(f"[DEBUG] Before calc: GT={values['grand_total']}, Shipping={values['shipping']}")
                # Calculate inventory = grand_total - shipping
                inventory_calc = values['grand_total'] - values['shipping']
                print(f"[DEBUG] Calculated inventory: {inventory_calc}")
                # Update subtotal and clear discounts to achieve this inventory
                values['subtotal'] = inventory_calc
                values['discount'] = 0
                values['inventory'] = inventory_calc
                print(f"[DEBUG] After update: subtotal={values['subtotal']}, discount={values['discount']}")
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
                    "RETURN AUTHORIZATION", "DEFECTIVE", "RA FOR CREDIT"
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
        is_credit = self._is_credit_memo()

        print(f"[DEBUG] Override rules: is_credit={is_credit}, values before={values}")

        # Rule 1: Inventory cannot be negative (skip for credit memos)
        if not is_credit and values['inventory'] < 0:
            print(f"[DEBUG] Rule 1 triggered: inventory {values['inventory']} < 0")
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
        if not is_credit and values['shipping'] < 0:
            print(f"[DEBUG] Rule 2 triggered: shipping {values['shipping']} < 0, setting to 0")

            # Make the most recently changed field "win" by adjusting the other field
            recent_changes = list(self.recently_changed)
            if len(recent_changes) >= 1:
                most_recent = recent_changes[0]
                print(f"[DEBUG] Most recent change: {most_recent}, adjusting other field to maintain consistency")

                if most_recent == 'grand_total':
                    # GT was most recently changed, adjust inventory to match GT - 0 shipping
                    values['shipping'] = 0
                    values['inventory'] = values['grand_total']  # Since shipping = 0
                    values['subtotal'] = values['inventory'] + values['discount']

                    # Update UI fields
                    self.shipping_field.blockSignals(True)
                    self.subtotal_field.blockSignals(True)
                    self.shipping_field.setText("0.00")
                    self.subtotal_field.setText(f"{values['subtotal']:.2f}")
                    self.shipping_field.blockSignals(False)
                    self.subtotal_field.blockSignals(False)

                elif most_recent == 'inventory':
                    # Inventory was most recently changed, adjust GT to match inventory + 0 shipping
                    values['shipping'] = 0
                    values['grand_total'] = values['inventory']  # Since shipping = 0

                    # Update UI fields
                    self.shipping_field.blockSignals(True)
                    self.grand_total_field.blockSignals(True)
                    self.shipping_field.setText("0.00")
                    self.grand_total_field.setText(f"{values['grand_total']:.2f}")
                    self.shipping_field.blockSignals(False)
                    self.grand_total_field.blockSignals(False)

                else:
                    # Shipping was most recently changed (shouldn't happen since shipping went negative)
                    # Just set shipping to 0 without other adjustments
                    values['shipping'] = 0
                    self.shipping_field.blockSignals(True)
                    self.shipping_field.setText("0.00")
                    self.shipping_field.blockSignals(False)
            else:
                # No recent changes, just set shipping to 0
                values['shipping'] = 0
                self.shipping_field.blockSignals(True)
                self.shipping_field.setText("0.00")
                self.shipping_field.blockSignals(False)

        print(f"[DEBUG] Override rules complete: values after={values}")
        return values
        
    def _update_displays(self, values):
        """Update all display labels with calculated values."""
        self.subtotal_display.setText(self.currency.format_money(values['subtotal']))
        self.discount_display.setText(self.currency.format_money(values['discount']))
        self.inventory_display.setText(self.currency.format_money(values['inventory']))
        self.shipping_display.setText(self.currency.format_money(values['shipping']))
        self.grand_total_display.setText(self.currency.format_money(values['grand_total']))
        
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
        return [
            self.currency.format_money(calculated_values['inventory']),  # Total Amount = Inventory
            self.currency.format_money(calculated_values['shipping'])    # Shipping Cost
        ]
        
    def get_inventory_for_invoice_table(self):
        """Return current inventory value for updating the invoice table Total column."""
        values = self._get_current_values()
        calculated_values = self._calculate_based_on_priority(values)
        return calculated_values['inventory']
        
    def get_data_for_persistence(self):
        """Return QC data for session persistence [subtotal, disc_pct, disc_amt, shipping, flag, save_state]."""
        values = self._get_current_values()
        calculated_values = self._calculate_based_on_priority(values)
        
        # Get discount percentage
        disc_pct = self.discount_pct_field.text().strip()
        
        # Get save state as JSON string
        import json
        save_state_json = json.dumps(self.get_save_state())
        
        # Determine if QC was actually used (either manually or via auto-calc acceptance)
        qc_was_used = self._auto_calc_accepted or self.is_dirty
        
        return [
            self.currency.format_money(calculated_values['subtotal']),
            disc_pct,
            self.currency.format_money(calculated_values['discount']),
            self.currency.format_money(calculated_values['shipping']),
            "true" if qc_was_used else "false",  # QC used flag
            save_state_json,  # Save state field
            self.currency.format_money(self._original_subtotal),  # Original subtotal
            self.currency.format_money(calculated_values['inventory'])  # Current inventory (for invoice table Total)
        ]
        
    def load_or_populate_from_form(self, values_list, current_index, form_fields):
        """Load saved QC state OR auto-populate from form data."""
        if current_index < 0 or current_index >= len(values_list):
            return False
            
        vals = values_list[current_index]
        if len(vals) < 13:
            return False
            
        qc_used = vals[12].lower() == "true" if len(vals) > 12 else False
        
        # Load original subtotal and saved inventory if available (new format)
        if len(vals) > 14:  # New format with original subtotal
            self._original_subtotal = self.currency.parse_money(vals[14]) or 0
        if len(vals) > 15:  # New format with saved inventory
            self._saved_inventory = self.currency.parse_money(vals[15]) or 0
        
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
            
            # Restore legacy saved QC state
            self.subtotal_field.setText(vals[8])
            self.discount_pct_field.setText(vals[9])  
            self.discount_amt_field.setText(vals[10])
            self.shipping_field.setText(vals[11])
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
            
            # 1. Auto-populate Subtotal from original total amount
            if hasattr(dialog, '_original_total_amount') and dialog._original_total_amount:
                total_text = dialog._original_total_amount.strip()
                if total_text:
                    total_value = self.currency.parse_money(total_text)
                    if total_value is not None and total_value > 0:
                        self.subtotal_field.setText(f"{total_value:.2f}")
                        # Store this as the original subtotal for highlighting comparison
                        self._original_subtotal = total_value
                        # Initial inventory equals subtotal (no discount yet)
                        self._saved_inventory = total_value
                        auto_populated = True
            
            # 2. Auto-populate Shipping from original shipping cost
            if hasattr(dialog, '_original_shipping_cost') and dialog._original_shipping_cost:
                shipping_text = dialog._original_shipping_cost.strip()
                if shipping_text:
                    shipping_value = self.currency.parse_money(shipping_text)
                    if shipping_value is not None and shipping_value > 0:
                        self.shipping_field.setText(f"{shipping_value:.2f}")
                        auto_populated = True
                
            # 3. Discount Terms field -> Discount %
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
            
            # Add auto-populated fields to priority queue for immediate calculation
            if auto_populated:
                # Add fields to priority queue based on what was auto-populated
                # This will trigger two-field calculation when signals are restored

                # Check what was auto-populated and add to priority queue
                # Add inventory first so it gets pushed down when GT is manually entered
                if hasattr(dialog, '_original_total_amount') and dialog._original_total_amount:
                    self._mark_field_changed('inventory')  # subtotal maps to inventory

                if hasattr(dialog, '_original_shipping_cost') and dialog._original_shipping_cost:
                    self._mark_field_changed('shipping')

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
            'subtotal': self.subtotal_field.text(),
            'discount_pct': self.discount_pct_field.text(),
            'discount_amt': self.discount_amt_field.text(),
            'shipping': self.shipping_field.text(),
            'grand_total': self.grand_total_field.text(),
            'recently_changed': self.recently_changed.copy(),
            'auto_calc_accepted': self._auto_calc_accepted
        }
        return state
    
    def set_save_state(self, state=None):
        """Set the saved state for dirty tracking."""
        if state is None:
            state = self.get_save_state()
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
            
        
        # Load field values
        self.subtotal_field.setText(state.get('subtotal', ''))
        self.discount_pct_field.setText(state.get('discount_pct', ''))
        self.discount_amt_field.setText(state.get('discount_amt', ''))
        self.shipping_field.setText(state.get('shipping', ''))
        self.grand_total_field.setText(state.get('grand_total', ''))
        
        # Restore priority queue and auto-calc flag
        self.recently_changed = state.get('recently_changed', []).copy()
        self._auto_calc_accepted = state.get('auto_calc_accepted', False)
        
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