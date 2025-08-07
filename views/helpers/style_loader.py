"""Style loading utilities for the application."""
import os

def load_stylesheet(filename):
    """Load a QSS stylesheet from a file.
    
    Args:
        filename (str): The path to the QSS file
        
    Returns:
        str: The stylesheet content or empty string if file not found
    """
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"[ERROR] Failed to load stylesheet {filename}: {e}")
        return ""

def get_style_path(style_name):
    """Get the full path for a style in the styles directory.
    
    Args:
        style_name (str): Name of the style file (with or without .qss extension)
        
    Returns:
        str: Full path to the style file
    """
    # Ensure style has .qss extension
    if not style_name.lower().endswith('.qss'):
        style_name += '.qss'
        
    # Get the directory where views module is located
    views_dir = os.path.dirname(os.path.dirname(__file__))
    
    # Build path to the style file
    return os.path.join(views_dir, 'styles', style_name)