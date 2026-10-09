"""Native controls for block insertion, dragging, and text formatting."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QToolButton, QVBoxLayout
from native.theme import icon

BLOCK_TYPES = [
    ("paragraph", "正文", "text paragraph 正文 文字", "普通文字段落"),
    ("heading1", "标题 1", "h1 heading 标题", "大标题"),
    ("heading2", "标题 2", "h2 heading 标题", "中标题"),
    ("heading3", "标题 3", "h3 heading 标题", "小标题"),
    ("bullet", "无序列表", "bullet list 无序 列表", "使用圆点组织内容"),
    ("ordered", "有序列表", "number ordered list 有序 编号 列表", "使用数字组织内容"),
    ("task", "待办事项", "todo task check 待办 任务 清单", "可勾选的任务"),
    ("toggle", "折叠块", "toggle 折叠", "展开或收起子内容"),
    ("quote", "引用", "quote 引用", "引用文字"),
    ("code", "代码块", "code 代码", "等宽字体的代码"),
    ("divider", "分隔线", "divider hr 分隔线", "分隔内容"),
    ("table", "表格", "table 表格", "全宽表格，支持行列操作"),
    ("columns", "两栏布局", "columns 分栏 两栏", "并排编辑两列内容"),
    ("image", "图片", "image photo 图片", "插入本地图片或图片地址"),
    ("link", "链接", "link url 链接", "插入或编辑链接"),
]


def button(parent, text, label, callback, icon_name=None):
    control = QToolButton(parent)
    control.setText(text)
    control.setToolTip(label)
    control.setAccessibleName(label)
    control.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    control.setFixedSize(30, 30)
    if icon_name:
        control.setProperty("iconName", icon_name)
        control.setIcon(icon(icon_name, parent.editor.colors["secondary"]))
    control.clicked.connect(callback)
    return control


class InsertMenu(QFrame):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setObjectName("blockPopup")
        self.setAccessibleName("插入块菜单")
        self.setFixedWidth(264)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        self.label = QLabel("插入块 · 输入中文或英文筛选")
        self.label.setObjectName("secondary")
        layout.addWidget(self.label)
        self.items = QListWidget()
        self.items.setObjectName("blockItems")
        self.items.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.items.setAccessibleName("块类型")
        self.items.itemClicked.connect(self.choose)
        layout.addWidget(self.items)
        layout.addWidget(QLabel("↑ ↓ 选择    Enter 插入    Esc 关闭"))
        self.hide()

    def filter(self, query):
        self.items.clear()
        for kind, title, keywords, description in BLOCK_TYPES:
            if query.casefold() in keywords.casefold():
                item = QListWidgetItem(title + "\n" + description)
                item.setData(Qt.ItemDataRole.UserRole, kind)
                self.items.addItem(item)
        if self.items.count():
            self.items.setCurrentRow(0)
        self.label.setText("没有匹配的块" if not self.items.count() else "插入块 · 输入中文或英文筛选")
        self.setFixedHeight(min(330, 60 + max(1, self.items.count()) * 42))

    def choose(self, item=None):
        item = item or self.items.currentItem()
        if item:
            self.editor.choose_block(item.data(Qt.ItemDataRole.UserRole))

    def step(self, direction):
        count = self.items.count()
        if count:
            self.items.setCurrentRow((self.items.currentRow() + direction) % count)


class BlockHandle(QToolButton):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setText("⠿")
        self.setObjectName("blockHandle")
        self.setFixedSize(24, 28)
        self.setToolTip("点击打开块菜单，拖动调整顺序")
        self.setAccessibleName("块菜单与拖动手柄")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.press_position = None
        self.dragged = False
        self.clicked.connect(self.open_menu)
        self.hide()

    def open_menu(self):
        if not self.dragged:
            self.editor.show_block_menu()

    def mousePressEvent(self, event):
        self.press_position = event.globalPosition().toPoint()
        self.dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.press_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            distance = (event.globalPosition().toPoint() - self.press_position).manhattanLength()
            if distance >= QApplication.startDragDistance() and not self.dragged:
                self.dragged = True
                self.setDown(False)
                self.editor.start_block_drag()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.press_position = None
        super().mouseReleaseEvent(event)


class SelectionBar(QFrame):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setObjectName("blockPopup")
        self.setAccessibleName("选中文字格式工具")
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 3, 4, 3)
        row.setSpacing(1)
        self.type_combo = QComboBox()
        self.type_combo.setAccessibleName("转换选中块")
        self.type_combo.addItems(["正文", "标题 1", "标题 2", "标题 3"])
        self.type_combo.activated.connect(editor.set_heading)
        row.addWidget(self.type_combo)
        self.format_buttons = {}
        for kind, text, label, icon_name in [
            ("bold", "B", "加粗", "bold"), ("italic", "I", "斜体", "italic"),
            ("underline", "U", "下划线", None), ("strike", "S", "删除线", "strike"),
            ("code", "</>", "行内代码", "code"),
        ]:
            control = button(self, text, label, lambda checked=False, kind=kind: editor.toggle_character(kind), icon_name)
            control.setCheckable(True)
            self.format_buttons[kind] = control
            row.addWidget(control)
        row.addWidget(button(self, "", "编辑链接", editor.linkRequested.emit, "link"))
        row.addWidget(button(self, "A", "文字颜色与高亮", self.show_colors))
        self.adjustSize()
        self.hide()

    def show_colors(self):
        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        for title, background in [("文字颜色", False), ("背景高亮", True)]:
            submenu = menu.addMenu(title)
            for name, color in [("默认", None), ("灰色", "#787774"), ("棕色", "#a46848"),
                                ("橙色", "#d9730d"), ("黄色", "#b58b08"), ("绿色", "#448361"),
                                ("蓝色", "#337ea9"), ("紫色", "#9065b0"), ("粉色", "#c14c8a"), ("红色", "#d44c47")]:
                action = submenu.addAction(name)
                action.triggered.connect(lambda checked=False, color=color, background=background: self.editor.set_color(color, background))
        menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    def refresh(self):
        character = self.editor.currentCharFormat()
        self.format_buttons["bold"].setChecked(character.fontWeight() >= 600)
        self.format_buttons["italic"].setChecked(character.fontItalic())
        self.format_buttons["underline"].setChecked(character.fontUnderline())
        self.format_buttons["strike"].setChecked(character.fontStrikeOut())
        self.format_buttons["code"].setChecked(character.fontFixedPitch())
        self.type_combo.setCurrentIndex(min(3, self.editor.textCursor().blockFormat().headingLevel()))
