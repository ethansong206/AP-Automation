"""Invoice data model."""

class Invoice:
    """Data model for an invoice."""
    
    def __init__(self, 
                 vendor_name="", 
                 invoice_number="", 
                 po_number="", 
                 invoice_date="", 
                 discount_terms="",
                 due_date="",
                 shipping_cost="",
                 total_amount="",
                 source_file=""):
        """Initialize with invoice data."""
        self.vendor_name = vendor_name
        self.invoice_number = invoice_number
        self.po_number = po_number
        self.invoice_date = invoice_date
        self.discount_terms = discount_terms
        self.due_date = due_date
        self.shipping_cost = shipping_cost
        self.total_amount = total_amount
        self.source_file = source_file
        self.is_no_ocr = self._check_is_no_ocr()
        
    def _check_is_no_ocr(self):
        """Check if this invoice has no extracted data."""
        fields = [
            self.vendor_name, self.invoice_number, self.po_number,
            self.invoice_date, self.discount_terms, self.due_date,
            self.total_amount
        ]
        return all(not f for f in fields)
        
    def to_row_data(self):
        """Convert to list format for table rows."""
        return [
            self.vendor_name,
            self.invoice_number,
            self.po_number,
            self.invoice_date,
            self.discount_terms,
            self.due_date,
            self.shipping_cost,
            self.total_amount
        ]
        
    @classmethod
    def from_extracted_data(cls, data, file_path):
        """Create an Invoice from extracted data and file path."""
        # Ensure data has at least 8 elements
        while len(data) < 8:
            data.append("")
            
        return cls(
            vendor_name=data[0],
            invoice_number=data[1],
            po_number=data[2],
            invoice_date=data[3],
            discount_terms=data[4],
            due_date=data[5],
            shipping_cost=data[6],
            total_amount=data[7],
            source_file=file_path
        )