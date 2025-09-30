#!/usr/bin/env python3
"""
Test script to demonstrate the new logging system.
Run this to see how the logging works at different levels.
"""

from logging_config import setup_logging, get_logger, set_debug_mode, set_quiet_mode
import time

def demonstrate_logging_levels():
    """Show different logging levels in action."""
    logger = get_logger('demo')

    print("=== LOGGING LEVELS DEMONSTRATION ===\n")

    # Demonstrate all log levels
    logger.debug("This is DEBUG level - shows detailed info (only visible in debug mode)")
    logger.info("This is INFO level - shows general application flow")
    logger.warning("This is WARNING level - shows potential issues")
    logger.error("This is ERROR level - shows actual problems")
    logger.critical("This is CRITICAL level - shows severe errors")

def demonstrate_vendor_extraction():
    """Simulate vendor extraction with logging."""
    logger = get_logger('vendor_demo')

    print("\n=== SIMULATED VENDOR EXTRACTION ===\n")

    # Simulate processing multiple vendors
    test_vendors = ["Patagonia", "Arc'teryx", "Columbia Sportswear", "The North Face"]

    logger.info(f"Starting vendor processing for {len(test_vendors)} vendors")

    for i, vendor in enumerate(test_vendors, 1):
        logger.debug(f"Processing vendor {i}/{len(test_vendors)}: {vendor}")

        # Simulate some processing time
        time.sleep(0.1)

        # Simulate different outcomes
        if vendor == "Arc'teryx":
            logger.warning(f"Special handling required for vendor with apostrophe: {vendor}")

        logger.info(f"Successfully processed: {vendor}")

    logger.info("Vendor processing complete")

def demonstrate_error_handling():
    """Show how errors are logged."""
    logger = get_logger('error_demo')

    print("\n=== ERROR LOGGING DEMONSTRATION ===\n")

    try:
        # Simulate an error
        result = 10 / 0
    except ZeroDivisionError as e:
        logger.error(f"Mathematical error occurred: {e}")
        logger.debug("Full error details: Division by zero in calculation")

def main():
    """Run the logging demonstration."""
    print("AP Automation Logging System Test")
    print("=" * 50)

    # Initialize logging in INFO mode (normal operation)
    setup_logging(level=None, debug_mode=False)

    # Run demonstrations
    demonstrate_logging_levels()
    demonstrate_vendor_extraction()
    demonstrate_error_handling()

    print("\n=== SWITCHING TO DEBUG MODE ===\n")
    set_debug_mode()

    # Now you'll see DEBUG messages too
    logger = get_logger('debug_test')
    logger.debug("Now you can see debug messages!")
    logger.info("Debug mode is active - you'll see much more detail")

    print("\n=== SWITCHING TO QUIET MODE ===\n")
    set_quiet_mode()

    # Now only warnings and errors show
    logger = get_logger('quiet_test')
    logger.debug("This debug message won't show")
    logger.info("This info message won't show either")
    logger.warning("But this warning WILL show")
    logger.error("And errors still show")

    print("\n=== TEST COMPLETE ===")
    print("Check the 'logs' directory for saved log files:")
    print("  - logs/ap_automation.log (full log)")
    print("  - logs/errors.log (errors only)")
    print("\nTry running this script with different log levels to see the difference!")

if __name__ == "__main__":
    main()