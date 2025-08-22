"""
Vendor Merge Conflict Resolution Dialog

Allows users to resolve conflicts when merging vendor data from the bundled
vendors.csv with their existing AppData/Roaming/vendors.csv file.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QGroupBox, QRadioButton, QButtonGroup, QScrollArea,
    QWidget, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

try:
    from views.app_shell import THEME
except ImportError:
    THEME = {
        "outer_bg": "#F2F3F5",
        "card_bg": "#FFFFFF", 
        "card_border": "#E1E4E8",
        "brand_green": "#064420"
    }


class VendorMergeDialog(QDialog):
    """Dialog for resolving vendor data merge conflicts."""
    
    def __init__(self, conflicts, parent=None):
        """
        Initialize the merge conflict dialog.
        
        Args:
            conflicts: List of conflict dictionaries with:
                - type: 'name_conflict' or 'number_conflict'
                - user_row: dict with user's vendor data
                - bundle_row: dict with bundled vendor data
                - reason: description of the conflict
        """
        super().__init__(parent)
        self.conflicts = conflicts
        self.resolutions = {}  # Will store user choices
        
        self.setWindowTitle("Vendor Data Merge Conflicts")
        self.setModal(True)
        self.setMinimumSize(800, 600)
        
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("Vendor Data Conflicts Found")
        title_font = QFont("Inter", 18, QFont.Bold)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {THEME['brand_green']}; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Description
        desc = QLabel(
            "The following vendor entries have conflicts between your existing data "
            "and the updated data from the application. Please choose which version "
            "to keep for each conflict."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; margin-bottom: 20px;")
        layout.addWidget(desc)
        
        # Scrollable conflict area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        conflicts_widget = QWidget()
        conflicts_layout = QVBoxLayout(conflicts_widget)
        conflicts_layout.setSpacing(16)
        
        # Create conflict resolution widgets
        for i, conflict in enumerate(self.conflicts):
            conflict_widget = self.create_conflict_widget(i, conflict)
            conflicts_layout.addWidget(conflict_widget)
            
        scroll.setWidget(conflicts_widget)
        layout.addWidget(scroll)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("""
            QPushButton { 
                background-color: #6c757d; 
                color: white; 
                border: none; 
                padding: 10px 20px; 
                border-radius: 6px; 
                font-weight: bold;
            }
            QPushButton:hover { background-color: #5a6268; }
        """)
        
        apply_btn = QPushButton("Apply Changes")
        apply_btn.clicked.connect(self.apply_changes)
        apply_btn.setStyleSheet(f"""
            QPushButton {{ 
                background-color: {THEME['brand_green']}; 
                color: white; 
                border: none; 
                padding: 10px 20px; 
                border-radius: 6px; 
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #053318; }}
        """)
        
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(apply_btn)
        layout.addLayout(button_layout)
        
    def create_conflict_widget(self, index, conflict):
        """Create a widget for a single conflict resolution."""
        # Main container
        container = QFrame()
        container.setFrameStyle(QFrame.Box)
        container.setStyleSheet(f"""
            QFrame {{ 
                background-color: {THEME['card_bg']}; 
                border: 1px solid {THEME['card_border']}; 
                border-radius: 8px; 
                padding: 16px;
            }}
        """)
        
        layout = QVBoxLayout(container)
        layout.setSpacing(12)
        
        # Conflict description
        conflict_title = QLabel(f"Conflict {index + 1}: {conflict['reason']}")
        conflict_title.setFont(QFont("Inter", 14, QFont.Bold))
        conflict_title.setStyleSheet(f"color: {THEME['brand_green']};")
        layout.addWidget(conflict_title)
        
        # Side-by-side comparison
        comparison_layout = QHBoxLayout()
        comparison_layout.setSpacing(20)
        
        # Left side - User's current data
        user_group = self.create_vendor_side(
            "Your Current Data", 
            conflict['user_row']
        )
        comparison_layout.addWidget(user_group)
        
        # Right side - Bundled data
        bundle_group = self.create_vendor_side(
            "Updated Application Data", 
            conflict['bundle_row']
        )
        comparison_layout.addWidget(bundle_group)
        
        layout.addLayout(comparison_layout)
        
        # Choice buttons
        choice_layout = QHBoxLayout()
        choice_layout.setSpacing(10)
        choice_layout.addStretch()
        
        # Create button group for radio buttons
        button_group = QButtonGroup(self)
        button_group.setExclusive(True)
        
        # Three choice options
        keep_user_btn = QRadioButton("Keep Your Data")
        keep_user_btn.setChecked(True)  # Default selection
        keep_user_btn.choice = f"user_{index}"
        keep_user_btn.setStyleSheet("font-weight: bold; padding: 8px; margin: 4px;")
        button_group.addButton(keep_user_btn)
        choice_layout.addWidget(keep_user_btn)
        
        keep_bundle_btn = QRadioButton("Keep App Data")
        keep_bundle_btn.choice = f"bundle_{index}"
        keep_bundle_btn.setStyleSheet("font-weight: bold; padding: 8px; margin: 4px;")
        button_group.addButton(keep_bundle_btn)
        choice_layout.addWidget(keep_bundle_btn)
        
        keep_both_btn = QRadioButton("Keep Both")
        keep_both_btn.choice = f"both_{index}"
        keep_both_btn.setStyleSheet("font-weight: bold; padding: 8px; margin: 4px; color: #064420;")
        button_group.addButton(keep_both_btn)
        choice_layout.addWidget(keep_both_btn)
        
        choice_layout.addStretch()
        layout.addLayout(choice_layout)
        
        # Store button group for later retrieval
        self.resolutions[index] = {
            'button_group': button_group,
            'conflict': conflict
        }
        
        return container
        
    def create_vendor_side(self, title, vendor_data):
        """Create one side of the vendor comparison."""
        group = QGroupBox(title)
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #ddd;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
            }
        """)
        
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        
        # Vendor details
        details_layout = QVBoxLayout()
        details_layout.setContentsMargins(10, 0, 0, 0)
        
        # Vendor Number
        vendor_no = vendor_data.get("Vendor No. (Sage)", "")
        if vendor_no:
            no_label = QLabel(f"<b>Vendor Number:</b> {vendor_no}")
        else:
            no_label = QLabel("<b>Vendor Number:</b> <i>Not specified</i>")
        no_label.setStyleSheet("color: #333; margin: 2px 0;")
        details_layout.addWidget(no_label)
        
        # Vendor Name
        vendor_name = vendor_data.get("Vendor Name", "")
        if vendor_name:
            name_label = QLabel(f"<b>Vendor Name:</b> {vendor_name}")
        else:
            name_label = QLabel("<b>Vendor Name:</b> <i>Not specified</i>")
        name_label.setStyleSheet("color: #333; margin: 2px 0;")
        details_layout.addWidget(name_label)
        
        # Identifier
        identifier = vendor_data.get("Identifier", "")
        if identifier:
            id_label = QLabel(f"<b>Identifier:</b> {identifier}")
        else:
            id_label = QLabel("<b>Identifier:</b> <i>None</i>")
        id_label.setStyleSheet("color: #666; margin: 2px 0;")
        details_layout.addWidget(id_label)
        
        layout.addLayout(details_layout)
        return group
        
    def apply_changes(self):
        """Apply the user's conflict resolutions."""
        # Validate that all conflicts have been resolved
        unresolved = []
        for index, resolution_data in self.resolutions.items():
            button_group = resolution_data['button_group']
            if not button_group.checkedButton():
                unresolved.append(index + 1)
                
        if unresolved:
            QMessageBox.warning(
                self,
                "Incomplete Selection",
                f"Please make a selection for conflict(s): {', '.join(map(str, unresolved))}"
            )
            return
            
        # Collect user choices
        self.user_choices = {}
        for index, resolution_data in self.resolutions.items():
            button_group = resolution_data['button_group']
            checked_button = button_group.checkedButton()
            choice = checked_button.choice  # 'user_X', 'bundle_X', or 'both_X'
            
            if choice.startswith('user_'):
                self.user_choices[index] = 'user'
            elif choice.startswith('bundle_'):
                self.user_choices[index] = 'bundle'
            elif choice.startswith('both_'):
                self.user_choices[index] = 'both'
                
        self.accept()
        
    def get_user_choices(self):
        """Get the user's conflict resolution choices."""
        return getattr(self, 'user_choices', {})