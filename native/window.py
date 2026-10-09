"""Native window, document state, and file operations."""
from datetime import datetime
from pathlib import Path
import time
from PySide6.QtCore import QSignalBlocker, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QTextCharFormat, QTextCursor, QImage
from PySide6.QtWidgets import QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QStackedWidget, QStyledItemDelegate, QToolButton, QVBoxLayout, QWidget
from native.documents import FileChangedError, initial_workspace, markdown_headings, new_document, open_markdown, read_workspace, requires_source, word_count, write_document, write_markdown, write_workspace
from native.editor import MarkdownEditor, MarkdownHighlighter, SourceEditor
from native.theme import apply_theme, icon


class DocumentDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        window = self.parent().window()
        colors = window.colors
        selected = index.row() == self.parent().currentRow()
        rectangle = option.rect.adjusted(0, 2, 0, -2)
        painter.save()
        if selected:
            painter.setBrush(QColor(colors["selected"]))
            painter.setPen(QColor(colors["border"]))
            painter.drawRoundedRect(rectangle.adjusted(1, 1, -1, -1), 6, 6)
        document = next(doc for doc in window.workspace["documents"] if doc["id"] == index.data(Qt.ItemDataRole.UserRole))
        icon("document", colors["text"] if selected else colors["secondary"]).paint(painter, rectangle.x()+10, rectangle.y()+12, 17, 17)
        font = QFont(window.font())
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.DemiBold if selected else QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QColor(colors["text"]))
        title = painter.fontMetrics().elidedText(document["title"], Qt.TextElideMode.ElideRight, rectangle.width()-60)
        painter.drawText(rectangle.x()+36, rectangle.y()+22, title)
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QColor(colors["secondary"]))
        updated = datetime.fromtimestamp(document["updated_at"])
        date = f"{updated.month}月{updated.day}日"
        subtitle = date + ("  ·  本地文件" if document.get("file_path") else "  ·  草稿")
        painter.drawText(rectangle.x()+36, rectangle.y()+40, subtitle)
        if document.get("favorite"):
            icon("star", colors["secondary"]).paint(painter, rectangle.right()-19, rectangle.y()+11, 12, 12)
        painter.restore()


class MainWindow(QMainWindow):
    def __init__(self, data_directory, initial_file=None):
        super().__init__()
        self.data_directory = Path(data_directory)
        self.workspace_path = self.data_directory / "workspace.json"
        self.storage_blocked = False
        self.loading = False
        self.mode = "write"
        self.only_favorites = False
        self.focus_mode = False
        self.last_draft_error = None
        try:
            self.workspace = read_workspace(self.workspace_path)
        except (OSError, ValueError) as error:
            self.workspace = initial_workspace()
            self.storage_blocked = True
            self.last_draft_error = "草稿数据无法读取，原文件已保留：" + str(error)
        self.colors = apply_theme(QApplication.instance(), self.workspace.get("theme") == "dark")
        self.setMinimumSize(880, 600)
        self.resize(1320, 860)
        self.setWindowIcon(icon("document", self.colors["blue"]))
        self.setAcceptDrops(True)
        self.draft_timer = QTimer(self)
        self.draft_timer.setSingleShot(True)
        self.draft_timer.setInterval(500)
        self.draft_timer.timeout.connect(self.flush_workspace)
        self.build_window()
        self.build_menus()
        self.refresh_sidebar()
        self.load_active_document()
        self.draft_timer.start()
        if initial_file:
            self.open_path(initial_file)
        if self.last_draft_error:
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, "草稿需要恢复", self.last_draft_error))

    @property
    def active_document(self):
        return next(doc for doc in self.workspace["documents"] if doc["id"] == self.workspace["active_id"])

    def tool_button(self, name, label, callback, checkable=False):
        button = QToolButton()
        button.setProperty("iconName", name)
        button.setIcon(icon(name, self.colors["secondary"]))
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(30, 30)
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.setCheckable(checkable)
        button.clicked.connect(callback)
        return button

    def build_window(self):
        root = QWidget()
        root.setObjectName("paper")
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.setCentralWidget(root)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(232)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(12, 14, 12, 10)
        side.setSpacing(10)
        brand_row = QHBoxLayout()
        brand = QLabel("墨记")
        brand.setObjectName("brand")
        brand_row.addWidget(brand)
        brand_row.addStretch()
        brand_row.addWidget(self.tool_button("new", "新建文稿 (Ctrl+N)", self.new_document))
        side.addLayout(brand_row)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索文稿")
        self.search.setAccessibleName("搜索文稿")
        self.search.setObjectName("sidebarSearch")
        self.search.setFixedHeight(30)
        self.search.addAction(icon("search", self.colors["secondary"]), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self.refresh_sidebar)
        side.addWidget(self.search)
        self.all_button = QPushButton("全部")
        self.favorite_filter = QPushButton("收藏")
        for button, name in [(self.all_button, "document"), (self.favorite_filter, "star")]:
            button.setObjectName("filterButton")
            button.setProperty("iconName", name)
            button.setCheckable(True)
            button.setIcon(icon(name, self.colors["secondary"]))
            button.setFixedHeight(28)
        self.all_button.setChecked(True)
        self.all_button.clicked.connect(lambda: self.set_filter(False))
        self.favorite_filter.clicked.connect(lambda: self.set_filter(True))
        filters = QHBoxLayout()
        filters.setSpacing(6)
        filters.addWidget(self.all_button)
        filters.addWidget(self.favorite_filter)
        side.addLayout(filters)
        label = QLabel("最近文稿")
        label.setObjectName("sectionLabel")
        label.setContentsMargins(2, 4, 0, 0)
        side.addWidget(label)
        self.document_list = QListWidget()
        self.document_list.setAccessibleName("最近文稿列表")
        self.document_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.document_list.customContextMenuRequested.connect(self.show_document_menu)
        self.document_list.setItemDelegate(DocumentDelegate(self.document_list))
        self.document_list.currentItemChanged.connect(self.select_document)
        side.addWidget(self.document_list, 1)
        open_button = QPushButton("打开文件…")
        open_button.setObjectName("openButton")
        open_button.setFixedHeight(30)
        open_button.setProperty("iconName", "open")
        open_button.setIcon(icon("open", self.colors["secondary"]))
        open_button.clicked.connect(self.open_file)
        side.addWidget(open_button)
        footer = QHBoxLayout()
        label = QLabel("保存在此设备")
        label.setObjectName("secondary")
        footer.addWidget(label)
        footer.addStretch()
        self.theme_button = self.tool_button("moon", "切换浅色 / 深色", self.toggle_theme)
        footer.addWidget(self.theme_button)
        side.addLayout(footer)
        row.addWidget(self.sidebar)
        content = QWidget()
        content.setObjectName("paper")
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        row.addWidget(content, 1)

        self.header = QFrame()
        self.header.setObjectName("header")
        self.header.setFixedHeight(52)
        header = QHBoxLayout(self.header)
        header.setContentsMargins(12, 6, 16, 6)
        header.setSpacing(6)
        header.addWidget(self.tool_button("sidebar", "显示 / 隐藏侧边栏", self.toggle_sidebar))
        self.title_label = QLabel()
        self.title_label.setObjectName("documentTitle")
        self.location_label = QLabel()
        self.location_label.setObjectName("fileLocation")
        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(1)
        titles.addWidget(self.title_label)
        titles.addWidget(self.location_label)
        header.addLayout(titles, 1)
        self.segments = QFrame()
        self.segments.setObjectName("segments")
        segments = QHBoxLayout(self.segments)
        segments.setContentsMargins(2, 2, 2, 2)
        segments.setSpacing(2)
        self.write_button = QPushButton("编辑")
        self.source_button = QPushButton("源码")
        group = QButtonGroup(self)
        for button in (self.write_button, self.source_button):
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setFixedHeight(28)
            group.addButton(button)
            segments.addWidget(button)
        self.write_button.clicked.connect(lambda: self.set_mode("write"))
        self.source_button.clicked.connect(lambda: self.set_mode("source"))
        header.addWidget(self.segments)
        self.format_button = QToolButton()
        self.format_button.setText("Aa")
        self.format_button.setObjectName("typeButton")
        self.format_button.setFixedSize(30, 30)
        self.format_button.setToolTip("显示 / 隐藏格式工具")
        self.format_button.setAccessibleName("显示 / 隐藏格式工具")
        self.format_button.setCheckable(True)
        self.format_button.toggled.connect(self.update_formatbar)
        header.addWidget(self.format_button)
        self.focus_button = self.tool_button("focus", "专注模式 (Ctrl+Shift+F)", self.toggle_focus, True)
        header.addWidget(self.focus_button)
        more_button = self.tool_button("more", "更多文稿操作", lambda: None)
        more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more_menu = QMenu(more_button)
        self.favorite_action = self.action(more_menu, "收藏文稿", self.toggle_favorite, checkable=True)
        self.outline_action = self.action(more_menu, "显示大纲", self.toggle_outline, checkable=True)
        more_menu.addSeparator()
        self.action(more_menu, "查找…", self.show_find)
        self.action(more_menu, "导出 PDF…", self.export_pdf)
        more_button.setMenu(more_menu)
        header.addWidget(more_button)
        self.save_button = QPushButton("保存")
        self.save_button.setObjectName("saveButton")
        self.save_button.setFixedHeight(30)
        self.save_button.setToolTip("保存 Markdown 文件 (Ctrl+S)")
        self.save_button.setAccessibleName("保存 Markdown 文件")
        self.save_button.clicked.connect(self.save_file)
        header.addWidget(self.save_button)
        column.addWidget(self.header)

        self.formatbar = QFrame()
        self.formatbar.setObjectName("formatbar")
        self.formatbar.setFixedHeight(36)
        formats = QHBoxLayout(self.formatbar)
        formats.setContentsMargins(12, 2, 12, 2)
        formats.setSpacing(4)
        self.heading_combo = QComboBox()
        self.heading_combo.setAccessibleName("段落格式")
        self.heading_combo.addItems(["正文", "标题 1", "标题 2", "标题 3", "标题 4", "标题 5", "标题 6"])
        self.heading_combo.activated.connect(lambda level: self.editor.set_heading(level))
        formats.addWidget(self.heading_combo)
        self.format_buttons = {}
        for name, label, callback in [
            ("bold", "加粗 (Ctrl+B)", lambda: self.editor.toggle_character("bold")),
            ("italic", "斜体 (Ctrl+I)", lambda: self.editor.toggle_character("italic")),
            ("strike", "删除线", lambda: self.editor.toggle_character("strike")),
            ("code", "行内代码", lambda: self.editor.toggle_character("code")),
            ("list", "无序列表", lambda: self.editor.make_list()),
            ("task", "任务清单", lambda: self.editor.make_list(task=True)),
            ("quote", "引用", lambda: self.editor.make_quote()),
            ("link", "插入链接", self.insert_link),
            ("table", "插入表格", self.insert_table),
        ]:
            button = self.tool_button(name, label, callback, name in ("bold", "italic", "strike", "code"))
            self.format_buttons[name] = button
            formats.addWidget(button)
        formats.addStretch()
        self.mode_label = QLabel("Markdown")
        self.mode_label.setObjectName("secondary")
        formats.addWidget(self.mode_label)
        column.addWidget(self.formatbar)
        self.formatbar.hide()
        self.findbar = QFrame()
        self.findbar.setObjectName("findbar")
        find = QHBoxLayout(self.findbar)
        find.setContentsMargins(12, 4, 12, 4)
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("在文稿中查找")
        self.find_input.setAccessibleName("查找文稿文字")
        self.find_input.returnPressed.connect(self.find_next)
        find.addWidget(self.find_input, 1)
        next_button = QPushButton("下一个")
        next_button.clicked.connect(self.find_next)
        find.addWidget(next_button)
        find.addWidget(self.tool_button("close", "关闭查找", self.hide_find))
        self.findbar.hide()
        column.addWidget(self.findbar)
        self.editor = MarkdownEditor()
        self.editor.colors = self.colors
        self.editor.set_full_width(self.workspace.get("full_width", False))
        self.editor.linkRequested.connect(self.insert_link)
        self.editor.imageRequested.connect(self.insert_image)
        self.editor.imageError.connect(lambda message: self.statusBar().showMessage(message, 6000))
        self.source = SourceEditor()
        self.source_highlighter = MarkdownHighlighter(self.source.document(), self.workspace.get("theme") == "dark")
        self.editor.textChanged.connect(self.editor_changed)
        self.source.textChanged.connect(self.editor_changed)
        self.editor.cursorPositionChanged.connect(self.update_format_buttons)
        self.editor_stack = QStackedWidget()
        self.editor_stack.addWidget(self.editor)
        self.editor_stack.addWidget(self.source)
        writing = QHBoxLayout()
        writing.setContentsMargins(0, 0, 0, 0)
        writing.setSpacing(0)
        writing.addWidget(self.editor_stack, 1)
        self.outline = QFrame()
        self.outline.setObjectName("outline")
        self.outline.setFixedWidth(200)
        outline = QVBoxLayout(self.outline)
        outline.setContentsMargins(12, 16, 10, 12)
        label = QLabel("文档大纲")
        label.setObjectName("sectionLabel")
        outline.addWidget(label)
        self.outline_list = QListWidget()
        self.outline_list.setObjectName("outlineList")
        self.outline_list.setAccessibleName("文档大纲")
        self.outline_list.itemClicked.connect(self.jump_to_heading)
        outline.addWidget(self.outline_list, 1)
        writing.addWidget(self.outline)
        self.outline.hide()
        column.addLayout(writing, 1)
        self.save_state = QLabel()
        self.save_state.setObjectName("secondary")
        self.count_label = QLabel()
        self.count_label.setObjectName("secondary")
        self.statusBar().addWidget(self.save_state, 1)
        self.statusBar().addPermanentWidget(self.count_label)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().setFixedHeight(26)
        self.statusBar().setContentsMargins(10, 0, 12, 0)

    def action(self, menu, text, callback, shortcut=None, checkable=False):
        action = QAction(text, self)
        action.setCheckable(checkable)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(shortcut)
        menu.addAction(action)
        return action

    def build_menus(self):
        menu = self.menuBar().addMenu("文件")
        self.action(menu, "新建文稿", self.new_document, QKeySequence.StandardKey.New)
        self.action(menu, "打开…", self.open_file, QKeySequence.StandardKey.Open)
        menu.addSeparator()
        self.action(menu, "保存", self.save_file, QKeySequence.StandardKey.Save)
        self.action(menu, "另存为…", self.save_as, QKeySequence.StandardKey.SaveAs)
        self.action(menu, "导出 Markdown 副本…", self.export_markdown)
        self.action(menu, "导出 HTML…", self.export_html)
        self.action(menu, "导出 PDF…", self.export_pdf)
        menu.addSeparator()
        self.action(menu, "退出", self.close, QKeySequence.StandardKey.Quit)
        menu = self.menuBar().addMenu("编辑")
        self.action(menu, "撤销", lambda: self.current_editor().undo(), QKeySequence.StandardKey.Undo)
        self.action(menu, "重做", lambda: self.current_editor().redo(), QKeySequence.StandardKey.Redo)
        menu.addSeparator()
        for title, operation, shortcut in [
            ("剪切", "cut", QKeySequence.StandardKey.Cut), ("复制", "copy", QKeySequence.StandardKey.Copy),
            ("粘贴", "paste", QKeySequence.StandardKey.Paste), ("全选", "selectAll", QKeySequence.StandardKey.SelectAll),
        ]:
            self.action(menu, title, lambda checked=False, operation=operation: getattr(self.current_editor(), operation)(), shortcut)
        menu.addSeparator()
        self.action(menu, "查找…", self.show_find, QKeySequence.StandardKey.Find)
        self.format_menu = self.menuBar().addMenu("格式")
        self.action(self.format_menu, "加粗", lambda: self.editor.toggle_character("bold"), QKeySequence("Ctrl+B"))
        self.action(self.format_menu, "斜体", lambda: self.editor.toggle_character("italic"), QKeySequence("Ctrl+I"))
        self.action(self.format_menu, "删除线", lambda: self.editor.toggle_character("strike"))
        self.action(self.format_menu, "行内代码", lambda: self.editor.toggle_character("code"))
        self.action(self.format_menu, "下划线", lambda: self.editor.toggle_character("underline"), QKeySequence("Ctrl+U"))
        self.action(self.format_menu, "文字颜色 / 高亮", self.editor.selection_bar.show_colors)
        self.format_menu.addSeparator()
        for level in range(4):
            self.action(self.format_menu, "正文" if not level else "标题 " + str(level), lambda checked=False, level=level: self.editor.set_heading(level))
        self.format_menu.addSeparator()
        for title, callback in [
            ("无序列表", lambda: self.editor.make_list()), ("有序列表", lambda: self.editor.make_list(ordered=True)),
            ("任务清单", lambda: self.editor.make_list(task=True)), ("引用", self.editor.make_quote),
            ("代码块", self.editor.make_code_block), ("折叠块", self.editor.insert_toggle),
            ("两栏布局", lambda: self.editor.insert_table(1, 2, True)), ("插入图片…", self.insert_image),
            ("插入链接…", self.insert_link), ("插入表格", self.insert_table),
        ]:
            self.action(self.format_menu, title, callback)
        self.action(self.format_menu, "标记任务完成 / 未完成", self.editor.toggle_task, QKeySequence("Ctrl+Return"))
        menu = self.menuBar().addMenu("显示")
        self.action(menu, "显示 / 隐藏侧边栏", self.toggle_sidebar)
        self.action(menu, "显示 / 隐藏大纲", self.toggle_outline)
        self.action(menu, "显示 / 隐藏格式工具", self.format_button.toggle)
        self.full_width_action = self.action(menu, "全宽正文", self.toggle_full_width, checkable=True)
        self.full_width_action.setChecked(self.editor.full_width)
        self.action(menu, "切换编辑 / 源码", lambda: self.set_mode("source" if self.mode=="write" else "write"), QKeySequence("Ctrl+E"))
        self.focus_action = self.action(menu, "专注模式", self.toggle_focus, QKeySequence("Ctrl+Shift+F"), True)
        menu.addSeparator()
        self.action(menu, "切换浅色 / 深色", self.toggle_theme)
        self.action(menu, "放大文字", lambda: self.current_editor().zoomIn(1), QKeySequence.StandardKey.ZoomIn)
        self.action(menu, "缩小文字", lambda: self.current_editor().zoomOut(1), QKeySequence.StandardKey.ZoomOut)
        menu = self.menuBar().addMenu("帮助")
        self.action(menu, "Markdown 参考", self.open_guide)
        self.action(menu, "关于墨记", lambda: QMessageBox.about(self, "墨记", "墨记 · 原生块编辑器 0.3\n\nQt 原生控件 · 本地 Markdown 文件\n\n草稿保存在：\n" + str(self.data_directory)))

    def document_is_modified(self, document):
        return (document.get("saved_markdown") != document["markdown"] or
                document.get("saved_rich_content") != document.get("rich_content"))

    def current_editor(self):
        return self.source if self.mode == "source" else self.editor

    def refresh_sidebar(self, *_):
        if not hasattr(self, "document_list"):
            return
        scroll = self.document_list.verticalScrollBar().value()
        blocker = QSignalBlocker(self.document_list)
        self.document_list.clear()
        query = self.search.text().strip().lower()
        for document in self.workspace["documents"]:
            if self.only_favorites and not document.get("favorite"):
                continue
            if query and query not in (document["title"] + document["markdown"]).lower():
                continue
            item = QListWidgetItem(document["title"])
            item.setData(Qt.ItemDataRole.UserRole, document["id"])
            item.setSizeHint(QSize(206, 56))
            item.setToolTip(document["title"])
            self.document_list.addItem(item)
            if document["id"] == self.workspace["active_id"]:
                self.document_list.setCurrentItem(item)
        self.document_list.verticalScrollBar().setValue(scroll)
        del blocker

    def set_filter(self, favorites):
        self.only_favorites = favorites
        self.all_button.setChecked(not favorites)
        self.favorite_filter.setChecked(favorites)
        self.refresh_sidebar()


    def show_document_menu(self, position):
        item = self.document_list.itemAt(position)
        if not item:
            return
        identifier = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction("重命名…", lambda: self.rename_document(identifier))
        menu.addAction("从最近文稿移除…", lambda: self.remove_document(identifier))
        menu.exec(self.document_list.viewport().mapToGlobal(position))

    def rename_document(self, identifier):
        document = next(doc for doc in self.workspace["documents"] if doc["id"] == identifier)
        title, accepted = QInputDialog.getText(self, "重命名文稿", "文稿名称", text=document["title"])
        if accepted and title.strip():
            document["title"] = title.strip()[:100]
            self.refresh_sidebar()
            self.update_header()
            self.draft_timer.start()

    def remove_document(self, identifier):
        document = next(doc for doc in self.workspace["documents"] if doc["id"] == identifier)
        message = "从最近文稿移除“" + document["title"] + "”？磁盘上的文件会保留。"
        if self.document_is_modified(document):
            message += "\n这篇文稿有未保存到文件的内容，请先保存。移除后草稿将被删除。"
        answer = QMessageBox.question(self, "移除文稿", message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.workspace["documents"].remove(document)
        if not self.workspace["documents"]:
            self.workspace["documents"].append(new_document())
        if self.workspace["active_id"] == identifier:
            self.workspace["active_id"] = self.workspace["documents"][0]["id"]
            self.load_active_document()
        self.refresh_sidebar()
        self.flush_workspace()

    def select_document(self, item, previous=None):
        if item:
            self.workspace["active_id"] = item.data(Qt.ItemDataRole.UserRole)
            self.load_active_document()
            self.draft_timer.start()

    def load_active_document(self):
        self.loading = True
        document = self.active_document
        base = Path(document["file_path"]).parent if document.get("file_path") else self.data_directory
        base_url = QUrl.fromLocalFile(str(base) + "/")
        if document.get("rich_content"):
            self.editor.load_rich_content(document["rich_content"], base_url)
        else:
            self.editor.load_markdown(document["markdown"], base_url)
        self.source.setReadOnly(bool(document.get("rich_content")))
        self.source.setToolTip("富文稿的 Markdown 内容预览；使用编辑模式修改以保留颜色和布局。" if document.get("rich_content") else "")
        self.source.setPlainText(document["markdown"])
        self.source.document().setModified(False)
        if requires_source(document["markdown"]) and not document.get("rich_content"):
            self.mode = "source"
        self.editor_stack.setCurrentWidget(self.current_editor())
        self.update_mode_controls()
        self.loading = False
        self.update_header()
        self.update_outline()
        self.update_format_buttons()

    def set_mode(self, mode):
        if mode == "write" and requires_source(self.active_document["markdown"]) and not self.active_document.get("rich_content"):
            QMessageBox.information(self, "保留 Markdown 原文", "这篇文稿含有公式、脚注、YAML 或 HTML 等扩展语法。\n当前使用源码模式编辑，避免格式转换造成内容丢失。")
            self.update_mode_controls()
            return
        if mode != self.mode:
            self.mode = mode
            self.load_active_document()
            self.current_editor().setFocus()

    def update_mode_controls(self):
        self.write_button.setChecked(self.mode=="write")
        self.source_button.setChecked(self.mode=="source")
        self.source_button.setText("预览" if self.active_document.get("rich_content") else "源码")
        self.source_button.setToolTip("只读 Markdown 预览；编辑模式保留颜色和布局。" if self.active_document.get("rich_content") else "编辑 Markdown 源码")
        self.formatbar.setEnabled(self.mode=="write")
        self.format_menu.setEnabled(self.mode=="write")
        self.format_button.setEnabled(self.mode=="write")
        self.update_formatbar()
        self.mode_label.setText("块编辑" if self.mode == "write" else "Markdown 预览（只读）" if self.active_document.get("rich_content") else "原始 Markdown")

    def editor_changed(self):
        if self.loading:
            return
        document = self.active_document
        if self.mode == "source" and document.get("rich_content"):
            return
        document["markdown"] = self.source.toPlainText() if self.mode == "source" else self.editor.toMarkdown()
        document["rich_content"] = None if self.mode == "source" else self.editor.rich_content()
        self.source.setReadOnly(bool(document.get("rich_content")))
        document["updated_at"] = time.time()
        self.draft_timer.start()
        self.save_state.setText("正在保存草稿…")
        self.setWindowModified(self.document_is_modified(document))
        self.count_label.setText(f"{word_count(document['markdown']):,} 字    UTF-8")
        self.update_outline()

    def update_header(self):
        document = self.active_document
        self.title_label.setText(document["title"])
        path = document.get("file_path")
        self.location_label.setText(str(Path(path).parent) if path else "本地草稿")
        self.location_label.setToolTip(path or str(self.data_directory))
        self.setWindowTitle(document["title"] + " — 墨记[*]")
        self.setWindowModified(self.document_is_modified(document))
        self.favorite_action.setChecked(bool(document.get("favorite")))
        self.count_label.setText(f"{word_count(document['markdown']):,} 字    UTF-8")
        self.update_save_state()

    def update_save_state(self):
        if self.storage_blocked or self.last_draft_error:
            self.save_state.setText("草稿保存不可用，请保存为文件")
        elif not self.document_is_modified(self.active_document):
            self.save_state.setText("已保存到文件")
        else:
            self.save_state.setText("草稿已保留 · 尚未保存到文件")

    def flush_workspace(self):
        self.draft_timer.stop()
        if self.storage_blocked:
            return False
        try:
            write_workspace(self.workspace_path, self.workspace)
            self.last_draft_error = None
            self.update_save_state()
            return True
        except OSError as error:
            self.last_draft_error = str(error)
            self.update_save_state()
            return False

    def new_document(self):
        document = new_document()
        self.workspace["documents"].insert(0, document)
        self.workspace["active_id"] = document["id"]
        self.mode = "write"
        self.search.clear()
        self.set_filter(False)
        self.load_active_document()
        self.refresh_sidebar()
        self.draft_timer.start()
        self.editor.setFocus()

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开文稿", "", "文稿 (*.inknote *.md *.markdown *.txt)")
        if path:
            self.open_path(path)

    def open_path(self, path):
        try:
            resolved = str(Path(path).resolve())
            existing = next((doc for doc in self.workspace["documents"] if doc.get("file_path")==resolved), None)
            if existing:
                self.workspace["active_id"] = existing["id"]
            else:
                document = open_markdown(path)
                self.workspace["documents"].insert(0, document)
                self.workspace["active_id"] = document["id"]
            # Opening in source mode preserves the original text until the user edits it.
            self.mode = "write" if Path(path).suffix.lower() == ".inknote" else "source"
            self.search.clear()
            self.set_filter(False)
            self.load_active_document()
            self.refresh_sidebar()
            self.draft_timer.start()
        except (OSError, UnicodeError, ValueError) as error:
            QMessageBox.warning(self, "无法打开文稿", str(error))

    def save_file(self):
        document = self.active_document
        if not document.get("file_path"):
            return self.save_as()
        if document.get("rich_content") and Path(document["file_path"]).suffix.lower() != ".inknote":
            self.statusBar().showMessage("富格式将另存为 .inknote，原 Markdown 文件保留。", 5000)
            return self.save_as()
        try:
            document["disk_hash"] = write_document(document["file_path"], document, document.get("disk_hash"))
        except FileChangedError:
            dialog = QMessageBox(self)
            dialog.setWindowTitle("文件已经变化")
            dialog.setText("磁盘上的文件已被其他程序修改、移动或删除。\n建议另存为保留两个版本。")
            save_copy = dialog.addButton("另存为…", QMessageBox.ButtonRole.AcceptRole)
            overwrite = dialog.addButton("覆盖原文件", QMessageBox.ButtonRole.DestructiveRole)
            dialog.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            dialog.setDefaultButton(save_copy)
            dialog.exec()
            if dialog.clickedButton() == save_copy:
                return self.save_as()
            if dialog.clickedButton() != overwrite:
                return False
            try:
                document["disk_hash"] = write_document(document["file_path"], document, overwrite=True)
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "无法保存文件", str(error))
                return False
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "无法保存文件", str(error))
            return False
        document["saved_markdown"] = document["markdown"]
        document["saved_rich_content"] = document.get("rich_content")
        self.flush_workspace()
        self.update_header()
        return True

    def save_as(self):
        document = self.active_document
        rich = bool(document.get("rich_content"))
        extension = ".inknote" if rich else ".md"
        suggested = str(Path(document["file_path"]).with_suffix(extension)) if document.get("file_path") else document["title"] + extension
        filters = "墨记富文稿 (*.inknote)" if rich else "Markdown 文稿 (*.md);;墨记富文稿 (*.inknote)"
        path, selected_filter = QFileDialog.getSaveFileName(self, "保存文稿", suggested, filters)
        if not path:
            return False
        if not Path(path).suffix:
            path += ".inknote" if rich or "inknote" in selected_filter else ".md"
        try:
            # The native save dialog confirms replacement of an existing file.
            document["disk_hash"] = write_document(path, document, overwrite=True)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "无法保存文件", str(error))
            return False
        document["file_path"] = str(Path(path).resolve())
        document["title"] = Path(path).stem
        document["saved_markdown"] = document["markdown"]
        document["saved_rich_content"] = document.get("rich_content")
        self.flush_workspace()
        self.refresh_sidebar()
        self.update_header()
        return True

    def toggle_favorite(self):
        self.active_document["favorite"] = not self.active_document.get("favorite")
        self.favorite_action.setChecked(self.active_document["favorite"])
        self.refresh_sidebar()
        self.draft_timer.start()

    def update_outline(self):
        self.outline_list.clear()
        if self.mode=="source":
            entries = markdown_headings(self.active_document["markdown"])
        else:
            entries = []
            block = self.editor.document().begin()
            while block.isValid():
                level = block.blockFormat().headingLevel()
                if level:
                    entries.append((level, block.text(), block.position()))
                block = block.next()
        for level, title, position in entries:
            item = QListWidgetItem("  "*max(0, level-2) + title)
            item.setData(Qt.ItemDataRole.UserRole, position)
            item.setToolTip(title)
            self.outline_list.addItem(item)

    def jump_to_heading(self, item):
        position = item.data(Qt.ItemDataRole.UserRole)
        editor = self.current_editor()
        cursor = editor.textCursor()
        if self.mode=="source":
            cursor.setPosition(self.source.document().findBlockByNumber(position).position())
        else:
            cursor.setPosition(position)
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()
        editor.setFocus()

    def update_format_buttons(self):
        if not hasattr(self, "format_buttons"):
            return
        character = self.editor.currentCharFormat()
        self.format_buttons["bold"].setChecked(character.fontWeight() >= QFont.Weight.DemiBold)
        self.format_buttons["italic"].setChecked(character.fontItalic())
        self.format_buttons["strike"].setChecked(character.fontStrikeOut())
        self.format_buttons["code"].setChecked(character.fontFixedPitch())
        blocker = QSignalBlocker(self.heading_combo)
        self.heading_combo.setCurrentIndex(self.editor.textCursor().blockFormat().headingLevel())
        del blocker

    def insert_link(self):
        self.editor.select_link()
        value, accepted = QInputDialog.getText(self, "编辑链接", "链接地址（留空移除链接）", text=self.editor.currentCharFormat().anchorHref())
        if not accepted:
            return
        if not value.strip():
            format = QTextCharFormat()
            format.setAnchor(False)
            format.setAnchorHref("")
            format.setFontUnderline(False)
            self.editor.mergeCurrentCharFormat(format)
            self.editor.set_color(None)
            return
        url = QUrl(value.strip())
        if not url.isValid() or url.scheme().lower() not in ("http", "https", "mailto"):
            QMessageBox.warning(self, "链接地址无效", "请输入 http、https 或 mailto 链接。")
            return
        cursor = self.editor.textCursor()
        text = cursor.selectedText() or value
        format = QTextCharFormat()
        format.setAnchor(True)
        format.setAnchorHref(url.toString())
        format.setForeground(QColor(self.colors["blue"]))
        format.setFontUnderline(True)
        original = self.editor.currentCharFormat()
        cursor.insertText(text, format)
        self.editor.setTextCursor(cursor)
        self.editor.setCurrentCharFormat(original)
        self.editor.setFocus()

    def insert_table(self):
        self.editor.insert_table()

    def insert_image(self):
        menu = QMenu(self)
        local = menu.addAction("选择本地图片…")
        remote = menu.addAction("输入图片地址…")
        selected = menu.exec(self.editor.mapToGlobal(self.editor.cursorRect().bottomLeft() + self.editor.viewport().pos()))
        if selected == local:
            path, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.gif *.webp *.bmp)")
            if not path:
                return
            image = QImage(path)
            if image.isNull():
                QMessageBox.warning(self, "无法打开图片", "这张图片无法读取。")
                return
            self.editor.insert_image(image)
            return
        elif selected == remote:
            name, accepted = QInputDialog.getText(self, "插入图片", "http / https 图片地址")
            if not accepted or not name:
                return
            url = QUrl(name.strip())
            if not url.isValid() or url.scheme().lower() not in ("http", "https"):
                QMessageBox.warning(self, "图片地址无效", "请输入 http 或 https 图片地址。")
                return
            self.editor.insert_image_url(url)
            self.statusBar().showMessage("正在下载图片…", 5000)
            return

    def export_markdown(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出 Markdown（颜色和布局转换为普通内容）", self.active_document["title"] + ".md", "Markdown (*.md)")
        if path:
            try:
                write_markdown(path if Path(path).suffix else path + ".md", self.active_document["markdown"], overwrite=True)
            except OSError as error:
                QMessageBox.warning(self, "无法导出", str(error))

    def export_html(self):
        if self.mode == "source":
            self.set_mode("write")
            if self.mode == "source":
                return
        path, _ = QFileDialog.getSaveFileName(self, "导出 HTML", self.active_document["title"] + ".html", "HTML (*.html)")
        if path:
            try:
                write_markdown(path if Path(path).suffix else path + ".html", self.editor.toHtml(), overwrite=True)
            except OSError as error:
                QMessageBox.warning(self, "无法导出", str(error))

    def toggle_full_width(self, enabled):
        self.workspace["full_width"] = bool(enabled)
        self.editor.set_full_width(enabled)
        self.draft_timer.start()

    def export_pdf(self):
        if self.mode=="source":
            QMessageBox.information(self, "导出 PDF", "请先切换到编辑模式，再导出排版后的 PDF。")
            return
        from PySide6.QtPrintSupport import QPrinter
        path, _ = QFileDialog.getSaveFileName(self, "导出 PDF", self.active_document["title"]+".pdf", "PDF 文件 (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        # Print all text, including children that are folded in the editing view.
        document = self.editor.document().clone()
        block = document.begin()
        while block.isValid():
            block.setVisible(True)
            block = block.next()
        document.markContentsDirty(0, document.characterCount())
        document.print_(printer)

    def show_find(self):
        self.findbar.show()
        self.find_input.setFocus()
        self.find_input.selectAll()

    def hide_find(self):
        self.findbar.hide()
        self.current_editor().setFocus()

    def find_next(self):
        text = self.find_input.text()
        if text:
            editor = self.current_editor()
            if not editor.find(text):
                editor.moveCursor(QTextCursor.MoveOperation.Start)
                if not editor.find(text):
                    self.statusBar().showMessage("没有找到“"+text+"”", 3000)

    def toggle_sidebar(self):
        self.sidebar.setVisible(not self.sidebar.isVisible())

    def toggle_outline(self):
        visible = self.outline.isHidden()
        self.outline.setVisible(visible)
        self.outline_action.setChecked(visible)

    def update_formatbar(self, *_):
        self.formatbar.setVisible(self.format_button.isChecked() and self.mode == "write" and not self.focus_mode)

    def toggle_focus(self):
        self.focus_mode = not self.focus_mode
        self.sidebar.setVisible(not self.focus_mode)
        self.outline.setVisible(not self.focus_mode and self.outline_action.isChecked())
        self.update_formatbar()
        self.focus_button.setChecked(self.focus_mode)
        self.focus_action.setChecked(self.focus_mode)
        self.current_editor().setFocus()

    def toggle_theme(self):
        dark = self.workspace.get("theme") != "dark"
        self.workspace["theme"] = "dark" if dark else "light"
        self.loading = True
        try:
            self.colors = apply_theme(QApplication.instance(), dark)
            self.source_highlighter.set_theme(dark)
            self.editor.colors = self.colors
            with QSignalBlocker(self.editor):
                self.editor.normalize_tables()
        finally:
            self.loading = False
        for button in self.findChildren(QToolButton) + self.findChildren(QPushButton):
            name = button.property("iconName")
            if name:
                button.setIcon(icon(name, self.colors["secondary"]))
        self.theme_button.setIcon(icon("sun" if dark else "moon", self.colors["secondary"]))
        self.document_list.viewport().update()
        self.draft_timer.start()

    def open_guide(self):
        guide = next((doc for doc in self.workspace["documents"] if doc["title"]=="Markdown 参考"), None)
        if guide:
            self.workspace["active_id"] = guide["id"]
            self.mode = "write"
            self.load_active_document()
            self.refresh_sidebar()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.open_path(url.toLocalFile())
                break
        event.acceptProposedAction()

    def keyPressEvent(self, event):
        if event.key()==Qt.Key.Key_Escape:
            if self.findbar.isVisible():
                self.hide_find()
            elif self.focus_mode:
                self.toggle_focus()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if not self.flush_workspace():
            answer = QMessageBox.question(self, "草稿尚未保存", "工作空间无法写入磁盘。退出可能丢失未保存的修改。\n请先把重要文稿另存为文件。", QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Discard:
                event.ignore()
                return
        event.accept()

