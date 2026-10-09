import test from 'node:test';
import assert from 'node:assert/strict';
import { STORAGE_KEY, createDocument, loadWorkspace, countWords, extractHeadings, requiresSourceMode, safeUrl } from '../src/documents.js';

function memoryStorage(value) {
  return { getItem: key => key === STORAGE_KEY ? value : null };
}

test('reload preserves Markdown exactly and repairs an obsolete active document ID', () => {
  const markdown = '---\ntitle: 原文\n---\n\n# 标题\r\n\n$$x^2$$\n\n脚注[^1]\n\n[^1]: 内容\n';
  const doc = createDocument('原文', markdown);
  const loaded = loadWorkspace(memoryStorage(JSON.stringify({ documents: [doc], activeId: 'missing' })));
  assert.equal(loaded.error, null);
  assert.equal(loaded.workspace.activeId, doc.id);
  assert.equal(loaded.workspace.documents[0].markdown, markdown);
});

test('corrupt storage is reported and is never mutated by loading', () => {
  const original = '{ damaged';
  let writes = 0;
  const storage = { ...memoryStorage(original), setItem: () => writes++ };
  const loaded = loadWorkspace(storage);
  assert.ok(loaded.error);
  assert.equal(writes, 0);
  assert.equal(storage.getItem(STORAGE_KEY), original);
});

test('duplicate document IDs are rejected before saving can overwrite a workspace', () => {
  const doc = createDocument();
  assert.ok(loadWorkspace(memoryStorage(JSON.stringify({ documents: [doc, doc], activeId: doc.id }))).error);
});

test('new documents have distinct IDs and start as Markdown', () => {
  const first = createDocument();
  const second = createDocument();
  assert.notEqual(first.id, second.id);
  assert.ok(first.markdown.startsWith('# '));
});

test('outline ignores headings inside backtick and tilde fences', () => {
  const markdown = '# 标题\n\n````md\n## 代码里的标题\n```\n### 仍在代码里\n````\n\n## 正文标题\n~~~\n# 另一个代码标题\n~~~\n\n副标题\n---\n';
  assert.deepEqual(extractHeadings(markdown).map(heading => heading.text), ['标题', '正文标题', '副标题']);
});

test('outline supports six levels, duplicate titles and trailing heading markers', () => {
  assert.deepEqual(extractHeadings('## 重复 ##\n###### 深层标题\n## 重复'), [
    { level: 2, text: '重复', line: 0 },
    { level: 6, text: '深层标题', line: 1 },
    { level: 2, text: '重复', line: 2 },
  ]);
});

test('word count combines Chinese characters and Latin words without counting URLs', () => {
  assert.equal(countWords('# 你好 world\n\n[链接](https://example.com/a) **hello**'), 6);
  assert.equal(countWords('![图片](https://example.com/image.png)'), 0);
});

test('unsupported syntax stays in source mode', () => {
  for (const markdown of ['---\ntitle: test\n---', '$$x^2$$', '$x$', '文字[^1]', '<div>内容</div>', ':::note\n内容']) {
    assert.equal(requiresSourceMode(markdown), true);
  }
  assert.equal(requiresSourceMode('# 正文\n\n**粗体**\n\n- [ ] 任务\n'), false);
});

test('links reject active-content URLs and images reject mailto', () => {
  for (const value of ['javascript:alert(1)', 'data:text/html,<script>', 'file:///secret.txt', 'not a url']) {
    assert.equal(safeUrl(value), null);
  }
  assert.equal(safeUrl('https://example.com'), 'https://example.com/');
  assert.equal(safeUrl('mailto:hello@example.com'), 'mailto:hello@example.com');
  assert.equal(safeUrl('mailto:hello@example.com', true), null);
});

test("code examples do not trigger the unsupported Markdown guard", () => {
  assert.equal(requiresSourceMode("\n```html\n<div>$value$</div>\n```\n"), false);
  assert.equal(requiresSourceMode("示例：`<div>$value$</div>`"), false);
});

test("word count ignores task checkmarks and fence language labels", () => {
  assert.equal(countWords("- [x] 完成\n- [ ] hello"), 3);
  assert.equal(countWords("```javascript\nhello\n```"), 1);
});
