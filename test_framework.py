"""
Automated testing framework for invoice extraction.
Tests the exact same pipeline: PDF -> pdf_reader -> extractor -> output
"""
import os
import csv
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Import the actual extraction pipeline
from pdf_reader import extract_text_data_from_pdfs
from extractor import extract_fields
from extractors.total_amount import extract_bottom_most_currency, extract_bottom_most_minus_shipping


class InvoiceTestFramework:
    def __init__(self, test_data_file="test_expectations.csv", invoices_folder=r"C:\Users\ethan\Desktop\Invoices"):
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
        
        # Save detailed results
        results_file = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
            
        # Print summary
        self._print_test_summary(results)
        print(f"\nDetailed results saved to: {results_file}")
        
        return results
    
    def test_single_extractor(self, extractor_field, limit=None):
        """Test a single extractor across all files with expectations."""
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
        test_files = list(self.test_expectations.items())
        
        # Limit number of files if specified
        if limit:
            test_files = test_files[:limit]
        
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
        
        for i, (file_key, expected) in enumerate(test_files, 1):
            vendor_folder, filename = file_key.split('/', 1)
            print(f"  [{i}/{len(test_files)}] Testing {extractor_field} on {file_key}...")
            
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
                    
                    # Display the cleaner format in terminal
                    print(f"    Vendor: {vendor_name[:25]} | Approach: {approach_used} | Expected: {expected_amount} | Actual: {actual_amount} | Status: {status}")
                    
                    test_result = {
                        "file": file_key,
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
                        "status": status,
                        "field_result": field_result,
                        "extracted_value": actual.get(field_to_test[0], ''),
                        "expected_value": expected.get(field_to_test[0], '')
                    }
                
            results["test_results"].append(test_result)
        
        # Save detailed results
        results_file = f"test_results_{extractor_field}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
            
        # Print summary
        self._print_extractor_summary(results, extractor_field)
        print(f"\nDetailed results saved to: {results_file}")
        
        return results

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
        # Check if vendor has a specific approach mapping
        VENDOR_APPROACH_MAP = {
            # Gross approach vendors  
            'Sendero Provisions Co., LLC': 'gross',
            'Yak Attack': 'gross',
            'Marine Layer': 'gross', 
            'Wapsi Fly': 'gross',
            'Columbia Sportswear': 'gross',
            'The North Face': 'gross',
            'Hareline Dubbin, Inc': 'gross',
            'Industrial Revolution, Inc': 'gross',
            'Korkers Products, LLC': 'gross',
            'ON Running': 'gross',
            'Oregon Freeze Dry': 'gross',
            'Outdoor Research': 'gross',
            'Waboba Inc': 'gross',
            'Birkenstock USA': 'gross',
            
            # Calculated approach vendors
            'Howler Brothers': 'calculated',
            'Oboz Footwear LLC': 'calculated',
            'Osprey Packs, Inc': 'calculated',
            'Temple Fork Outfitters': 'calculated',
            'National Geographic Maps': 'calculated',
            'Toad & Co': 'calculated',
            'Astral Footwear': 'calculated',
            'Eagles Nest Outfitters, Inc.': 'calculated',
            'Fulling Mill Fly Fishing LLC': 'calculated',
            'Olukai LLC': 'calculated',
            
            # Bottom-most approach vendors
            'Hobie Cat Company II, LLC': 'bottom_most',
            'TOPO ATHLETIC': 'bottom_most', 
            'Free Fly Apparel': 'bottom_most',
            'Patagonia': 'bottom_most',
            'Black Diamond Equipment Ltd': 'bottom_most',
            
            # Bottom-minus-shipping approach vendors
            'Angler\'s Book Supply': 'bottom_minus_ship',
            'Liberty Mountain Sports': 'bottom_minus_ship',
            
            # Label detection approach vendors
            'Badfish': 'label',
            
            # Label minus shipping approach vendors
            'Accent & Cannon': 'label_minus_ship',
            'Cotopaxi': 'label_minus_ship', 
            'Hoka': 'label_minus_ship',
            'Katin': 'label_minus_ship',
            'Loksak': 'label_minus_ship',
            'Vuori': 'label_minus_ship',
        }
        
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
            print(f"{'Vendor':<30} {'Approach':<15} {'Expected':<12} {'Actual':<12} {'Status':<15}")
            print('-' * 120)
            
            for test in results['test_results']:
                if test['status'] == 'error':
                    continue
                    
                vendor = test.get('vendor_name', 'Unknown')
                if len(vendor) > 27:
                    vendor = vendor[:27] + "..."
                
                approach = test.get('approach_used', 'unknown')
                expected = test.get('expected_amount', '')
                actual = test.get('actual_amount', '')
                status = test.get('status', '')
                
                print(f"{vendor:<30} {approach:<15} {expected:<12} {actual:<12} {status:<15}")
        else:
            print(f"\n{'='*120}")
            print(f"{'File':<45} {'Expected':<25} {'Actual':<25} {'Status':<10}")
            print('-' * 120)
            
            for test in results['test_results']:
                filename = test['file'].split('/')[-1] if '/' in test['file'] else test['file']
                # Truncate long filenames
                if len(filename) > 42:
                    filename = filename[:39] + "..."
                    
                expected = test.get('expected_value', '')[:22]
                actual = test.get('extracted_value', '')[:22]
                
                # Add ellipsis if truncated
                if len(test.get('expected_value', '')) > 22:
                    expected += "..."
                if len(test.get('extracted_value', '')) > 22:
                    actual += "..."
                
                # Status without emoji for Windows compatibility
                status_map = {
                    'pass': 'PASS',
                    'fail': 'FAIL',
                    'skipped': 'SKIP',
                    'error': 'ERROR'
                }
                status = status_map.get(test['status'], test['status'])
                
                print(f"{filename:<45} {expected:<25} {actual:<25} {status:<10}")
        
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


if __name__ == "__main__":
    # Example usage
    tester = InvoiceTestFramework()
    
    print("Invoice Extraction Test Framework")
    print("=" * 40)
    print("1. run_all_tests() - Run tests with expectations")
    print("2. run_extraction_test(vendor, filename) - Test single file")
    
    # Uncomment to run all tests (after filling expectations):
    # tester.run_all_tests()