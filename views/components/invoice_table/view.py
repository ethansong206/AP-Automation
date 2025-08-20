from __future__ import annotations

import sys, os
from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QRect, QRectF, QPoint, QObject, QEvent
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainterPath, QRegion, QPalette, QPainter
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QTableView,
    QMessageBox, QHeaderView, QAbstractItemView, QStyle, QStyleOptionButton
)
from PyQt5.QtSvg import QSvgRenderer

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

def resource_path(*parts):
    """Return absolute path, working in dev and in PyInstaller .exe."""
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
    return os.path.join(base, *parts)

ASSETS_DIR = resource_path("assets", "icons")

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
    Header that paints a center-aligned SVG checkbox in the Select column.
    We draw in paintEvent AFTER base header painting so nothing can cover it.
    Only two states: unchecked / checked (partial is shown as unchecked).
    """
    def __init__(self, orientation: Qt.Orientation, parent=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setHighlightSections(False)

        # Load SVGs once
        self._svg_unchecked = QSvgRenderer(os.path.join(ASSETS_DIR, "checkbox_unchecked.svg"), self)
        self._svg_checked = QSvgRenderer(os.path.join(ASSETS_DIR, "checkbox_checked.svg"), self)

    # Qt5-safe viewport-relative section rect (replacement for sectionRect)
    def _section_rect(self, logicalIndex: int) -> QRect:
        if self.orientation() == Qt.Horizontal:
            x = self.sectionViewportPosition(logicalIndex)
            if x < 0:
                return QRect()
            w = self.sectionSize(logicalIndex)
            h = self.viewport().height()
            return QRect(x, 0, w, h)
        else:
            y = self.sectionViewportPosition(logicalIndex)
            if y < 0:
                return QRect()
            h = self.sectionSize(logicalIndex)
            w = self.viewport().width()
            return QRect(0, y, w, h)

    def _draw_header_checkbox(self, painter: QPainter, rect: QRect, checked: bool):
        # Scale SVG nicely inside the header cell with some padding
        target_size = max(16, min(22, rect.height() - 8))
        box = QRect(0, 0, target_size, target_size)
        box.moveCenter(rect.center())

        renderer = self._svg_checked if checked else self._svg_unchecked
        if renderer and renderer.isValid():
            renderer.render(painter, QRectF(box))
        else:
            # Fallback: minimal drawn box/check
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, True)
            border = QColor(46, 52, 64)
            painter.setPen(border)
            painter.setBrush(QColor("#F7F9FC"))
            painter.drawRect(box)
            if checked:
                p1 = box.topLeft() + QPoint(3, box.height() // 2)
                p2 = box.topLeft() + QPoint(box.width() // 2 - 1, box.height() - 3)
                p3 = box.topLeft() + QPoint(box.width() - 3, 4)
                painter.drawPolyline(p1, p2, p3)
            painter.restore()

    def paintEvent(self, event):
        # Let Qt draw the header first (background, text, borders)
        super().paintEvent(event)

        if self.orientation() != Qt.Horizontal or self.isSectionHidden(C_SELECT):
            return

        rect = self._section_rect(C_SELECT)
        if rect.isEmpty():
            return

        # Determine two-state value from the model (partial -> unchecked)
        opt = QStyleOptionButton()
        opt.state = QStyle.State_Enabled
        try:
            view = self.parent()           # QTableView
            proxy = view.model()           # Proxy
            model = proxy.sourceModel()    # Source
            selected, total = model.selection_stats()
        except Exception:
            selected, total = 0, 0

        checked = bool(total > 0 and selected == total)

        painter = QPainter(self.viewport())
        painter.setClipRect(rect)
        self._draw_header_checkbox(painter, rect, checked)

    def mousePressEvent(self, event):
        idx = self.logicalIndexAt(event.pos())
        view: QTableView = self.parent()  # type: ignore
        if idx == C_SELECT:
            proxy = view.model()
            model = proxy.sourceModel()
            selected, total = model.selection_stats()
            select_all = not (total > 0 and selected == total)
            model.set_all_selected(select_all)
            self.viewport().update()
            return
        
        # Manual sort cycling: desc → asc → default (insertion order)
        proxy = view.model()
        prev_col = getattr(proxy, "_sort_column", -1)
        prev_order = getattr(proxy, "_sort_order", Qt.AscendingOrder)

        if prev_col != idx:
            next_col, next_order, show_indicator = idx, Qt.DescendingOrder, True
        elif prev_order == Qt.DescendingOrder:
            next_col, next_order, show_indicator = idx, Qt.AscendingOrder, True
        elif prev_order == Qt.AscendingOrder:
            next_col, next_order, show_indicator = -1, Qt.AscendingOrder, False
        else:
            next_col, next_order, show_indicator = idx, Qt.DescendingOrder, True

        view.sortByColumn(next_col, next_order)
        if show_indicator:
            self.setSortIndicatorShown(True)
            self.setSortIndicator(next_col, next_order)
        else:
            self.setSortIndicatorShown(False)


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

        # Use custom header with Select-All SVG checkbox
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
        # Default: preserve insertion order with no sort indicator
        self.table.sortByColumn(-1, Qt.AscendingOrder)
        header.setSortIndicatorShown(False)

        # Keep header icon in sync with row selection changes
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
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked | QAbstractItemView.EditKeyPressed
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setCornerButtonEnabled(False)
        self.table.setMouseTracking(True)

        # Compatibility with legacy controller code
        self.manually_edited = set()

        # Column sizing: body stretch; select fixed; actions to contents
        hdr = self.table.horizontalHeader()
        hdr.setDefaultSectionSize(100)
        hdr.setMinimumSectionSize(24)
        for c in BODY_COLS:
            hdr.setSectionResizeMode(c, QHeaderView.Stretch)

        # Make discounted/total columns a bit narrower by default
        for c in (C_INV_DATE, C_DUE):
            hdr.setSectionResizeMode(c, QHeaderView.Interactive)
            hdr.resizeSection(c, 100)

        hdr.setSectionResizeMode(C_SELECT, QHeaderView.Fixed)
        hdr.resizeSection(C_SELECT, 36)

        hdr.setSectionResizeMode(C_ACTIONS, QHeaderView.Fixed)
        hdr.resizeSection(C_ACTIONS, 135)

        # Delegates
        self._select_delegate = SelectCheckboxDelegate(self.table)
        self.table.setItemDelegateForColumn(C_SELECT, self._select_delegate)

        self._actions_delegate = ActionsDelegate(self.table, self._icon_font)
        self.table.setItemDelegateForColumn(C_ACTIONS, self._actions_delegate)
        self._actions_delegate.editClicked.connect(self._emit_manual_entry)
        self._actions_delegate.deleteClicked.connect(self._handle_delete_clicked)

        self._body_delegate = BodyEditDelegate(self.table)
        for c in BODY_COLS:
            self.table.setItemDelegateForColumn(c, self._body_delegate)

        # Edits → compatibility signals
        self._model.rawEdited.connect(self._bubble_edit_signal)

        # ---------- Drag-to-select across the Select column ----------
        self._drag_active = False
        self._drag_check_value: Optional[bool] = None
        self.table.viewport().installEventFilter(self)

    # ------------------- Drag select behavior -------------------
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.table.viewport():
            if event.type() == QEvent.MouseButtonPress and event.buttons() & Qt.LeftButton:
                idx = self.table.indexAt(event.pos())
                if idx.isValid() and idx.column() == C_SELECT:
                    self._drag_active = True
                    src = self._proxy.mapToSource(idx)
                    cur_state = self._model.data(self._model.index(src.row(), C_SELECT), Qt.CheckStateRole)
                    self._drag_check_value = (cur_state != Qt.Checked)
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
                if self._drag_active:
                    self._drag_active = False
                    self._drag_check_value = None
                    return True

        return super().eventFilter(obj, event)

    # ------------------- Search / filter passthrough -------------------
    def set_search_text(self, text: str):
        self._proxy.set_text_filter(text or "")
        if not (text or "").strip():
            hdr = self.table.horizontalHeader()
            self.table.sortByColumn(-1, Qt.AscendingOrder)
            hdr.setSortIndicatorShown(False)

    def set_flagged_only(self, on: bool):
        self._proxy.set_flagged_only(bool(on))

    def set_incomplete_only(self, on: bool):
        self._proxy.set_incomplete_only(bool(on))

    # ------------------- Public API -------------------
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
        vals = self._model.row_values(src)
        mapping = {
            C_VENDOR: 0, C_INVOICE: 1, C_PO: 2, C_INV_DATE: 3,
            C_TERMS: 4, C_DUE: 5, C_DISC_TOTAL: 6, C_TOTAL: 7
        }
        if col in mapping:
            return vals[mapping[col]] or ""
        return ""
    
    def update_calculated_field(self, view_row: int, col: int, value: str, emit_change: bool = True):
        """Update a table cell without marking it as manually edited."""
        src = self._view_to_source_row(view_row)
        if src < 0:
            return

        attr_map = {
            C_VENDOR: "vendor",
            C_INVOICE: "invoice",
            C_PO: "po",
            C_INV_DATE: "inv_date",
            C_TERMS: "terms",
            C_DUE: "due",
            C_DISC_TOTAL: "disc_total",
            C_TOTAL: "total",
        }

        attr = attr_map.get(col)
        if not attr:
            return

        row = self._model._rows[src]
        setattr(row, attr, value)
        row.edited_cells.discard(col)
        self.manually_edited.discard((view_row, col))

        if col == C_INVOICE:
            self._model._rebuild_duplicates()

        if emit_change:
            idx = self._model.index(src, col)
            self._model.dataChanged.emit(idx, idx, [Qt.DisplayRole, Qt.EditRole, Qt.BackgroundRole])

    def is_row_flagged(self, view_row: int) -> bool:
        src = self._view_to_source_row(view_row)
        return False if src < 0 else self._model.get_flag(src)

    def toggle_row_flag(self, view_row: int):
        src = self._view_to_source_row(view_row)
        if src >= 0:
            self._model.set_flag(src, not self._model.get_flag(src))

    def get_checked_rows(self) -> List[int]:
        """Return view row indexes where the Select checkbox is checked."""
        rows: List[int] = []
        for i in self._model.selected_rows():
            v = self._source_to_view_row(i)
            if v != -1:
                rows.append(v)
        return rows

    def set_row_checked(self, view_row: int, checked: bool):
        """Set the Select checkbox state for a view row."""
        src = self._view_to_source_row(view_row)
        if src >= 0:
            state = Qt.Checked if checked else Qt.Unchecked
            self._model.setData(self._model.index(src, C_SELECT), state, Qt.CheckStateRole)

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
