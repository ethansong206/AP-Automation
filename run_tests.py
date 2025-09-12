"""
Demo script showing how to use the invoice testing framework.
"""
from test_framework import InvoiceTestFramework

def main():
    # Initialize the test framework
    tester = InvoiceTestFramework()
    
    print("AP Automation Testing Framework")
    print("=" * 50)
    
    while True:
        print("\nOptions:")
        print("1. Test a single file") 
        print("2. Run all tests")
        print("3. Test single extractor")
        print("4. Test extractor performance summary (quick overview)")
        print("5. Calculate shipping cost confidence scores")
        print("6. Exit")
        
        choice = input("\nEnter choice (1-6): ").strip()
        
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
                print(f"\nTest complete! Check the generated JSON file for detailed results.")
            
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
            
            # Ask for limit
            limit_input = input("Enter number of files to test (press Enter for all): ").strip()
            limit = int(limit_input) if limit_input.isdigit() else None
            
            results = tester.test_single_extractor(extractor_choice, limit)
            
            if results:
                print(f"\nExtractor test complete! Check the generated JSON file for detailed results.")
                
        elif choice == "4":
            print("\nRunning performance summary on first 50 files for each extractor...")
            results = tester.test_extractor_performance_summary()
            
            if results:
                print(f"\nPerformance summary complete!")
            
        elif choice == "5":
            print("\nCalculating shipping cost confidence scores...")
            tester.calculate_shipping_confidence_scores()
            
        elif choice == "6":
            print("Goodbye!")
            break
            
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()