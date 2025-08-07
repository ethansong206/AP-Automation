"""File handling controller for invoice processing."""
import os
import subprocess

from PyQt5.QtWidgets import QMessageBox
from pdf_reader import extract_text_data_from_pdfs
from extractor import extract_fields

class FileController:
    """Controller for file operations."""
    
    def __init__(self, main_window):
        """Initialize with reference to main window."""
        self.main_window = main_window
        self.loaded_files = set()
    
    def process_files(self, pdf_paths):
        """Process PDF files and add them to the table."""
        new_files = self.filter_new_files(pdf_paths)
        if not new_files:
            print("[INFO] No new files to process.")
            return False

        print(f"[INFO] Processing {len(new_files)} new files...")
        self.loaded_files.update(new_files)
        
        text_blocks = extract_text_data_from_pdfs(new_files)
        extracted_data = extract_fields(text_blocks)
        
        # Return data to be handled by the view
        return list(zip(extracted_data, new_files))
        
    def filter_new_files(self, files):
        """Filter out already processed files."""
        # Normalize paths for comparison
        normalized_loaded = {os.path.normpath(f) for f in self.loaded_files}
        new_files = []
        
        for file in files:
            norm_path = os.path.normpath(file)
            if norm_path not in normalized_loaded:
                new_files.append(file)
        
        return new_files
    
    def open_file(self, file_path):
        """Open a file with the system's default application."""
        if not os.path.isfile(file_path):
            QMessageBox.warning(
                self.main_window, 
                "File Not Found", 
                f"The file does not exist:\n{file_path}"
            )
            return False
        
        try:
            if os.name == 'nt':
                os.startfile(file_path)
            elif os.name == 'posix':
                subprocess.call(('open', file_path))
            else:
                subprocess.call(('xdg-open', file_path))
            return True
        except Exception as e:
            QMessageBox.critical(
                self.main_window, 
                "Error", 
                f"Failed to open file:\n{e}"
            )
            return False
    
    def remove_file(self, file_path):
        """Remove a file from the loaded files list."""
        if file_path in self.loaded_files:
            self.loaded_files.remove(file_path)
            return True
        return False
    
    def clear_all_files(self):
        """Clear all loaded files."""
        self.loaded_files.clear()