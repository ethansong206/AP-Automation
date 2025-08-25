"""File handling controller for invoice processing."""
import os
import subprocess
import logging

from PyQt5.QtWidgets import QApplication, QMessageBox, QProgressDialog
from PyQt5.QtCore import Qt
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
            logging.info("No new files to process.")
            return False

        logging.info("Processing %d new files...", len(new_files))
        progress = QProgressDialog("Processing files...", "Cancel", 0, len(new_files), self.main_window)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        results = []
        for i, file in enumerate(new_files, 1):
            if progress.wasCanceled():
                break

            text_blocks = extract_text_data_from_pdfs([file])
            extracted = extract_fields(text_blocks)
            data = extracted[0] if extracted else []
            results.append((data, file))
            self.loaded_files.add(os.path.normpath(file))

            progress.setValue(i)
            QApplication.processEvents()

        progress.close()
        return results
        
    def filter_new_files(self, files):
        """Filter out already processed files."""
        new_files = []
        for file in files:
            norm_path = os.path.normpath(file)
            if norm_path not in self.loaded_files:
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
        if not file_path:
            return False
        norm = os.path.normpath(file_path)
        if norm in self.loaded_files:
            self.loaded_files.remove(norm)
            return True
        return False
    
    def clear_all_files(self):
        """Clear all loaded files."""
        self.loaded_files.clear()

    def load_saved_files(self, files):
        """Load previously saved file paths into the controller."""
        if not files:
            self.loaded_files.clear()
            return
        self.loaded_files = {os.path.normpath(f) for f in files if f}