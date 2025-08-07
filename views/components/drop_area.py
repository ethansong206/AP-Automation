"""Custom drag-and-drop area for file uploads."""
import os
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QDragLeaveEvent
from PyQt5.QtCore import Qt, pyqtSignal

class FileDropArea(QFrame):
    """A professional-looking area for file browsing and drag-and-drop."""
    
    # Signal emitted when files are dropped or selected
    filesSelected = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("fileDropArea")
        
        # Set up the visual appearance
        self.setStyleSheet("""
            #fileDropArea {
                background-color: #f8f9fa;
                border: 2px dashed #adb5bd;
                border-radius: 10px;
                padding: 10px;  /* Reduced padding */
            }
            #fileDropArea[dragOver="true"] {
                border-color: #2E7D32;
                background-color: #e8f5e9;
            }
            QLabel {
                color: #495057;
            }
            #dropIcon {
                color: #2E7D32;
                font-size: 20px;  /* Reduced size */
            }
            #browseButton {
                background-color: #2E7D32;
                color: white;
                border-radius: 4px;
                padding: 4px 12px;  /* Reduced padding */
                font-weight: bold;
                min-width: 110px;
            }
            #browseButton:hover {
                background-color: #246428;
            }
        """)
        
        # Create layout with reduced spacing
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)  # Reduced margins
        layout.setSpacing(2)  # Reduced spacing between elements
        layout.setAlignment(Qt.AlignCenter)
        
        # Add drop icon
        self.icon_label = QLabel("📄")
        self.icon_label.setObjectName("dropIcon")
        self.icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.icon_label)
        
        # Add instruction text
        self.instruction = QLabel("Drop PDF files here")
        self.instruction.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.instruction)
        
        # Add "or" text
        self.or_label = QLabel("or")
        self.or_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.or_label)
        
        # Add browse button
        self.browse_button = QPushButton("Browse Files")
        self.browse_button.setObjectName("browseButton")
        self.browse_button.clicked.connect(self.browse_clicked)
        layout.addWidget(self.browse_button, 0, Qt.AlignCenter)
        
        # Default state
        self.setProperty("dragOver", False)
        self.setMinimumHeight(60)  # Reduced height by 2/3
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events."""
        if event.mimeData().hasUrls():
            self.setProperty("dragOver", True)
            self.style().unpolish(self)
            self.style().polish(self)
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event: QDragLeaveEvent):
        """Handle drag leave events."""
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)
        event.accept()
    
    def dropEvent(self, event: QDropEvent):
        """Handle drop events."""
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)
        
        if event.mimeData().hasUrls():
            files = [url.toLocalFile() for url in event.mimeData().urls()]
            pdf_files = [f for f in files if f.lower().endswith(".pdf")]
            if pdf_files:
                self.filesSelected.emit(pdf_files)
            event.acceptProposedAction()
    
    def browse_clicked(self):
        """Signal that browse button was clicked."""
        # Just emit the signal - the actual file dialog will be in the main window
        self.filesSelected.emit([])