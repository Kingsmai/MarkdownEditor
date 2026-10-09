import { useEffect } from 'react';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from '@tiptap/markdown';
import Image from '@tiptap/extension-image';
import Placeholder from '@tiptap/extension-placeholder';
import { TableKit } from '@tiptap/extension-table';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
import { Bold, Italic, Strikethrough, Code2, Link2, List, ListOrdered, ListTodo, Quote, ImagePlus, Table2, Undo2, Redo2, Minus } from 'lucide-react';

export function ToolButton({ label, icon: Icon, active = false, disabled = false, onClick, children }) {
  return <button type="button" className={'tool-button' + (active ? ' is-active' : '')} title={label} aria-label={label} aria-pressed={active} disabled={disabled} onClick={onClick}>
    {Icon ? <Icon size={16} strokeWidth={1.8} /> : children}
  </button>;
}

export default function MarkdownEditor({ markdown, onChange, onReady, onInsert, children }) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({ link: { openOnClick: false, autolink: true } }),
      Markdown,
      Image.configure({ allowBase64: false, HTMLAttributes: { loading: 'lazy' } }),
      Placeholder.configure({ placeholder: '写下你的想法，或输入 # 开始一个标题…' }),
      TableKit.configure({ table: { resizable: false } }),
      TaskList,
      TaskItem.configure({ nested: true }),
    ],
    content: markdown,
    contentType: 'markdown',
    shouldRerenderOnTransaction: true,
    editorProps: { attributes: { 'aria-label': '文档编辑区', spellcheck: 'false' } },
    onUpdate: ({ editor: updated }) => onChange(updated.getMarkdown()),
  });

  useEffect(() => {
    onReady(editor);
    return () => onReady(null);
  }, [editor, onReady]);

  if (!editor) return <div className="editor-loading">正在打开文档…</div>;
  const run = action => action(editor.chain().focus()).run();
  const heading = [1, 2, 3].find(level => editor.isActive('heading', { level })) || 0;

  return <>
    <div className="format-toolbar" aria-label="格式工具栏">
      <select className="heading-select" aria-label="段落格式" value={heading} onChange={event => {
        const level = Number(event.target.value);
        run(chain => level ? chain.toggleHeading({ level }) : chain.setParagraph());
      }}>
        <option value={0}>正文</option><option value={1}>标题 1</option><option value={2}>标题 2</option><option value={3}>标题 3</option>
      </select>
      <span className="toolbar-divider" />
      <ToolButton label="粗体 (Ctrl / ⌘ B)" icon={Bold} active={editor.isActive('bold')} onClick={() => run(chain => chain.toggleBold())} />
      <ToolButton label="斜体 (Ctrl / ⌘ I)" icon={Italic} active={editor.isActive('italic')} onClick={() => run(chain => chain.toggleItalic())} />
      <ToolButton label="删除线" icon={Strikethrough} active={editor.isActive('strike')} onClick={() => run(chain => chain.toggleStrike())} />
      <ToolButton label="行内代码" icon={Code2} active={editor.isActive('code')} onClick={() => run(chain => chain.toggleCode())} />
      <ToolButton label="插入链接" icon={Link2} active={editor.isActive('link')} onClick={() => onInsert('link')} />
      <span className="toolbar-divider" />
      <ToolButton label="无序列表" icon={List} active={editor.isActive('bulletList')} onClick={() => run(chain => chain.toggleBulletList())} />
      <ToolButton label="有序列表" icon={ListOrdered} active={editor.isActive('orderedList')} onClick={() => run(chain => chain.toggleOrderedList())} />
      <ToolButton label="任务清单" icon={ListTodo} active={editor.isActive('taskList')} onClick={() => run(chain => chain.toggleTaskList())} />
      <ToolButton label="引用" icon={Quote} active={editor.isActive('blockquote')} onClick={() => run(chain => chain.toggleBlockquote())} />
      <span className="toolbar-divider" />
      <ToolButton label="插入图片" icon={ImagePlus} onClick={() => onInsert('image')} />
      <ToolButton label={editor.isActive('table') ? '表格操作' : '插入表格'} icon={Table2} active={editor.isActive('table')} onClick={() => {
        if (editor.isActive('table')) onInsert('table');
        else run(chain => chain.insertTable({ rows: 3, cols: 3, withHeaderRow: true }));
      }} />
      <ToolButton label="代码块" onClick={() => run(chain => chain.toggleCodeBlock())} active={editor.isActive('codeBlock')}><span className="code-block-icon">{'{ }'}</span></ToolButton>
      <ToolButton label="分隔线" icon={Minus} onClick={() => run(chain => chain.setHorizontalRule())} />
      <div className="toolbar-spacer" />
      <ToolButton label="撤销" icon={Undo2} disabled={!editor.can().undo()} onClick={() => run(chain => chain.undo())} />
      <ToolButton label="重做" icon={Redo2} disabled={!editor.can().redo()} onClick={() => run(chain => chain.redo())} />
    </div>
    {children}
    <EditorContent editor={editor} className="document-content" />
  </>;
}
