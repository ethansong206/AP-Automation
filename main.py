"""Entry point for the AP Automation application."""
import sys
from PyQt5.QtWidgets import QApplication
from ui import InvoiceApp  # Import from ui.py instead of views directly

def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    invoice_app = InvoiceApp()
    invoice_app.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()