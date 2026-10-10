# 桌面三端发布

当前项目以 Python + PySide6 / Qt Widgets 为主。GitHub Actions 在各系统上运行同一构建入口，GitHub Releases 分发桌面压缩包。没有网页部署流程。

## 发布目标

| 目标 | GitHub runner | 发布资产 | 用户启动方式 |
| --- | --- | --- | --- |
| Windows x64 | windows-2022 | InkNote-Windows-x64.zip | 解压后运行 InkNote/InkNote.exe |
| macOS Apple Silicon | macos-14 | InkNote-macOS-arm64.zip | 解压后把 InkNote.app 放入 Applications |
| macOS Intel | macos-15-intel | InkNote-macOS-x64.zip | 解压后把 InkNote.app 放入 Applications |
| Linux x64 | ubuntu-22.04 | InkNote-Linux-x64.tar.gz | 解压后运行 ./InkNote/InkNote |

每个压缩包旁边都有同名 .sha256 文件。保留 Windows/Linux 包内的 _internal 目录；macOS 必须保留完整 .app。

校验文件统一使用 UTF-8 和 LF 换行，避免 Windows 的 CRLF 被 Linux `sha256sum` 当成文件名的一部分。发布校验前也会去除行尾的 `\r`，兼容旧 Windows 校验文件，然后执行 `sha256sum -c`；安装包内容或哈希不匹配时仍会阻止发布。遇到文件名后带 `$'\r'` 的错误，可先检查校验文件的换行格式。修复需提交到新版本标签所指向的提交；重新运行旧标签仍使用旧代码。

PyInstaller 在目标系统上构建，不是交叉编译器，因此 Windows 本机只能验证 Windows 产物。[PyInstaller 官方说明](https://www.pyinstaller.org/en/stable/)。

固定使用 Python 3.11、PySide6 Essentials 6.10.3 和 PyInstaller 6.22.3。Qt 当前依赖的 macOS wheel 要求 13.0+，Linux x64 wheel 要求 glibc 2.34+；Linux 实际构建基线为 Ubuntu 22.04，还需要 Qt 的系统图形库。[依赖的官方 wheel 列表](https://pypi.org/project/PySide6-Essentials/6.10.3/#files)。

## 首次放到 GitHub

1. 创建 GitHub 仓库，把本项目源码推送进去；仓库可以公开或私有。
2. 保留 .github/workflows/desktop-release.yml。仓库允许运行 GitHub Actions。
3. 普通分支提交、Pull Request 或 Actions 页面的 Run workflow 会运行四组测试与构建；下载本次运行的 desktop-* artifacts 验证各端。
4. 确认本次提交可以发布后，推送版本标签，例如 v0.3.0：

~~~bash
git tag v0.3.0
git push origin v0.3.0
~~~

四组测试、构建和实际启动检查全部成功后，工作流校验 SHA-256 并创建 GitHub Release，把四个压缩包与校验文件附上。失败时不执行 release job。重复运行同一标签会更新对应的发布资产。

标签推送会正式发布 Release；普通分支和手动运行只生成 artifacts。无需额外的 GitHub PAT：只有 release job 获得 contents: write，其他 job 使用 contents: read。

此目录清理前没有 .git 或配置好的 GitHub remote。工作流已经就绪，但尚未上传仓库或在 GitHub runner 上实际运行。初始化仓库时可以使用：

~~~bash
git init -b main
git add .
git commit -m "Prepare desktop releases"
git remote add origin <你的仓库 URL>
git push -u origin main
~~~

将占位 URL 替换为实际仓库。提交前查看 git status，确认只有源码、测试、资源、文档和配置。

## 本地开发与构建

清理后的目录不含依赖环境和安装包。依赖清单保留，环境可以重建。

Windows 安装 Python 3.11 后：

~~~powershell
.\run-native.ps1
~~~

它创建 .venv-native、安装固定依赖并启动应用。构建：

~~~powershell
.\build-native.ps1
~~~

macOS / Linux：

~~~bash
python3.11 -m venv .venv-native
source .venv-native/bin/activate
python -m pip install -r native/requirements.txt
python -m native
python -m native.build --smoke-test
~~~

输出统一放在 desktop-dist/，中间文件和生成的 .spec 统一放在 build-native/。Windows 的 build-native.ps1 只是 Python 构建入口的快捷方式，不再维护另一套打包逻辑。

测试：

~~~bash
python -X utf8 -m unittest discover -s native/tests -v
python -m native --smoke-test
~~~

构建时的 --smoke-test 启动实际打包程序，使用自动清理的临时草稿，运行事件循环、退出保存并检查草稿已经写入。它不能与 file 或 --data-dir 同时使用，避免误用用户数据。

Linux CI 安装 xvfb、xauth、Qt 所需的完整 XCB/OpenGL 库和中文字体，通过 xvfb-run 执行真实 Qt 控件测试与打包程序启动检查。对应 apt 软件包在工作流中直接列出，继续使用 xcb 平台验证桌面程序。

测试前的 `Check Linux Qt platform dependencies` 步骤通过 `QLibraryInfo` 找到当前 PySide6 的 `libqxcb.so`，用 `ldd` 检查它及其间接依赖，再通过 Xvfb 创建一个 `QApplication`，确认实际使用 xcb。缺库时会提前失败并列出 `not found`；Qt 初始化失败时会输出插件加载日志。

如果出现 `From 6.5.0, xcb-cursor0 or libxcb-cursor0 is needed` 和退出码 134，先查看这个检查步骤。该提示也可能由其他 xcb 动态库缺失引起，不能只检查 cursor 包；例如 `libxcb-shape.so.0` 对应 Ubuntu 的 `libxcb-shape0`。按 `ldd` 的缺失项调整工作流中的 apt 安装清单，依赖依据见 [Qt 6.10 的 X11 要求](https://doc.qt.io/qt-6.10/linux-requirements.html)。修改后提交并推送新的提交以触发构建；重新运行旧提交仍使用旧工作流。

## 维护地图

| 文件 | 修改入口 |
| --- | --- |
| .github/workflows/desktop-release.yml | 系统/架构矩阵、测试、构建、artifacts、标签发布条件及 GitHub 权限 |
| native/build.py | PyInstaller 参数、资源与许可证、各端打包方式和 SHA-256 |
| build-native.ps1 | Windows 快捷入口 |
| run-native.ps1 / native/requirements.txt | 环境重建与固定依赖 |
| native/app.py | 正常启动、草稿锁和隔离启动检查 |
| native/create_icon.py / native/assets/ | 同一个 SVG 生成 PNG、Windows ICO 和 macOS ICNS |
| native/QUICK_START.txt | 包内操作说明 |

执行路径：

~~~text
源码提交 / 版本标签
  ↓
GitHub Actions 系统与架构矩阵
  ↓
安装依赖 → Linux xcb 动态库与启动检查 → Qt 回归测试
  ↓
native.build → PyInstaller → 实际程序 --smoke-test
  ↓
Windows ZIP / macOS APP ZIP / Linux TAR.GZ + SHA-256
  ├─ 普通提交 → Actions artifacts
  └─ 版本标签 → GitHub Release
~~~

现有文件读写和草稿数据结构保持不变。没有新增运行依赖、网页服务或发布服务层。macOS 用 ditto 保留 .app 框架符号链接；Linux 用 tar 保留可执行权限和符号链接。

## 当前边界

- 本机已验证 Windows 的测试、构建、压缩包内容、校验文件和实际程序启动。macOS/Linux 的真实验证由首次 GitHub Actions 运行完成。
- 当前提供便携包。Windows 未配置 Authenticode 签名；macOS 使用 PyInstaller 的 ad-hoc 签名，未配置 Developer ID 签名或 Apple 公证。面向普通用户正式分发时，证书与公证步骤需要加入相应构建 job。当前没有 MSI、DMG 或系统软件包安装器。[PyInstaller macOS 签名参数](https://pyinstaller.org/en/stable/usage.html#macos-specific-options)。
- macOS 同时提供 Intel 和 Apple Silicon 包；未增加 Windows/Linux ARM64 目标。
- 发布包含现有第三方许可证与说明。项目自身的源码授权由项目所有者决定。
- 旧网页原型 src/、public/、tests/ 和 Node 配置是源码，按照“只保留源码”保留；桌面工作流不会安装 Node 依赖或发布网页。
- 自动生成的预览截图不保留在源码目录；python -m native.render_preview 可以重新生成。
- 用户正式草稿目录由 QStandardPaths 管理，清理项目不删除它。

参考：[GitHub runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)、[构建与测试 Python](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)、[GitHub Release CLI](https://cli.github.com/manual/gh_release_create)。
