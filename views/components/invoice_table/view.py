from __future__ import annotations

import os
from typing import List

from PyQt5.QtCore import Qt, pyqtSignal, QRectF
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainterPath, QRegion, QPalette
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QTableView,
    QMessageBox, QHeaderView, QAbstractItemView
)

from .model import (
    InvoiceTableModel,
    InvoiceSortProxy,
    BODY_COLS,
    C_FLAG,
    C_ACTIONS,
    C_VENDOR,
    C_INVOICE,
    C_PO,
    C_INV_DATE,
    C_TERMS,
    C_DUE,
    C_DISC_TOTAL,
    C_TOTAL,
)
from .delegates import BodyEditDelegate, FlagDelegate, ActionsDelegate

class RoundedClipper(QFrame):
    """Child frame that clips its contents to a rounded rect so children
    (the table) don't bleed under the parent's rounded corners."""
    def __init__(self, radius: int = 17, parent=None):
        super().__init__(parent)
        self._radius = radius
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setContentsMargins(0, 0, 0, 0)
        self.setObjectName("RoundedClipper")

    def setRadius(self, r: int):
        self._radius = r
        self._updateMask()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._updateMask()

    def _updateMask(self):
        rect = self.rect()
        if rect.isEmpty():
            return
        path = QPainterPath()
        # Use QRectF + float radii to satisfy overload
        path.addRoundedRect(QRectF(rect), float(self._radius), float(self._radius))
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)


# =============================================================
# Public View Wrapper (compat API)
# =============================================================
class InvoiceTable(QWidget):
    """
    Public-facing widget that:
      - exposes the same API/signals as the former QTableWidget version,
      - renders a QTableView inside a rounded, bordered mini-card,
      - wires model + proxy + delegates.
    """
    # Signals preserved for controller wiring
    row_deleted = pyqtSignal(int, str)              # (view_row, file_path)
    source_file_clicked = pyqtSignal(str)           # file_path
    manual_entry_clicked = pyqtSignal(int, object)  # (view_row, button=None)
    cell_manually_edited = pyqtSignal(int, int)     # (view_row, view_col)
    cellChanged = pyqtSignal(int, int)              # mirror QTableWidget cellChanged

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- Outer mini-card container ---
        self._card = QFrame(self)
        self._card.setObjectName("TableCard")
        self._card.setFrameShape(QFrame.NoFrame)
        self._card.setGraphicsEffect(None)  # no shadow per latest design

        # QTableView itself
        self.table = QTableView(self._card)
        self.table.setObjectName("InvoiceQTableView")
        
        # Increase body (data) font by ~+4pt
        body_font = self.table.font()
        if body_font.pointSizeF() > 0:
            body_font.setPointSizeF(body_font.pointSizeF() + 4.0)
        else:
            body_font.setPixelSize(max(body_font.pixelSize() + 6, 14))
        self.table.setFont(body_font)
        metrics = self.table.fontMetrics()
        row_h = max(32, metrics.height() + 12)

        # Icon font ~25% larger than body (used for flag + action glyphs)
        self._icon_font = QFont(body_font)
        if self._icon_font.pointSizeF() > 0:
            self._icon_font.setPointSizeF(self._icon_font.pointSizeF() * 1.25)
        else:
            self._icon_font.setPixelSize(int(max(int(body_font.pixelSize() * 1.25), body_font.pixelSize() + 3)))

        icon_metrics = QFontMetrics(self._icon_font)
        row_h = max(row_h, icon_metrics.height() + 12)
        self.table.verticalHeader().setDefaultSectionSize(row_h)

        # Layout: main → card → clipper → table
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._card)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)

        # Clipper ensures the table is hard-clipped to rounded corners
        self._clipper = RoundedClipper(radius=17, parent=self._card)
        self._clipper.setStyleSheet("background: transparent;")
        card_layout.addWidget(self._clipper)

        inner = QVBoxLayout(self._clipper)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.addWidget(self.table)
        self.table.setViewportMargins(0, 0, 0, 0)

        # Styling
        self.setStyleSheet(
            """
            QFrame#TableCard {
                background: #FFFFFF;
                border: 2px solid #C4CAD3;   /* thicker, slightly darker gray border */
                border-radius: 16px;
            }
            QFrame#RoundedClipper { background: transparent; }

            QTableView#InvoiceQTableView {
                background: transparent;        /* shows white below */
                border: none;
                gridline-color: #EEF1F4;
                selection-background-color: #E6F2FF;
                selection-color: #000000;
                /* alternate row color handled via palette AlternateBase */
            }
            QTableView#InvoiceQTableView::item { border: none; }
            
            /* Ensure editors are opaque so typed text doesn't overlap with painted text */
            QTableView#InvoiceQTableView QLineEdit,
            QTableView#InvoiceQTableView QTextEdit,
            QTableView#InvoiceQTableView QPlainTextEdit {
                background: #FFFFFF;
                color: #000000;
                padding: 0 4px;
            }

            QHeaderView::section {
                background: #FFFFFF;            /* white header */
                padding: 6px;
                border: none;
                border-bottom: 1px solid #E0E4EA; /* divider */
            }
            QTableCornerButton::section {
                background: #FFFFFF;
                border: none;
                border-bottom: 1px solid #E0E4EA;
                border-right: 1px solid #E0E4EA;
            }
            """
        )

        # Model + Proxy
        self._model = InvoiceTableModel(self)
        self._proxy = InvoiceSortProxy(self)
        self._proxy.setSourceModel(self._model)
        self.table.setModel(self._proxy)

        # Zebra rows via palette so model BackgroundRole (e.g., yellow empties) still wins
        pal = self.table.palette()
        pal.setColor(QPalette.AlternateBase, QColor("#F1F4F8"))  # slightly darker than before
        self.table.setPalette(pal)

        # View behavior
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableView.SelectItems)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked | QAbstractItemView.EditKeyPressed)
        self.table.verticalHeader().setVisible(False)   # hide row numbers
        self.table.setCornerButtonEnabled(False)        # hide corner button
        self.table.setMouseTracking(True)

        # Compatibility with legacy controller code
        self.manually_edited = set()

        # Columns: stretch body to fill; keep flag/actions compact
        header = self.table.horizontalHeader()
        header.setDefaultSectionSize(120)
        header.setMinimumSectionSize(24)
        for c in BODY_COLS:
            header.setSectionResizeMode(c, QHeaderView.Stretch)
        # Make flag column square: fix width to current row height and keep in sync
        header.setSectionResizeMode(C_FLAG, QHeaderView.Fixed)
        header.resizeSection(C_FLAG, row_h)
        self.table.verticalHeader().sectionResized.connect(self._on_row_height_changed)
        # Actions auto-size
        header.setSectionResizeMode(C_ACTIONS, QHeaderView.ResizeToContents)

        # Delegates
  # base stripe for all cells

        self._flag_delegate = FlagDelegate(self.table, self._icon_font)
        self.table.setItemDelegateForColumn(C_FLAG, self._flag_delegate)

        self._actions_delegate = ActionsDelegate(self.table, self._icon_font)
        self.table.setItemDelegateForColumn(C_ACTIONS, self._actions_delegate)
        self._actions_delegate.editClicked.connect(self._emit_manual_entry)
        self._actions_delegate.deleteClicked.connect(self._handle_delete_clicked)

        # Body editor delegate: opaque editors + no underlying paint while editing
        self._body_delegate = BodyEditDelegate(self.table)
        for c in BODY_COLS:
            self.table.setItemDelegateForColumn(c, self._body_delegate)

        # Edits → compatibility signals
        self._model.rawEdited.connect(self._bubble_edit_signal)

    # ---------------------------------------------------------
    # Signal bubbling / helpers
    # ---------------------------------------------------------
    def _on_row_height_changed(self, logical_index: int, old_size: int, new_size: int):
        # Keep the flag column square by matching its width to the row height
        self.table.horizontalHeader().resizeSection(C_FLAG, new_size)

    
    def _bubble_edit_signal(self, src_row: int, src_col: int):
        view_row = self._source_to_view_row(src_row)
        view_col = src_col
        self.cell_manually_edited.emit(view_row, view_col)
        self.cellChanged.emit(view_row, view_col)

    def _emit_manual_entry(self, src_row: int):
        # placeholder for button param to keep signature
        self.manual_entry_clicked.emit(self._source_to_view_row(src_row), None)

    def _handle_delete_clicked(self, src_row: int):
        file_path = self._model.get_file_path(src_row)
        confirm = QMessageBox.question(
            self, "Delete Row", "Are you sure you want to delete this row?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            view_row = self._source_to_view_row(src_row)
            self._model.remove_row(src_row)
            self.row_deleted.emit(view_row, file_path)

    def _open_source_file(self, vrow: int):
        src_row = self._view_to_source_row(vrow)
        if src_row < 0:
            return
        path = self._model.get_file_path(src_row)
        if path:
            self.source_file_clicked.emit(path)

    def update_calculated_field(self, view_row: int, col: int, value: str, force: bool = True):
        """Compatibility method used by the legacy controller:
        write a computed value into the model at (row, col)."""
        src = self._view_to_source_row(view_row)
        if src < 0:
            return
        idx = self._model.index(src, col)
        self._model.setData(idx, value, Qt.EditRole)

    # ---------------------------------------------------------
    # Public API (compat with your existing code)
    # ---------------------------------------------------------
    def add_row(self, row_data: List[str], file_path: str, is_no_ocr: bool = False):
        """row_data = [vendor, invoice, po, inv_date, terms, due, disc_total, total]"""
        self._model.add_row(row_data, file_path)

    def update_row_by_source(self, file_path: str, row_values: List[str]):
        self._model.update_row_by_source(file_path, row_values)

    def get_file_path_for_row(self, view_row: int) -> str:
        src = self._view_to_source_row(view_row)
        return "" if src < 0 else self._model.get_file_path(src)

    def get_cell_text(self, view_row: int, col: int) -> str:
        src = self._view_to_source_row(view_row)
        if src < 0:
            return ""
        # Return RAW (no superscript) for export/save
        vals = self._model.row_values(src)
        mapping = {
            C_VENDOR: 0, C_INVOICE: 1, C_PO: 2, C_INV_DATE: 3,
            C_TERMS: 4, C_DUE: 5, C_DISC_TOTAL: 6, C_TOTAL: 7
        }
        if col in mapping:
            return vals[mapping[col]] or ""
        return ""

    def is_row_flagged(self, view_row: int) -> bool:
        src = self._view_to_source_row(view_row)
        return False if src < 0 else self._model.get_flag(src)

    def toggle_row_flag(self, view_row: int):
        src = self._view_to_source_row(view_row)
        if src >= 0:
            self._model.set_flag(src, not self._model.get_flag(src))

    def find_row_by_file_path(self, file_path: str) -> int:
        abs_target = os.path.abspath(file_path or "")
        for i in range(self._model.rowCount()):
            if os.path.abspath(self._model.get_file_path(i) or "") == abs_target:
                return self._source_to_view_row(i)
        return -1

    def delete_row_by_file_path(self, file_path: str, confirm: bool = False) -> bool:
        abs_target = os.path.abspath(file_path or "")
        for i in range(self._model.rowCount()):
            if os.path.abspath(self._model.get_file_path(i) or "") == abs_target:
                if confirm:
                    ans = QMessageBox.question(
                        self, "Delete Row", "Are you sure you want to delete this row?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if ans != QMessageBox.Yes:
                        return False
                view_row = self._source_to_view_row(i)
                self._model.remove_row(i)
                self.row_deleted.emit(view_row, file_path)
                return True
        return False

    def clear_tracking_data(self):
        for i in range(self._model.rowCount()):
            self._model._rows[i].edited_cells.clear()
        self._model._rebuild_duplicates()

    def cleanup_row_data(self, row: int):
        # compatibility no-op; keep for callers that expect it
        pass

    # Qt-style helpers mirrored
    def rowCount(self) -> int:
        return self._proxy.rowCount()

    def setRowCount(self, n: int):
        if n == 0:
            self._model.clear()

    def removeRow(self, view_row: int):
        src = self._view_to_source_row(view_row)
        if src >= 0:
            self._model.remove_row(src)

    def selectedIndexes(self):
        return self.table.selectedIndexes()

    # Mapping helpers
    def _view_to_source_row(self, vrow: int) -> int:
        if vrow < 0 or vrow >= self._proxy.rowCount():
            return -1
        src = self._proxy.mapToSource(self._proxy.index(vrow, 0))
        return src.row()

    def _source_to_view_row(self, srow: int) -> int:
        if srow < 0 or srow >= self._model.rowCount():
            return -1
        v = self._proxy.mapFromSource(self._model.index(srow, 0))
        return v.row()