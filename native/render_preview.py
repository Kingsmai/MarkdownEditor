"""Render the application's own Qt widgets for design review."""
from pathlib import Path
import tempfile
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from native.window import MainWindow
from native.theme import application_font


def render_blocks(window, root, app):
    editor = window.editor
    window.loading = True
    editor.load_markdown("# 用块整理你的想法\n\n输入 / 插入内容，拖动左侧手柄调整顺序。\n\n每一段，都可以成为一个块。", QUrl())
    window.active_document["title"] = "块编辑体验"
    window.loading = False
    editor.find("每一段，都可以成为一个块。")
    editor.set_color("#337ea9")
    editor.set_color("#b58b08", True)
    editor.moveCursor(QTextCursor.MoveOperation.End)
    editor.setCurrentCharFormat(editor.body_character_format())
    editor.textCursor().insertBlock()
    editor.insertPlainText("本周计划")
    editor.convert_blocks("heading2")
    editor.textCursor().insertBlock()
    editor.convert_blocks("paragraph")
    table = editor.insert_table(3, 3)
    values = [["任务", "负责人", "进度"], ["梳理产品思路", "我", "已完成"], ["写下第一个想法", "我", "进行中"]]
    for row, entries in enumerate(values):
        for column, value in enumerate(entries):
            editor.setTextCursor(table.cellAt(row, column).firstCursorPosition())
            editor.insertPlainText(value)
    editor.table_action("exit")
    editor.insertPlainText("更多细节")
    editor.insert_toggle()
    editor.insertPlainText("折叠块会记住展开状态，内容随文稿一起保存。")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.keyClick(editor, Qt.Key.Key_Return)
    columns = editor.insert_table(1, 2, True)
    editor.setTextCursor(columns.cellAt(0, 0).firstCursorPosition())
    editor.insertPlainText("灵感收集")
    editor.setTextCursor(columns.cellAt(0, 1).firstCursorPosition())
    editor.insertPlainText("下一步行动")
    editor.table_action("exit")
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    window.editor_changed()
    window.update_header()
    app.processEvents()
    window.grab().save(str(root / "docs" / "native-blocks.png"))
    editor.moveCursor(QTextCursor.MoveOperation.End)
    editor.insertPlainText("/")
    editor.update_controls()
    app.processEvents()
    window.grab().save(str(root / "docs" / "native-block-menu.png"))


def main():
    app = QApplication([])
    app.setFont(application_font())
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as data:
        window = MainWindow(Path(data))
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.show()
        app.processEvents()
        window.grab().save(str(root / "docs" / "native-light.png"))
        window.toggle_theme()
        app.processEvents()
        window.grab().save(str(root / "docs" / "native-dark.png"))
        window.toggle_theme()
        window.toggle_focus()
        app.processEvents()
        window.grab().save(str(root / "docs" / "native-focus.png"))
        window.toggle_focus()
        render_blocks(window, root, app)
        window.close()
    print("Native Qt previews rendered.")

if __name__ == "__main__":
    main()
