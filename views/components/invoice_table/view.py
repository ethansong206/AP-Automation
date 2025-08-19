from __future__ import annotations

import os
from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QRect, QRectF, QPoint, QObject, QEvent
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainterPath, QRegion, QPalette
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QTableView,
    QMessageBox, QHeaderView, QAbstractItemView, QStyle, QStyleOptionButton
)

from .model import (
    InvoiceTableModel,
    InvoiceSortProxy,
    BODY_COLS,
    C_SELECT,
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
from .delegates import BodyEditDelegate, ActionsDelegate, SelectCheckboxDelegate


class RoundedClipper(QFrame):
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
        path.addRoundedRect(QRectF(rect), float(self._radius), float(self._radius))
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)


class SelectHeader(QHeaderView):
    """
    Header with a center-aligned checkbox in the Select column.
    Draws tri-state based on model.selection_stats() and toggles all on click.
    """
    def __init__(self, orientation: Qt.Orientation, parent=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setHighlightSections(False)

    def paintSection(self, painter, rect, logicalIndex):
        # draw the normal section first
        super().paintSection(painter, rect, logicalIndex)

        if logicalIndex != C_SELECT or rect.isEmpty():
                return

        # Checkbox state (tri-state) from the model
        opt = QStyleOptionButton()
        opt.state = QStyle.State_Enabled
        try:
            view: QTableView = self.parent()  # type: ignore
            proxy = view.model()
            model = proxy.sourceModel()
            selected, total = model.selection_stats()
        except Exception:
            selected, total = 0, 0

        if total == 0 or selected == 0:
            opt.state |= QStyle.State_Off
        elif selected == total:
            opt.state |= QStyle.State_On
        else:
            opt.state |= QStyle.State_NoChange  # partial

        # Size & position: use pixel metrics; center inside the header cell
        style = self.style()
        w = style.pixelMetric(QStyle.PM_IndicatorWidth, opt, self) or 16
        h = style.pixelMetric(QStyle.PM_IndicatorHeight, opt, self) or 16

        indicator_rect = QRect(0, 0, w, h)
        indicator_rect.moveCenter(rect.center())

        ind_opt = QStyleOptionButton(opt)
        ind_opt.rect = indicator_rect

        style.drawPrimitive(QStyle.PE_IndicatorCheckBox, ind_opt, painter, self)
        
    def mousePressEvent(self, event):
        idx = self.logicalIndexAt(event.pos())
        if idx == C_SELECT:
            view: QTableView = self.parent()  # type: ignore
            proxy = view.model()
            model = proxy.sourceModel()
            selected, total = model.selection_stats()
            select_all = not (total > 0 and selected == total)
            model.set_all_selected(select_all)
            self.viewport().update()
            return
        super().mousePressEvent(event)


class InvoiceTable(QWidget):
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

        # Use custom header with Select-All checkbox
        header = SelectHeader(Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(header)

        # Increase body (data) font by ~+4pt
        body_font = self.table.font()
        if body_font.pointSizeF() > 0:
            body_font.setPointSizeF(body_font.pointSizeF() + 4.0)
        else:
            body_font.setPixelSize(max(body_font.pixelSize() + 6, 14))
        self.table.setFont(body_font)
        metrics = self.table.fontMetrics()
        row_h = max(32, metrics.height() + 12)

        # Icon font ~25% larger than body (used for actions glyphs)
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

        # Clipper
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
                border: 2px solid #C4CAD3;
                border-radius: 16px;
            }
            QFrame#RoundedClipper { background: transparent; }

            QTableView#InvoiceQTableView {
                background: transparent;
                border: none;
                gridline-color: #EEF1F4;
                selection-background-color: #E6F2FF;
                selection-color: #000000;
            }
            QTableView#InvoiceQTableView::item { border: none; }
            QTableView#InvoiceQTableView QLineEdit,
            QTableView#InvoiceQTableView QTextEdit,
            QTableView#InvoiceQTableView QPlainTextEdit {
                background: #FFFFFF;
                color: #000000;
                padding: 0 4px;
            }

            QHeaderView::section {
                background: #FFFFFF;
                padding: 6px;
                border: none;
                border-bottom: 1px solid #E0E4EA;
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

        # Keep header checkbox in sync with row selection changes
        self._model.dataChanged.connect(lambda *_: header.viewport().update())
        self._model.modelReset.connect(lambda: header.viewport().update())
        self._model.rowsInserted.connect(lambda *_: header.viewport().update())
        self._model.rowsRemoved.connect(lambda *_: header.viewport().update())

        # Zebra via palette
        pal = self.table.palette()
        pal.setColor(QPalette.AlternateBase, QColor("#F1F4F8"))
        self.table.setPalette(pal)

        # View behavior
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked | QAbstractItemView.EditKeyPressed)
        self.table.verticalHeader().setVisible(False)
        self.table.setCornerButtonEnabled(False)
        self.table.setMouseTracking(True)

        # Compatibility with legacy controller code
        self.manually_edited = set()

        # Column sizing: body stretch; select fixed; actions to contents
        hdr = self.table.horizontalHeader()
        hdr.setDefaultSectionSize(120)
        hdr.setMinimumSectionSize(24)
        for c in BODY_COLS:
            hdr.setSectionResizeMode(c, QHeaderView.Stretch)

        # Select column (checkboxes) – fixed narrow width
        hdr.setSectionResizeMode(C_SELECT, QHeaderView.Fixed)
        hdr.resizeSection(C_SELECT, 36)

        # Actions: size to contents
        hdr.setSectionResizeMode(C_ACTIONS, QHeaderView.ResizeToContents)

        # Delegates
        self._select_delegate = SelectCheckboxDelegate(self.table)
        self.table.setItemDelegateForColumn(C_SELECT, self._select_delegate)

        self._actions_delegate = ActionsDelegate(self.table, self._icon_font)
        self.table.setItemDelegateForColumn(C_ACTIONS, self._actions_delegate)
        self._actions_delegate.editClicked.connect(self._emit_manual_entry)
        self._actions_delegate.deleteClicked.connect(self._handle_delete_clicked)

        # Body editor delegate
        self._body_delegate = BodyEditDelegate(self.table)
        for c in BODY_COLS:
            self.table.setItemDelegateForColumn(c, self._body_delegate)

        # Edits → compatibility signals
        self._model.rawEdited.connect(self._bubble_edit_signal)

        # ---------- Drag-to-select across the Select column ----------
        self._drag_active = False          # are we currently dragging in select column?
        self._drag_check_value: Optional[bool] = None  # True to check, False to uncheck
        self.table.viewport().installEventFilter(self)

    # ------------------- New: event filter for drag-to-select -------------------
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.table.viewport():
            if event.type() == QEvent.MouseButtonPress and event.buttons() & Qt.LeftButton:
                idx = self.table.indexAt(event.pos())
                if idx.isValid() and idx.column() == C_SELECT:
                    self._drag_active = True
                    # Determine desired state based on the starting row
                    src = self._proxy.mapToSource(idx)
                    cur_state = self._model.data(self._model.index(src.row(), C_SELECT), Qt.CheckStateRole)
                    self._drag_check_value = (cur_state != Qt.Checked)  # flip: if unchecked → check, else uncheck
                    # Apply to the first row immediately
                    new_state = Qt.Checked if self._drag_check_value else Qt.Unchecked
                    if cur_state != new_state:
                        self._model.setData(self._model.index(src.row(), C_SELECT), new_state, Qt.CheckStateRole)
                    return True

            elif event.type() == QEvent.MouseMove and self._drag_active:
                idx = self.table.indexAt(event.pos())
                if idx.isValid() and idx.column() == C_SELECT:
                    src = self._proxy.mapToSource(idx)
                    target_state = Qt.Checked if self._drag_check_value else Qt.Unchecked
                    cur_state = self._model.data(self._model.index(src.row(), C_SELECT), Qt.CheckStateRole)
                    if cur_state != target_state:
                        self._model.setData(self._model.index(src.row(), C_SELECT), target_state, Qt.CheckStateRole)
                return True

            elif event.type() in (QEvent.MouseButtonRelease, QEvent.Leave):
                # End drag mode
                if self._drag_active:
                    self._drag_active = False
                    self._drag_check_value = None
                    return True

        return super().eventFilter(obj, event)

    # ------------------- Search / filter passthrough -------------------
    def set_search_text(self, text: str):
        self._proxy.set_text_filter(text or "")

    def set_flagged_only(self, on: bool):
        self._proxy.set_flagged_only(bool(on))

    def set_incomplete_only(self, on: bool):
        self._proxy.set_incomplete_only(bool(on))

    # ------------------- Existing public API (unchanged) -----------------
    def add_row(self, row_data: List[str], file_path: str, is_no_ocr: bool = False):
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

    # ---------------------------------------------------------
    # Signal bubbling / helpers
    # ---------------------------------------------------------
    def _bubble_edit_signal(self, src_row: int, src_col: int):
        view_row = self._source_to_view_row(src_row)
        view_col = src_col
        self.cell_manually_edited.emit(view_row, view_col)
        self.cellChanged.emit(view_row, view_col)

    def _emit_manual_entry(self, src_row: int):
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
