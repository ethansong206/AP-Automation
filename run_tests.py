"""
Demo script showing how to use the invoice testing framework.
"""
from test_framework import InvoiceTestFramework

def main():
    print("AP Automation Testing Framework")
    print("=" * 50)

    # Ask user which dataset to test
    print("\nSelect dataset to test:")
    print("1. Sorted (test_expectations_sorted.csv)")
    print("2. September (test_expectations_september.csv)")

    dataset_choice = input("\nEnter choice (1-2): ").strip()

    if dataset_choice == "1":
        csv_file = "test_expectations_sorted.csv"
        print("\nUsing: test_expectations_sorted.csv")
    elif dataset_choice == "2":
        csv_file = "test_expectations_september.csv"
        print("\nUsing: test_expectations_september.csv")
    else:
        print("Invalid choice. Defaulting to test_expectations_sorted.csv")
        csv_file = "test_expectations_sorted.csv"

    # Initialize the test framework with selected CSV
    tester = InvoiceTestFramework(test_data_file=csv_file)

    print("=" * 50)
    
    while True:
        print("\nOptions:")
        print("1. Test a single file") 
        print("2. Run all tests")
        print("3. Test single extractor")
        print("4. Calculate shipping cost confidence scores")
        print("5. Exit")
        
        choice = input("\nEnter choice (1-5): ").strip()
        
        if choice == "1":
            vendor = input("Enter vendor folder name: ").strip()
            filename = input("Enter PDF filename: ").strip()
            
            print(f"\nTesting {vendor}/{filename}...")
            result = tester.run_extraction_test(vendor, filename)
            
            print("\nExtraction Result:")
            print("-" * 30)
            if "error" in result:
                print(f"❌ Error: {result['error']}")
            else:
                for field, value in result.items():
                    print(f"{field}: {value}")
                    
        elif choice == "2":
            print("\nRunning all tests...")
            results = tester.run_all_tests()
            
            if results:
                print(f"\nTest complete!")
            
        elif choice == "3":
            print("\nAvailable extractors:")
            extractors = ['vendor_name', 'invoice_number', 'po_number', 'invoice_date', 
                         'discount_terms', 'discount_due_date', 'total_amount', 'shipping_cost']
            for i, ext in enumerate(extractors, 1):
                print(f"  {i}. {ext}")
                
            extractor_choice = input("\nEnter extractor name or number: ").strip()
            
            # Handle numeric choice
            if extractor_choice.isdigit():
                idx = int(extractor_choice) - 1
                if 0 <= idx < len(extractors):
                    extractor_choice = extractors[idx]
                else:
                    print("Invalid number choice.")
                    continue
            
            # Ask for selection method
            print("\nSelection options:")
            print("1. Index/range (e.g., 1-10, 50-75, or single number)")
            print("2. Vendor name (e.g., Arc'teryx, Patagonia)")
            print("3. All files")
            
            selection_type = input("Choose selection method (1/2/3): ").strip()
            
            if selection_type == "1":
                range_input = input("Enter range (e.g., 1-10, 50-75), single number (e.g., 10): ").strip()
                vendor_filter = None
            elif selection_type == "2":
                vendor_filter = input("Enter vendor name: ").strip()
                range_input = ""
            else:
                range_input = ""
                vendor_filter = None
            
            results = tester.test_single_extractor_with_index(extractor_choice, range_input, vendor_filter)
            
            if results:
                print(f"\nExtractor test complete!")
                
        elif choice == "4":
            print("\nCalculating shipping cost confidence scores...")
            tester.calculate_shipping_confidence_scores()
            
        elif choice == "5":
            print("Goodbye!")
            break
            
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()