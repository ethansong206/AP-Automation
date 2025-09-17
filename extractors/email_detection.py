"""
Helper functions for detecting if a PDF was generated from an email.
"""

def is_email_format(words):
    """
    Determine if a PDF was generated from a downloaded email based on text content.
    
    Args:
        words: List of word dictionaries from PDF extraction
        
    Returns:
        bool: True if the document appears to be from an email
    """
    if not words:
        return False
    
    # Create text blob for analysis (only check first 500 characters for efficiency)
    raw_text = " ".join([w["text"] for w in words])[:500]
    text_lower = raw_text.lower()
    
    # Very specific email client indicators (must appear at start of document)
    email_client_indicators = [
        "outlook",           # Outlook email client
        "gmail",             # Gmail
        "thunderbird",       # Thunderbird
        "apple mail",        # Apple Mail
        "yahoo mail",        # Yahoo Mail
    ]
    
    # Email header patterns that are very specific to email format
    email_header_patterns = [
        r'\bfrom\s+[^<]*<[^>]+@[^>]+>',     # "From Name <email@domain.com>"
        r'\bto\s+[^<]*<[^>]+@[^>]+>',       # "To Name <email@domain.com>"
        r'\bsent:\s+\w+\s+\d+/\d+/\d+',     # "Sent: Wed 8/27/2025"
        r'\bdate\s+\w+\s+\d+/\d+/\d+\s+\d+:\d+',  # "Date Wed 8/27/2025 10:00"
    ]
    
    import re
    
    # Check for email client at beginning of document
    has_email_client = any(indicator in text_lower[:50] for indicator in email_client_indicators)
    
    # Check for email header patterns
    header_pattern_count = sum(1 for pattern in email_header_patterns 
                              if re.search(pattern, text_lower, re.IGNORECASE))
    
    # Must have email client AND at least 2 header patterns for high confidence
    if has_email_client and header_pattern_count >= 2:
        return True
    
    # Alternative: Look for very specific email forwarding pattern
    forwarding_patterns = [
        r'forwarded message',
        r'original message',
        r'begin forwarded message',
    ]
    
    if any(re.search(pattern, text_lower, re.IGNORECASE) for pattern in forwarding_patterns):
        return True
    
    return False


def get_email_context_info(words):
    """
    Extract email-specific context information from words.
    
    Args:
        words: List of word dictionaries from PDF extraction
        
    Returns:
        dict: Email context information including sender, recipient, date, etc.
    """
    if not words:
        return {}
    
    raw_text = " ".join([w["text"] for w in words])
    context = {}
    
    import re
    
    # Extract email addresses
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, raw_text)
    if emails:
        context['email_addresses'] = emails
    
    # Extract From field
    from_match = re.search(r'from\s+[^<]*<([^>]+)>', raw_text, re.IGNORECASE)
    if from_match:
        context['from_email'] = from_match.group(1)
    
    # Extract To field  
    to_match = re.search(r'to\s+[^<]*<([^>]+)>', raw_text, re.IGNORECASE)
    if to_match:
        context['to_email'] = to_match.group(1)
    
    # Check if it's an Outlook email
    if 'outlook' in raw_text.lower():
        context['email_client'] = 'Outlook'
    
    return context