"""Regression coverage for rich block editing and lossless local persistence."""
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, Qt, QUrl
from PySide6.QtGui import QColor, QImage, QTextCursor, QTextDocument, QTextFormat, QTextLength
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog
from native.documents import FileChangedError, open_markdown, write_document
from native.editor import COLUMNS, TOGGLE_ID, TOGGLE_PARENT, MarkdownEditor
from native.window import MainWindow

APP = QApplication.instance() or QApplication([])


class BlockEditorTests(unittest.TestCase):
    def setUp(self):
        self.editor = MarkdownEditor()
        self.editor.resize(1100, 700)
        self.editor.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        self.editor.show()
        APP.processEvents()

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()
        APP.processEvents()

    def load(self, text):
        self.editor.load_markdown(text, QUrl())
        APP.processEvents()

    def at(self, number):
        cursor = QTextCursor(self.editor.document().findBlockByNumber(number))
        self.editor.setTextCursor(cursor)
        return cursor

    def test_slash_search_and_keyboard_insert(self):
        QTest.keyClicks(self.editor, "/h2")
        APP.processEvents()
        self.assertTrue(self.editor.insert_menu.isVisible())
        self.assertEqual(self.editor.insert_menu.items.count(), 1)
        QTest.keyClick(self.editor, Qt.Key.Key_Return)
        self.assertEqual(self.editor.toPlainText(), "")
        self.assertEqual(self.editor.textCursor().blockFormat().headingLevel(), 2)
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), "/h2")

    def test_escape_keeps_literal_slash_and_code_has_no_popup(self):
        QTest.keyClicks(self.editor, "/")
        APP.processEvents()
        QTest.keyClick(self.editor, Qt.Key.Key_Escape)
        APP.processEvents()
        self.assertEqual(self.editor.toPlainText(), "/")
        self.assertFalse(self.editor.insert_menu.isVisible())
        self.load("")
        self.editor.make_code_block()
        QTest.keyClicks(self.editor, "/")
        APP.processEvents()
        self.assertFalse(self.editor.insert_menu.isVisible())

    def test_add_below_preserves_existing_next_paragraph(self):
        self.load("first\n\nsecond")
        self.editor.hover_cursor = self.at(0)
        self.editor.add_block_below()
        self.assertEqual(self.editor.toPlainText().splitlines(), ["first", "/", "second"])
        self.editor.choose_block("heading2")
        self.editor.insertPlainText("middle")
        self.assertIn("second", self.editor.toPlainText())

    def test_moves_at_both_document_ends_preserve_boundaries_and_undo(self):
        self.load("A\n\nB\n\nC")
        self.at(0)
        self.editor.move_block(1)
        self.assertEqual(self.editor.toPlainText(), "B\nA\nC")
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), "A\nB\nC")
        self.at(2)
        self.editor.move_block_to(4, 0)
        self.assertEqual(self.editor.toPlainText(), "C\nA\nB")
        self.editor.undo()
        self.at(0)
        self.editor.move_block_to(0, self.editor.document().characterCount() - 1)
        self.assertEqual(self.editor.toPlainText(), "B\nC\nA")

    def test_duplicate_last_and_delete_keep_neighbor_content(self):
        self.load("A\n\nB")
        self.at(1)
        self.editor.duplicate_block()
        self.assertEqual(self.editor.toPlainText(), "A\nB\nB")
        self.editor.delete_block()
        self.assertEqual(self.editor.toPlainText(), "A\nB")
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), "A\nB\nB")

    def test_move_preserves_inline_format_and_emoji(self):
        self.load("**😀 first**\n\nsecond")
        self.at(0)
        self.editor.move_block(1)
        self.assertEqual(self.editor.toPlainText(), "second\n😀 first")
        self.assertIn("**😀 first**", self.editor.toMarkdown())

    def test_color_highlight_and_underline_round_trip(self):
        self.load("彩色 😀")
        self.editor.selectAll()
        self.editor.set_color("#d44c47")
        self.editor.set_color("#b58b08", True)
        self.editor.toggle_character("underline")
        rich = self.editor.rich_content()
        self.assertIsNotNone(rich)
        self.editor.load_rich_content(rich, QUrl())
        self.editor.selectAll()
        character = self.editor.textCursor().charFormat()
        self.assertEqual(character.foreground().color().name(), "#d44c47")
        self.assertTrue(character.hasProperty(QTextFormat.Property.BackgroundBrush))
        self.assertTrue(character.fontUnderline())
        self.assertEqual(self.editor.toPlainText(), "彩色 😀")
        self.editor.set_color(None)
        self.assertFalse(self.editor.textCursor().charFormat().hasProperty(QTextFormat.Property.ForegroundBrush))
        self.assertTrue(self.editor.textCursor().charFormat().fontUnderline())

    def test_old_rich_spacing_is_normalized_without_losing_formats_or_fold_state(self):
        self.load("title")
        self.editor.insert_toggle()
        self.editor.insertPlainText("colored child")
        self.editor.selectAll()
        self.editor.set_color("#d44c47")
        self.editor.set_color("#b58b08", True)
        title = self.editor.document().firstBlock()
        self.editor.hover_cursor = QTextCursor(title)
        self.editor.toggle_fold()
        block = title
        while block.isValid():
            cursor = QTextCursor(block)
            format = cursor.blockFormat()
            format.setTopMargin(90)
            format.setBottomMargin(90)
            format.setLineHeight(250, format.LineHeightTypes.ProportionalHeight.value)
            cursor.setBlockFormat(format)
            block = block.next()
        old = self.editor.rich_content()
        self.editor.load_rich_content(old, QUrl())
        title = self.editor.document().firstBlock()
        self.assertEqual(self.editor.toPlainText(), "title\ncolored child")
        self.assertFalse(title.next().isVisible())
        self.assertEqual(title.blockFormat().property(TOGGLE_ID), old["blocks"][0]["toggle"])
        self.assertLess(title.blockFormat().topMargin(), 20)
        self.assertLess(title.next().blockFormat().bottomMargin(), 20)
        self.editor.selectAll()
        character = self.editor.textCursor().charFormat()
        self.assertEqual(character.foreground().color().name(), "#d44c47")
        self.assertEqual(character.background().color().name(), "#b58b08")
        self.assertFalse(self.editor.document().isModified())
        self.assertFalse(self.editor.document().isUndoAvailable())

    def test_fold_arrow_remains_clickable_inside_compact_body(self):
        self.load("title")
        self.editor.insert_toggle()
        self.editor.insertPlainText("child")
        APP.processEvents()
        title = self.editor.document().firstBlock()
        rectangle = self.editor.cursorRect(QTextCursor(title))
        point = rectangle.center()
        point.setX(rectangle.left() - 14)
        self.assertTrue(self.editor.viewport().rect().contains(point))
        QTest.mouseClick(self.editor.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertFalse(title.next().isVisible())
        self.editor.undo()
        self.assertTrue(title.next().isVisible())

    def test_import_typing_and_conversion_use_consistent_block_spacing(self):
        self.load("first\n\n## section\n\n- item")
        imported_heading = self.editor.document().findBlockByNumber(1).blockFormat()
        imported_list = self.editor.document().findBlockByNumber(2).blockFormat()
        self.load("first")
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        QTest.keyClick(self.editor, Qt.Key.Key_Return)
        self.editor.convert_blocks("heading2")
        typed_heading = self.editor.textCursor().blockFormat()
        self.assertEqual(
            (typed_heading.topMargin(), typed_heading.bottomMargin(), typed_heading.lineHeight()),
            (imported_heading.topMargin(), imported_heading.bottomMargin(), imported_heading.lineHeight()))
        self.editor.insertPlainText("section")
        QTest.keyClick(self.editor, Qt.Key.Key_Return)
        self.editor.make_list()
        typed_list = self.editor.textCursor().blockFormat()
        self.assertEqual(typed_list.bottomMargin(), imported_list.bottomMargin())
        self.assertEqual(typed_list.lineHeight(), imported_list.lineHeight())

    def test_plain_markdown_does_not_require_rich_format(self):
        self.load("# Title\n\n**bold** and text\n\n- item")
        self.assertIsNone(self.editor.rich_content())

    def test_toggle_round_trip_and_undo_reveal_child(self):
        self.load("title")
        self.editor.insert_toggle()
        self.editor.insertPlainText("child")
        title = self.editor.document().firstBlock()
        self.editor.hover_cursor = QTextCursor(title)
        self.editor.toggle_fold()
        self.assertFalse(title.next().isVisible())
        rich = self.editor.rich_content()
        self.editor.load_rich_content(rich, QUrl())
        self.assertEqual(self.editor.toPlainText(), "title\nchild")
        self.assertFalse(self.editor.document().firstBlock().next().isVisible())
        self.editor.hover_cursor = QTextCursor(self.editor.document().firstBlock())
        self.editor.toggle_fold()
        self.assertTrue(self.editor.document().firstBlock().next().isVisible())
        self.editor.undo()
        self.assertFalse(self.editor.document().firstBlock().next().isVisible())

    def test_toggle_duplicate_gets_independent_children(self):
        self.load("title")
        self.editor.insert_toggle()
        self.editor.insertPlainText("child")
        self.at(0)
        self.editor.duplicate_block()
        titles = []
        block = self.editor.document().begin()
        while block.isValid():
            if block.blockFormat().property(TOGGLE_ID):
                titles.append(block)
            block = block.next()
        self.assertEqual(len(titles), 2)
        self.assertNotEqual(titles[0].blockFormat().property(TOGGLE_ID), titles[1].blockFormat().property(TOGGLE_ID))
        self.editor.hover_cursor = QTextCursor(titles[0])
        self.editor.toggle_fold()
        self.assertFalse(titles[0].next().isVisible())
        self.assertTrue(titles[1].next().isVisible())

    def test_toggle_blank_enter_exits_and_list_tab_indents(self):
        self.editor.insert_toggle()
        QTest.keyClicks(self.editor, "child")
        QTest.keyClick(self.editor, Qt.Key.Key_Return)
        QTest.keyClick(self.editor, Qt.Key.Key_Return)
        self.assertFalse(self.editor.textCursor().blockFormat().property(TOGGLE_PARENT))
        self.editor.make_list()
        QTest.keyClicks(self.editor, "item")
        QTest.keyClick(self.editor, Qt.Key.Key_Tab)
        self.assertEqual(self.editor.textCursor().currentList().format().indent(), 2)

    def test_imported_and_inserted_tables_fill_body_and_follow_full_width(self):
        self.load("| A | B |\n| --- | --- |\n| 1 | 2 |")
        table = self.editor.tables()[0]
        self.assertEqual(table.format().width().type(), QTextLength.Type.PercentageLength)
        self.assertEqual(table.format().width().rawValue(), 100)
        narrow = self.editor.document().documentLayout().frameBoundingRect(table).width()
        self.editor.set_full_width(True)
        APP.processEvents()
        wide = self.editor.document().documentLayout().frameBoundingRect(table).width()
        self.assertGreater(wide, narrow)
        self.assertGreater(wide, self.editor.viewport().width() * .95)

    def test_table_row_column_changes_tab_append_exit_and_undo(self):
        table = self.editor.insert_table(2, 2)
        self.editor.insertPlainText("keep")
        self.editor.table_action("column_after")
        self.editor.table_action("row_after")
        self.assertEqual((table.rows(), table.columns()), (3, 3))
        self.assertIn("keep", self.editor.toPlainText())
        self.editor.setTextCursor(table.cellAt(2, 2).firstCursorPosition())
        QTest.keyClick(self.editor, Qt.Key.Key_Tab)
        self.assertEqual(table.rows(), 4)
        self.editor.undo()
        self.assertEqual(table.rows(), 3)
        self.editor.table_action("exit")
        self.assertIsNone(self.editor.textCursor().currentTable())

    def test_columns_round_trip_and_moving_table_preserve_content(self):
        self.load("before\n\nafter")
        self.at(1)
        table = self.editor.insert_table(1, 2, True)
        self.editor.insertPlainText("left")
        self.editor.setTextCursor(table.cellAt(0, 1).firstCursorPosition())
        self.editor.insertPlainText("right")
        rich = self.editor.rich_content()
        self.editor.load_rich_content(rich, QUrl())
        table = self.editor.tables()[0]
        self.assertTrue(table.format().property(COLUMNS))
        self.assertEqual(table.format().border(), 0)
        self.editor.move_block_to(table.firstPosition(), 0)
        self.assertEqual(len(self.editor.tables()), 1)
        self.assertTrue(self.editor.tables()[0].format().property(COLUMNS))
        for text in ("before", "after", "left", "right"):
            self.assertIn(text, self.editor.toPlainText())


    def test_embedded_and_pasted_images_restore_without_original_file(self):
        image = QImage(80, 40, QImage.Format.Format_ARGB32)
        image.fill(QColor("#337ea9"))
        mime = QMimeData()
        mime.setImageData(image)
        self.editor.insertFromMimeData(mime)
        content = self.editor.rich_content()
        self.assertIn("data:image/png;base64,", content["html"])
        self.editor.load_rich_content(content, QUrl())
        cursor = QTextCursor(self.editor.document())
        cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
        name = cursor.charFormat().toImageFormat().name()
        resource = self.editor.document().resource(QTextDocument.ResourceType.ImageResource, QUrl(name))
        self.assertIsInstance(resource, QImage)
        self.assertEqual((resource.width(), resource.height()), (80, 40))

    def test_custom_column_width_survives_rich_round_trip(self):
        table = self.editor.insert_table(1, 2, True)
        self.editor.set_column_width(70)
        self.editor.insertPlainText("wide")
        content = self.editor.rich_content()
        self.editor.load_rich_content(content, QUrl())
        widths = self.editor.tables()[0].format().columnWidthConstraints()
        self.assertAlmostEqual(widths[0].rawValue(), 70)
        self.assertAlmostEqual(widths[1].rawValue(), 30)

    def test_convert_folded_toggle_to_text_reveals_and_detaches_child(self):
        self.load("title")
        self.editor.insert_toggle()
        self.editor.insertPlainText("child")
        self.editor.hover_cursor = self.at(0)
        self.editor.toggle_fold()
        self.at(0)
        self.editor.convert_blocks("paragraph")
        child = self.editor.document().firstBlock().next()
        self.assertTrue(child.isVisible())
        self.assertFalse(child.blockFormat().property(TOGGLE_PARENT))
        self.assertEqual(self.editor.toPlainText(), "title\nchild")

    def test_multi_paragraph_selection_converts_all_blocks(self):
        self.load("A\n\nB\n\nC")
        self.editor.selectAll()
        self.editor.convert_blocks("heading2")
        block = self.editor.document().begin()
        while block.isValid():
            self.assertEqual(block.blockFormat().headingLevel(), 2)
            block = block.next()



    def test_remote_image_download_uses_native_network_and_embeds_result(self):
        image = QImage(32, 16, QImage.Format.Format_ARGB32)
        image.fill(QColor("#448361"))
        encoded = QByteArray()
        buffer = QBuffer(encoded)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        payload = bytes(encoded)
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.end_headers()
                self.wfile.write(payload)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.editor.insert_image_url(QUrl("http://127.0.0.1:" + str(server.server_port) + "/image.png"))
            for _ in range(60):
                QTest.qWait(25)
                if self.editor.rich_content():
                    break
            self.assertIn("data:image/png;base64,", self.editor.rich_content()["html"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_deleting_the_only_table_column_keeps_surrounding_text(self):
        self.load("before\n\nafter")
        self.at(1)
        table = self.editor.insert_table(1, 1)
        self.editor.insertPlainText("cell")
        self.editor.table_action("remove_column")
        self.assertEqual(len(self.editor.tables()), 0)
        self.assertIn("before", self.editor.toPlainText())
        self.assertIn("after", self.editor.toPlainText())
        self.editor.undo()
        self.assertEqual(len(self.editor.tables()), 1)
        self.assertIn("cell", self.editor.toPlainText())



    def test_paragraph_can_move_into_a_column_without_losing_existing_text(self):
        self.load("move me\n\nlast")
        self.at(1)
        table = self.editor.insert_table(1, 2, True)
        self.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
        self.editor.insertPlainText("existing")
        target = table.cellAt(0, 0).firstCursorPosition().position()
        self.editor.move_block_to(0, target)
        self.assertIn("move me", table.cellAt(0, 0).firstCursorPosition().block().text())
        self.assertIn("existing", self.editor.toPlainText())
        self.assertIn("last", self.editor.toPlainText())
        self.editor.undo()
        self.assertTrue(self.editor.toPlainText().startswith("move me"))

    def test_shift_enter_stays_in_one_block(self):
        self.load("line")
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        QTest.keyClick(self.editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        QTest.keyClicks(self.editor, "next")
        self.assertEqual(self.editor.document().blockCount(), 1)



class RichPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.window = MainWindow(self.root / "drafts")

    def tearDown(self):
        self.window.close()
        self.directory.cleanup()
        APP.processEvents()

    def add_rich_text(self):
        self.window.editor.selectAll()
        self.window.editor.set_color("#d44c47")

    def test_rich_file_round_trip_and_external_change_protection(self):
        self.add_rich_text()
        document = self.window.active_document
        path = self.root / "rich.inknote"
        digest = write_document(path, document)
        reopened = open_markdown(path)
        self.assertEqual(reopened["rich_content"], document["rich_content"])
        self.assertEqual(reopened["markdown"], document["markdown"])
        path.write_text("external", encoding="utf-8")
        with self.assertRaises(FileChangedError):
            write_document(path, document, digest)
        self.assertEqual(path.read_text(encoding="utf-8"), "external")

    def test_restart_restores_rich_state_and_full_width(self):
        self.add_rich_text()
        self.window.toggle_full_width(True)
        self.window.flush_workspace()
        restored = MainWindow(self.root / "drafts")
        try:
            restored.editor.selectAll()
            self.assertEqual(restored.editor.textCursor().charFormat().foreground().color().name(), "#d44c47")
            self.assertTrue(restored.editor.full_width)
            self.assertTrue(restored.source.isReadOnly())
        finally:
            restored.close()

    def test_color_only_change_marks_file_modified(self):
        path = self.root / "rich.inknote"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "")):
            self.assertTrue(self.window.save_as())
        self.add_rich_text()
        self.assertTrue(self.window.document_is_modified(self.window.active_document))
        self.assertTrue(self.window.save_file())
        self.assertFalse(self.window.document_is_modified(self.window.active_document))

    def test_rich_source_preview_does_not_erase_styles_and_export_is_explicit(self):
        self.add_rich_text()
        rich = self.window.active_document["rich_content"]
        self.window.set_mode("source")
        self.assertTrue(self.window.source.isReadOnly())
        self.assertEqual(self.window.active_document["rich_content"], rich)
        exported = self.root / "export.md"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(exported), "")):
            self.window.export_markdown()
        self.assertEqual(exported.read_text(encoding="utf-8"), self.window.active_document["markdown"])
        self.assertEqual(self.window.active_document["rich_content"], rich)

    def test_rich_content_cannot_silently_save_to_markdown(self):
        self.add_rich_text()
        path = self.root / "rich.md"
        with self.assertRaises(ValueError):
            write_document(path, self.window.active_document)
        self.assertFalse(path.exists())

    def test_oversized_rich_save_keeps_the_previous_file(self):
        path = self.root / "limit.inknote"
        path.write_text("keep previous", encoding="utf-8")
        document = {"markdown": "", "rich_content": {"html": "a" * (8 * 1024 * 1024), "blocks": [], "columns": []}}
        with self.assertRaises(ValueError):
            write_document(path, document, overwrite=True)
        self.assertEqual(path.read_text(encoding="utf-8"), "keep previous")

    def test_invalid_rich_metadata_is_rejected_without_modifying_file(self):
        path = self.root / "invalid.inknote"
        text = '{"format":"inknote","version":1,"markdown":"text","rich_content":{"html":"text","blocks":[{"index":"wrong"}]}}'
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(ValueError):
            open_markdown(path)
        self.assertEqual(path.read_text(encoding="utf-8"), text)

if __name__ == "__main__":
    unittest.main()
