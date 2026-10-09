"""Markdown documents and safe disk persistence; no UI dependencies."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

WELCOME = """# 开始写作。

让注意力回到文字本身。

墨记是一个安静、直接的 Markdown 编辑器。像写一份文档一样开始，格式会随着你的输入自然出现。输入 / 打开块菜单，拖动左侧手柄调整内容顺序。

## 一个想法，一篇文稿

不必先想好结构。记录第一句话，再让思路慢慢展开。

- **即时排版**：输入标题、列表和引用，格式随文字呈现。
- **真正的文件**：打开本机的 Markdown，用 Ctrl+S 保存到磁盘。
- **安心写作**：未保存的修改会保留为本地草稿，下次打开继续。

> 先把想法写下来，再找到最合适的表达。

## 熟悉的方式，轻盈的体验

输入 `#` 后按空格，开始一个标题；输入 `-` 和空格，开始一份列表。也可以使用工具栏或熟悉的键盘快捷键。

```python
thought = "一个值得记录的想法"
print(thought)
```

## 从这里开始

- [x] 打开一个舒服的写作空间
- [ ] 写下今天的第一个想法
- [ ] 把它保存为一份 Markdown 文件

---

文字属于你，也保存在你的设备上。
"""

GUIDE = """# Markdown 参考

简单的语法，让文字拥有结构。

## 常用格式

| 格式 | 写法 |
| --- | --- |
| 标题 | # 标题 |
| 加粗 | **文字** |
| 斜体 | *文字* |
| 引用 | > 文字 |
| 列表 | - 列表项 |
| 任务 | - [ ] 待办 |

## 键盘快捷键

- **Ctrl+N**：新建文稿
- **Ctrl+O**：打开文件
- **Ctrl+S**：保存文件
- **Ctrl+Shift+S**：另存为
- **Ctrl+B / Ctrl+I**：加粗 / 斜体
- **Ctrl+F**：查找文内文字
- **Ctrl+E**：切换编辑 / 源码
- **Ctrl+Shift+F**：专注模式
- **Ctrl+Enter**：勾选当前任务
- **Ctrl+Shift+D**：复制当前块
- **Ctrl+Shift+↑ / ↓**：上移 / 下移块
- **Ctrl+Shift+Enter**：退出表格或分栏
- **Shift+Enter**：块内换行
- **Tab / Shift+Tab**：列表缩进或表格单元格导航

## 块编辑

输入 / 可以搜索正文、标题、列表、待办、折叠、引用、代码、分隔线、表格、分栏、图片和链接。选中文字会显示格式工具，包含颜色、高亮和下划线。块左侧的 + 插入内容，手柄可拖动，也可打开转换、复制和删除菜单。

折叠块中按 Enter 添加子段落，在空子段落再次按 Enter 回到正文。分栏和表格可以通过块菜单增删列、设置列宽。表格的 Tab 在末尾自动新增一行。

“显示 → 全宽正文”展开写作区域。表格始终填满当前正文宽度。

## 富文稿

颜色、高亮、折叠、分栏和内嵌图片保存为 .inknote 文件。它是一份包含 Markdown 内容、HTML 排版和块状态的 JSON，图片直接嵌入文件。普通 Markdown 仍可保存为 .md。

富文稿的源码按钮显示只读 Markdown 预览；修改内容请切回编辑。文件菜单可以导出 Markdown 副本、HTML 和 PDF。Markdown 副本保留文字，颜色与高亮不保留，分栏转为表格。

macOS 使用相应的 Command 快捷键。

## 文件与草稿

保存会写入磁盘上的 .md 文件。尚未选择文件位置的文稿保存在应用草稿中。工作空间列表只是最近文稿，不是一个云端文件库。

源码模式保留原文；富文本修改会规范化 Markdown 的排版。公式、脚注、YAML 和 HTML 等扩展内容目前通过源码编辑保留。
"""


def new_document(title="未命名文稿", markdown="# 新的文稿\n\n"):
    now = time.time()
    return {
        "id": uuid.uuid4().hex,
        "title": title,
        "markdown": markdown,
        "file_path": None,
        "disk_hash": None,
        "saved_markdown": None,
        "favorite": False,
        "created_at": now,
        "updated_at": now,
    }


def initial_workspace():
    welcome = new_document("开始写作", WELCOME)
    welcome["favorite"] = True
    guide = new_document("Markdown 参考", GUIDE)
    return {"documents": [welcome, guide], "active_id": welcome["id"], "theme": "light"}



def validate_rich_content(content):
    if content is None:
        return
    if not isinstance(content, dict) or not isinstance(content.get("html"), str):
        raise ValueError("富文稿内容格式不正确")
    blocks = content.get("blocks", [])
    columns = content.get("columns", [])
    if not isinstance(blocks, list) or not isinstance(columns, list):
        raise ValueError("富文稿布局格式不正确")
    for metadata in blocks:
        if not isinstance(metadata, dict) or type(metadata.get("index")) is not int or metadata["index"] < 0:
            raise ValueError("富文稿块索引不正确")
        for key in ("toggle", "parent"):
            if key in metadata and (not isinstance(metadata[key], str) or not metadata[key]):
                raise ValueError("折叠块标识不正确")
        if "collapsed" in metadata and type(metadata["collapsed"]) is not bool:
            raise ValueError("折叠块状态不正确")
    if any(type(index) is not int or index < 0 for index in columns):
        raise ValueError("分栏索引不正确")


def read_workspace(path):
    if not path.exists():
        return initial_workspace()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("工作空间数据格式不正确")
    documents = data.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValueError("工作空间中没有有效文稿")
    identifiers = set()
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("文稿数据格式不正确")
        for field in ("id", "title", "markdown"):
            if not isinstance(document.get(field), str):
                raise ValueError("文稿数据格式不正确")
        for field in ("file_path", "disk_hash", "saved_markdown"):
            if document.get(field) is not None and not isinstance(document[field], str):
                raise ValueError("文稿文件信息格式不正确")
        for field in ("created_at", "updated_at"):
            value = document.setdefault(field, time.time())
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value < 32503680000:
                raise ValueError("文稿日期格式不正确")
        if document["id"] in identifiers:
            raise ValueError("文稿标识重复")
        identifiers.add(document["id"])
        validate_rich_content(document.get("rich_content"))
        validate_rich_content(document.get("saved_rich_content"))
    if data.get("active_id") not in identifiers:
        data["active_id"] = documents[0]["id"]
    return data


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def write_workspace(path, workspace):
    atomic_write(path, json.dumps(workspace, ensure_ascii=False, indent=2))


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class FileChangedError(Exception):
    """The file no longer matches the version this application opened."""


def write_markdown(path, markdown, expected_hash=None, overwrite=False):
    path = Path(path)
    # Prevent saving an old draft over edits made in another application.
    if not overwrite:
        if path.exists():
            if expected_hash is None or fingerprint(path) != expected_hash:
                raise FileChangedError("文件已被其他程序修改")
        elif expected_hash is not None:
            raise FileChangedError("原文件已被移动或删除")
    atomic_write(path, markdown)
    return fingerprint(path)


def write_document(path, document, expected_hash=None, overwrite=False):
    rich = document.get("rich_content")
    validate_rich_content(rich)
    if Path(path).suffix.lower() == ".inknote":
        content = json.dumps({"format": "inknote", "version": 1,
                              "markdown": document["markdown"], "rich_content": rich},
                             ensure_ascii=False, indent=2)
    else:
        if rich:
            raise ValueError("颜色、高亮、折叠和分栏需要保存为 .inknote；请使用导出 Markdown 获取纯文本副本。")
        content = document["markdown"]
    if Path(path).suffix.lower() == ".inknote" and len(content.encode("utf-8")) > 8 * 1024 * 1024:
        raise ValueError("富文稿超过 8 MB，请缩小图片或拆分文稿后保存。草稿仍然保留。")
    return write_markdown(path, content, expected_hash, overwrite)


def open_markdown(path):
    path = Path(path).resolve()
    rich_file = path.suffix.lower() == ".inknote"
    if path.suffix.lower() not in (".md", ".markdown", ".txt", ".inknote"):
        raise ValueError("请选择 Markdown、文本或 .inknote 富文稿")
    content = path.read_bytes()
    limit = (8 if rich_file else 2) * 1024 * 1024
    if len(content) > limit:
        raise ValueError("文稿超过支持大小（Markdown 2 MB，富文稿 8 MB）")
    text = content.decode("utf-8-sig")
    rich = None
    if rich_file:
        data = json.loads(text)
        if not isinstance(data, dict) or data.get("format") != "inknote" or data.get("version") != 1 or not isinstance(data.get("markdown"), str):
            raise ValueError("不支持的富文稿格式")
        text = data["markdown"]
        rich = data.get("rich_content")
        validate_rich_content(rich)
    document = new_document(path.stem, text)
    document.update(file_path=str(path), disk_hash=hashlib.sha256(content).hexdigest(), saved_markdown=text)
    if rich:
        document.update(rich_content=rich, saved_rich_content=rich)
    return document


def requires_source(markdown):
    prose = re.sub(r"(?m)^ {0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?^ {0,3}\1[ \t]*$", "", markdown)
    prose = re.sub(r"(`+)[^\n]*?\1", "", prose)
    # Front matter starts the document; ordinary thematic breaks are safe to render.
    front_matter = re.match(r"\A---[ \t]*\r?\n", prose)
    extensions = re.search(r"\$\$|\$[^$\n]+\$|\[\^[^\]]+\]|</?[a-z][^>]*>|^ {0,3}:::", prose, re.I | re.M)
    return bool(front_matter or extensions)


def word_count(markdown):
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", markdown)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+\[[ xX]\]\s+|^ {0,3}(?:`{3,}|~{3,}).*$", "", text)
    chinese = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text)
    words = re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", re.sub(r"[\u3400-\u4dbf\u4e00-\u9fff]", " ", text))
    return len(chinese) + len(words)


def markdown_headings(markdown):
    headings = []
    fence = ""
    for index, line in enumerate(markdown.splitlines()):
        delimiter = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if delimiter and delimiter[1][0] == fence[0] and len(delimiter[1]) >= len(fence) and not line[delimiter.end():].strip():
                fence = ""
            continue
        if delimiter:
            fence = delimiter[1]
            continue
        heading = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading:
            headings.append((len(heading[1]), re.sub(r"[*_`]", "", heading[2]), index))
    return headings
