"""Entry point for the AP Automation application."""
import sys
import logging
import traceback

from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
)
from PyQt5.QtGui import QFont

from ui import InvoiceApp  # Import from ui.py instead of views directly


class CrashDialog(QDialog):
    """Dialog to display uncaught exception details with copy support."""

    def __init__(self, message: str, details: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Unexpected Error")
        # Requested default size; user can resize larger as needed
        self.setMinimumSize(300, 150)

        layout = QVBoxLayout(self)

        # Short message
        lbl = QLabel(message, self)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        # Detailed traceback (selectable & copyable)
        self.text_edit = QTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.text_edit.setFont(QFont("Consolas", 9))
        self.text_edit.setPlainText(details)
        layout.addWidget(self.text_edit)

        # Buttons: Copy to Clipboard + Close
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self.copy_btn = QPushButton("Copy to Clipboard", self)
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        self.copy_btn.setShortcut("Ctrl+C")
        btn_row.addWidget(self.copy_btn)

        self.close_btn = QPushButton("Close", self)
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)

        layout.addLayout(btn_row)

    def copy_to_clipboard(self):
        QApplication.clipboard().setText(self.text_edit.toPlainText())


def handle_exception(exc_type, exc_value, exc_traceback):
    """Handle uncaught exceptions by logging, showing a dialog, then exiting."""
    if exc_type is KeyboardInterrupt:
        # Allow Ctrl+C to behave normally
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    formatted_trace = "".join(
        traceback.format_exception(exc_type, exc_value, exc_traceback)
    )
    logging.error("Uncaught exception:\n%s", formatted_trace)

    app = QApplication.instance()

    # If the crash happens very early (before app exists), spin up a temp app
    created_temp_app = False
    if app is None:
        app = QApplication(sys.argv)
        created_temp_app = True

    try:
        dlg = CrashDialog(
            message="An unexpected error occurred.",
            details=formatted_trace,
        )
        dlg.exec_()
    finally:
        # Ensure the process exits with a non-zero status after the dialog closes
        if created_temp_app:
            # No running event loop to quit—exit the process
            sys.exit(1)
        else:
            # Tell the existing event loop to exit
            QCoreApplication.exit(1)


USE_SHELL = True  # ⟵ flip to False anytime to compare with your normal window

def main():
    """Application entry point."""
    logging.basicConfig(level=logging.ERROR, format="%(asctime)s [%(levelname)s] %(message)s")
    sys.excepthook = handle_exception

    app = QApplication(sys.argv)

    if USE_SHELL:
        # import the shell (robust for both run-from-root and inside views/)
        try:
            from views.app_shell import AppShell
        except Exception:
            from app_shell import AppShell  # fallback if placed next to main.py

        # Wrap your existing main widget in the frameless shell
        win = AppShell(InvoiceApp)  # pass the factory (class) itself
        win.show()
        sys.exit(app.exec_())
    else:
        # Original path (no shell)
        invoice_app = InvoiceApp()
        invoice_app.show()
        sys.exit(app.exec_())

if __name__ == "__main__":
    main()