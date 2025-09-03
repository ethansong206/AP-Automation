"""
Automated testing framework for invoice extraction.
Tests the exact same pipeline: PDF -> pdf_reader -> extractor -> output
"""
import os
import csv
import json
from pathlib import Path
from datetime import datetime

# Import the actual extraction pipeline
from pdf_reader import extract_text_data_from_pdfs
from extractor import extract_fields


class InvoiceTestFramework:
    def __init__(self, test_data_file="test_expectations.csv", invoices_folder=r"C:\Users\ethan\Desktop\Invoices"):
        self.test_data_file = test_data_file
        self.invoices_folder = Path(invoices_folder)
        self.test_expectations = {}
        
    def generate_test_template(self):
        """Generate a CSV template with all invoice files found in the folder structure."""
        print("Scanning invoice folders...")
        
        template_rows = []
        template_rows.append([
            "vendor_folder", "filename", "vendor_name", "invoice_number", "po_number", 
            "invoice_date", "discount_terms", "discount_due_date", "total_amount", 
            "shipping_cost", "grand_total"
        ])
        
        # Folders to skip
        skip_folders = {'3 of each', '5Unreadable'}
        
        # Scan all vendor folders
        for vendor_folder in self.invoices_folder.iterdir():
            if vendor_folder.is_dir() and not vendor_folder.name.startswith('.'):
                # Skip specified folders
                if vendor_folder.name in skip_folders:
                    print(f"  Skipping folder: {vendor_folder.name}")
                    continue
                    
                print(f"  Found vendor folder: {vendor_folder.name}")
                
                # Find all PDFs in this vendor folder
                pdf_files = list(vendor_folder.glob("*.pdf"))
                print(f"    Found {len(pdf_files)} PDF files")
                
                for pdf_file in pdf_files:
                    template_rows.append([
                        vendor_folder.name,  # vendor_folder
                        pdf_file.name,       # filename
                        "",                  # vendor_name (to be filled)
                        "",                  # invoice_number (to be filled)
                        "",                  # po_number (to be filled)
                        "",                  # invoice_date (to be filled)
                        "",                  # discount_terms (to be filled)
                        "",                  # discount_due_date (to be filled)
                        "",                  # total_amount (to be filled)
                        "",                  # shipping_cost (to be filled)
                        ""                   # grand_total (to be filled)
                    ])
        
        # Write template CSV
        template_file = "test_expectations_template.csv"
        with open(template_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(template_rows)
            
        print(f"\nTemplate generated: {template_file}")
        print(f"Total files to test: {len(template_rows) - 1}")
        print("Fill in the expected values and save as 'test_expectations.csv'")
        
    def load_test_expectations(self):
        """Load expected results from CSV file."""
        if not os.path.exists(self.test_data_file):
            print(f"Test expectations file '{self.test_data_file}' not found.")
            print("Run generate_test_template() first to create a template.")
            return False
            
        self.test_expectations = {}
        
        with open(self.test_data_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Skip empty rows
                if not row['vendor_folder'] or not row['filename']:
                    continue
                    
                key = f"{row['vendor_folder']}/{row['filename']}"
                self.test_expectations[key] = {
                    'vendor_name': row['vendor_name'],
                    'invoice_number': row['invoice_number'],
                    'po_number': row['po_number'],
                    'invoice_date': row['invoice_date'],
                    'discount_terms': row['discount_terms'],
                    'discount_due_date': row['discount_due_date'],
                    'total_amount': row['total_amount'],
                    'shipping_cost': row['shipping_cost'],
                    'grand_total': row['grand_total']
                }
        
        print(f"Loaded {len(self.test_expectations)} test expectations")
        return True
        
    def run_extraction_test(self, vendor_folder_name, pdf_filename):
        """Run extraction on a single PDF file using the exact same pipeline as the app."""
        
        # Build full path to PDF
        pdf_path = self.invoices_folder / vendor_folder_name / pdf_filename
        
        if not pdf_path.exists():
            return {"error": f"File not found: {pdf_path}"}
            
        try:
            # Step 1: Extract text data (same as app)
            documents = extract_text_data_from_pdfs([str(pdf_path)])
            
            # Step 2: Run extraction (same as app) 
            extracted_rows = extract_fields(documents)
            
            if not extracted_rows:
                return {"error": "No data extracted"}
                
            # Return the exact row data that would go to the invoice table
            # Format: [vendor_name, invoice_number, po_number, invoice_date, 
            #         discount_terms, discount_due_date, total_amount, shipping_cost,
            #         QC_subtotal, QC_disc_pct, QC_disc_amount, QC_shipping, QC_used_flag]
            row = extracted_rows[0]  # First row (should only be one per PDF)
            
            return {
                "vendor_name": row[0],
                "invoice_number": row[1], 
                "po_number": row[2],
                "invoice_date": row[3],
                "discount_terms": row[4],
                "discount_due_date": row[5], 
                "total_amount": row[6],
                "shipping_cost": row[7],
                "grand_total": row[6]  # For testing, grand_total should match total_amount initially
                # QC fields (rows[8-12]) are not tested as they're user-entered
            }
            
        except Exception as e:
            return {"error": f"Extraction failed: {str(e)}"}
    
    def compare_results(self, expected, actual):
        """Compare expected vs actual results, handling formatting differences."""
        comparison = {
            "passed": True,
            "field_results": {}
        }
        
        fields_to_check = ['vendor_name', 'invoice_number', 'po_number', 
                          'invoice_date', 'discount_terms', 'discount_due_date',
                          'total_amount', 'shipping_cost', 'grand_total']
        
        for field in fields_to_check:
            expected_val = expected.get(field, '').strip()
            actual_val = str(actual.get(field, '')).strip()
            
            # Skip comparison if expected value is empty (not defined)
            if not expected_val:
                comparison["field_results"][field] = {"status": "skipped", "reason": "No expected value"}
                continue
                
            # Normalize values for comparison
            expected_normalized = self._normalize_value(expected_val)
            actual_normalized = self._normalize_value(actual_val)
            
            if expected_normalized == actual_normalized:
                comparison["field_results"][field] = {"status": "pass"}
            else:
                comparison["field_results"][field] = {
                    "status": "fail", 
                    "expected": expected_val,
                    "actual": actual_val
                }
                comparison["passed"] = False
                
        return comparison
    
    def _normalize_value(self, value):
        """Normalize values for comparison (handle formatting differences)."""
        if not value:
            return ""
            
        # Convert to string and strip
        normalized = str(value).strip()
        
        # Handle currency formatting
        if normalized.startswith('$'):
            # Remove $ and commas, keep decimals
            normalized = normalized.replace('$', '').replace(',', '')
            
        return normalized.lower()
        
    def run_all_tests(self):
        """Run tests on all files with expectations."""
        if not self.load_test_expectations():
            return
            
        print(f"\nRunning tests on {len(self.test_expectations)} files...")
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(self.test_expectations),
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "test_results": []
        }
        
        for i, (file_key, expected) in enumerate(self.test_expectations.items(), 1):
            vendor_folder, filename = file_key.split('/', 1)
            print(f"  [{i}/{len(self.test_expectations)}] Testing {file_key}...")
            
            # Run extraction
            actual = self.run_extraction_test(vendor_folder, filename)
            
            if "error" in actual:
                results["errors"] += 1
                test_result = {
                    "file": file_key,
                    "status": "error", 
                    "error": actual["error"]
                }
            else:
                # Compare results
                comparison = self.compare_results(expected, actual)
                
                if comparison["passed"]:
                    results["passed"] += 1
                    status = "pass"
                else:
                    results["failed"] += 1
                    status = "fail"
                    
                test_result = {
                    "file": file_key,
                    "status": status,
                    "field_results": comparison["field_results"],
                    "extracted_data": actual
                }
                
            results["test_results"].append(test_result)
        
        # Save detailed results
        results_file = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
            
        # Print summary
        self._print_test_summary(results)
        print(f"\nDetailed results saved to: {results_file}")
        
        return results
        
    def _print_test_summary(self, results):
        """Print a summary of test results."""
        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Total Tests: {results['total_tests']}")
        print(f"Passed: {results['passed']} ({results['passed']/results['total_tests']*100:.1f}%)")
        print(f"Failed: {results['failed']} ({results['failed']/results['total_tests']*100:.1f}%)")
        print(f"Errors: {results['errors']} ({results['errors']/results['total_tests']*100:.1f}%)")
        
        # Show failed tests
        if results['failed'] > 0 or results['errors'] > 0:
            print(f"\n{'='*60}")
            print("FAILED/ERROR DETAILS")
            print(f"{'='*60}")
            
            for test in results['test_results']:
                if test['status'] in ['fail', 'error']:
                    print(f"\n❌ {test['file']} - {test['status'].upper()}")
                    
                    if test['status'] == 'error':
                        print(f"   Error: {test['error']}")
                    else:
                        for field, result in test['field_results'].items():
                            if result['status'] == 'fail':
                                print(f"   {field}: Expected '{result['expected']}', Got '{result['actual']}'")


if __name__ == "__main__":
    # Example usage
    tester = InvoiceTestFramework()
    
    print("Invoice Extraction Test Framework")
    print("=" * 40)
    print("1. generate_test_template() - Create CSV template")
    print("2. run_all_tests() - Run tests with expectations")
    print("3. run_extraction_test(vendor, filename) - Test single file")
    
    # Uncomment to generate template:
    # tester.generate_test_template()
    
    # Uncomment to run all tests (after filling expectations):
    # tester.run_all_tests()