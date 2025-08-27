"""
Redesigned Quick Calculator with inline editing for manual entry dialog.
Provides professional financial summary with editable fields and smart calculation logic.
"""

from copy import deepcopy
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
        self.recently_changed = []  # Most recent at index 0

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
        """Check for pending auto-calculation confirmation and show dialog if needed."""
        if not self._pending_confirmation or not self._pending_confirmation.get('needs_confirmation'):
            return False
            
        pending = self._pending_confirmation
        print(f"[QC DEBUG] Showing pending confirmation dialog")
        
        # Show confirmation dialog
        user_accepted = self._show_auto_calculation_confirmation(
            pending['original_total'], 
            pending['calculated_inventory'], 
            pending['subtotal'], 
            pending['discount_pct']
        )
        
        # Block signals during processing
        self._block_all_signals(True)
        
        if user_accepted:
            # User accepted: mark QC as used and set accepted flag
            self._auto_calc_accepted = True
            print(f"[QC DEBUG] User accepted auto-calculation")
            
            # Force recalculation and display update
            self._recalculate()
            
            # Clear pending confirmation and restore signals
            self._pending_confirmation = None
            self._block_all_signals(False)
            
            # Trigger save to persist the changes to the invoice table
            self._trigger_auto_save()
            
        else:
            # User denied: clear discount and reset to original
            print(f"[QC DEBUG] User denied auto-calculation, clearing discount")
            self.discount_pct_field.clear()
            self.discount_amt_field.clear()
            # Keep subtotal as original total
            self.subtotal_field.setText(f"{pending['original_total']:.2f}")
            self._auto_calc_accepted = False
            
            # Force recalculation and display update
            self._recalculate()
            
            # Clear pending confirmation and restore signals
            self._pending_confirmation = None
            self._block_all_signals(False)
        
        return True
    
    def _trigger_auto_save(self):
        """Trigger save to persist auto-calculation changes to the invoice table."""
        if self.dialog_ref and hasattr(self.dialog_ref, 'save_current_invoice'):
            try:
                print(f"[QC DEBUG] Triggering auto-save after auto-calculation acceptance")
                
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
                        print(f"[QC DEBUG] Auto-save completed and invoice table updated")
                
            except Exception as e:
                print(f"[QC DEBUG] Error during auto-save: {e}")
    
    def _block_all_signals(self, block):
        """Block or unblock signals on all QC input fields."""
        print(f"[SYNC DEBUG] _block_all_signals called with block={block}")
        fields = [
            self.subtotal_field, self.discount_pct_field, 
            self.discount_amt_field, self.shipping_field, self.grand_total_field
        ]
        for field in fields:
            if field:
                field.blockSignals(block)
                print(f"[SYNC DEBUG] {field.objectName() or 'unnamed_field'} signals blocked: {field.signalsBlocked()}")
        
    def _connect_signals(self):
        # Subtotal should tell us it changed, so we can resync discounts
        self.subtotal_field.textChanged.connect(lambda: self._on_field_changed('subtotal'))

        self.discount_pct_field.textChanged.connect(lambda: self._on_field_changed('discount_pct'))
        self.discount_amt_field.textChanged.connect(lambda: self._on_field_changed('discount_amt'))
        self.shipping_field.textChanged.connect(lambda: self._on_field_changed('shipping'))
        self.grand_total_field.textChanged.connect(lambda: self._on_field_changed('grand_total'))
        
    def _on_field_changed(self, field_name):
        print(f"[SYNC DEBUG] _on_field_changed called with: '{field_name}'")

        # Debug signal blocking status for discount fields
        if field_name == 'discount_pct':
            print(f"[SYNC DEBUG] discount_pct_field signals blocked: {self.discount_pct_field.signalsBlocked()}")
        elif field_name == 'discount_amt':
            print(f"[SYNC DEBUG] discount_amt_field signals blocked: {self.discount_amt_field.signalsBlocked()}")

        # Record the last discount source to decide which value stays 'authoritative'
        if field_name in ['discount_pct', 'discount_amt']:
            self._last_discount_source = field_name
            print(f"[SYNC DEBUG] _last_discount_source set to: {self._last_discount_source}")

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
        self.recently_changed.insert(0, field_name)
        
        # Keep only last 2 for our priority logic
        if len(self.recently_changed) > 2:
            self.recently_changed.pop()
            
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
        print(f"[SYNC DEBUG] _sync_discount_fields called with: '{changed_field}'")
        
        try:
            subtotal_value = self.currency.parse_money(self.subtotal_field.text()) or 0
            print(f"[SYNC DEBUG] Subtotal value: {subtotal_value}")
            
            # Temporarily block signals to prevent circular updates
            print(f"[SYNC DEBUG] Blocking signals on discount fields")
            self.discount_pct_field.blockSignals(True)
            self.discount_amt_field.blockSignals(True)
            
            if changed_field == 'discount_pct' and subtotal_value > 0:
                # Update $ field based on % field
                pct_text = self.discount_pct_field.text().strip()
                print(f"[SYNC DEBUG] % field text: '{pct_text}', updating $ field")
                if pct_text:
                    try:
                        pct_value = float(pct_text) / 100
                        amt_value = subtotal_value * pct_value
                        print(f"[SYNC DEBUG] Setting $ field to: {amt_value:.2f}")
                        self.discount_amt_field.setText(f"{amt_value:.2f}")
                        print(f"[SYNC DEBUG] $ field now shows: '{self.discount_amt_field.text()}'")
                    except ValueError as e:
                        print(f"[SYNC DEBUG] Error parsing %: {e}")
                        pass
                    
            elif changed_field == 'discount_amt':
                # Update % field based on $ field
                amt_text = self.discount_amt_field.text().strip()
                amt_value = self.currency.parse_money(amt_text) or 0
                amt_value = abs(amt_value)
                print(f"[SYNC DEBUG] $ field text: '{amt_text}', parsed: {amt_value}, updating % field")
                if subtotal_value > 0:
                    pct_value = (amt_value / subtotal_value) * 100
                    print(f"[SYNC DEBUG] Setting % field to: {pct_value:.1f}")
                    self.discount_pct_field.setText(f"{pct_value:.1f}")
                    print(f"[SYNC DEBUG] % field now shows: '{self.discount_pct_field.text()}'")
                else:
                    print(f"[SYNC DEBUG] Cannot sync %, subtotal is 0")

            elif changed_field == 'subtotal':
                # Decide which discount input is authoritative
                last = getattr(self, '_last_discount_source', None)
                print(f"[SYNC DEBUG] Subtotal changed; _last_discount_source={last}")

                if last == 'discount_amt':
                    # Keep $ fixed, recompute % from $
                    amt_text = self.discount_amt_field.text().strip()
                    if amt_text:
                        amt_value = self.currency.parse_money(amt_text) or 0
                        amt_value = abs(amt_value)
                        if subtotal_value > 0:
                            pct_value = (amt_value / subtotal_value) * 100.0
                            print(f"[SYNC DEBUG] Subtotal changed; keeping $, setting % to {pct_value:.1f}")
                            self.discount_pct_field.setText(f"{pct_value:.1f}")
                        else:
                            # If subtotal is 0, percent is undefined—clear it
                            print(f"[SYNC DEBUG] Subtotal is 0; clearing %")
                            self.discount_pct_field.clear()
                    # If $ is blank, do nothing
                else:
                    # Default: keep % fixed, recompute $ from %
                    pct_text = self.discount_pct_field.text().strip()
                    if pct_text:
                        try:
                            pct_value = float(pct_text) / 100.0
                            amt_value = subtotal_value * pct_value
                            print(f"[SYNC DEBUG] Subtotal changed; keeping %, setting $ to {amt_value:.2f}")
                            self.discount_amt_field.setText(f"{amt_value:.2f}")
                        except ValueError as e:
                            print(f"[SYNC DEBUG] Error parsing % on subtotal change: {e}")
                    # If % is blank, do nothing
                    
        except (ValueError, ZeroDivisionError) as e:
            print(f"[SYNC DEBUG] Exception during sync: {e}")
            pass
        finally:
            # Always restore signals
            print(f"[SYNC DEBUG] Restoring signals on discount fields")
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
        
        recent_changes = self.recently_changed[:2]  # Last 2 changed
        
        # Always calculate inventory first (this ensures the key exists)
        values['inventory'] = values['subtotal'] - values['discount']
        
        if len(recent_changes) >= 2:
            changed_set = set(recent_changes)
            
            if changed_set == {'grand_total', 'shipping'}:
                # Calculate inventory = grand_total - shipping
                inventory_calc = values['grand_total'] - values['shipping']
                # Update subtotal and clear discounts to achieve this inventory
                values['subtotal'] = inventory_calc
                values['discount'] = 0
                values['inventory'] = inventory_calc
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
                values['grand_total'] = values['inventory'] + values['shipping']
                self.grand_total_field.blockSignals(True)
                self.grand_total_field.setText(f"{values['grand_total']:.2f}")
                self.grand_total_field.blockSignals(False)
        else:
            # Default behavior: calculate grand_total
            values['grand_total'] = values['inventory'] + values['shipping']
            self.grand_total_field.blockSignals(True)
            self.grand_total_field.setText(f"{values['grand_total']:.2f}")
            self.grand_total_field.blockSignals(False)
        
        return values
        
    def _update_displays(self, values):
        """Update all display labels with calculated values."""
        self.subtotal_display.setText(self.currency.format_money(values['subtotal']))
        self.discount_display.setText(self.currency.format_money(values['discount']))
        self.inventory_display.setText(self.currency.format_money(values['inventory']))
        self.shipping_display.setText(self.currency.format_money(values['shipping']))
        self.grand_total_display.setText(self.currency.format_money(values['grand_total']))
        
    def get_financial_data_for_form(self):
        """Return [Total Amount, Shipping Cost] for form data compatibility."""
        values = self._get_current_values()
        calculated_values = self._calculate_based_on_priority(values)
        return [
            self.currency.format_money(calculated_values['inventory']),  # Total Amount = Inventory
            self.currency.format_money(calculated_values['shipping'])    # Shipping Cost
        ]
        
    def get_data_for_persistence(self):
        """Return QC data for session persistence [subtotal, disc_pct, disc_amt, shipping, flag, save_state]."""
        values = self._get_current_values()
        
        # Get discount percentage
        disc_pct = self.discount_pct_field.text().strip()
        
        # Get save state as JSON string
        import json
        save_state_json = json.dumps(self.get_save_state())
        
        # Determine if QC was actually used (either manually or via auto-calc acceptance)
        qc_was_used = self._auto_calc_accepted or self.is_dirty
        
        return [
            self.currency.format_money(values['subtotal']),
            disc_pct,
            self.currency.format_money(values['discount']),
            self.currency.format_money(values['shipping']),
            "true" if qc_was_used else "false",  # QC used flag
            save_state_json  # New save state field
        ]
        
    def load_or_populate_from_form(self, values_list, current_index, form_fields):
        """Load saved QC state OR auto-populate from form data."""
        if current_index < 0 or current_index >= len(values_list):
            return False
            
        vals = values_list[current_index]
        if len(vals) < 13:
            return False
            
        qc_used = vals[12].lower() == "true" if len(vals) > 12 else False
        
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
            print(f"[QC DEBUG] Starting auto-population. Available fields: {list(form_fields.keys())}")
            
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
            
            # Store auto-population info for later confirmation check
            if auto_populated:
                # Get current values after auto-population
                current_values = self._get_current_values()
                calculated_inventory = current_values['subtotal'] - current_values['discount']
                
                # Get original total amount for comparison
                original_total = 0
                if hasattr(dialog, '_original_total_amount') and dialog._original_total_amount:
                    original_total = self.currency.parse_money(dialog._original_total_amount) or 0
                
                # Store for later confirmation check
                self._pending_confirmation = {
                    'original_total': original_total,
                    'calculated_inventory': calculated_inventory,
                    'subtotal': current_values['subtotal'],
                    'discount_pct': self.discount_pct_field.text().strip(),
                    'needs_confirmation': abs(calculated_inventory - original_total) > 0.01
                }
                print(f"[QC DEBUG] Auto-calc pending confirmation. Original: {original_total}, Calculated: {calculated_inventory}")
            else:
                self._pending_confirmation = None
            
            # Set as clean state after auto-population (and possible confirmation)
            self.set_save_state()
            needs_recalc = True
            
        # Always restore signals at the end
        self._block_all_signals(False)
        
        # Force a recalculation if we auto-populated to ensure displays update
        if needs_recalc:
            self._recalculate()
        
        return needs_recalc
            
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
        print(f"[QC DEBUG] Saving state with deque: {state['recently_changed']}, auto_calc: {state['auto_calc_accepted']}")
        return state
    
    def set_save_state(self, state=None):
        """Set the saved state for dirty tracking."""
        if state is None:
            state = self.get_save_state()
        self.saved_state = state
        self.is_dirty = False
    
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
            
        print(f"[QC DEBUG] Loading state with deque: {state.get('recently_changed', [])}, auto_calc: {state.get('auto_calc_accepted', False)}")
        
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
        if name == 'load_or_populate_from_form':
            print(f"[QC DEBUG] Manager delegating {name} to widget")
        if self.widget:
            return getattr(self.widget, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")