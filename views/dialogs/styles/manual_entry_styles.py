"""
Stylesheet definitions for Manual Entry Dialog.
Centralized styling to reduce code duplication and improve maintainability.
"""

from views.app_shell import THEME
import os

try:
    from views.app_shell import _resolve_icon
except ImportError:
    try:
        from app_shell import _resolve_icon
    except ImportError:
        def _resolve_icon(name):
            return os.path.join("assets", "icons", name)


class ManualEntryStyles:
    """Centralized styling for Manual Entry Dialog components."""
    
    def __init__(self, dpi_scale=1.0, min_width=1200, min_height=850):
        self.dpi_scale = dpi_scale
        self.min_width = min_width
        self.min_height = min_height
        
        # Calculate DPI-scaled dimensions
        self.border_radius = max(4, int(6 * dpi_scale))
        self.padding_sm = max(6, int(8 * dpi_scale))
        self.padding_md = max(8, int(12 * dpi_scale))
        self.padding_lg = max(12, int(15 * dpi_scale))
        self.min_input_height = max(16, int(min_height * 0.02))
        
        # Get arrow icon for dropdowns
        self.arrow_icon = _resolve_icon("down_arrow.svg").replace(os.sep, "/")
        
    def get_base_dialog_styles(self):
        """Get comprehensive base dialog styles that apply globally."""
        base_font_size = max(12, int(14 * self.dpi_scale))
        large_font_size = max(16, int(20 * self.dpi_scale))
        
        return f"""
            QLabel {{ font-size: {base_font_size}px; }}
            
            /* Override global QDialog QLabel rules that might add unwanted spacing */
            QDialog QLabel#InvoiceDetailsTitle {{
                margin: 0px !important;
                padding: 0px !important;
                font-weight: bold !important;
            }}
            
            /* Aggressive override for Invoice Details title to eliminate all spacing */
            QLabel#InvoiceDetailsTitle {{
                margin: 0px !important;
                padding: 0px !important;
                border: none !important;
                background: transparent !important;
                line-height: 1.0 !important;
                qproperty-wordWrap: false;
                qproperty-indent: 0;
                qproperty-margin: 0;
                min-height: 0px !important;
                max-height: none !important;
            }}
            
            
            /* Input fields with white background - using specific selectors and !important */
            ManualEntryDialog QLineEdit,
            ManualEntryDialog QComboBox,
            ManualEntryDialog QDateEdit {{
                font-size: {base_font_size}px !important; 
                padding: 8px 12px !important; 
                background-color: #FFFFFF !important;
                color: #000000 !important;
                border: 1px solid {THEME['card_border']} !important;
                border-radius: 6px !important;
                min-height: 20px !important;
                selection-background-color: {THEME['brand_green']} !important;
                selection-color: white !important;
            }}
            
            /* GLOBAL ComboBox dropdown styling to ensure it always appears */
            ManualEntryDialog QComboBox {{
                padding-right: 30px !important;
            }}
            ManualEntryDialog QComboBox::drop-down {{
                subcontrol-origin: padding !important;
                subcontrol-position: top right !important;
                width: 28px !important;
                border-left: 2px solid {THEME['card_border']} !important;
                border-top-right-radius: 6px !important;
                border-bottom-right-radius: 6px !important;
                background-color: #FFFFFF !important;
                padding-right: 8px !important;
                margin: 0 !important;
            }}
            ManualEntryDialog QComboBox::drop-down:hover {{
                background-color: #e0e0e0 !important;
            }}
            ManualEntryDialog QComboBox::drop-down:pressed {{
                background-color: #d0d0d0 !important;
            }}
            ManualEntryDialog QComboBox::down-arrow {{
                image: url({self.arrow_icon}) !important;
                width: {max(10, int(12 * self.dpi_scale))}px !important;
                height: {max(10, int(12 * self.dpi_scale))}px !important;
                subcontrol-origin: padding !important;
                subcontrol-position: center !important;
            }}
            
            /* Additional specific overrides for problematic elements */
            /* Exclude calendar widgets from global styling */
            QWidget QLineEdit:not(QCalendarWidget QLineEdit),
            QWidget QComboBox:not(QCalendarWidget QComboBox), 
            QWidget QDateEdit:not(QCalendarWidget QDateEdit) {{
                background-color: #FFFFFF !important;
                color: #000000 !important;
            }}
            
            /* Ensure calendar widgets are excluded from main styling */
            QCalendarWidget, QCalendarWidget * {{
                font-family: default;
                font-size: 9pt;
                background-color: white;
                color: black;
            }}
            
            ManualEntryDialog QLineEdit:focus, 
            ManualEntryDialog QComboBox:focus, 
            ManualEntryDialog QDateEdit:focus {{
                border-color: {THEME['brand_green']} !important;
                outline: none !important;
                background-color: #FFFFFF !important;
            }}
            
            ManualEntryDialog QComboBox QAbstractItemView {{
                background-color: #FFFFFF !important;
                color: #000000 !important;
                border: 1px solid {THEME['card_border']} !important;
                border-radius: {max(3, int(4 * self.dpi_scale))}px !important;
                selection-background-color: {THEME['brand_green']} !important;
                selection-color: white !important;
            }}
            
            QPushButton {{ 
                font-size: {base_font_size}px; 
                padding: {max(7, int(9 * self.dpi_scale))}px {max(12, int(15 * self.dpi_scale))}px; 
            }}
            
            QGroupBox {{ 
                font-size: {large_font_size}px; 
                font-weight: bold; 
                margin-top: 0px !important; 
                background-color: transparent;
                border: 1px solid {THEME['card_border']};
                border-radius: {self.padding_sm}px;
                padding-top: {max(8, int(10 * self.dpi_scale))}px;
            }}
            
            QGroupBox::title {{
                color: {THEME['brand_green']};
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                background-color: {THEME['outer_bg']};
            }}
        """
    
    def get_input_field_styles(self):
        """Get standard input field styles."""
        return f"""
            background-color: #FFFFFF;
            color: #000000;
            border: 1px solid {THEME['card_border']};
            border-radius: {self.border_radius}px;
            padding: {self.padding_sm}px {self.padding_md}px;
            min-height: {self.min_input_height}px;
        """
    
    def get_empty_field_style(self):
        """Get style for empty/required fields (yellow highlight)."""
        return f"""
            background-color: #FFF1A6;
            color: #000000;
            border: 1px solid {THEME['card_border']};
            border-radius: {self.border_radius}px;
            padding: {self.padding_sm}px {self.padding_md}px;
            min-height: {self.min_input_height}px;
        """
    
    def get_manual_edit_style(self):
        """Get style for manually edited fields (green highlight)."""
        return f"""
            background-color: #DCFCE7;
            color: #000000;
            border: 1px solid {THEME['card_border']};
            border-radius: {self.border_radius}px;
            padding: {self.padding_sm}px {self.padding_md}px;
            min-height: {self.min_input_height}px;
        """
    
    def get_primary_button_style(self):
        """Get primary button style (green buttons)."""
        btn_border_radius = max(3, int(4 * self.dpi_scale))
        btn_padding_v = max(7, int(9 * self.dpi_scale))
        btn_padding_h = max(12, int(15 * self.dpi_scale))
        
        return (
            f"QPushButton {{ background-color: #5E6F5E; color: white; border-radius: {btn_border_radius}px; "
            f"padding: {btn_padding_v}px {btn_padding_h}px; font-weight: bold; }} "
            "QPushButton:hover { background-color: #6b7d6b; } "
            "QPushButton:pressed { background-color: #526052; }"
        )
    
    def get_navigation_button_style(self):
        """Get navigation button style (arrow buttons with disabled state)."""
        nav_font_size = max(24, int(28 * self.dpi_scale))
        nav_padding = max(8, int(10 * self.dpi_scale))
        
        return (
            f"QPushButton {{ background-color: #5E6F5E; color: #f0f0f0; border: 1px solid #3E4F3E; "
            f"font-size: {nav_font_size}px; padding: {nav_padding}px; }} "
            "QPushButton:hover { background-color: #546454; } "
            "QPushButton:pressed { background-color: #485848; } "
            "QPushButton:disabled { background-color: #bbbbbb; color: #666666; }"
        )
    
    def get_delete_button_style(self):
        """Get delete button style (red button)."""
        delete_border_radius = max(3, int(4 * self.dpi_scale))
        delete_padding_v = max(7, int(9 * self.dpi_scale))
        delete_padding_h = max(12, int(15 * self.dpi_scale))
        delete_font_size = max(13, int(15 * self.dpi_scale))
        
        return (
            f"QPushButton {{ background-color: #C0392B; color: white; border-radius: {delete_border_radius}px; "
            f"padding: {delete_padding_v}px {delete_padding_h}px; font-weight: bold; font-size: {delete_font_size}px; }} "
            "QPushButton:hover { background-color: #A0311F; } "
            "QPushButton:pressed { background-color: #8B2914; }"
        )
    
    def get_window_control_button_style(self):
        """Get window control button style (minimize/maximize/close)."""
        return (
            "QToolButton#WinBtn { background: transparent; border: none; padding: 0; }"
            f"QToolButton#WinBtn:hover {{ background: rgba(0,0,0,0.06); border-radius: {self.border_radius}px; }}"
        )
    
    def get_title_style(self, font_size):
        """Get title label style (now handled by CSS - kept for compatibility)."""
        return f"color: {THEME['brand_green']} !important; font-size: {font_size}px !important; font-weight: bold !important;"
    
    def get_card_style(self):
        """Get card container style."""
        return f"""
            QFrame#LeftCard, QFrame#RightCard {{
                background: {THEME['card_bg']};
                border: 1px solid {THEME['card_border']};
                border-radius: {THEME['radius']}px;
            }}
        """
    
    def get_file_list_style(self):
        """Get file list widget style with zebra striping and viewed states."""
        return """
            QListWidget#FileListWidget {
                border: none;
                background: transparent;
                selection-background-color: rgba(6, 68, 32, 0.1);
                outline: none;
            }
            QListWidget#FileListWidget::item {
                padding: 8px 12px;
                border-radius: 6px;
                margin: 1px 0px;
            }
            QListWidget#FileListWidget::item:nth-child(even) {
                background-color: #F8F9FA;
            }
            QListWidget#FileListWidget::item:nth-child(odd) {
                background-color: transparent;
            }
            QListWidget#FileListWidget::item:hover {
                background-color: rgba(6, 68, 32, 0.05);
            }
            QListWidget#FileListWidget::item:selected {
                background-color: rgba(6, 68, 32, 0.1);
                border: 1px solid rgba(6, 68, 32, 0.2);
            }
        """
    
    def get_calendar_style(self):
        """Get calendar widget style (removes inherited styling)."""
        return """
            QCalendarWidget {
                font-family: default !important;
                font-size: default !important;
                color: default !important;
                background-color: default !important;
                border: default !important;
            }
            QCalendarWidget * {
                font-family: default !important;
                font-size: default !important;
                color: default !important;
                background-color: default !important;
                border: default !important;
            }
        """
    
    def get_splitter_style(self):
        """Get splitter handle style."""
        return """
            QSplitter::handle {
                background: transparent;
            }
            QSplitter::handle:horizontal {
                width: 2px;
                background: #ddd;
            }
            QSplitter::handle:vertical {
                height: 2px;
                background: #ddd;
            }
        """
    
    def get_toast_notification_style(self):
        """Get toast notification style (dark)."""
        toast_border_radius = max(3, int(4 * self.dpi_scale))
        toast_padding_v = max(2, int(3 * self.dpi_scale))
        toast_padding_h = max(6, int(8 * self.dpi_scale))
        
        return f"""
            QLabel {{
                background-color: rgba(0, 0, 0, 0.8);
                color: white;
                border-radius: {toast_border_radius}px;
                padding: {toast_padding_v}px {toast_padding_h}px;
                font-weight: bold;
            }}
        """
    
    def get_success_toast_style(self):
        """Get success toast notification style (green)."""
        toast_border_radius = max(3, int(4 * self.dpi_scale))
        toast_padding_v = max(2, int(3 * self.dpi_scale))
        toast_padding_h = max(6, int(8 * self.dpi_scale))
        
        return f"""
            QLabel {{
                background-color: #e7f5e7;
                color: #2f7a2f;
                border: 1px solid #b9e0b9;
                border-radius: {toast_border_radius}px;
                padding: {toast_padding_v}px {toast_padding_h}px;
                font-weight: bold;
            }}
        """
    
    def get_transparent_background_style(self):
        """Get transparent background style."""
        return "background: transparent;"