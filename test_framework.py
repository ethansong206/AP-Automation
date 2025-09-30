"""
Automated testing framework for invoice extraction.
Tests the exact same pipeline: PDF -> pdf_reader -> extractor -> output
"""
import os
import csv
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Import the actual extraction pipeline
from pdf_reader import extract_text_data_from_pdfs
from extractor import extract_fields
from extractors.total_amount import extract_bottom_most_currency, extract_bottom_most_minus_shipping, VENDOR_APPROACH_MAP


class InvoiceTestFramework:
    def __init__(self, test_data_file="test_expectations_sorted.csv", invoices_folder=r"C:\Users\ethan\Desktop\Invoices"):
        self.test_data_file = test_data_file
        self.invoices_folder = Path(invoices_folder)
        self.test_expectations = {}
        
    def load_test_expectations(self):
        """Load expected results from CSV file."""
        if not os.path.exists(self.test_data_file):
            print(f"Test expectations file '{self.test_data_file}' not found.")
            print("Please ensure the test expectations CSV file exists.")
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

            # Step 3: Also get enhanced total_amount data for testing
            enhanced_total_data = None
            try:
                from extractors.total_amount import extract_total_amount
                words = documents[0]["words"]
                vendor_name = extracted_rows[0][0]  # vendor_name from row
                enhanced_total_data = extract_total_amount(words, vendor_name)
            except Exception as e:
                print(f"[TEST] Failed to extract enhanced total data: {e}")

            # Return the exact row data that would go to the invoice table
            # Format: [vendor_name, invoice_number, po_number, invoice_date,
            #         discount_terms, discount_due_date, total_amount, shipping_cost,
            #         QC_subtotal, QC_disc_pct, QC_disc_amount, QC_shipping, QC_used_flag]
            row = extracted_rows[0]  # First row (should only be one per PDF)
            
            result = {
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

            # Add enhanced total_amount data for testing
            if enhanced_total_data and isinstance(enhanced_total_data, dict):
                result["_enhanced_total"] = enhanced_total_data

            return result
            
        except Exception as e:
            return {"error": f"Extraction failed: {str(e)}"}
    
    
    def compare_results(self, expected, actual, fields_to_test=None):
        """Compare expected vs actual results, handling formatting differences."""
        comparison = {
            "passed": True,
            "field_results": {}
        }
        
        all_fields = ['vendor_name', 'invoice_number', 'po_number', 
                     'invoice_date', 'discount_terms', 'discount_due_date',
                     'total_amount', 'shipping_cost', 'grand_total']
        
        # Use specific fields if provided, otherwise test all fields
        fields_to_check = fields_to_test if fields_to_test else all_fields
        
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
    
    def _parse_index_selection(self, all_files, range_input):
        """Parse user input to select files by index. Returns list of (file_key, expected, original_index) tuples."""
        if not range_input.strip():
            # Return all files with their 1-based indexes
            return [(file_key, expected, i) for i, (file_key, expected) in enumerate(all_files, 1)]
        
        range_input = range_input.strip()
        selected_files = []
        
        try:
            if '-' in range_input:
                # Handle range input (e.g., "1-10", "50-75")
                start_str, end_str = range_input.split('-', 1)
                start_idx = int(start_str.strip())
                end_idx = int(end_str.strip())
                
                # Validate range
                if start_idx < 1 or end_idx > len(all_files) or start_idx > end_idx:
                    print(f"Invalid range: {range_input}. Must be between 1 and {len(all_files)}")
                    return []
                
                # Select files in range (inclusive, 1-based to 0-based conversion)
                for i in range(start_idx - 1, end_idx):
                    file_key, expected = all_files[i]
                    selected_files.append((file_key, expected, i + 1))  # Keep 1-based index for display
                    
            else:
                # Handle single number input (e.g., "10")
                single_idx = int(range_input)
                
                # Validate index
                if single_idx < 1 or single_idx > len(all_files):
                    print(f"Invalid index: {single_idx}. Must be between 1 and {len(all_files)}")
                    return []
                
                # Select single file (1-based to 0-based conversion)
                file_key, expected = all_files[single_idx - 1]
                selected_files.append((file_key, expected, single_idx))
                
        except ValueError:
            print(f"Invalid input format: {range_input}. Use format like '10' or '1-50'")
            return []
        
        return selected_files

    def _parse_vendor_selection(self, all_files, vendor_filter):
        """Filter files by vendor name. Returns list of (file_key, expected, original_index) tuples."""
        if not vendor_filter.strip():
            return [(file_key, expected, i) for i, (file_key, expected) in enumerate(all_files, 1)]
        
        vendor_filter = vendor_filter.strip().lower()
        selected_files = []
        
        print(f"Filtering for vendor: '{vendor_filter}'")
        
        for i, (file_key, expected) in enumerate(all_files, 1):
            # Extract vendor from filename (first part before underscore)
            if '/' in file_key:
                filename = file_key.split('/')[-1]
                # Get vendor name from filename - everything before first underscore
                if '_' in filename:
                    file_vendor = filename.split('_')[0].lower()
                    # Also try the vendor name from the expected data
                    expected_vendor = expected.get('vendor_name', '').lower()
                    
                    # Check if filter matches either the filename vendor or expected vendor
                    if (vendor_filter in file_vendor or 
                        vendor_filter in expected_vendor or
                        file_vendor.startswith(vendor_filter) or
                        expected_vendor.startswith(vendor_filter)):
                        selected_files.append((file_key, expected, i))
                        
        print(f"Found {len(selected_files)} files matching vendor '{vendor_filter}'")
        
        if not selected_files:
            print(f"No files found for vendor '{vendor_filter}'. Check spelling or try a partial match.")
            return []
            
        return selected_files

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
        
    def calculate_shipping_confidence_scores(self):
        """
        Calculate confidence scores for vendors based on current shipping cost test results.
        Only considers cases where expected value is "0.00" (explicit zero shipping).
        """
        if not self.load_test_expectations():
            return {}
            
        vendor_stats = defaultdict(lambda: {"passes": 0, "total": 0})
        
        print("Analyzing shipping cost confidence scores...")
        print("=" * 60)
        
        # Analyze each test case
        for file_key, expected in self.test_expectations.items():
            vendor_folder, filename = file_key.split('/', 1)
            
            # Only analyze cases where we expect "0.00" (explicit zero shipping)
            if expected.get('shipping_cost') == '0.00':
                vendor_stats[vendor_folder]["total"] += 1
                
                # Run extraction to see if we get the expected "0.00"
                actual = self.run_extraction_test(vendor_folder, filename)
                
                if "error" not in actual and actual.get('shipping_cost') == '0.00':
                    vendor_stats[vendor_folder]["passes"] += 1
        
        # Calculate confidence scores
        confidence_scores = {}
        for vendor, stats in vendor_stats.items():
            if stats["total"] > 0:
                pass_rate = stats["passes"] / stats["total"]
                
                # Sample size factor: penalize small samples
                optimal_sample_size = 5
                sample_size_factor = min(1.0, stats["total"] / optimal_sample_size)
                
                # Combined confidence score
                confidence = pass_rate * sample_size_factor
                
                confidence_scores[vendor] = {
                    "score": confidence,
                    "passes": stats["passes"],
                    "total": stats["total"],
                    "pass_rate": pass_rate
                }
        
        # Display results sorted by confidence
        print(f"\nShipping Cost Confidence Analysis:")
        print(f"{'Vendor':<25} {'Score':<8} {'Tests':<8} {'Pass Rate':<10} {'Level'}")
        print("-" * 70)
        
        for vendor, data in sorted(confidence_scores.items(), key=lambda x: x[1]["score"], reverse=True):
            score = data["score"]
            passes = data["passes"]
            total = data["total"]
            pass_rate = data["pass_rate"]
            
            # Determine confidence level
            if score >= 0.8:
                level = "HIGH"
            elif score >= 0.5:
                level = "MEDIUM"
            else:
                level = "LOW"
                
            print(f"{vendor:<25} {score:.3f}    {passes}/{total:<5} {pass_rate:.1%}      {level}")
        
        return confidence_scores
        
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
        
        # Print summary
        self._print_test_summary(results)
        # JSON file creation disabled to avoid clutter
        # print(f"\nDetailed results saved to: {results_file}")
        
        return results
    
    def test_single_extractor_with_index(self, extractor_field, range_input="", vendor_filter=None, silent=False):
        """Test a single extractor across selected files using index-based selection."""
        if not self.load_test_expectations():
            return
            
        # Define extractor field mapping
        extractor_fields = {
            'vendor_name': 'vendor_name',
            'invoice_number': 'invoice_number', 
            'po_number': 'po_number',
            'invoice_date': 'invoice_date',
            'discount_terms': 'discount_terms',
            'discount_due_date': 'discount_due_date',
            'total_amount': 'total_amount',
            'shipping_cost': 'shipping_cost',
            'grand_total': 'grand_total'
        }
        
        if extractor_field not in extractor_fields:
            print(f"Invalid extractor field: {extractor_field}")
            print(f"Available fields: {', '.join(extractor_fields.keys())}")
            return
            
        field_to_test = [extractor_fields[extractor_field]]
        all_test_files = list(self.test_expectations.items())
        
        # Parse range input or vendor filter to determine which files to test
        if vendor_filter:
            test_files = self._parse_vendor_selection(all_test_files, vendor_filter)
        else:
            test_files = self._parse_index_selection(all_test_files, range_input)
        
        print(f"\nTesting {extractor_field.upper()} extractor on {len(test_files)} files...")
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "extractor_field": extractor_field,
            "total_tests": len(test_files),
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "test_results": []
        }
        
        for i, (file_key, expected, original_index) in enumerate(test_files, 1):
            vendor_folder, filename = file_key.split('/', 1)
            print(f"  [{i}/{len(test_files)}] Testing {extractor_field} on {file_key}...")

            # Run extraction
            actual = self.run_extraction_test(vendor_folder, filename)

            if "error" in actual:
                results["errors"] += 1

                # Display error for all extractors to show what went wrong
                vendor_name = actual.get('vendor_name', 'Unknown')
                error_msg = actual.get('error', 'Unknown error')[:50]  # Truncate long errors

                if extractor_field == 'total_amount':
                    print(f"[{original_index:>3}] {vendor_name[:25]:<25} {'ERROR':<20} {'':<15} {'':<15} [X] ERROR: {error_msg}")
                else:
                    # For other extractors, show in the standard format
                    filename = file_key.split('/')[-1] if '/' in file_key else file_key
                    if len(filename) > 42:
                        filename = filename[:42] + "..."
                    print(f"[{original_index:>3}] {filename:<50} {'':<20} {'':<20} [X] ERROR: {error_msg}")

                test_result = {
                    "file": file_key,
                    "original_index": original_index,
                    "status": "error",
                    "error": actual["error"]
                }
            else:
                # Special handling for total_amount extractor: show vendor, approach, expected, actual, status
                if extractor_field == 'total_amount':
                    expected_amount = expected.get('total_amount', '')
                    actual_amount = actual.get('total_amount', '')
                    vendor_name = actual.get('vendor_name', 'Unknown')
                    
                    # Determine which approach was used by the extractor
                    approach_used = self._determine_approach_used(vendor_name, actual_amount, expected_amount, vendor_folder, filename)
                    
                    # Check if result matches expected
                    is_pass = (str(actual_amount) == str(expected_amount))
                    status = "pass" if is_pass else "fail"
                    
                    if is_pass:
                        results["passed"] += 1
                    else:
                        results["failed"] += 1
                    
                    # Status with X only for failures to make them stand out
                    status_map = {
                        'pass': 'PASS',
                        'fail': '[X] FAIL',
                        'skipped': 'SKIP',
                        'error': '[X] ERROR'
                    }
                    visual_status = status_map.get(status, status)

                    # Display with proper column alignment
                    print(f"[{original_index:>3}] {vendor_name[:25]:<25} {approach_used:<20} {expected_amount:<15} {actual_amount:<15} {visual_status}")
                    
                    test_result = {
                        "file": file_key,
                        "original_index": original_index,
                        "vendor_name": vendor_name,
                        "approach_used": approach_used,
                        "status": status,
                        "expected_amount": expected_amount,
                        "actual_amount": actual_amount,
                        "is_match": is_pass
                    }
                else:
                    # Compare results for this specific field only
                    comparison = self.compare_results(expected, actual, field_to_test)
                    field_result = comparison["field_results"][field_to_test[0]]
                    
                    if field_result["status"] == "pass":
                        results["passed"] += 1
                        status = "pass"
                    elif field_result["status"] == "skipped":
                        results["skipped"] += 1
                        status = "skipped"
                    else:
                        results["failed"] += 1
                        status = "fail"
                        
                    test_result = {
                        "file": file_key,
                        "original_index": original_index,
                        "status": status,
                        "field_result": field_result,
                        "extracted_value": actual.get(field_to_test[0], ''),
                        "expected_value": expected.get(field_to_test[0], '')
                    }
                
            results["test_results"].append(test_result)
        
        # Print summary with vendor metrics
        self._print_extractor_summary(results, extractor_field)
        self._print_vendor_metrics(results, extractor_field)
        # JSON file creation disabled to avoid clutter
        # print(f"\nDetailed results saved to: {results_file}")
        
        return results
    
    def test_single_extractor(self, extractor_field, limit=None):
        """Legacy method - test a single extractor with simple limit (for backward compatibility)."""
        range_input = "" if limit is None else f"1-{limit}"
        return self.test_single_extractor_with_index(extractor_field, range_input)

    def analyze_total_amount_logic(self, limit=None):
        """
        Analyze total_amount test results to determine rules for gross vs calculated values.
        """
        print("Analyzing total_amount extraction patterns...")
        
        # Run the total_amount tests
        results = self.test_single_extractor('total_amount', limit)
        
        if not results or not results.get('test_results'):
            print("No test results to analyze.")
            return
        
        # Collect data for analysis
        analysis_data = []
        for test in results['test_results']:
            if test.get('status') == 'error':
                continue
                
            # Extract key information for analysis
            vendor_folder, filename = test['file'].split('/', 1)
            
            data_point = {
                'file': filename,
                'vendor': vendor_folder,
                'expected': test.get('expected_amount', ''),
                'gross': test.get('gross_amount', ''),
                'calculated': test.get('calculated_amount', ''),
                'gross_match': test.get('gross_match', False),
                'calculated_match': test.get('calculated_match', False),
                'status': test.get('status', '')
            }
            
            # Get additional context from the raw extraction
            try:
                actual = self.run_extraction_test(vendor_folder, filename)
                if 'error' not in actual:
                    data_point['discount_terms'] = actual.get('discount_terms', '')
                    data_point['shipping_cost'] = actual.get('shipping_cost', '0.00')
            except:
                pass
                
            analysis_data.append(data_point)
        
        # Perform analysis
        self._analyze_patterns(analysis_data)
        return analysis_data

    def _analyze_patterns(self, data):
        """Analyze patterns in the total_amount test data."""
        total_files = len(data)
        gross_wins = sum(1 for d in data if d['gross_match'] and not d['calculated_match'])
        calculated_wins = sum(1 for d in data if d['calculated_match'] and not d['gross_match'])
        both_work = sum(1 for d in data if d['gross_match'] and d['calculated_match'])
        neither_work = sum(1 for d in data if not d['gross_match'] and not d['calculated_match'])
        
        print(f"\n{'='*80}")
        print(f"TOTAL AMOUNT EXTRACTION ANALYSIS")
        print(f"{'='*80}")
        print(f"Total files analyzed: {total_files}")
        print(f"Gross value correct:     {gross_wins:3d} ({gross_wins/total_files*100:.1f}%)")
        print(f"Calculated value correct: {calculated_wins:3d} ({calculated_wins/total_files*100:.1f}%)")
        print(f"Both values work:        {both_work:3d} ({both_work/total_files*100:.1f}%)")
        print(f"Neither works:           {neither_work:3d} ({neither_work/total_files*100:.1f}%)")
        
        # Analyze by vendor
        vendor_analysis = {}
        for d in data:
            vendor = d['vendor']
            if vendor not in vendor_analysis:
                vendor_analysis[vendor] = {'gross': 0, 'calculated': 0, 'both': 0, 'neither': 0, 'total': 0}
            
            vendor_analysis[vendor]['total'] += 1
            if d['gross_match'] and d['calculated_match']:
                vendor_analysis[vendor]['both'] += 1
            elif d['gross_match']:
                vendor_analysis[vendor]['gross'] += 1
            elif d['calculated_match']:
                vendor_analysis[vendor]['calculated'] += 1
            else:
                vendor_analysis[vendor]['neither'] += 1
        
        print(f"\n{'='*80}")
        print(f"VENDOR ANALYSIS")
        print(f"{'='*80}")
        print(f"{'Vendor':<25} {'Total':<6} {'Gross':<6} {'Calc':<6} {'Both':<6} {'Neither':<8} {'Recommendation':<15}")
        print('-' * 80)
        
        recommendations = {}
        for vendor, stats in sorted(vendor_analysis.items()):
            if stats['total'] == 0:
                continue
                
            gross_pct = stats['gross'] / stats['total'] * 100
            calc_pct = stats['calculated'] / stats['total'] * 100
            both_pct = stats['both'] / stats['total'] * 100
            
            # Determine recommendation
            if gross_pct >= 70:
                recommendation = "Use Gross"
            elif calc_pct >= 70:
                recommendation = "Use Calculated"
            elif both_pct >= 50:
                recommendation = "Either Works"
            else:
                recommendation = "Needs Review"
                
            recommendations[vendor] = recommendation
            
            print(f"{vendor:<25} {stats['total']:<6} {stats['gross']:<6} {stats['calculated']:<6} {stats['both']:<6} {stats['neither']:<8} {recommendation:<15}")
        
        # Analyze by discount terms
        print(f"\n{'='*80}")
        print(f"DISCOUNT TERMS ANALYSIS")
        print(f"{'='*80}")
        
        discount_analysis = {}
        for d in data:
            discount = d.get('discount_terms', 'No Discount')[:20]  # Truncate for display
            if discount not in discount_analysis:
                discount_analysis[discount] = {'gross': 0, 'calculated': 0, 'both': 0, 'total': 0}
            
            discount_analysis[discount]['total'] += 1
            if d['gross_match'] and d['calculated_match']:
                discount_analysis[discount]['both'] += 1
            elif d['gross_match']:
                discount_analysis[discount]['gross'] += 1
            elif d['calculated_match']:
                discount_analysis[discount]['calculated'] += 1
        
        print(f"{'Discount Terms':<22} {'Total':<6} {'Gross':<6} {'Calc':<6} {'Both':<6} {'Pattern':<15}")
        print('-' * 75)
        
        for discount, stats in sorted(discount_analysis.items(), key=lambda x: x[1]['total'], reverse=True):
            if stats['total'] < 2:  # Only show patterns with multiple examples
                continue
                
            gross_pct = stats['gross'] / stats['total'] * 100
            calc_pct = stats['calculated'] / stats['total'] * 100
            
            if gross_pct >= 70:
                pattern = "Prefers Gross"
            elif calc_pct >= 70:
                pattern = "Prefers Calculated"
            else:
                pattern = "Mixed"
                
            print(f"{discount:<22} {stats['total']:<6} {stats['gross']:<6} {stats['calculated']:<6} {stats['both']:<6} {pattern:<15}")
        
        # Generate decision rules
        print(f"\n{'='*80}")
        print(f"SUGGESTED DECISION RULES")
        print(f"{'='*80}")
        
        # Rule 1: By vendor
        gross_vendors = [v for v, r in recommendations.items() if r == "Use Gross"]
        calc_vendors = [v for v, r in recommendations.items() if r == "Use Calculated"]
        
        if gross_vendors:
            print(f"1. Use GROSS total for these vendors:")
            for vendor in gross_vendors[:10]:  # Show first 10
                print(f"   - {vendor}")
            if len(gross_vendors) > 10:
                print(f"   ... and {len(gross_vendors)-10} more")
        
        if calc_vendors:
            print(f"2. Use CALCULATED total for these vendors:")
            for vendor in calc_vendors[:10]:  # Show first 10
                print(f"   - {vendor}")
            if len(calc_vendors) > 10:
                print(f"   ... and {len(calc_vendors)-10} more")
        
        # Rule 2: By discount presence
        no_discount_data = [d for d in data if not d.get('discount_terms') or 'NET' in d.get('discount_terms', '').upper()]
        with_discount_data = [d for d in data if d.get('discount_terms') and '%' in d.get('discount_terms', '')]
        
        if no_discount_data:
            no_disc_gross = sum(1 for d in no_discount_data if d['gross_match'])
            no_disc_calc = sum(1 for d in no_discount_data if d['calculated_match'])
            print(f"3. For invoices WITHOUT percentage discounts: Gross works {no_disc_gross}/{len(no_discount_data)} times, Calculated works {no_disc_calc}/{len(no_discount_data)} times")
        
        if with_discount_data:
            with_disc_gross = sum(1 for d in with_discount_data if d['gross_match'])
            with_disc_calc = sum(1 for d in with_discount_data if d['calculated_match'])
            print(f"4. For invoices WITH percentage discounts: Gross works {with_disc_gross}/{len(with_discount_data)} times, Calculated works {with_disc_calc}/{len(with_discount_data)} times")
        
        print(f"\nRecommendation: Based on this analysis, consider implementing vendor-specific logic or discount-based rules.")

    def _determine_approach_used(self, vendor_name, actual_amount, expected_amount, vendor_folder, filename):
        """Determine which approach was used by the total_amount extractor."""
        # Use the imported VENDOR_APPROACH_MAP from total_amount extractor
        
        if vendor_name in VENDOR_APPROACH_MAP:
            return VENDOR_APPROACH_MAP[vendor_name]
        else:
            # Not in vendor mapping, so it used fallback logic
            is_match = (str(actual_amount) == str(expected_amount))
            if is_match:
                return "fallback_success"
            else:
                return "fallback_fail"

    def _calculate_adjusted_total_amount(self, actual_data):
        """
        Calculate adjusted total amount for testing: (total_amount - shipping_cost) * (1 - discount_rate)
        """
        try:
            # Get base values
            total_amount = float(actual_data.get('total_amount', '0').replace(',', ''))
            shipping_cost = float(actual_data.get('shipping_cost', '0').replace(',', ''))
            discount_terms = actual_data.get('discount_terms', '').strip()
            
            # Subtract shipping cost
            net_amount = total_amount - shipping_cost
            
            # Parse discount percentage if present
            discount_rate = 0.0
            if discount_terms and '%' in discount_terms:
                # Extract percentage from strings like "5% NET 30", "8% 60 NET 61", etc.
                import re
                discount_match = re.search(r'(\d+(?:\.\d+)?)%', discount_terms)
                if discount_match:
                    discount_rate = float(discount_match.group(1)) / 100.0
            
            # Apply discount
            adjusted_amount = net_amount * (1 - discount_rate)
            
            # Format to 2 decimal places
            return f"{adjusted_amount:.2f}"
            
        except (ValueError, TypeError) as e:
            # If calculation fails, return original total_amount
            return actual_data.get('total_amount', '0')
    
    def test_extractor_performance_summary(self):
        """Test all extractors and show a performance summary."""
        if not self.load_test_expectations():
            return
            
        extractors = ['vendor_name', 'invoice_number', 'po_number', 'invoice_date', 
                     'discount_terms', 'discount_due_date', 'total_amount', 'shipping_cost']
        
        print("\nTesting all extractors for performance summary...")
        summary_results = {}
        
        for extractor in extractors:
            print(f"\n--- Testing {extractor.upper()} ---")
            results = self.test_single_extractor(extractor, limit=50)  # Test first 50 for quick overview
            if results:
                summary_results[extractor] = {
                    'total': results['total_tests'],
                    'passed': results['passed'],
                    'failed': results['failed'],
                    'errors': results['errors'],
                    'skipped': results['skipped'],
                    'accuracy': results['passed'] / (results['total_tests'] - results['skipped']) * 100 if (results['total_tests'] - results['skipped']) > 0 else 0
                }
        
        # Print overall summary
        print(f"\n{'='*80}")
        print("EXTRACTOR PERFORMANCE SUMMARY (First 50 files)")
        print(f"{'='*80}")
        print(f"{'Extractor':<20} {'Total':<8} {'Pass':<6} {'Fail':<6} {'Skip':<6} {'Error':<6} {'Accuracy':<8}")
        print("-" * 80)
        
        for extractor, stats in summary_results.items():
            accuracy = f"{stats['accuracy']:.1f}%"
            print(f"{extractor:<20} {stats['total']:<8} {stats['passed']:<6} {stats['failed']:<6} {stats['skipped']:<6} {stats['errors']:<6} {accuracy:<8}")
        
        return summary_results
    
    def analyze_vendor_priority_for_total_amount(self):
        """Analyze which vendors should be prioritized for total_amount extraction fixes."""
        print("Analyzing vendor priority for total_amount extraction fixes...")
        
        # Run total_amount extraction on all files
        results = self.test_single_extractor('total_amount')
        
        if not results or not results.get('test_results'):
            print("No test results available for analysis.")
            return
        
        # Collect vendor statistics
        vendor_stats = {}
        
        for test in results['test_results']:
            if test['status'] == 'error':
                continue
                
            vendor = test.get('vendor_name', 'Unknown')
            if vendor not in vendor_stats:
                vendor_stats[vendor] = {
                    'total_files': 0, 
                    'failed_files': 0, 
                    'passed_files': 0,
                    'failure_rate': 0.0,
                    'priority_score': 0.0
                }
            
            vendor_stats[vendor]['total_files'] += 1
            
            if test['status'] == 'fail':
                vendor_stats[vendor]['failed_files'] += 1
            elif test['status'] == 'pass':
                vendor_stats[vendor]['passed_files'] += 1
        
        # Calculate priority scores
        for vendor, stats in vendor_stats.items():
            if stats['total_files'] > 0:
                stats['failure_rate'] = stats['failed_files'] / stats['total_files']
                # Priority score = (number of failures) * (failure rate) * (volume factor)
                # Volume factor gives higher weight to vendors with more files
                volume_factor = min(2.0, stats['total_files'] / 5.0)  # Cap at 2x weight
                stats['priority_score'] = stats['failed_files'] * stats['failure_rate'] * volume_factor
        
        # Filter out vendors with no failures
        problem_vendors = {v: s for v, s in vendor_stats.items() if s['failed_files'] > 0}
        
        # Sort by priority score (highest first)
        sorted_vendors = sorted(problem_vendors.items(), key=lambda x: x[1]['priority_score'], reverse=True)
        
        print(f"\\n{'='*100}")
        print("VENDOR PRIORITY ANALYSIS - TOTAL_AMOUNT EXTRACTION")
        print(f"{'='*100}")
        print(f"{'Rank':<5} {'Vendor':<30} {'Failed':<8} {'Total':<8} {'Rate':<8} {'Priority':<10} {'Impact':<15}")
        print('-' * 100)
        
        for rank, (vendor, stats) in enumerate(sorted_vendors[:20], 1):  # Top 20
            failure_rate_pct = stats['failure_rate'] * 100
            priority_score = stats['priority_score']
            
            # Determine impact level
            if stats['failed_files'] >= 5 and failure_rate_pct >= 50:
                impact = "HIGH"
            elif stats['failed_files'] >= 3 or failure_rate_pct >= 75:
                impact = "MEDIUM"
            else:
                impact = "LOW"
            
            # Truncate long vendor names
            display_vendor = vendor[:27] + "..." if len(vendor) > 27 else vendor
            
            print(f"{rank:<5} {display_vendor:<30} {stats['failed_files']:<8} {stats['total_files']:<8} {failure_rate_pct:<7.1f}% {priority_score:<9.2f} {impact:<15}")
        
        # Summary recommendations
        high_priority = [v for v, s in sorted_vendors if s['failed_files'] >= 5 and s['failure_rate'] >= 0.5]
        medium_priority = [v for v, s in sorted_vendors if s['failed_files'] >= 3 or s['failure_rate'] >= 0.75]
        
        print(f"\\n{'='*100}")
        print("PRIORITY RECOMMENDATIONS")
        print(f"{'='*100}")
        print(f"Total vendors with failures: {len(problem_vendors)}")
        print(f"High priority vendors (>=5 failures, >=50% rate): {len(high_priority)}")
        print(f"Medium priority vendors (>=3 failures or >=75% rate): {len([v for v in medium_priority if v not in high_priority])}")
        
        if high_priority:
            print(f"\\nHIGH PRIORITY - Fix these first:")
            for vendor in high_priority[:5]:  # Top 5 high priority
                stats = problem_vendors[vendor]
                print(f"  • {vendor} ({stats['failed_files']}/{stats['total_files']} failures, {stats['failure_rate']*100:.1f}% rate)")
        
        if len(sorted_vendors) > len(high_priority):
            remaining_vendors = [v for v in sorted_vendors if v[0] not in high_priority][:3]
            if remaining_vendors:
                print(f"\\nNEXT PRIORITY:")
                for vendor, stats in remaining_vendors:
                    print(f"  • {vendor} ({stats['failed_files']}/{stats['total_files']} failures, {stats['failure_rate']*100:.1f}% rate)")
        
        print(f"\\nPriority Score = (Failed Files) × (Failure Rate) × (Volume Factor)")
        print(f"Focus on vendors with high priority scores for maximum impact.")
        
        return sorted_vendors
    
    def _print_vendor_metrics(self, results, extractor_field):
        """Print vendor-specific metrics showing pass rates."""
        if not results.get('test_results'):
            return
            
        # Collect vendor statistics
        vendor_stats = {}
        
        for test in results['test_results']:
            if test['status'] == 'error':
                continue
                
            # Extract vendor name from the test results
            if extractor_field == 'total_amount':
                vendor = test.get('vendor_name', 'Unknown')
            else:
                # For other extractors, need to get vendor from file path or extracted data
                file_key = test.get('file', '')
                # Try to extract vendor from filename (first part before underscore)
                if file_key and '/' in file_key:
                    filename = file_key.split('/')[-1]
                    vendor = filename.split('_')[0].replace('.pdf', '')
                else:
                    vendor = 'Unknown'
                    
            if vendor not in vendor_stats:
                vendor_stats[vendor] = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0}
            
            vendor_stats[vendor]['total'] += 1
            
            if test['status'] == 'pass':
                vendor_stats[vendor]['passed'] += 1
            elif test['status'] == 'fail':
                vendor_stats[vendor]['failed'] += 1
            elif test['status'] == 'skipped':
                vendor_stats[vendor]['skipped'] += 1
        
        # Calculate metrics
        total_vendors = len(vendor_stats)
        vendors_100_percent = 0
        vendors_with_tests = 0  # Vendors that have testable results (not all skipped)
        
        print(f"\n{'='*80}")
        print(f"VENDOR METRICS - {extractor_field.upper()} EXTRACTOR")
        print(f"{'='*80}")
        
        print(f"{'Vendor':<30} {'Total':<6} {'Pass':<6} {'Fail':<6} {'Skip':<6} {'Accuracy':<10}")
        print('-' * 80)
        
        for vendor, stats in sorted(vendor_stats.items()):
            testable = stats['total'] - stats['skipped']
            
            if testable > 0:
                vendors_with_tests += 1
                accuracy = stats['passed'] / testable * 100
                if accuracy == 100.0:
                    vendors_100_percent += 1
                    accuracy_str = f"{accuracy:.0f}%*"  # Mark 100% vendors with *
                else:
                    accuracy_str = f"{accuracy:.1f}%"
            else:
                accuracy_str = "N/A"
            
            # Truncate long vendor names
            display_vendor = vendor[:27] + "..." if len(vendor) > 27 else vendor
            
            print(f"{display_vendor:<30} {stats['total']:<6} {stats['passed']:<6} {stats['failed']:<6} {stats['skipped']:<6} {accuracy_str:<10}")
        
        # Summary statistics
        print(f"\n{'='*80}")
        print(f"VENDOR SUMMARY")
        print(f"{'='*80}")
        print(f"Total unique vendors: {total_vendors}")
        print(f"Vendors with testable data: {vendors_with_tests}")
        print(f"Vendors with 100% accuracy: {vendors_100_percent}")
        
        if vendors_with_tests > 0:
            percent_perfect = vendors_100_percent / vendors_with_tests * 100
            print(f"Percentage of vendors with 100% accuracy: {percent_perfect:.1f}%")
            print(f"Vendors with issues: {vendors_with_tests - vendors_100_percent}")
        
        if vendors_100_percent > 0:
            print(f"\n* = 100% accuracy")
        
    def _print_extractor_summary(self, results, extractor_field):
        """Print a summary for single extractor test results."""
        print(f"\n{'='*80}")
        print(f"{extractor_field.upper()} EXTRACTOR TEST RESULTS")
        print(f"{'='*80}")
        
        # Summary stats with breakdown for total_amount
        if extractor_field == 'total_amount':
            # Count different approach matches
            gross_matches = sum(1 for test in results['test_results'] if test.get('gross_match', False))
            calculated_matches = sum(1 for test in results['test_results'] if test.get('calculated_match', False))
            bottom_most_matches = sum(1 for test in results['test_results'] if test.get('bottom_most_match', False))
            bottom_minus_ship_matches = sum(1 for test in results['test_results'] if test.get('bottom_minus_shipping_match', False))
            
            print(f"Total Tests: {results['total_tests']} | ", end="")
            print(f"Passed: {results['passed']} | ", end="")
            print(f"Failed: {results['failed']} | ", end="")
            print(f"Errors: {results['errors']}")
            print(f"Approach Performance: Gross={gross_matches}, Calculated={calculated_matches}, Bottom-most={bottom_most_matches}, Bottom-Ship={bottom_minus_ship_matches}")
        else:
            print(f"Total Tests: {results['total_tests']} | ", end="")
            print(f"Passed: {results['passed']} | ", end="")
            print(f"Failed: {results['failed']} | ", end="")
            print(f"Skipped: {results['skipped']} | ", end="")
            print(f"Errors: {results['errors']}")
        
        # Calculate accuracy excluding skipped tests
        testable = results['total_tests'] - results['skipped']
        if testable > 0:
            accuracy = results['passed'] / testable * 100
            print(f"Accuracy: {accuracy:.1f}% ({results['passed']}/{testable} testable files)")
        
        # Side-by-side results display
        if extractor_field == 'total_amount':
            print(f"\n{'='*120}")
            print(f"{'Idx':>5} {'Vendor':<25} {'Approach':<20} {'Expected':<15} {'Actual':<15} {'Status'}")
            print('─' * 120)

            for test in results['test_results']:
                if test['status'] == 'error':
                    continue

                idx = test.get('original_index', '?')
                vendor = test.get('vendor_name', 'Unknown')
                if len(vendor) > 25:
                    vendor = vendor[:22] + "..."

                approach = test.get('approach_used', 'unknown')
                expected = test.get('expected_amount', '')
                actual = test.get('actual_amount', '')
                status = test.get('status', '')

                # Status with X only for failures to make them stand out
                status_map = {
                    'pass': 'PASS',
                    'fail': '[X] FAIL',
                    'skipped': 'SKIP',
                    'error': '[X] ERROR'
                }
                visual_status = status_map.get(status, status)

                print(f"[{idx:>3}] {vendor:<25} {approach:<20} {expected:<15} {actual:<15} {visual_status}")
        else:
            print(f"\n{'='*120}")
            print(f"{'Idx':>5} {'File':<50} {'Expected':<20} {'Actual':<20} {'Status'}")
            print('─' * 120)
            
            for test in results['test_results']:
                idx = test.get('original_index', '?')
                filename = test['file'].split('/')[-1] if '/' in test['file'] else test['file']
                # Truncate long filenames
                if len(filename) > 42:
                    filename = filename[:39] + "..."
                    
                expected = (test.get('expected_value') or '')[:22]
                actual = (test.get('extracted_value') or '')[:22]
                
                # Add ellipsis if truncated
                if len(test.get('expected_value') or '') > 22:
                    expected += "..."
                if len(test.get('extracted_value') or '') > 22:
                    actual += "..."
                
                # Status with X only for failures to make them stand out
                status_map = {
                    'pass': 'PASS',
                    'fail': '[X] FAIL',
                    'skipped': 'SKIP',
                    'error': '[X] ERROR'
                }
                status = status_map.get(test['status'], test['status'])

                # Better formatting with fixed column widths
                print(f"[{idx:>3}] {filename:<50} {expected:<20} {actual:<20} {status}")
        
        # Show detailed failures if there are any but not too many
        failed_tests = [t for t in results['test_results'] if t['status'] == 'fail']
        if failed_tests and len(failed_tests) <= 5:
            print(f"\n{'='*80}")
            print(f"DETAILED FAILURE ANALYSIS ({len(failed_tests)} failures)")
            print(f"{'='*80}")
            
            for i, test in enumerate(failed_tests, 1):
                print(f"\n{i}. FAIL {test['file']}")
                if extractor_field == 'total_amount':
                    print(f"   Expected: '{test.get('expected_amount', '')}'")
                    print(f"   Gross:    '{test.get('gross_amount', '')}'")
                    print(f"   Calculated: '{test.get('calculated_amount', '')}'")
                    print(f"   Bottom-most: '{test.get('bottom_most_amount', '')}'")
                    print(f"   Bottom-Ship: '{test.get('bottom_minus_shipping_amount', '')}'")
                else:
                    print(f"   Expected: '{test.get('expected_value', '')}'")
                    print(f"   Actual:   '{test.get('extracted_value', '')}'")  
        elif len(failed_tests) > 5:
            print(f"\n{'='*80}")
            print(f"TOO MANY FAILURES TO SHOW DETAILS ({len(failed_tests)} total)")
            print(f"Check the JSON file for complete failure analysis")
            print(f"{'='*80}")

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
                    print(f"\nFAIL {test['file']} - {test['status'].upper()}")
                    
                    if test['status'] == 'error':
                        print(f"   Error: {test['error']}")
                    else:
                        for field, result in test['field_results'].items():
                            if result['status'] == 'fail':
                                # Format with alignment for readability
                                expected = result['expected'][:25] + "..." if len(str(result['expected'])) > 25 else result['expected']
                                actual = result['actual'][:25] + "..." if len(str(result['actual'])) > 25 else result['actual']
                                print(f"   {field:<18} Expected: {expected:<28} Got: {actual}")

                        # Show enhanced total data if available
                        if 'extracted_data' in test and '_enhanced_total' in test['extracted_data']:
                            enhanced = test['extracted_data']['_enhanced_total']
                            print(f"   Enhanced Total Data:")
                            print(f"      Method: {enhanced.get('calculation_method', 'none')}")
                            print(f"      Discount Type: {enhanced.get('discount_type', 'none')}")
                            if enhanced.get('discount_value'):
                                print(f"      Discount Value: {enhanced.get('discount_value')}")
                            if enhanced.get('pre_discount_amount'):
                                print(f"      Pre-discount Amount: {enhanced.get('pre_discount_amount')}")
                            print(f"      Has Calculation: {enhanced.get('has_calculation', False)}")


    def test_enhanced_extraction(self, vendor_folder, filename):
        """Test enhanced total_amount extraction and display results."""
        print(f"\nTesting enhanced extraction for: {vendor_folder}/{filename}")
        print("=" * 60)

        result = self.run_extraction_test(vendor_folder, filename)

        if "error" in result:
            print(f"Error: {result['error']}")
            return

        # Display standard extraction results
        print("Standard Extraction Results:")
        for key, value in result.items():
            if key != '_enhanced_total':
                print(f"  {key}: {value}")

        # Display enhanced total data
        if '_enhanced_total' in result:
            enhanced = result['_enhanced_total']
            print(f"\nEnhanced Total Amount Data:")
            print(f"  Method: {enhanced.get('calculation_method', 'none')}")
            print(f"  Discount Type: {enhanced.get('discount_type', 'none')}")
            print(f"  Has Calculation: {enhanced.get('has_calculation', False)}")
            if enhanced.get('discount_value'):
                print(f"  Discount Value: {enhanced.get('discount_value')}")
            if enhanced.get('pre_discount_amount'):
                print(f"  Pre-discount Amount: {enhanced.get('pre_discount_amount')}")
            print(f"  Final Total Amount: {enhanced.get('total_amount', 'none')}")
        else:
            print("\nNo enhanced total data available")


if __name__ == "__main__":
    # Example usage
    tester = InvoiceTestFramework()

    print("Invoice Extraction Test Framework")
    print("=" * 40)
    print("1. run_all_tests() - Run tests with expectations")
    print("2. run_extraction_test(vendor, filename) - Test single file")
    print("3. test_enhanced_extraction(vendor, filename) - Test enhanced total extraction")

    # Uncomment to run all tests (after filling expectations):
    # tester.run_all_tests()

    # Example: Test enhanced extraction
    # tester.test_enhanced_extraction("All", "Accent_&_Cannon_45288.pdf")