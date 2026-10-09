"""Critical persistence and native editor behavior, exercised without a desktop."""
import os
# The Windows font backend resolves bold/italic correctly without showing windows.
os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox
from native.documents import FileChangedError, WELCOME, fingerprint, initial_workspace, markdown_headings, open_markdown, read_workspace, requires_source, word_count, write_markdown, write_workspace
from native.editor import MarkdownEditor
from native.window import MainWindow

APP = QApplication.instance() or QApplication([])


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_source_open_and_save_preserve_crlf_and_unicode(self):
        path = self.root / "原文.md"
        original = "# 标题\r\n\r\n**粗体**\r\n\r\n$$x^2$$\r\n"
        path.write_bytes(original.encode("utf-8"))
        document = open_markdown(path)
        write_markdown(path, document["markdown"], document["disk_hash"])
        self.assertEqual(path.read_bytes(), original.encode("utf-8"))

    def test_external_changes_are_not_overwritten(self):
        path = self.root / "test.md"
        path.write_text("original", encoding="utf-8")
        digest = fingerprint(path)
        path.write_text("changed by someone else", encoding="utf-8")
        with self.assertRaises(FileChangedError):
            write_markdown(path, "stale draft", digest)
        self.assertEqual(path.read_text(encoding="utf-8"), "changed by someone else")

    def test_new_save_cannot_replace_existing_file_without_confirmation(self):
        path = self.root / "existing.md"
        path.write_text("existing", encoding="utf-8")
        with self.assertRaises(FileChangedError):
            write_markdown(path, "new")

    def test_explicit_overwrite_replaces_file_and_returns_new_hash(self):
        path = self.root / "existing.md"
        path.write_text("existing", encoding="utf-8")
        digest = write_markdown(path, "new", overwrite=True)
        self.assertEqual(path.read_text(encoding="utf-8"), "new")
        self.assertEqual(digest, fingerprint(path))

    def test_deleted_original_is_reported_before_save(self):
        path = self.root / "missing.md"
        with self.assertRaises(FileChangedError):
            write_markdown(path, "old", "expected digest")

    def test_atomic_workspace_restores_unsaved_draft_and_active_document(self):
        workspace = initial_workspace()
        workspace["documents"][0]["markdown"] += "\n尚未保存到文件的文字\n"
        path = self.root / "workspace.json"
        write_workspace(path, workspace)
        self.assertEqual(read_workspace(path), workspace)
        self.assertEqual(list(self.root.glob(".workspace.json.*")), [])

    def test_corrupt_workspace_is_not_modified(self):
        path = self.root / "workspace.json"
        path.write_text("{ broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            read_workspace(path)
        self.assertEqual(path.read_text(encoding="utf-8"), "{ broken")

    def test_outline_skips_fenced_examples(self):
        source = "# 标题\n````md\n## 示例\n```\n# 仍在示例\n````\n## 正文\n"
        self.assertEqual([title for _, title, _ in markdown_headings(source)], ["标题", "正文"])

    def test_invalid_workspace_shapes_are_rejected_without_overwriting(self):
        path = self.root / "workspace.json"
        for text in ('[]', '{"documents": [1]}', '{"documents": [{"id":"1","title":"A","markdown":"B","updated_at":"invalid"}]}'):
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(ValueError):
                read_workspace(path)
            self.assertEqual(path.read_text(encoding="utf-8"), text)

    def test_thematic_breaks_do_not_force_source_mode(self):
        self.assertFalse(requires_source(WELCOME))
        self.assertFalse(requires_source("# 标题\n\n正文\n\n---\n\n结束"))

    def test_unsupported_syntax_guard_excludes_code_examples(self):
        self.assertTrue(requires_source("---\ntitle: title\n---"))
        self.assertTrue(requires_source("公式 $x^2$"))
        self.assertFalse(requires_source("```html\n<div>$value$</div>\n```"))
        self.assertFalse(requires_source("示例 `<div>$value$</div>`"))

    def test_word_count_ignores_urls_and_task_markers(self):
        self.assertEqual(word_count("# 你好 world\n[链接](https://example.com)"), 5)
        self.assertEqual(word_count("- [x] 完成\n- [ ] hello"), 3)


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.editor = MarkdownEditor()

    def tearDown(self):
        self.editor.close()

    def test_hash_space_creates_heading_and_enter_returns_to_body(self):
        QTest.keyClicks(self.editor, "# ")
        self.assertEqual(self.editor.textCursor().blockFormat().headingLevel(), 1)
        QTest.keyClicks(self.editor, "Title")
        QTest.keyClick(self.editor, Qt.Key.Key_Return)
        self.assertEqual(self.editor.textCursor().blockFormat().headingLevel(), 0)
        QTest.keyClicks(self.editor, "Body")
        markdown = self.editor.toMarkdown()
        self.assertIn("# Title", markdown)
        self.assertIn("Body", markdown)

    def test_inline_markdown_becomes_native_bold(self):
        QTest.keyClicks(self.editor, "**hello**")
        self.assertEqual(self.editor.toPlainText(), "hello")
        self.assertIn("**hello**", self.editor.toMarkdown())


    def test_inline_markdown_keeps_emoji_cursor_positions(self):
        self.editor.insertPlainText("**😀")
        QTest.keyClicks(self.editor, "**")
        self.assertEqual(self.editor.toPlainText(), "😀")
        self.assertIn("**😀**", self.editor.toMarkdown())

    def test_list_prefix_creates_a_native_list(self):
        QTest.keyClicks(self.editor, "- ")
        QTest.keyClicks(self.editor, "item")
        self.assertIsNotNone(self.editor.textCursor().currentList())
        self.assertIn("item", self.editor.toMarkdown())
        self.assertRegex(self.editor.toMarkdown(), r"[-*]\s+item")

    def test_tasks_serialize_checked_and_unchecked(self):
        self.editor.make_list(task=True)
        self.editor.insertPlainText("task")
        self.assertIn("[ ]", self.editor.toMarkdown())
        self.editor.toggle_task()
        self.assertIn("[x]", self.editor.toMarkdown())

    def test_code_block_serializes_with_a_fence(self):
        self.editor.make_code_block()
        self.editor.insertPlainText("print('hello')")
        self.assertIn("```", self.editor.toMarkdown())
        self.assertIn("print('hello')", self.editor.toMarkdown())

    def test_markdown_tables_and_headings_render(self):
        self.editor.load_markdown("# 标题\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n", QUrl())
        self.assertEqual(self.editor.document().firstBlock().blockFormat().headingLevel(), 1)
        self.assertIn("|", self.editor.toMarkdown())
        self.assertIn("1", self.editor.toPlainText())


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.window = MainWindow(self.root / "drafts")

    def tearDown(self):
        self.window.storage_blocked = False
        self.window.close()
        self.directory.cleanup()

    def test_initial_workspace_is_saved_by_the_timer(self):
        QTest.qWait(650)
        self.assertEqual(read_workspace(self.window.workspace_path), self.window.workspace)

    def test_native_save_as_writes_disk_and_remembers_file(self):
        self.window.set_mode("source")
        text = "# 原文\n\n保持 **Markdown**\n"
        self.window.source.setPlainText(text)
        path = self.root / "文稿.md"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "")):
            self.assertTrue(self.window.save_as())
        self.assertEqual(path.read_text(encoding="utf-8"), text)
        self.assertEqual(self.window.active_document["file_path"], str(path.resolve()))
        self.assertEqual(self.window.active_document["saved_markdown"], text)

    def test_relaunch_restores_changed_source_draft(self):
        self.window.set_mode("source")
        text = "# 未保存的草稿\n\n你好。\n"
        self.window.source.setPlainText(text)
        self.window.flush_workspace()
        restored = MainWindow(self.root / "drafts")
        self.assertEqual(restored.active_document["markdown"], text)
        restored.close()

    def test_open_source_is_exact_until_first_edit(self):
        path = self.root / "raw.md"
        text = "# 标题\r\n\r\n**文字**\r\n"
        path.write_bytes(text.encode("utf-8"))
        self.window.open_path(path)
        self.assertEqual(self.window.mode, "source")
        self.assertEqual(self.window.active_document["markdown"], text)
        self.assertTrue(self.window.save_file())
        self.assertEqual(path.read_bytes(), text.encode("utf-8"))

    def test_switching_documents_does_not_leak_editor_changes(self):
        original_id = self.window.active_document["id"]
        original_text = self.window.active_document["markdown"]
        self.window.new_document()
        self.window.set_mode("source")
        self.window.source.setPlainText("# New draft")
        original = next(doc for doc in self.window.workspace["documents"] if doc["id"]==original_id)
        self.assertEqual(original["markdown"], original_text)

    def test_unsafe_conversion_stays_in_source_mode(self):
        self.window.set_mode("source")
        self.window.source.setPlainText("$$x^2$$")
        with patch.object(QMessageBox, "information"):
            self.window.set_mode("write")
        self.assertEqual(self.window.mode, "source")

    def test_dark_theme_changes_native_palette_and_source_highlighter(self):
        self.window.toggle_theme()
        self.assertEqual(self.window.workspace["theme"], "dark")
        self.assertEqual(self.window.colors["paper"], "#1c1c1e")
        self.window.toggle_theme()
        self.assertEqual(self.window.workspace["theme"], "light")


    def test_theme_change_does_not_modify_original_source(self):
        path = self.root / "raw.md"
        original = "# 原文\r\n\r\n**保留**\r\n"
        path.write_bytes(original.encode("utf-8"))
        self.window.open_path(path)
        self.window.toggle_theme()
        self.assertEqual(self.window.active_document["markdown"], original)

    def test_cancelled_file_conflict_preserves_external_edits(self):
        path = self.root / "raw.md"
        path.write_text("original", encoding="utf-8")
        self.window.open_path(path)
        path.write_text("external change", encoding="utf-8")
        with patch.object(QMessageBox, "exec", return_value=0):
            self.assertFalse(self.window.save_file())
        self.assertEqual(path.read_text(encoding="utf-8"), "external change")

    def test_rename_changes_workspace_title(self):
        identifier = self.window.active_document["id"]
        with patch.object(QInputDialog, "getText", return_value=("我的文稿", True)):
            self.window.rename_document(identifier)
        self.assertEqual(self.window.active_document["title"], "我的文稿")

    def test_remove_keeps_disk_file_and_selects_another_document(self):
        path = self.root / "keep.md"
        path.write_text("# Keep", encoding="utf-8")
        self.window.open_path(path)
        identifier = self.window.active_document["id"]
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window.remove_document(identifier)
        self.assertTrue(path.exists())
        self.assertNotEqual(self.window.active_document["id"], identifier)

    def test_source_mode_disables_format_actions(self):
        self.window.set_mode("source")
        self.assertFalse(self.window.format_menu.isEnabled())
        self.window.set_mode("write")
        self.assertTrue(self.window.format_menu.isEnabled())

    def test_pdf_export_produces_a_pdf_file(self):
        path = self.root / "文稿.pdf"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "")):
            self.window.export_pdf()
        self.assertTrue(path.read_bytes().startswith(b"%PDF-"))

    def test_find_wraps_to_the_start_of_the_document(self):
        self.window.find_input.setText("一个想法")
        self.window.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.window.find_next()
        self.assertIn("一个想法", self.window.editor.textCursor().selectedText())


if __name__ == "__main__":
    unittest.main()

