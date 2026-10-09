export const STORAGE_KEY = 'inknote.workspace.v1';
export const PREFERENCES_KEY = 'inknote.preferences.v1';

const welcome = '# 让思绪，自然成文。\n\n每一个值得记录的想法，都需要一个安静的地方。\n\n欢迎来到 **墨记**，你的轻盈 Markdown 写作空间。在这里，把注意力交给文字，把排版交给我们。\n\n> 写作不是把想法放在纸上，而是在纸上发现想法。\n\n## 一个安静的写作空间\n\n没有复杂的设置，也没有打断思路的工具。像在纸上书写一样，让文字自然流动。\n\n- **所见即所得** — 输入 Markdown，格式随文字一起呈现。\n- **安心记录** — 每一次修改，都会自动保存在当前浏览器。\n- **自由带走** — 随时导出为 .md 文件，让你的文字属于你。\n\n## 用 Markdown，顺着思路写\n\n试着输入 `#` 再按空格，一个标题就诞生了。用 `-` 开始列表，用 `>` 写下一段引用。你也可以选中文字，用上方工具栏为它添加格式。\n\n```javascript\nconst thought = "一个好想法";\nconst writing = thought + "，从这里开始。";\nconsole.log(writing);\n```\n\n## 从这里开始\n\n- [x] 找到一个舒服的写作空间\n- [x] 认识你的 Markdown 编辑器\n- [ ] 写下今天的第一个想法\n\n---\n\n不必等到准备好。第一句话，就从现在开始。\n';

const guide = '# Markdown 小抄\n\n让格式成为写作的自然延伸。\n\n## 常用格式\n\n| 想要的格式 | Markdown 写法 |\n| --- | --- |\n| 一级标题 | # 标题 |\n| 粗体 | **文字** |\n| 斜体 | *文字* |\n| 行内代码 | `code` |\n| 引用 | > 一段引用 |\n| 无序列表 | - 列表项 |\n| 任务清单 | - [ ] 待办事项 |\n\n## 快捷键\n\n- **Ctrl / ⌘ + B**：加粗\n- **Ctrl / ⌘ + I**：斜体\n- **Ctrl / ⌘ + Z**：撤销\n- **Ctrl / ⌘ + S**：导出 Markdown\n- **Ctrl / ⌘ + Shift + F**：进入 / 退出专注模式\n\n## 文件与保存\n\n在左侧点击「打开文件」，或将 .md 文件拖进编辑器。文件先以源码打开，原文会完整保留。\n\n文档自动保存在当前浏览器里。定期导出 .md 文件，可以在其他设备打开，也可以作为备份。清除浏览器数据会清除本地文档。\n\n## 不止一种写法\n\n点击上方「源码」可以查看和编辑 Markdown 原文；点击「编辑」回到所见即所得模式。普通 Markdown 支持两种模式切换；包含公式、脚注、HTML 或 YAML 的文件会保持源码模式，避免丢失内容。\n';

const ideas = '# 那些还没成文的想法\n\n给灵感留一个位置，不必急着整理。\n\n## 今天想记录什么？\n\n- 一段偶然读到的话\n- 一个想去的地方\n- 一件微小但开心的事\n\n## 写给未来的自己\n\n此刻的你，在想些什么？\n';

export function createDocument(title = '未命名文档', markdown = '# 新的开始\n\n') {
  const now = Date.now();
  return { id: crypto.randomUUID(), title, markdown, favorite: false, createdAt: now, updatedAt: now };
}

export function createInitialWorkspace() {
  const docs = [
    { ...createDocument('开始一段好文字', welcome), favorite: true },
    createDocument('Markdown 小抄', guide),
    createDocument('灵感收集箱', ideas),
  ];
  return { documents: docs, activeId: docs[0].id };
}

export function loadWorkspace(storage = localStorage) {
  const raw = storage.getItem(STORAGE_KEY);
  if (!raw) return { workspace: createInitialWorkspace(), error: null };
  try {
    const workspace = JSON.parse(raw);
    if (!Array.isArray(workspace.documents) || workspace.documents.length === 0) throw new Error('empty');
    for (const doc of workspace.documents) {
      if (typeof doc.id !== 'string' || typeof doc.title !== 'string' || typeof doc.markdown !== 'string') throw new Error('invalid document');
    }
    const ids = new Set(workspace.documents.map(doc => doc.id));
    if (ids.size !== workspace.documents.length) throw new Error('duplicate document');
    if (!ids.has(workspace.activeId)) workspace.activeId = workspace.documents[0].id;
    return { workspace, error: null };
  } catch {
    // Keep the original value intact so a damaged workspace can still be recovered.
    return { workspace: createInitialWorkspace(), error: '本地文档数据无法读取。原始数据仍被保留；请先导出重要内容，再重置本地存储。' };
  }
}

export function countWords(markdown) {
  const text = markdown
    .replace(/^\s*[-*+]\s+\[[ xX]\]\s+/gm, '')
    .replace(/^ {0,3}(?:`{3,}|~{3,}).*$/gm, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');
  const chinese = text.match(/[\p{Script=Han}]/gu) || [];
  const words = text.replace(/[\p{Script=Han}]/gu, ' ').match(/[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*/gu) || [];
  return chinese.length + words.length;
}

export function extractHeadings(markdown) {
  const headings = [];
  let fence = null;
  const lines = markdown.split('\n');
  lines.forEach((line, lineIndex) => {
    const opening = line.match(/^ {0,3}(`{3,}|~{3,})/);
    if (fence) {
      const closing = line.match(/^ {0,3}(`{3,}|~{3,})\s*$/);
      if (closing && closing[1][0] === fence[0] && closing[1].length >= fence.length) fence = null;
      return;
    }
    if (opening) { fence = opening[1]; return; }
    const heading = line.match(/^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (heading) headings.push({ level: heading[1].length, text: heading[2].replace(/[*_`]/g, ''), line: lineIndex });
    else if (/^ {0,3}(={3,}|-{3,})\s*$/.test(line) && lineIndex > 0 && lines[lineIndex - 1].trim() && !/^\s*[-*>]/.test(lines[lineIndex - 1])) {
      headings.push({ level: line.trim()[0] === '=' ? 1 : 2, text: lines[lineIndex - 1].trim(), line: lineIndex - 1 });
    }
  });
  return headings;
}

export function requiresSourceMode(markdown) {
  // Syntax inside code examples is literal text and is safe in the rich editor.
  const prose = markdown
    .replace(/^ {0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?^ {0,3}\1[ \t]*$/gm, '')
    .replace(/(`+)[^\n]*?\1/g, '');
  return /^---\s*\r?\n/.test(prose) ||
    /\$\$|\$[^$\n]+\$|\[\^[^\]]+\]|<\/?[a-z][^>]*>/i.test(prose) ||
    /^ {0,3}:::/m.test(prose);
}

export function safeUrl(value, image = false) {
  try {
    const url = new URL(value);
    if (!['http:', 'https:', ...(image ? [] : ['mailto:'])].includes(url.protocol)) return null;
    return url.href;
  } catch { return null; }
}

export function downloadMarkdown(doc) {
  const blob = new Blob([doc.markdown], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  const name = doc.title.replace(/[\\/:*?"<>|]/g, '_').replace(/\.md$/i, '').trim() || '未命名文档';
  link.href = url;
  link.download = name + '.md';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
