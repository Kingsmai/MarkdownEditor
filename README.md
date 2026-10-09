# 墨记 · 原生块编辑器

主版本使用 Python + PySide6 / Qt Widgets，保留原生窗口、菜单和文件对话框。正文采用 Notion 风格的块编辑方式。

## 运行

此目录只保留源码、测试、资源、文档与构建配置。依赖环境、缓存、生成截图、测试草稿和历史发布包已清理。

桌面发布支持 Windows x64、macOS Intel / Apple Silicon、Linux x64。GitHub Actions 在各系统上测试、构建、实际启动检查，推送 v* 版本标签后发布到 GitHub Releases。完整操作见 [桌面三端发布说明](docs/desktop-release.md)。

开发运行：

~~~powershell
.\run-native.ps1
~~~

## 正文编辑

- 在空段落输入 /，用中文或英文搜索块；↑ / ↓ 选择，Enter 插入，Esc 保留输入并关闭菜单。
- 支持正文、标题、无序/有序列表、待办、折叠、引用、代码、分隔线、表格、分栏、图片和链接。
- 左侧 + 在块下方插入；手柄可以拖动，也能打开转换、选中、复制、上移、下移和删除菜单。
- 选中文字显示浮动格式工具：加粗、斜体、下划线、删除线、行内代码、链接、文字颜色和背景高亮。
- 折叠块的箭头展开/收起子内容。Enter 添加子段落，在空子段落按 Enter 退出。折叠状态随富文稿保存。
- 分栏使用可编辑的无边框 Qt 表格。支持两栏插入、增删列、调整列宽，以及将正文块拖进某一列。
- 图片可以从文件、剪贴板或 http/https 地址插入。插入的图片嵌入富文稿，无需附件文件夹。
- 编辑已有链接时选中链接文本；留空移除，Ctrl+点击打开链接。

表格之前没有宽度约束，Qt 按内容收缩。现在导入和新建表格都使用 100% 正文宽度、百分比列宽、明确的网格线和表头底色。块菜单或右键菜单支持插入/删除行列、切换表头、调整列宽和退出表格。Tab / Shift+Tab 切换单元格，末尾 Tab 新增一行。

默认正文居中，目标宽度 800；“显示 → 全宽正文”使用可用写作区域。窗口变宽、隐藏侧栏或切换全宽时，表格随正文一起变宽。

## 紧凑排版

参考 [Typora 行距与段距](https://support.typora.io/Line-Spacing/)、[Notion 页面宽度](https://www.notion.com/en-gb/help/customize-and-style-your-content) 和 [Obsidian 编辑器设置](https://obsidian.md/help/settings)，将工具区密度、正文可读宽度、块内行距和块间距分别控制。下面的数值是本项目的设计选择，并非这些软件的精确像素复刻。

| 区域 | 调整前 | 当前 |
| --- | --- | --- |
| 顶部文稿工具区 | 76 px 高 | 52 px 高 |
| 侧栏 / 文稿行 | 256 / 72 px | 232 / 56 px |
| 正文顶部 / 底部留白 | 48 / 80 px | 20 / 32 px |
| 居中正文目标宽度 | 720 px | 800 px |
| 普通段落上下边距 | 5 / 10 px | 0 / 6 px |
| 表格单元格内边距 | 9 px | 5 px |
| 分栏内边距 / 栏间距 | 14 / 12 px | 6 / 8 px |

正文保持 17 px。Qt 的比例行高作用于字体度量：当前正文 135%、标题 120%，不能直接等同于 CSS 的 line-height。单行表格在本机预览中的行高由约 55 px 降到 41 px。列表和代码行使用更小的块间距，首个标题取消额外上边距。

Markdown 导入、旧富文稿加载、块转换、Enter 新段落都使用 MarkdownEditor.apply_block_spacing。加载只调整显示排版，不触发草稿回写；用户编辑后，当前排版随富文稿正常保存。正文内容、颜色、高亮、折叠元数据和列宽继续保留。

预览截图不保留在源码目录；运行 python -m native.render_preview 可重新生成真实 Qt 窗口预览。

## 保存格式

普通文稿继续保存为 .md。颜色、高亮、下划线、折叠、分栏、图片和自定义列宽使用 **.inknote 富文稿**，保留完整编辑状态。

.inknote 是 UTF-8 JSON：

~~~json
{
  "format": "inknote",
  "version": 1,
  "markdown": "正文的 Markdown 内容",
  "rich_content": {
    "html": "Qt 富文本 HTML",
    "blocks": [],
    "columns": []
  }
}
~~~

HTML 保存排版和图片；blocks 保存折叠标题、父子关系和展开状态；columns 标记哪些 Qt 表格是分栏。块元数据使用 HTML 文档中的块顺序。没有额外服务、数据库或附件目录。

富格式无法由纯 Markdown 完整表达，因此：

- 富文稿的“预览”按钮显示只读 Markdown，修改内容请切回“编辑”。
- 当前 .md 文稿加入富格式后，Ctrl+S 会进入 .inknote 另存为流程，保留原 Markdown 文件。
- “文件 → 导出 Markdown 副本”明确转换成普通 Markdown；颜色、高亮和下划线不保留，分栏转成表格，折叠内容完整导出。
- “文件 → 导出 HTML / PDF”保留可打印的排版。PDF 包含折叠块内部的文字。
- 新插入图片嵌入 .inknote；旧 Markdown 中已有的图片引用仍依赖原路径。

500 ms 后自动保存本地草稿；Ctrl+S 保存当前文件。草稿和文件使用临时写入加原子替换。保存前检查 SHA-256，外部修改、移动或删除文件时继续显示冲突选择。应用关闭时立即保存草稿。

草稿目录可在“帮助 → 关于墨记”查看。Windows 通常位于 %APPDATA%/InkNote/InkNote/workspace.json。旧版草稿可以继续读取。

## 快捷键

| 操作 | 快捷键 |
| --- | --- |
| 新建 / 打开 / 保存 / 另存为 | Ctrl+N / Ctrl+O / Ctrl+S / Ctrl+Shift+S |
| 编辑 / 源码或预览 | Ctrl+E |
| 加粗 / 斜体 / 下划线 | Ctrl+B / Ctrl+I / Ctrl+U |
| 复制当前块 | Ctrl+Shift+D |
| 上移 / 下移当前块 | Ctrl+Shift+↑ / ↓ |
| 块内换行 | Shift+Enter |
| 列表缩进 / 取消缩进 | Tab / Shift+Tab |
| 勾选任务 | Ctrl+Enter，或点击复选框 |
| 退出表格 / 分栏 | Ctrl+Shift+Enter |
| 查找 / 专注模式 | Ctrl+F / Ctrl+Shift+F |

## 维护地图

### What changed

正文使用块编辑和富格式持久化，表格填满正文宽度。工具栏、侧栏、段落、表格和分栏统一收紧间距，旧富文稿加载后使用同一排版规则。继续使用现有 Qt 控件和本地文稿字典。

### Files involved / How to modify it later

| 文件 | 职责及修改入口 |
| --- | --- |
| native/editor.py | apply_block_spacing 统一加载、转换和输入的正文间距；另有块编辑、表格、折叠、图片和富格式快照 |
| native/block_controls.py | 块类型目录、/ 菜单、手柄、浮动格式工具和颜色菜单；修改正文控件到这里 |
| native/window.py | build_window 控制侧栏、文稿行、工具栏、大纲与状态栏尺寸；文件保存和导出流程也在这里 |
| native/documents.py | 文稿结构、富格式校验、.md/.inknote 读写、冲突保护、默认操作说明；修改数据规则到这里 |
| native/theme.py | 正文宽度、上下留白、标题与段落间距常量，以及字体、颜色和控件 padding；修改密度从这里开始 |
| native/tests/test_blocks.py | 块编辑与持久化回归，含旧富格式间距规范化、输入/导入一致性和折叠箭头点击 |
| native/tests/test_native.py | 原有 Markdown、文件、草稿、PDF 等安全回归测试 |
| native/render_preview.py | 使用真实应用控件生成浅色、深色、专注和块编辑预览 |
| native/QUICK_START.txt | 各平台包内的用户操作说明 |
| run-native.ps1 / build-native.ps1 | Windows 环境重建、启动及通用构建入口的快捷方式 |
| native/build.py | 三端 PyInstaller 构建、压缩包、隔离启动检查和 SHA-256 |
| .github/workflows/desktop-release.yml | GitHub 测试/构建矩阵、artifacts 和版本标签发布 |
| docs/desktop-release.md | 首次 GitHub 配置、三端操作和发布维护地图 |

block_controls.py 把控件展示与编辑行为分开。apply_block_spacing 是单个排版函数，避免各编辑入口重复不同的间距；没有加入新架构层或依赖。

### Data flow

~~~text
加载文稿 / 用户输入 / 块菜单 / 拖动 / 格式工具
  ↓
MarkdownEditor（Qt 文本、表格、块属性 + apply_block_spacing）
  ↓
MainWindow.editor_changed
  ↓
active_document：markdown + 可选 rich_content
  ├─ 500 ms → workspace.json（本地草稿）
  ├─ Ctrl+S → .md 或 .inknote（原子写入、外部修改检查）
  └─ 导出 → Markdown 副本 / HTML / PDF
~~~

加载时根据 rich_content 选择 setHtml 加块元数据恢复，或使用现有 Markdown 加载。切换文稿和模式时由 loading 阻止信号回写到其他文稿。

### Technical debt / assumptions

- .inknote 是墨记自己的富文稿格式；导出 Markdown 是内容转换，无法保留所有富排版。
- 分栏由无边框 Qt 表格实现；编辑器保留 Qt 的文本和表格模型，未加入独立的页面布局引擎。
- 普通 Markdown 支持 UTF-8、2 MB 以内；富文稿支持 8 MB 以内；单张新插入图片压缩为 PNG 后不超过 2 MB。保存前检查富文稿大小，超限不会覆盖文件。
- 富文本编辑会规范化 Markdown。公式、脚注、YAML 和通用 HTML 等原有扩展语法继续通过源码模式保留。
- 切换文稿或源码/编辑模式会重置撤销历史。
- 当前采用固定的紧凑桌面密度；正文全宽仍可切换，未增加单独的密度设置。Qt 字体度量和系统缩放会影响实际像素行高。
- Windows 已本地构建和验证；macOS/Linux 由首次 GitHub Actions 运行实际验证。当前是便携包，尚未配置分发证书与 macOS 公证。
- 项目中的 src/、public/ 和 Node 配置为原有浏览器原型，不参与原生构建；说明保存在 docs/web-mvp.md。

## 开发、验证与打包

~~~powershell
.\.venv-native\Scripts\python.exe -X utf8 -m unittest discover -s native\tests -v
.\.venv-native\Scripts\python.exe -X utf8 -m native.render_preview
.\build-native.ps1
~~~

测试操作真实 Qt 控件；文件对话框使用指定路径替代。HTTP 图片测试使用本机临时服务器，不依赖外部网站。预览使用临时草稿目录，不读取用户工作空间。

依赖由 native/requirements.txt 固定。构建使用 Qt Essentials，不包含 Qt WebEngine。输出集中在 desktop-dist/，构建缓存和生成的 .spec 集中在 build-native/，均被 .gitignore 排除。纯源码交付不保留这些目录或 .venv-native/；启动脚本会重新创建环境。

发布路径为：源码/标签 → GitHub Actions 系统矩阵 → Qt 测试 → native.build → 隔离启动检查 → 平台压缩包与 SHA-256 → GitHub Release。

交互参考：[Notion 写作与编辑](https://www.notion.com/help/writing-and-editing-basics)。表格实现依据：[Qt QTextTableFormat 文档](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QTextTableFormat.html)。
