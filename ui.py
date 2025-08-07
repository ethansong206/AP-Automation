"""Main UI components for the AP Automation application."""

# Re-export the main components for easy access
from views.main_window import InvoiceApp
from views.components.pdf_viewer import InteractivePDFViewer
from views.dialogs.vendor_dialog import VendorSelectDialog, VendorDialog
from views.components.date_selection import DateDelegate

# This pattern mirrors how extractor.py works with the extractors package
__all__ = ['InvoiceApp', 'InteractivePDFViewer', 'VendorSelectDialog', 'VendorDialog', 'DateDelegate']