"""Native desktop entry point; no browser, server, or WebView."""
import argparse
from pathlib import Path
import sys
import tempfile
from PySide6.QtCore import QLockFile, QStandardPaths, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from native.documents import read_workspace
from native.window import MainWindow
from native.theme import application_font


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", nargs="?")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()
    if args.smoke_test and (args.file or args.data_dir):
        parser.error("--smoke-test always uses isolated temporary drafts.")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("InkNote")
    app.setOrganizationName("InkNote")
    app.setApplicationDisplayName("墨记")
    app.setFont(application_font())
    temporary_directory = tempfile.TemporaryDirectory(prefix="inknote-smoke-") if args.smoke_test else None
    directory = Path(temporary_directory.name) if temporary_directory else args.data_dir or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    directory.mkdir(parents=True, exist_ok=True)
    # One process owns the workspace, preventing competing draft writes.
    lock = QLockFile(str(directory / "workspace.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, "墨记已经打开", "请返回已经打开的墨记窗口。")
        return 0
    window = MainWindow(directory, args.file)
    if args.smoke_test:
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        QTimer.singleShot(750, window.close)
    window.show()
    result = app.exec()
    lock.unlock()
    if temporary_directory:
        # Exercise the real event loop and close/save flow without touching user drafts.
        workspace_path = directory / "workspace.json"
        if not workspace_path.exists() or not read_workspace(workspace_path)["documents"]:
            result = 1
        temporary_directory.cleanup()
    return result


if __name__ == "__main__":
    sys.exit(main())

