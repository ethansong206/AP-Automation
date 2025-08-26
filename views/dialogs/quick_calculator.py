"""
Quick Calculator component for manual entry dialog.
Handles cost calculations and summary display.
"""

from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QFormLayout, QLineEdit, QLabel, QFrame, QHBoxLayout
from PyQt5.QtCore import pyqtSignal
from .currency_utils import CurrencyUtils


class QuickCalculator(QGroupBox):
    """Quick Calculator widget for invoice cost calculations.
    
    Provides input fields for subtotal, discount (% and $), and shipping,
    with a professional cost summary display showing calculated totals.
    """
    
    # Signal emitted when calculations change and form fields should be updated
    calculation_changed = pyqtSignal(dict)  # Emits dict with calculated values
    
    def __init__(self, parent=None):
        super().__init__("Quick Calculator", parent)
        self.currency = CurrencyUtils()
        self._setup_ui()
        
    def _setup_ui(self):
        """Initialize the calculator UI components."""
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 15)
        layout.setSpacing(12)

        # Input fields section
        input_form = QFormLayout()
        input_form.setVerticalSpacing(8)
        input_form.setHorizontalSpacing(12)

        # Create input fields
        self.qc_subtotal = self._create_input_field()
        self.qc_disc_pct = self._create_input_field()   # %
        self.qc_disc_amt = self._create_input_field()   # $
        self.qc_shipping = self._create_input_field()

        input_form.addRow(QLabel("Subtotal:"), self.qc_subtotal)
        input_form.addRow(QLabel("Discount %:"), self.qc_disc_pct)
        input_form.addRow(QLabel("Discount $:"), self.qc_disc_amt)
        input_form.addRow(QLabel("Shipping:"), self.qc_shipping)

        layout.addLayout(input_form)
        layout.addSpacing(15)

        # Professional cost summary
        summary_frame = self._create_summary_frame()
        layout.addWidget(summary_frame)
        
        self.setLayout(layout)

    def _create_input_field(self) -> QLineEdit:
        """Create an input field that triggers recalculation on changes."""
        field = QLineEdit()
        field.textChanged.connect(self._recalculate)
        return field

    def _create_summary_frame(self) -> QFrame:
        """Create the professional cost summary display frame."""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(3)

        # Create summary rows
        self.summary_subtotal_value = QLabel("$0.00")
        self.summary_discount_value = QLabel("$0.00")
        self.summary_inventory_value = QLabel("$0.00")
        self.summary_shipping_value = QLabel("$0.00")
        self.summary_grand_value = QLabel("$0.00")

        # Add rows to layout
        layout.addLayout(self._create_summary_row("Subtotal", self.summary_subtotal_value))
        layout.addLayout(self._create_summary_row("Discount", self.summary_discount_value))
        layout.addWidget(self._create_separator_line("#cccccc"))
        layout.addLayout(self._create_summary_row("Inventory (140-000)", self.summary_inventory_value))
        layout.addLayout(self._create_summary_row("Shipping (520-004)", self.summary_shipping_value))
        layout.addWidget(self._create_separator_line("#cccccc"))
        layout.addLayout(self._create_summary_row("Grand Total", self.summary_grand_value, bold=True))
        layout.addWidget(self._create_separator_line("#000000", height=2))
        
        return frame

    def _create_summary_row(self, label_text: str, value_widget: QLabel, bold: bool = False):
        """Create a summary row with label and value."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        
        label = QLabel(label_text)
        if bold:
            label.setStyleSheet("font-weight: bold;")
            value_widget.setStyleSheet("font-weight: bold;")
        
        row.addWidget(label)
        row.addStretch()
        row.addWidget(value_widget)
        
        return row

    def _create_separator_line(self, color: str = "#cccccc", height: int = 1):
        """Create a horizontal separator line."""
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        line.setStyleSheet(f"color: {color}; background-color: {color}; height: {height}px; border: none; margin: 2px 0px;")
        line.setFixedHeight(height + 4)
        return line

    def _recalculate(self):
        """Perform calculations and update display."""
        # Parse input values
        subtotal = self.currency.parse_money(self.qc_subtotal.text())
        shipping = self.currency.parse_money(self.qc_shipping.text())
        disc_pct = self.currency.parse_percent(self.qc_disc_pct.text())
        disc_amt_input = self.currency.parse_money(self.qc_disc_amt.text())

        # Calculate discount amount
        disc_amt = abs(disc_amt_input) if disc_amt_input is not None else (
            (subtotal * disc_pct) if (subtotal is not None and disc_pct is not None) else 0.0
        )
        if disc_amt is None:
            disc_amt = 0.0

        # Calculate totals
        subtotal_val = subtotal or 0.0
        discount_val = disc_amt
        inventory_val = subtotal_val - discount_val  # Subtotal - Discount
        shipping_val = shipping or 0.0
        grand_total_val = inventory_val + shipping_val

        # Update display
        self.summary_subtotal_value.setText(self.currency.format_money(subtotal_val))
        self.summary_discount_value.setText(self.currency.format_money(discount_val))
        self.summary_inventory_value.setText(self.currency.format_money(inventory_val))
        self.summary_shipping_value.setText(self.currency.format_money(shipping_val))
        self.summary_grand_value.setText(self.currency.format_money(grand_total_val))

        # Emit signal with calculated values
        calc_data = {
            'subtotal': subtotal_val,
            'discount': discount_val,
            'inventory': inventory_val,
            'shipping': shipping_val,
            'grand_total': grand_total_val
        }
        self.calculation_changed.emit(calc_data)

    def clear_fields(self):
        """Clear all input fields and reset summary display."""
        self.qc_subtotal.clear()
        self.qc_disc_pct.clear()
        self.qc_disc_amt.clear()
        self.qc_shipping.clear()
        
        # Reset summary display
        self.summary_subtotal_value.setText("$0.00")
        self.summary_discount_value.setText("$0.00")
        self.summary_inventory_value.setText("$0.00")
        self.summary_shipping_value.setText("$0.00")
        self.summary_grand_value.setText("$0.00")

    def set_values(self, subtotal: str = "", disc_pct: str = "", disc_amt: str = "", shipping: str = ""):
        """Set calculator values programmatically."""
        self.qc_subtotal.setText(subtotal)
        self.qc_disc_pct.setText(disc_pct)
        self.qc_disc_amt.setText(disc_amt)
        self.qc_shipping.setText(shipping)

    def get_values(self) -> dict:
        """Get current calculator input values."""
        return {
            'subtotal': self.qc_subtotal.text().strip(),
            'disc_pct': self.qc_disc_pct.text().strip(),
            'disc_amt': self.qc_disc_amt.text().strip(),
            'shipping': self.qc_shipping.text().strip()
        }

    def has_values(self) -> bool:
        """Check if calculator has any input values."""
        return bool(
            self.qc_subtotal.text().strip() or
            self.qc_disc_pct.text().strip() or
            self.qc_disc_amt.text().strip() or
            self.qc_shipping.text().strip()
        )