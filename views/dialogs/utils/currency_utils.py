"""
Currency utility functions for parsing and formatting monetary values.
"""


class CurrencyUtils:
    """Utility class for currency parsing, formatting, and display operations."""
    
    @staticmethod
    def parse_money(s):
        """Parse a string into a float monetary value.
        
        Handles formats like: $1,234.56, (1234.56), 1234.56, $-1,234.56, -$1,234.56
        Returns None if parsing fails.
        """
        if not s:
            return None
        s = s.strip().replace(",", "")
        neg = False
        
        # Handle parentheses format: (1234.56)
        if s.startswith("(") and s.endswith(")"):
            neg = True
            s = s[1:-1]
        
        # Handle negative sign formats: -$1234.56 or $-1234.56
        if s.startswith("-$"):
            neg = True
            s = s[2:]  # Remove -$
        elif s.startswith("$-"):
            neg = True
            s = s[2:]  # Remove $-
        elif s.startswith("$"):
            s = s[1:]  # Remove $
        elif s.startswith("-"):
            neg = True
            s = s[1:]  # Remove -
            
        try:
            val = float(s)
            return -val if neg else val
        except ValueError:
            return None

    @staticmethod
    def parse_percent(s):
        """Parse a string into a decimal percentage value.
        
        Handles formats like: 15%, 15, 0.15
        Returns None if parsing fails.
        """
        if not s:
            return None
        s = s.strip()
        try:
            if s.endswith("%"):
                num = float(s[:-1])
                return num / 100.0
            num = float(s)
            return num / 100.0 if num > 1 else num
        except ValueError:
            return None

    @staticmethod
    def format_money(val):
        """Format a numeric value as currency string."""
        try:
            return f"${val:,.2f}"
        except Exception:
            return "$0.00"

    @staticmethod
    def money_to_plain(s: str) -> str:
        """Convert formatted money string to plain decimal format.
        
        Example: "$1,234.56" -> "1234.56"
        """
        if not s:
            return ""
        t = s.replace("$", "").replace(",", "").strip()
        neg = False
        if t.startswith("(") and t.endswith(")"):
            neg = True
            t = t[1:-1].strip()
        try:
            val = float(t)
            if neg:
                val = -val
            return f"{val:.2f}"
        except ValueError:
            return t

    @staticmethod
    def money_to_pretty(s: str) -> str:
        """Convert any money format to pretty formatted string.
        
        Example: "1234.56" -> "$1,234.56"
        """
        p = CurrencyUtils.money_to_plain(s)
        if p == "":
            return ""
        try:
            return f"${float(p):,.2f}"
        except ValueError:
            return s