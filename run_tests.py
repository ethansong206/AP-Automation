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
        print("1. Generate test template (scan all invoice PDFs)")
        print("2. Test a single file") 
        print("3. Run all tests")
        print("4. Exit")
        
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == "1":
            print("\nGenerating test template...")
            tester.generate_test_template()
            print("\nNext steps:")
            print("1. Open 'test_expectations_template.csv'")
            print("2. Fill in the expected values for each file")
            print("3. Save as 'test_expectations.csv'")
            print("4. Run option 3 to test all files")
            
        elif choice == "2":
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
                    
        elif choice == "3":
            print("\nRunning all tests...")
            results = tester.run_all_tests()
            
            if results:
                print(f"\nTest complete! Check the generated JSON file for detailed results.")
            
        elif choice == "4":
            print("Goodbye!")
            break
            
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()