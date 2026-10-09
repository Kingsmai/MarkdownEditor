"""Generate Windows, macOS and PNG application icons with Qt's SVG renderer."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import struct
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

app = QApplication([])
svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect x="8" y="8" width="240" height="240" rx="54" fill="#007aff"/><path d="M78 62h67l34 34v98H78zM145 62v34h34M100 127h56M100 151h56M100 175h36" fill="none" stroke="white" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/></svg>'


def render_icon(size):
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    QSvgRenderer(svg).render(painter)
    painter.end()
    return image


directory = Path(__file__).parent / "assets"
directory.mkdir(exist_ok=True)
image = render_icon(256)
assert image.save(str(directory / "inknote.png"))
assert image.save(str(directory / "inknote.ico"))
# Modern ICNS records contain PNG images; no image conversion dependency is needed.
records = []
for kind, size in [(b"ic07", 128), (b"ic08", 256), (b"ic09", 512), (b"ic10", 1024)]:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert render_icon(size).save(buffer, "PNG")
    png = bytes(data)
    records.append(kind + struct.pack(">I", len(png) + 8) + png)
content = b"".join(records)
(directory / "inknote.icns").write_bytes(b"icns" + struct.pack(">I", len(content) + 8) + content)
print("Native Windows, macOS and PNG icons generated.")
