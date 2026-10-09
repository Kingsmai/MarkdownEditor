"""Native Qt text editing, Markdown shortcuts, and source highlighting."""
import re
import base64
from uuid import uuid4
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QDrag, QImage, QPainter, QPolygon, QFont, QFontMetricsF, QSyntaxHighlighter, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument, QTextDocumentFragment, QTextFormat, QTextListFormat, QTextLength, QTextTable, QTextTableFormat, QTextImageFormat, QTextFrameFormat, QTextTableCellFormat
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QFrame, QInputDialog, QMenu, QTextEdit, QPlainTextEdit, QToolButton

from native.block_controls import BLOCK_TYPES, BlockHandle, InsertMenu, SelectionBar
from native.theme import LIGHT, BODY_LINE_HEIGHT, CODE_LINE_HEIGHT, HEADING_LINE_HEIGHT, HEADING_SIZES, FONT_SIZES, PARAGRAPH_GAP, HEADING_SPACING, CONTENT_WIDTH, EDITOR_GUTTER, EDITOR_TOP, EDITOR_BOTTOM, font_for


TOGGLE_ID = QTextFormat.Property.UserProperty + 1
TOGGLE_PARENT = QTextFormat.Property.UserProperty + 2
TOGGLE_COLLAPSED = QTextFormat.Property.UserProperty + 3
COLUMNS = QTextFormat.Property.UserProperty + 4


class MarkdownEditor(QTextEdit):
    linkRequested = Signal()
    imageRequested = Signal()
    imageError = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(True)
        self.setAccessibleName("文稿编辑区")
        self.setPlaceholderText("输入 / 插入块，或写下你的第一个想法…")
        self.setFrameStyle(0)
        self.setLineWrapMode(QTextEdit.LineWrapMode.FixedPixelWidth)
        self.document().setDocumentMargin(0)
        self.body_font = font_for("body")
        self.code_font = font_for("code")
        self.setFont(self.body_font)
        self.setTabStopDistance(QFontMetricsF(self.code_font).horizontalAdvance("    "))
        self.document().setDefaultFont(self.body_font)
        self.colors = LIGHT
        self.content_generation = 0
        self.network = QNetworkAccessManager(self)
        self.full_width = False
        self.slash_dismissed = False
        self.loading_content = False
        self.hover_cursor = QTextCursor(self.document())
        self.drag_cursor = None
        self.drag_target = None
        self.insert_menu = InsertMenu(self)
        self.block_handle = BlockHandle(self)
        self.add_button = QToolButton(self)
        self.add_button.setText("+")
        self.add_button.setAccessibleName("在此块下方插入")
        self.add_button.setToolTip("在此块下方插入")
        self.add_button.setFixedSize(24, 28)
        self.add_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.add_button.clicked.connect(self.add_block_below)
        self.add_button.hide()
        self.fold_button = QToolButton(self)
        self.fold_button.setFixedSize(22, 26)
        self.fold_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.fold_button.setAccessibleName("展开或收起折叠块")
        self.fold_button.clicked.connect(self.toggle_fold)
        self.fold_button.hide()
        self.selection_bar = SelectionBar(self)
        self.drop_line = QFrame(self)
        self.drop_line.setObjectName("blockDropLine")
        self.drop_line.setFixedHeight(2)
        self.drop_line.hide()
        self.viewport().setMouseTracking(True)
        self.cursorPositionChanged.connect(self.update_controls)
        self.selectionChanged.connect(self.update_controls)
        self.textChanged.connect(self.content_changed)
        self.verticalScrollBar().valueChanged.connect(self.update_controls)
        self.setCurrentCharFormat(self.body_character_format())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_content_width()

    def update_content_width(self):
        gutter = EDITOR_GUTTER if self.full_width else max(EDITOR_GUTTER, (self.width() - CONTENT_WIDTH) // 2)
        self.setViewportMargins(gutter, EDITOR_TOP, gutter, EDITOR_BOTTOM)
        self.setLineWrapColumnOrWidth(max(80, self.viewport().width()))
        self.update_controls()

    def set_full_width(self, enabled):
        self.full_width = bool(enabled)
        self.update_content_width()

    def load_markdown(self, markdown, base_url):
        self.loading_content = True
        self.content_generation += 1
        self.hide_controls()
        try:
            self.document().setBaseUrl(base_url)
            self.setMarkdown(markdown)
            self.style_blocks()
            self.normalize_tables()
            self.document().clearUndoRedoStacks()
            self.document().setModified(False)
        finally:
            self.loading_content = False

    def style_blocks(self):
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        code_spans = []
        block = self.document().begin()
        while block.isValid():
            cursor.setPosition(block.position())
            level = block.blockFormat().headingLevel()
            block_format = block.blockFormat()
            code_block = bool(block_format.property(QTextFormat.Property.BlockCodeFence))
            fragment_iterator = block.begin()
            while not fragment_iterator.atEnd():
                fragment = fragment_iterator.fragment()
                if fragment.charFormat().fontFixedPitch():
                    code_spans.append((fragment.position(), fragment.length()))
                fragment_iterator += 1
            self.apply_block_spacing(cursor)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            body_character = self.body_character_format()
            # Imported fragments need explicit families to keep Qt's fallback consistent.
            body_character.clearProperty(QTextFormat.Property.FontWeight)
            cursor.mergeCharFormat(body_character)
            if level:
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                character = QTextCharFormat()
                character.setFontPointSize(HEADING_SIZES[level] * 72 / self.logicalDpiY())
                character.setFontWeight(QFont.Weight.DemiBold)
                cursor.mergeCharFormat(character)
            if code_block:
                cursor.setPosition(block.position())
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                cursor.mergeCharFormat(self.code_character_format())
            block = block.next()
        for position, length in code_spans:
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(self.code_character_format())
        cursor.endEditBlock()
        self.document().clearUndoRedoStacks()

    def apply_block_spacing(self, cursor):
        # One rule covers import, typing and conversion without replacing rich text.
        format = cursor.blockFormat()
        level = format.headingLevel()
        code = bool(format.property(QTextFormat.Property.BlockCodeFence))
        top, bottom = HEADING_SPACING.get(level, (0, PARAGRAPH_GAP))
        height = CODE_LINE_HEIGHT if code else HEADING_LINE_HEIGHT if level else BODY_LINE_HEIGHT
        if code or cursor.currentList():
            top, bottom = 0, 2
        table = cursor.currentTable()
        if table and not table.format().property(COLUMNS):
            top, bottom = 0, 0
        first = not cursor.block().previous().isValid()
        if table:
            first = cursor.block() == table.cellAt(cursor).firstCursorPosition().block()
        if format.property(TOGGLE_ID):
            # Keep the fold arrow inside the painted viewport, away from the gutter handles.
            format.setLeftMargin(22)
        format.setTopMargin(0 if first else top)
        format.setBottomMargin(bottom)
        format.setLineHeight(height, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        cursor.setBlockFormat(format)

    def code_character_format(self):
        character = QTextCharFormat()
        character.setFontFamilies(self.code_font.families())
        character.setFontFixedPitch(True)
        # Convert logical pixels to points for QTextDocument, including PDF output.
        character.setFontPointSize(FONT_SIZES["code"] * 72 / self.logicalDpiY())
        return character

    def set_heading(self, level):
        self.convert_blocks("paragraph" if not level else "heading" + str(level))

    def toggle_character(self, kind):
        current = self.currentCharFormat()
        change = QTextCharFormat()
        if kind == "bold":
            change.setFontWeight(QFont.Weight.Normal if current.fontWeight() >= QFont.Weight.DemiBold else QFont.Weight.Bold)
        elif kind == "italic":
            change.setFontItalic(not current.fontItalic())
        elif kind == "strike":
            change.setFontStrikeOut(not current.fontStrikeOut())
        elif kind == "underline":
            change.setFontUnderline(not current.fontUnderline())
        elif kind == "code":
            if current.fontFixedPitch():
                change.setFontFamilies(self.body_font.families())
                change.setFontPointSize(FONT_SIZES["body"] * 72 / self.logicalDpiY())
                change.setFontFixedPitch(False)
            else:
                change = self.code_character_format()
        self.mergeCurrentCharFormat(change)
        self.setFocus()

    def make_list(self, ordered=False, task=False):
        self.convert_blocks("task" if task else "ordered" if ordered else "bullet")

    def toggle_task(self):
        cursor = self.textCursor()
        if not cursor.currentList():
            self.make_list(task=True)
            return
        block_format = cursor.blockFormat()
        marker = block_format.marker()
        block_format.setMarker(QTextBlockFormat.MarkerType.Unchecked if marker == QTextBlockFormat.MarkerType.Checked else QTextBlockFormat.MarkerType.Checked)
        cursor.setBlockFormat(block_format)

    def make_quote(self):
        quoted = self.textCursor().blockFormat().property(QTextFormat.Property.BlockQuoteLevel)
        self.convert_blocks("paragraph" if quoted else "quote")

    def make_code_block(self):
        code = self.textCursor().blockFormat().property(QTextFormat.Property.BlockCodeFence)
        self.convert_blocks("paragraph" if code else "code")


    def convert_blocks(self, kind):
        selection = self.textCursor()
        start, end = selection.selectionStart(), selection.selectionEnd()
        if end > start:
            end -= 1
        block = self.document().findBlock(start)
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        while block.isValid() and block.position() <= end:
            cursor.setPosition(block.position())
            identifier = cursor.blockFormat().property(TOGGLE_ID)
            if identifier:
                cursor_format = cursor.blockFormat()
                cursor_format.setLeftMargin(0)
                cursor.setBlockFormat(cursor_format)
                child = self.document().begin()
                while child.isValid():
                    child_format = child.blockFormat()
                    if child_format.property(TOGGLE_PARENT) == identifier:
                        child_format.clearProperty(TOGGLE_PARENT)
                        child_format.setIndent(0)
                        QTextCursor(child).setBlockFormat(child_format)
                    child = child.next()
            old_list = cursor.currentList()
            if old_list:
                old_list.remove(block)
            block_format = cursor.blockFormat()
            for prop in (QTextFormat.Property.BlockCodeFence, QTextFormat.Property.BlockCodeLanguage,
                         QTextFormat.Property.BlockQuoteLevel, QTextFormat.Property.BlockTrailingHorizontalRulerWidth):
                block_format.clearProperty(prop)
            block_format.clearProperty(TOGGLE_ID)
            block_format.clearProperty(TOGGLE_COLLAPSED)
            level = int(kind[-1]) if kind.startswith("heading") else 0
            block_format.setHeadingLevel(level)
            block_format.setIndent(1 if block_format.property(TOGGLE_PARENT) else 0)
            block_format.setMarker(QTextBlockFormat.MarkerType.NoMarker)
            block_format.setNonBreakableLines(kind == "code")
            if kind == "code":
                block_format.setProperty(QTextFormat.Property.BlockCodeFence, chr(96) * 3)
            if kind == "quote":
                block_format.setProperty(QTextFormat.Property.BlockQuoteLevel, 1)
                block_format.setIndent(1)
            cursor.setBlockFormat(block_format)
            character = self.code_character_format() if kind == "code" else QTextCharFormat()
            if kind != "code":
                character.setFontFamilies(self.body_font.families())
                character.setFontFixedPitch(False)
                character.setFontPointSize(HEADING_SIZES[level] * 72 / self.logicalDpiY())
                character.setFontWeight(QFont.Weight.DemiBold if level else QFont.Weight.Normal)
            cursor.mergeBlockCharFormat(character)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.mergeCharFormat(character)
            cursor.clearSelection()
            if kind in ("bullet", "ordered", "task"):
                list_format = QTextListFormat()
                list_format.setStyle(QTextListFormat.Style.ListDecimal if kind == "ordered" else QTextListFormat.Style.ListDisc)
                list_format.setIndent(1 + int(bool(block_format.property(TOGGLE_PARENT))))
                previous = block.previous()
                previous_list = previous.textList() if previous.isValid() else None
                if previous_list and previous_list.format().style() == list_format.style() and previous_list.format().indent() == list_format.indent():
                    previous_list.add(block)
                else:
                    cursor.createList(list_format)
                if kind == "task":
                    block_format = cursor.blockFormat()
                    block_format.setMarker(QTextBlockFormat.MarkerType.Unchecked)
                    cursor.setBlockFormat(block_format)
            self.apply_block_spacing(cursor)
            block = block.next()
        cursor.endEditBlock()
        self.setTextCursor(selection)
        self.setFocus()
        self.update_controls()

    def set_color(self, color, background=False):
        cursor = self.textCursor()
        prop = QTextFormat.Property.BackgroundBrush if background else QTextFormat.Property.ForegroundBrush
        cursor.beginEditBlock()
        if color:
            change = QTextCharFormat()
            shade = QColor(color)
            if background:
                shade.setAlpha(65)
                change.setBackground(shade)
            else:
                change.setForeground(shade)
            self.mergeCurrentCharFormat(change)
        elif cursor.hasSelection():
            position = cursor.selectionStart()
            while position < cursor.selectionEnd():
                character_cursor = QTextCursor(self.document())
                character_cursor.setPosition(position)
                character_cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
                character = character_cursor.charFormat()
                character.clearProperty(prop)
                character_cursor.setCharFormat(character)
                position = character_cursor.position()
        else:
            character = self.currentCharFormat()
            character.clearProperty(prop)
            self.setCurrentCharFormat(character)
        cursor.endEditBlock()
        self.setFocus()

    def tables(self):
        result = []
        def visit(frame):
            for child in frame.childFrames():
                if isinstance(child, QTextTable):
                    result.append(child)
                visit(child)
        visit(self.document().rootFrame())
        return result

    def table_format(self, columns, layout=False):
        # Borderless Qt tables provide real editable columns without a WebView.
        format = QTextTableFormat()
        format.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
        format.setColumnWidthConstraints([QTextLength(QTextLength.Type.PercentageLength, 100 / columns) for _ in range(columns)])
        format.setHeaderRowCount(0 if layout else 1)
        format.setBorder(0 if layout else 1)
        format.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        format.setBorderBrush(QColor(self.colors["border"]))
        format.setCellPadding(6 if layout else 5)
        format.setCellSpacing(8 if layout else 0)
        format.setProperty(COLUMNS, layout)
        return format

    def normalize_tables(self):
        for table in self.tables():
            old = table.format()
            format = self.table_format(table.columns(), bool(old.property(COLUMNS)))
            format.setHeaderRowCount(old.headerRowCount())
            constraints = old.columnWidthConstraints()
            if len(constraints) == table.columns() and all(item.type() == QTextLength.Type.PercentageLength for item in constraints):
                format.setColumnWidthConstraints(constraints)
            table.setFormat(format)
            self.style_table_cells(table)

    def style_table_cells(self, table):
        layout = bool(table.format().property(COLUMNS))
        for row in range(table.rows()):
            for column in range(table.columns()):
                cell = table.cellAt(row, column)
                format = QTextTableCellFormat(cell.format())
                format.setBorder(0 if layout else 1)
                format.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
                format.setBorderBrush(QColor(self.colors["border"]))
                if not layout and row < table.format().headerRowCount():
                    format.setBackground(QColor(self.colors["code"]))
                else:
                    format.clearBackground()
                cell.setFormat(format)
                cursor = cell.firstCursorPosition()
                block_format = cursor.blockFormat()
                if not block_format.headingLevel() and not block_format.property(QTextFormat.Property.BlockCodeFence):
                    cursor.mergeBlockCharFormat(self.body_character_format())
                    if not cursor.block().text():
                        cursor.setCharFormat(self.body_character_format())
                end = cell.lastCursorPosition().position()
                block = cursor.block()
                while block.isValid() and block.position() <= end:
                    self.apply_block_spacing(QTextCursor(block))
                    block = block.next()

    def body_character_format(self):
        format = QTextCharFormat()
        format.setFontFamilies(self.body_font.families())
        format.setFontPointSize(FONT_SIZES["body"] * 72 / self.logicalDpiY())
        format.setFontWeight(QFont.Weight.Normal)
        return format

    def set_column_width(self, percent):
        table = self.textCursor().currentTable()
        if table is None or table.columns() < 2:
            return
        column = table.cellAt(self.textCursor()).column()
        percent = max(10, min(90, percent))
        other = (100 - percent) / (table.columns() - 1)
        format = table.format()
        format.setColumnWidthConstraints([QTextLength(QTextLength.Type.PercentageLength, percent if index == column else other) for index in range(table.columns())])
        table.setFormat(format)

    def choose_column_width(self):
        table = self.textCursor().currentTable()
        if table is None:
            return
        percent, accepted = QInputDialog.getInt(self, "列宽", "当前列占正文宽度的百分比", round(100 / table.columns()), 10, 90)
        if accepted:
            self.set_column_width(percent)

    def insert_table(self, rows=3, columns=3, layout=False):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        table = cursor.insertTable(rows, columns, self.table_format(columns, layout))
        self.style_table_cells(table)
        self.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
        cursor.endEditBlock()
        self.setCurrentCharFormat(self.body_character_format())
        self.setFocus()
        return table

    def table_action(self, operation):
        cursor = self.textCursor()
        table = cursor.currentTable()
        if table is None:
            return
        cell = table.cellAt(cursor)
        row, column = cell.row(), cell.column()
        cursor.beginEditBlock()
        if operation == "row_before":
            table.insertRows(row, 1)
        elif operation == "row_after":
            table.insertRows(row + 1, 1)
        elif operation == "column_before":
            table.insertColumns(column, 1)
        elif operation == "column_after":
            table.insertColumns(column + 1, 1)
        elif operation == "remove_row":
            if table.rows() == 1:
                self.delete_block(table.firstPosition())
                cursor.endEditBlock()
                return
            table.removeRows(row, 1)
        elif operation == "remove_column":
            if table.columns() == 1:
                self.delete_block(table.firstPosition())
                cursor.endEditBlock()
                return
            table.removeColumns(column, 1)
        elif operation == "header":
            format = table.format()
            format.setHeaderRowCount(0 if format.headerRowCount() else 1)
            table.setFormat(format)
        elif operation == "exit":
            cursor.setPosition(table.lastPosition() + 1)
            self.setTextCursor(cursor)
            cursor.endEditBlock()
            self.setFocus()
            return
        self.normalize_tables()
        self.setTextCursor(table.cellAt(min(row, table.rows() - 1), min(column, table.columns() - 1)).firstCursorPosition())
        cursor.endEditBlock()
        self.setFocus()

    def insert_toggle(self):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        self.convert_blocks("paragraph")
        format = cursor.blockFormat()
        identifier = uuid4().hex
        format.setProperty(TOGGLE_ID, identifier)
        format.setProperty(TOGGLE_COLLAPSED, False)
        cursor.setBlockFormat(format)
        self.apply_block_spacing(cursor)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        child_format = QTextBlockFormat()
        child_format.setProperty(TOGGLE_PARENT, identifier)
        child_format.setIndent(1)
        cursor.insertBlock(child_format, self.body_character_format())
        self.apply_block_spacing(cursor)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.setFocus()

    def apply_folding(self):
        collapsed = set()
        block = self.document().begin()
        while block.isValid():
            format = block.blockFormat()
            if format.property(TOGGLE_ID) and (format.property(TOGGLE_COLLAPSED) or format.property(TOGGLE_PARENT) in collapsed):
                collapsed.add(format.property(TOGGLE_ID))
            block = block.next()
        block = self.document().begin()
        while block.isValid():
            hidden = block.blockFormat().property(TOGGLE_PARENT) in collapsed
            block.setVisible(not hidden)
            if hidden:
                block.setLineCount(0)
            block = block.next()
        self.document().markContentsDirty(0, self.document().characterCount())
        self.viewport().update()

    def toggle_fold(self):
        cursor = QTextCursor(self.hover_cursor)
        format = cursor.blockFormat()
        if not format.property(TOGGLE_ID):
            return
        cursor.beginEditBlock()
        format.setProperty(TOGGLE_COLLAPSED, not bool(format.property(TOGGLE_COLLAPSED)))
        cursor.setBlockFormat(format)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.apply_folding()
        self.setFocus()
        self.update_controls()

    def rich_content(self):
        blocks = []
        rich = False
        block = self.document().begin()
        while block.isValid():
            format = block.blockFormat()
            metadata = {"index": block.blockNumber()}
            for key, prop in (("toggle", TOGGLE_ID), ("parent", TOGGLE_PARENT), ("collapsed", TOGGLE_COLLAPSED)):
                if format.hasProperty(prop):
                    metadata[key] = format.property(prop)
            if len(metadata) > 1:
                blocks.append(metadata)
                rich = True
            iterator = block.begin()
            while not iterator.atEnd():
                character = iterator.fragment().charFormat()
                if character.isImageFormat() and character.toImageFormat().name().startswith("data:"):
                    rich = True
                if character.hasProperty(QTextFormat.Property.BackgroundBrush) or (character.hasProperty(QTextFormat.Property.ForegroundBrush) and not character.isAnchor()) or (character.fontUnderline() and not character.isAnchor()):
                    rich = True
                iterator += 1
            block = block.next()
        columns = [index for index, table in enumerate(self.tables()) if table.format().property(COLUMNS)]
        if columns or any(len({round(item.rawValue(), 2) for item in table.format().columnWidthConstraints()}) > 1 for table in self.tables()):
            rich = True
        if not rich:
            return None
        return {"html": self.toHtml(), "blocks": blocks, "columns": columns}

    def load_rich_content(self, content, base_url):
        self.loading_content = True
        self.content_generation += 1
        self.hide_controls()
        try:
            self.document().setBaseUrl(base_url)
            self.setHtml(content["html"])
            for metadata in content.get("blocks", []):
                block = self.document().findBlockByNumber(metadata["index"])
                if not block.isValid():
                    continue
                cursor = QTextCursor(block)
                format = block.blockFormat()
                for key, prop in (("toggle", TOGGLE_ID), ("parent", TOGGLE_PARENT), ("collapsed", TOGGLE_COLLAPSED)):
                    if key in metadata:
                        format.setProperty(prop, metadata[key])
                cursor.setBlockFormat(format)
            tables = self.tables()
            for index in content.get("columns", []):
                if 0 <= index < len(tables):
                    format = tables[index].format()
                    format.setProperty(COLUMNS, True)
                    tables[index].setFormat(format)
            # Older rich HTML contains the previous generous margins.
            block = self.document().begin()
            while block.isValid():
                self.apply_block_spacing(QTextCursor(block))
                block = block.next()
            self.normalize_tables()
            self.apply_folding()
            self.document().clearUndoRedoStacks()
            self.document().setModified(False)
        finally:
            self.loading_content = False

    def content_changed(self):
        if self.loading_content:
            return
        self.apply_folding()
        QTimer.singleShot(0, self.update_controls)

    def hide_controls(self):
        for control in (self.insert_menu, self.selection_bar, self.add_button, self.block_handle, self.fold_button, self.drop_line):
            control.hide()
        self.slash_dismissed = False

    def position_popup(self, popup, point):
        popup.move(max(4, min(point.x(), self.width() - popup.width() - 4)),
                   max(4, min(point.y(), self.height() - popup.height() - 4)))
        popup.show()
        popup.raise_()

    def update_controls(self, *_):
        if self.loading_content or not self.isVisible():
            return
        cursor = self.textCursor()
        prefix = cursor.block().text().encode("utf-16-le")[:cursor.positionInBlock() * 2].decode("utf-16-le")
        match = re.fullmatch(r"/([^\n]*)", prefix)
        code = cursor.blockFormat().property(QTextFormat.Property.BlockCodeFence)
        at_end = cursor.positionInBlock() == cursor.block().length() - 1
        if match and at_end and not code and not cursor.hasSelection() and not self.slash_dismissed:
            self.insert_menu.filter(match[1].strip())
            self.position_popup(self.insert_menu, self.viewport().pos() + self.cursorRect().bottomLeft() + QPoint(0, 8))
        else:
            self.insert_menu.hide()
            if not match:
                self.slash_dismissed = False
        if cursor.hasSelection() and not self.insert_menu.isVisible():
            self.selection_bar.refresh()
            self.selection_bar.adjustSize()
            point = self.viewport().pos() + self.cursorRect().topLeft() - QPoint(0, self.selection_bar.height() + 10)
            self.position_popup(self.selection_bar, point)
        else:
            self.selection_bar.hide()
        self.show_handle(self.hover_cursor if self.block_handle.underMouse() or self.add_button.underMouse() else cursor)

    def show_handle(self, cursor):
        self.hover_cursor = QTextCursor(cursor)
        start, _ = self.block_range(cursor.position())
        block_cursor = QTextCursor(self.document())
        block_cursor.setPosition(start)
        rectangle = self.cursorRect(block_cursor)
        y = self.viewport().y() + rectangle.top()
        visible = 0 <= rectangle.top() < self.viewport().height()
        x = self.viewport().x()
        self.add_button.move(x - 54, y)
        self.block_handle.move(x - 28, y)
        self.add_button.setVisible(visible)
        self.block_handle.setVisible(visible)
        format = cursor.blockFormat()
        toggle = bool(format.property(TOGGLE_ID))
        self.fold_button.setVisible(visible and toggle)
        if toggle:
            self.fold_button.setText("▸" if format.property(TOGGLE_COLLAPSED) else "▾")
            self.fold_button.move(x + self.cursorRect(cursor).x() - 24, self.viewport().y() + self.cursorRect(cursor).top())

    def choose_block(self, kind):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        if cursor.block().text().startswith("/"):
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            self.setTextCursor(cursor)
        self.insert_menu.hide()
        if kind == "toggle":
            self.insert_toggle()
        elif kind == "table":
            self.insert_table()
        elif kind == "columns":
            self.insert_table(1, 2, True)
        elif kind == "divider":
            cursor.insertHtml("<hr />")
            self.setTextCursor(cursor)
        elif kind == "image":
            self.imageRequested.emit()
        elif kind == "link":
            self.linkRequested.emit()
        else:
            self.convert_blocks(kind)
        cursor.endEditBlock()
        self.setFocus()

    def add_block_below(self):
        _, end = self.block_range(self.hover_cursor.position())
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        cursor.setPosition(end)
        if end == self.document().characterCount() - 1:
            cursor.insertBlock(QTextBlockFormat(), QTextCharFormat())
            cursor.insertText("/")
        else:
            next_format = cursor.blockFormat()
            next_character = cursor.blockCharFormat()
            cursor.setBlockFormat(QTextBlockFormat())
            cursor.insertText("/", QTextCharFormat())
            position = cursor.position()
            cursor.insertBlock(next_format, next_character)
            cursor.setPosition(position)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.slash_dismissed = False
        self.setFocus()
        self.update_controls()

    def block_ranges(self):
        ranges = []
        toggle_ids = set()
        iterator = self.document().rootFrame().begin()
        while not iterator.atEnd():
            frame = iterator.currentFrame()
            block = iterator.currentBlock()
            if frame is not None:
                start = frame.firstPosition() - 1
                if ranges and ranges[-1][0] == start:
                    # Qt's empty paragraph before a table is part of that table's boundary.
                    ranges.pop()
                ranges.append((start, frame.lastPosition() + 1))
                toggle_ids.clear()
            elif block.isValid():
                start = block.position()
                end = min(start + block.length(), self.document().characterCount() - 1)
                if ranges:
                    previous = self.document().findBlock(ranges[-1][0])
                    parent = block.blockFormat().property(TOGGLE_PARENT)
                    code = block.blockFormat().property(QTextFormat.Property.BlockCodeFence)
                    if (parent and parent in toggle_ids) or (code and code == previous.blockFormat().property(QTextFormat.Property.BlockCodeFence)):
                        ranges[-1] = (ranges[-1][0], end)
                    else:
                        ranges.append((start, end))
                        toggle_ids.clear()
                else:
                    ranges.append((start, end))
                identifier = block.blockFormat().property(TOGGLE_ID)
                if identifier:
                    toggle_ids.add(identifier)
            iterator += 1
        return ranges

    def block_range(self, position):
        for start, end in self.block_ranges():
            if start <= position < end or start == end == position:
                return start, end
        return self.block_ranges()[-1]

    def select_block(self, position=None):
        start, end = self.block_range(self.textCursor().position() if position is None else position)
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
        self.setFocus()

    def delete_block(self, position=None):
        start, end = self.block_range(self.textCursor().position() if position is None else position)
        cursor = QTextCursor(self.document())
        if end == self.document().characterCount() - 1 and start > 0 and self.document().characterAt(start - 1) == "\u2029":
            start -= 1
        cursor.beginEditBlock()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.setFocus()

    def move_block_to(self, position, target, duplicate=False):
        start, end = self.block_range(position)
        if start <= target <= end and not (duplicate and target == end):
            return
        last = self.document().characterCount() - 1
        content_end = end
        if end < last and self.document().characterAt(end - 1) == "\u2029":
            content_end -= 1
        selection = QTextCursor(self.document())
        selection.setPosition(start)
        selection.setPosition(content_end, QTextCursor.MoveMode.KeepAnchor)
        fragment = selection.selection()
        first_format = self.document().findBlock(start).blockFormat()
        first_character = self.document().findBlock(start).charFormat()
        table = any(start == item.firstPosition() - 1 for item in self.tables())
        destination = QTextCursor(self.document())
        destination.setPosition(target)
        destination_format = destination.blockFormat()
        destination_character = destination.blockCharFormat()
        edit = QTextCursor(self.document())
        edit.beginEditBlock()
        if not duplicate:
            # The final paragraph has no trailing separator; remove its leading one instead.
            remove_start = start
            if end == last and start > 0 and self.document().characterAt(start - 1) == "\u2029":
                remove_start -= 1
            edit.setPosition(remove_start)
            edit.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            edit.removeSelectedText()
        tail = destination.position() == self.document().characterCount() - 1
        if tail and not table:
            destination.insertBlock(first_format, first_character)
        inserted_start = destination.position()
        destination.insertFragment(fragment)
        if not tail and not table:
            destination.insertBlock(destination_format, destination_character)
        if duplicate:
            inserted_end = destination.position()
            replacements = {}
            block = self.document().findBlock(inserted_start)
            while block.isValid() and block.position() < inserted_end:
                identifier = block.blockFormat().property(TOGGLE_ID)
                if identifier:
                    replacements[identifier] = uuid4().hex
                block = block.next()
            block = self.document().findBlock(inserted_start)
            while block.isValid() and block.position() < inserted_end:
                format = block.blockFormat()
                for prop in (TOGGLE_ID, TOGGLE_PARENT):
                    if format.property(prop) in replacements:
                        format.setProperty(prop, replacements[format.property(prop)])
                QTextCursor(block).setBlockFormat(format)
                block = block.next()
        edit.endEditBlock()
        destination.setPosition(min(inserted_start, self.document().characterCount() - 1))
        self.setTextCursor(destination)
        self.setFocus()

    def move_block(self, direction):
        ranges = self.block_ranges()
        selected = self.block_range(self.textCursor().position())
        index = ranges.index(selected)
        if direction < 0 and index:
            self.move_block_to(selected[0], ranges[index - 1][0])
        elif direction > 0 and index + 1 < len(ranges):
            self.move_block_to(selected[0], ranges[index + 1][1])

    def duplicate_block(self):
        start, end = self.block_range(self.textCursor().position())
        self.move_block_to(start, end, True)

    def show_block_menu(self):
        self.setTextCursor(self.hover_cursor)
        cursor = self.textCursor()
        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        if not cursor.currentTable():
            submenu = menu.addMenu("转换为")
            for kind, title, _, _ in BLOCK_TYPES[:10]:
                submenu.addAction(title, lambda checked=False, kind=kind: self.insert_toggle() if kind == "toggle" else self.convert_blocks(kind))
        menu.addAction("选中块", lambda: self.select_block())
        menu.addAction("在下方插入", self.add_block_below)
        menu.addAction("复制块", self.duplicate_block)
        menu.addAction("上移", lambda: self.move_block(-1))
        menu.addAction("下移", lambda: self.move_block(1))
        if cursor.blockFormat().property(TOGGLE_ID):
            menu.addAction("展开 / 收起", self.toggle_fold)
        table = cursor.currentTable()
        if table:
            submenu = menu.addMenu("分栏操作" if table.format().property(COLUMNS) else "表格操作")
            submenu.addAction("设置当前列宽…", self.choose_column_width)
            for title, operation in [("上方插入行", "row_before"), ("下方插入行", "row_after"),
                                     ("左侧插入列", "column_before"), ("右侧插入列", "column_after"),
                                     ("删除当前行", "remove_row"), ("删除当前列", "remove_column"),
                                     ("切换表头", "header"), ("退出到下方正文", "exit")]:
                if table.format().property(COLUMNS) and operation in ("row_before", "row_after", "remove_row", "header"):
                    continue
                submenu.addAction(title, lambda checked=False, operation=operation: self.table_action(operation))
        menu.addSeparator()
        menu.addAction("删除块", lambda: self.delete_block())
        menu.popup(self.block_handle.mapToGlobal(self.block_handle.rect().bottomLeft()))

    def start_block_drag(self):
        self.drag_cursor = QTextCursor(self.hover_cursor)
        self.drag_target = None
        drag = QDrag(self.block_handle)
        mime = QMimeData()
        mime.setData("application/x-inknote-block", b"move")
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)
        self.drag_cursor = None
        self.drop_line.hide()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-inknote-block") and event.source() is self.block_handle:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-inknote-block") and event.source() is self.block_handle:
            point = event.position().toPoint()
            cursor = self.cursorForPosition(point)
            table = cursor.currentTable()
            if table and table.format().property(COLUMNS):
                # Dropping into a column inserts a new paragraph before that cell's text.
                start = cursor.block().position()
                end = start
            else:
                start, end = self.block_range(cursor.position())
            first = QTextCursor(self.document())
            first.setPosition(start)
            last = QTextCursor(self.document())
            last.setPosition(end)
            top, bottom = self.cursorRect(first).top(), self.cursorRect(last).top()
            after = start != end and point.y() > (top + max(top + 26, bottom)) / 2
            self.drag_target = end if after else start
            y = bottom if after else top
            self.drop_line.setGeometry(self.viewport().x(), self.viewport().y() + y, self.viewport().width(), 2)
            self.drop_line.show()
            scroll = self.verticalScrollBar()
            if point.y() < 36:
                scroll.setValue(scroll.value() - 20)
            elif point.y() > self.viewport().height() - 36:
                scroll.setValue(scroll.value() + 20)
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self.drop_line.hide()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-inknote-block") and event.source() is self.block_handle:
            if self.drag_cursor is not None and self.drag_target is not None:
                self.move_block_to(self.drag_cursor.position(), self.drag_target)
            self.drop_line.hide()
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.colors["secondary"]))
        block = self.document().begin()
        while block.isValid():
            format = block.blockFormat()
            if block.isVisible() and format.property(TOGGLE_ID):
                rectangle = self.cursorRect(QTextCursor(block))
                x, y = rectangle.left() - 18, rectangle.top() + 12
                if format.property(TOGGLE_COLLAPSED):
                    points = [QPoint(x, y - 5), QPoint(x, y + 5), QPoint(x + 6, y)]
                else:
                    points = [QPoint(x - 2, y - 3), QPoint(x + 8, y - 3), QPoint(x + 3, y + 3)]
                painter.drawPolygon(QPolygon(points))
            block = block.next()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            block = self.document().begin()
            while block.isValid():
                if block.isVisible() and block.blockFormat().property(TOGGLE_ID):
                    rectangle = self.cursorRect(QTextCursor(block))
                    point = event.position()
                    if rectangle.left() - 26 <= point.x() < rectangle.left() and rectangle.top() <= point.y() <= rectangle.bottom():
                        self.hover_cursor = QTextCursor(block)
                        self.toggle_fold()
                        return
                block = block.next()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if not event.buttons():
            self.show_handle(self.cursorForPosition(event.position().toPoint()))

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            url = QUrl(self.anchorAt(event.position().toPoint()))
            if url.scheme().lower() in ("http", "https", "mailto"):
                QDesktopServices.openUrl(url)
                return
        cursor = self.cursorForPosition(event.position().toPoint())
        marker = cursor.blockFormat().marker()
        text_x = self.cursorRect(QTextCursor(cursor.block())).x()
        if marker != QTextBlockFormat.MarkerType.NoMarker and text_x - 28 <= event.position().x() < text_x:
            self.setTextCursor(cursor)
            self.toggle_task()
        self.update_controls()

    def contextMenuEvent(self, event):
        if self.textCursor().currentTable():
            self.hover_cursor = self.textCursor()
            self.show_block_menu()
        else:
            super().contextMenuEvent(event)

    def hideEvent(self, event):
        self.hide_controls()
        super().hideEvent(event)

    def keyPressEvent(self, event):
        cursor = self.textCursor()
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            super().keyPressEvent(event)
            return
        modifiers = event.modifiers()
        if self.insert_menu.isVisible():
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self.insert_menu.step(1 if key == Qt.Key.Key_Down else -1)
                return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.insert_menu.choose()
                return
            if key == Qt.Key.Key_Escape:
                self.slash_dismissed = True
                self.insert_menu.hide()
                return
        if modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            if key == Qt.Key.Key_D:
                self.duplicate_block()
                return
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                self.move_block(-1 if key == Qt.Key.Key_Up else 1)
                return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and cursor.currentTable():
                self.table_action("exit")
                return
        if key == Qt.Key.Key_Escape:
            if cursor.hasSelection():
                cursor.clearSelection()
                self.setTextCursor(cursor)
            else:
                self.select_block()
            return
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab) and cursor.currentTable():
            table = cursor.currentTable()
            cell = table.cellAt(cursor)
            backwards = key == Qt.Key.Key_Backtab or bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
            index = cell.row() * table.columns() + cell.column() + (-1 if backwards else 1)
            if index < 0:
                return
            if index >= table.rows() * table.columns():
                if table.format().property(COLUMNS):
                    self.table_action("exit")
                    return
                cursor.beginEditBlock()
                table.appendRows(1)
                self.normalize_tables()
                cursor.endEditBlock()
            self.setTextCursor(table.cellAt(index // table.columns(), index % table.columns()).firstCursorPosition())
            return
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab) and cursor.currentList():
            format = cursor.currentList().format()
            backwards = key == Qt.Key.Key_Backtab or bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
            indent = format.indent() + (-1 if backwards else 1)
            if indent < 1:
                self.convert_blocks("paragraph")
            else:
                format.setIndent(indent)
                cursor.createList(format)
            return
        if key == Qt.Key.Key_Backspace and cursor.positionInBlock() == 0 and not cursor.hasSelection():
            if cursor.currentList() or cursor.blockFormat().headingLevel() or cursor.blockFormat().property(QTextFormat.Property.BlockQuoteLevel):
                self.convert_blocks("paragraph")
                return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (modifiers & Qt.KeyboardModifier.ShiftModifier):
            format = cursor.blockFormat()
            if format.property(TOGGLE_ID):
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                child = QTextBlockFormat()
                child.setIndent(1)
                child.setProperty(TOGGLE_PARENT, format.property(TOGGLE_ID))
                cursor.insertBlock(child, self.body_character_format())
                self.apply_block_spacing(cursor)
                self.setTextCursor(cursor)
                return
            if format.property(TOGGLE_PARENT) and not cursor.block().text():
                format.clearProperty(TOGGLE_PARENT)
                format.setIndent(0)
                cursor.setBlockFormat(format)
                self.setTextCursor(cursor)
                return
        block_text = cursor.block().text()
        at_end = cursor.positionInBlock() == len(block_text.encode("utf-16-le")) // 2 and not cursor.hasSelection()
        in_code = bool(cursor.blockFormat().property(QTextFormat.Property.BlockCodeFence))
        if event.key() == Qt.Key.Key_Space and at_end and not in_code:
            heading = re.fullmatch(r"(#{1,6})", block_text)
            list_marker = re.fullmatch(r"[-*+]|\d+[.)]", block_text)
            task = re.fullmatch(r"(?:[-*+] )?\[([ xX])\]", block_text)
            if heading or list_marker or task or block_text == ">":
                cursor.beginEditBlock()
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                cursor.removeSelectedText()
                self.setTextCursor(cursor)
                if heading:
                    self.set_heading(len(heading[1]))
                elif task:
                    self.make_list(task=True)
                    if task[1].lower() == "x":
                        self.toggle_task()
                elif list_marker:
                    self.make_list(ordered=block_text[0].isdigit())
                else:
                    self.make_quote()
                cursor.endEditBlock()
                return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and at_end:
            if re.fullmatch(r"```[\w+-]*", block_text):
                cursor.beginEditBlock()
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                language = block_text[3:]
                cursor.removeSelectedText()
                self.setTextCursor(cursor)
                self.make_code_block()
                block_format = cursor.blockFormat()
                block_format.setProperty(QTextFormat.Property.BlockCodeLanguage, language)
                cursor.setBlockFormat(block_format)
                cursor.endEditBlock()
                return
            if in_code and not block_text:
                block_format = cursor.blockFormat()
                block_format.clearProperty(QTextFormat.Property.BlockCodeFence)
                block_format.clearProperty(QTextFormat.Property.BlockCodeLanguage)
                block_format.setNonBreakableLines(False)
                cursor.setBlockFormat(block_format)
                self.apply_block_spacing(cursor)
                self.setCurrentCharFormat(self.body_character_format())
                return
        super().keyPressEvent(event)
        if event.text() in ("*", "`", "~") and not in_code:
            self.replace_inline_markdown()
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor = self.textCursor()
            if cursor.blockFormat().headingLevel():
                self.set_heading(0)
            self.apply_block_spacing(cursor)
            self.setCurrentCharFormat(self.body_character_format())

    def replace_inline_markdown(self):
        cursor = self.textCursor()
        # Qt cursor positions use UTF-16 units, including two units for emoji.
        prefix = cursor.block().text().encode("utf-16-le")[:cursor.positionInBlock() * 2].decode("utf-16-le")
        patterns = [
            (r"\*\*([^*\n]+)\*\*$", "bold"),
            (r"(?<!\*)\*([^*\n]+)\*$", "italic"),
            (r"`([^`\n]+)`$", "code"),
            (r"~~([^~\n]+)~~$", "strike"),
        ]
        for pattern, kind in patterns:
            match = re.search(pattern, prefix)
            if not match:
                continue
            character = QTextCharFormat()
            if kind == "bold":
                character.setFontWeight(QFont.Weight.Bold)
            elif kind == "italic":
                character.setFontItalic(True)
            elif kind == "strike":
                character.setFontStrikeOut(True)
            else:
                character = self.code_character_format()
            restore = self.currentCharFormat()
            cursor.beginEditBlock()
            cursor.setPosition(cursor.position() - len(match[0].encode("utf-16-le")) // 2, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(match[1], character)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            self.setCurrentCharFormat(restore)
            return

    def select_link(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            return
        href = cursor.charFormat().anchorHref()
        if not href:
            return
        iterator = cursor.block().begin()
        first, last = None, None
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.charFormat().anchorHref() == href:
                first = fragment.position() if first is None else first
                last = fragment.position() + fragment.length()
            elif first is not None and fragment.position() > cursor.position():
                break
            iterator += 1
        if first is not None:
            cursor.setPosition(first)
            cursor.setPosition(last, QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(cursor)

    def insert_image(self, image, cursor=None):
        if image.isNull():
            self.imageError.emit("图片无法读取")
            return
        # A data URL keeps pasted/local images inside the rich file without attachment folders.
        encoded = QByteArray()
        buffer = QBuffer(encoded)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        if len(encoded) > 2 * 1024 * 1024:
            self.imageError.emit("图片超过 2 MB，请先缩小或压缩图片。")
            return
        name = "data:image/png;base64," + base64.b64encode(bytes(encoded)).decode("ascii")
        cursor = QTextCursor(cursor) if cursor is not None else self.textCursor()
        table = cursor.currentTable()
        available = self.viewport().width() - 16
        if table:
            available = available / table.columns() - 28
        width = min(image.width(), max(60, available))
        format = QTextImageFormat()
        format.setName(name)
        format.setWidth(width)
        format.setHeight(width * image.height() / image.width())
        self.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
        cursor.insertImage(format)
        self.setTextCursor(cursor)
        self.setFocus()

    def insert_image_url(self, url):
        cursor = QTextCursor(self.textCursor())
        generation = self.content_generation
        request = QNetworkRequest(url)
        request.setTransferTimeout(15000)
        reply = self.network.get(request)
        reply.downloadProgress.connect(lambda received, total: reply.abort() if max(received, total) > 5 * 1024 * 1024 else None)
        def finished():
            try:
                if generation != self.content_generation:
                    return
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    self.imageError.emit("图片下载失败：" + reply.errorString())
                    return
                image = QImage.fromData(reply.readAll())
                self.insert_image(image, cursor)
            finally:
                reply.deleteLater()
        reply.finished.connect(finished)

    def canInsertFromMimeData(self, source):
        return source.hasImage() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if source.hasImage():
            self.insert_image(QImage(source.imageData()))
            return
        if source.hasText() and re.search(r"(?m)^#{1,6} |^[-*] |\n```", source.text()):
            document = QTextDocument()
            document.setDefaultFont(self.body_font)
            document.setMarkdown(source.text())
            cursor = self.textCursor()
            cursor.beginEditBlock()
            cursor.insertFragment(QTextDocumentFragment(document))
            self.normalize_tables()
            cursor.endEditBlock()
        else:
            super().insertFromMimeData(source)


class SourceEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Markdown 源码编辑区")
        self.setFont(font_for("code"))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(QFontMetricsF(self.font()).horizontalAdvance("    "))
        self.document().setDocumentMargin(20)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Tab and not event.modifiers():
            self.insertPlainText("    ")
        else:
            super().keyPressEvent(event)


class MarkdownHighlighter(QSyntaxHighlighter):
    def __init__(self, document, dark=False):
        super().__init__(document)
        self.set_theme(dark)

    def set_theme(self, dark):
        self.rules = []
        for pattern, color, bold in [
            (r"^#{1,6}\s.*$", "#64a8ff" if dark else "#005cc5", True),
            (r"\*\*.+?\*\*", "#c78bff" if dark else "#7042a3", True),
            (r"`[^`]+`", "#eeaf70" if dark else "#a45419", False),
            (r"\[[^\]]+\]\([^)]+\)", "#64a8ff" if dark else "#005cc5", False),
            (r"^\s*[-*+]\s", "#9b9ba1" if dark else "#6e6e73", False),
        ]:
            format = QTextCharFormat()
            format.setForeground(QColor(color))
            if bold:
                format.setFontWeight(QFont.Weight.DemiBold)
            self.rules.append((re.compile(pattern), format))
        self.rehighlight()

    def highlightBlock(self, text):
        for pattern, format in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)
