import { useCallback, useEffect, useRef, useState } from 'react';
import { FileText, ChevronRight, Check, Star, PanelLeftClose, PanelLeftOpen, Maximize2, Minimize2, Download, ChevronDown, AlignLeft, Code2, CalendarDays, Clock3, MoreHorizontal, Pencil, Trash2, X, CircleHelp, CheckCircle2, WifiOff, Printer, Feather } from 'lucide-react';
import MarkdownEditor from './MarkdownEditor.jsx';
import Sidebar from './Sidebar.jsx';
import Dialog from './Dialog.jsx';
import { STORAGE_KEY, PREFERENCES_KEY, createDocument, createInitialWorkspace, loadWorkspace, countWords, extractHeadings, requiresSourceMode, safeUrl, downloadMarkdown } from './documents.js';

function readInitialState() {
  try { return loadWorkspace(); }
  catch { return { workspace: createInitialWorkspace(), error: '浏览器不允许访问本地存储，请导出文档以保留内容。' }; }
}

function readPreferences() {
  try { return JSON.parse(localStorage.getItem(PREFERENCES_KEY)) || {}; }
  catch { return {}; }
}

export default function App() {
  const [initial] = useState(readInitialState);
  const [workspace, setWorkspace] = useState(initial.workspace);
  const [preferences] = useState(readPreferences);
  const [theme, setTheme] = useState(preferences.theme === 'dark' ? 'dark' : 'light');
  const [mode, setMode] = useState(() => requiresSourceMode(initial.workspace.documents.find(doc => doc.id === initial.workspace.activeId).markdown) ? 'source' : 'write');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [mobileSidebar, setMobileSidebar] = useState(false);
  const [outlineVisible, setOutlineVisible] = useState(true);
  const [focusMode, setFocusMode] = useState(false);
  const [activeHeading, setActiveHeading] = useState(0);
  const [status, setStatus] = useState(initial.error ? 'error' : 'saved');
  const [storageError, setStorageError] = useState(initial.error);
  const [toast, setToast] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [dialogValue, setDialogValue] = useState('');
  const [dialogError, setDialogError] = useState('');
  const [exportMenu, setExportMenu] = useState(false);
  const [moreMenu, setMoreMenu] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);
  const editorRef = useRef(null);
  const sourceRef = useRef(null);
  const scrollRef = useRef(null);
  const fileRef = useRef(null);
  const workspaceRef = useRef(workspace);
  const toastTimer = useRef(null);
  // A failed read must never be followed by an automatic overwrite of the original data.
  const storageBlocked = useRef(Boolean(initial.error));

  workspaceRef.current = workspace;
  const activeDoc = workspace.documents.find(doc => doc.id === workspace.activeId) || workspace.documents[0];
  const headings = extractHeadings(activeDoc.markdown);
  const wordCount = countWords(activeDoc.markdown);
  const effectiveMode = mode;

  const notify = useCallback(message => {
    clearTimeout(toastTimer.current);
    setToast(message);
    toastTimer.current = setTimeout(() => setToast(null), 3800);
  }, []);

  const saveWorkspace = useCallback(() => {
    if (storageBlocked.current) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(workspaceRef.current));
      setStatus('saved');
      setStorageError(null);
    } catch {
      setStatus('error');
      setStorageError('本地存储不可用或空间不足。请导出文档备份后，检查浏览器设置。');
    }
  }, []);

  useEffect(() => {
    if (storageBlocked.current) return;
    setStatus('saving');
    const timer = setTimeout(saveWorkspace, 500);
    return () => clearTimeout(timer);
  }, [workspace, saveWorkspace]);

  useEffect(() => {
    const onHidden = () => { if (document.visibilityState === 'hidden') saveWorkspace(); };
    window.addEventListener('pagehide', saveWorkspace);
    window.addEventListener('beforeunload', saveWorkspace);
    document.addEventListener('visibilitychange', onHidden);
    return () => {
      window.removeEventListener('pagehide', saveWorkspace);
      window.removeEventListener('beforeunload', saveWorkspace);
      document.removeEventListener('visibilitychange', onHidden);
    };
  }, [saveWorkspace]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#252b26' : '#58745e';
    try { localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ theme })); } catch { /* Writing remains available without saved preferences. */ }
  }, [theme]);

  useEffect(() => {
    document.title = activeDoc.title + ' · 墨记';
    setActiveHeading(0);
    scrollRef.current?.scrollTo({ top: 0 });
  }, [activeDoc.id, activeDoc.title]);

  useEffect(() => {
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => { window.removeEventListener('online', onOnline); window.removeEventListener('offline', onOffline); };
  }, []);

  const updateDocument = useCallback(markdown => {
    setWorkspace(current => ({
      ...current,
      documents: current.documents.map(doc => doc.id === current.activeId ? { ...doc, markdown, updatedAt: Date.now() } : doc),
    }));
  }, []);

  const onEditorReady = useCallback(editor => { editorRef.current = editor; }, []);

  function newDocument() {
    const doc = createDocument();
    setWorkspace(current => ({ documents: [doc, ...current.documents], activeId: doc.id }));
    setMode('write');
    setQuery('');
    setFilter('all');
    setMobileSidebar(false);
    notify('新文档已准备好，开始写吧。');
  }

  function selectDocument(id) {
    if (requiresSourceMode(workspace.documents.find(doc => doc.id === id).markdown)) setMode('source');
    setWorkspace(current => ({ ...current, activeId: id }));
    setMobileSidebar(false);
    setMoreMenu(false);
  }

  function openDialog(type) {
    setDialog(type);
    setDialogValue(type === 'rename' ? activeDoc.title : type === 'link' ? editorRef.current?.getAttributes('link').href || '' : '');
    setDialogError('');
    setMoreMenu(false);
  }

  function closeDialog() { setDialog(null); setDialogError(''); }

  function exportDocument() {
    downloadMarkdown(activeDoc);
    setExportMenu(false);
    notify('Markdown 文件已导出。');
  }

  async function importFile(file) {
    if (!file) return;
    if (!/\.(md|markdown|txt)$/i.test(file.name)) { notify('请选择 .md、.markdown 或 .txt 文件。'); return; }
    if (file.size > 2 * 1024 * 1024) { notify('MVP 支持 2 MB 以内的 Markdown 文件。'); return; }
    try {
      const text = await file.text();
      const doc = createDocument(file.name.replace(/\.(md|markdown|txt)$/i, ''), text);
      setWorkspace(current => ({ documents: [doc, ...current.documents], activeId: doc.id }));
      setMode('source');
      setQuery('');
      setFilter('all');
      setMobileSidebar(false);
      notify('文件已打开，Markdown 原文完整保留。');
    } catch { notify('文件读取失败，请重新选择。'); }
  }

  function setEditorMode(nextMode) {
    if (nextMode === 'write' && requiresSourceMode(activeDoc.markdown)) {
      notify('这篇文档含有公式、脚注、HTML 或 YAML，MVP 使用源码编辑以完整保留内容。');
      return;
    }
    setMode(nextMode);
  }

  function toggleFavorite() {
    setWorkspace(current => ({ ...current, documents: current.documents.map(doc => doc.id === current.activeId ? { ...doc, favorite: !doc.favorite } : doc) }));
  }

  function submitDialog(event) {
    event.preventDefault();
    const value = dialogValue.trim();
    if (dialog === 'rename') {
      if (!value) { setDialogError('请为文档取一个名字。'); return; }
      setWorkspace(current => ({ ...current, documents: current.documents.map(doc => doc.id === current.activeId ? { ...doc, title: value, updatedAt: Date.now() } : doc) }));
    } else if (dialog === 'link' || dialog === 'image') {
      const url = safeUrl(value, dialog === 'image');
      if (!url) { setDialogError(dialog === 'image' ? '请输入以 https:// 或 http:// 开头的图片地址。' : '请输入有效的 http、https 或 mailto 链接。'); return; }
      const chain = editorRef.current?.chain().focus();
      if (dialog === 'image') chain?.setImage({ src: url, alt: '插入的图片' }).run();
      else if (editorRef.current?.state.selection.empty) chain?.insertContent({ type: 'text', text: url, marks: [{ type: 'link', attrs: { href: url } }] }).run();
      else chain?.extendMarkRange('link').setLink({ href: url }).run();
    }
    closeDialog();
  }

  function deleteDocument() {
    const remaining = workspace.documents.filter(doc => doc.id !== activeDoc.id);
    if (remaining.length === 0) remaining.push(createDocument());
    setWorkspace({ documents: remaining, activeId: remaining[0].id });
    closeDialog();
    notify('文档已删除。');
  }

  function jumpToHeading(index) {
    setActiveHeading(index);
    if (effectiveMode === 'source') {
      const textarea = sourceRef.current;
      const position = activeDoc.markdown.split('\n').slice(0, headings[index].line).join('\n').length + (headings[index].line > 0 ? 1 : 0);
      textarea?.focus();
      textarea?.setSelectionRange(position, position);
      if (textarea) textarea.scrollTop = Math.max(0, headings[index].line * 26 - 80);
    } else {
      const nodes = scrollRef.current?.querySelectorAll('.tiptap h1, .tiptap h2, .tiptap h3, .tiptap h4, .tiptap h5, .tiptap h6');
      nodes?.[index]?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
    }
  }

  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === 'Escape') { setFocusMode(false); setMobileSidebar(false); setMoreMenu(false); setExportMenu(false); }
      if (dialog || !(event.ctrlKey || event.metaKey)) return;
      if (event.key.toLowerCase() === 's') { event.preventDefault(); downloadMarkdown(workspaceRef.current.documents.find(doc => doc.id === workspaceRef.current.activeId)); notify('Markdown 文件已导出。'); }
      if (event.shiftKey && event.key.toLowerCase() === 'f') { event.preventDefault(); setFocusMode(current => !current); }
      if (event.altKey && event.key.toLowerCase() === 'n') { event.preventDefault(); newDocument(); }
      if (event.key.toLowerCase() === 'o') { event.preventDefault(); fileRef.current?.click(); }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [dialog, notify]);

  useEffect(() => () => clearTimeout(toastTimer.current), []);

  const dialogTitles = { rename: '给文字一个名字', link: '插入链接', image: '插入图片', delete: '删除这篇文档？', help: '把注意力交给文字', table: '编辑表格' };

  return <div className={'app' + (!sidebarVisible ? ' sidebar-hidden' : '') + (focusMode ? ' focus-mode' : '')}
    onDragOver={event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); }}
    onDrop={event => { if (event.dataTransfer.files.length) { event.preventDefault(); importFile(event.dataTransfer.files[0]); } }}>
    <a className="skip-link" href="#writing">跳到编辑区</a>
    <input ref={fileRef} type="file" accept=".md,.markdown,.txt" hidden onChange={event => { importFile(event.target.files?.[0]); event.target.value = ''; }} />
    <Sidebar documents={workspace.documents} activeId={workspace.activeId} query={query} setQuery={setQuery} filter={filter} setFilter={setFilter}
      onSelect={selectDocument} onNew={newDocument} onOpen={() => fileRef.current?.click()} onHelp={() => openDialog('help')} theme={theme} onTheme={() => setTheme(theme === 'light' ? 'dark' : 'light')}
      isOpen={mobileSidebar} onClose={() => setMobileSidebar(false)} storageError={storageError} />
    <main className="main">
      <header className="app-header">
        <div className="header-left">
          <button className="icon-button sidebar-toggle" title={sidebarVisible ? '收起侧边栏' : '展开侧边栏'} aria-label="切换文档列表" onClick={() => {
            if (window.innerWidth <= 760) setMobileSidebar(current => !current);
            else setSidebarVisible(current => !current);
          }}>{sidebarVisible ? <PanelLeftClose size={19} /> : <PanelLeftOpen size={19} />}</button>
          <div className="breadcrumbs"><span>我的文档</span><ChevronRight size={13} /><button onClick={() => openDialog('rename')}>{activeDoc.title}</button><span className="file-type">.md</span></div>
        </div>
        <div className="header-actions">
          <span className={'save-state ' + status}><span>{status === 'saved' ? <CheckCircle2 size={14} /> : status === 'saving' ? <span className="saving-dot" /> : <CircleHelp size={14} />}</span><span>{status === 'saved' ? '已保存到本地' : status === 'saving' ? '保存中…' : '请导出备份'}</span></span>
          <button className="icon-button focus-button" aria-label={focusMode ? '退出专注模式' : '专注模式'} title={focusMode ? '退出专注模式 (Esc)' : '专注模式 (Ctrl / ⌘ Shift F)'} onClick={() => setFocusMode(!focusMode)}>{focusMode ? <Minimize2 size={17} /> : <Maximize2 size={17} />}</button>
          <div className="menu-container">
            <button className="export-button" onClick={() => { setExportMenu(!exportMenu); setMoreMenu(false); }} aria-expanded={exportMenu}><Download size={15} /><span>导出</span><ChevronDown size={13} /></button>
            {exportMenu && <><button className="menu-dismiss" aria-label="关闭导出菜单" onClick={() => setExportMenu(false)} /><div className="dropdown-menu export-menu">
              <button onClick={exportDocument}><FileText size={15} />Markdown 文件<span>.md</span></button>
              <button disabled={effectiveMode === 'source'} onClick={() => { setExportMenu(false); window.print(); }}><Printer size={15} />打印 / 保存 PDF</button>
            </div></>}
          </div>
        </div>
      </header>

      <div className="workspace-bar">
        <div className="document-tab"><FileText size={15} /><span>{activeDoc.title}</span><button className={'icon-button favorite-button' + (activeDoc.favorite ? ' favorited' : '')} aria-label={activeDoc.favorite ? '取消收藏' : '收藏文档'} title={activeDoc.favorite ? '取消收藏' : '收藏文档'} onClick={toggleFavorite}><Star size={14} /></button></div>
        <div className="view-switch" aria-label="编辑模式">
          <button className={effectiveMode === 'write' ? 'active' : ''} aria-pressed={effectiveMode === 'write'} onClick={() => setEditorMode('write')}><Pencil size={13} />编辑</button>
          <button className={effectiveMode === 'source' ? 'active' : ''} aria-pressed={effectiveMode === 'source'} onClick={() => setEditorMode('source')}><Code2 size={14} />源码</button>
        </div>
        <div className="workspace-actions">
          <button className={'icon-button outline-toggle' + (outlineVisible ? ' selected-icon' : '')} aria-label="切换文档大纲" title="文档大纲" aria-pressed={outlineVisible} onClick={() => setOutlineVisible(!outlineVisible)}><AlignLeft size={17} /></button>
          <div className="menu-container"><button className="icon-button" aria-label="更多文档操作" title="更多文档操作" aria-expanded={moreMenu} onClick={() => { setMoreMenu(!moreMenu); setExportMenu(false); }}><MoreHorizontal size={19} /></button>
            {moreMenu && <><button className="menu-dismiss" aria-label="关闭文档菜单" onClick={() => setMoreMenu(false)} /><div className="dropdown-menu">
              <button onClick={() => openDialog('rename')}><Pencil size={15} />重命名</button>
              <button onClick={toggleFavorite}><Star size={15} />{activeDoc.favorite ? '取消收藏' : '收藏文档'}</button>
              <button className="danger" onClick={() => openDialog('delete')}><Trash2 size={15} />删除文档</button>
            </div></>}
          </div>
        </div>
      </div>

      {storageError && <div className="storage-warning" role="alert">{storageError}<button onClick={exportDocument}>导出备份</button></div>}

      <div className={'writing-layout' + (!outlineVisible ? ' no-outline' : '')}>
        <section className="writing-scroll" id="writing" ref={scrollRef} tabIndex={-1} aria-label="写作区">
          {effectiveMode === 'source' ? <>
            <div className="source-toolbar"><Code2 size={15} /><span>Markdown 源码</span><span className="source-tip">原始文字，完整保留</span></div>
            <div className="source-editor">
              <div className="line-numbers" aria-hidden="true">{activeDoc.markdown.split('\n').map((_, index) => <div key={index}>{index + 1}</div>)}</div>
              <textarea wrap="off" ref={sourceRef} aria-label="Markdown 源码编辑区" value={activeDoc.markdown} spellCheck={false} onChange={event => updateDocument(event.target.value)} onKeyDown={event => {
                if (event.key === 'Tab') {
                  event.preventDefault();
                  const target = event.target;
                  const start = target.selectionStart;
                  const end = target.selectionEnd;
                  updateDocument(activeDoc.markdown.slice(0, start) + '  ' + activeDoc.markdown.slice(end));
                  requestAnimationFrame(() => target.setSelectionRange(start + 2, start + 2));
                }
              }} style={{ height: Math.max(500, activeDoc.markdown.split('\n').length * 26 + 120) }} />
            </div>
          </> : <>
            <MarkdownEditor key={activeDoc.id} markdown={activeDoc.markdown} onChange={updateDocument} onReady={onEditorReady} onInsert={openDialog}>
            <div className="document-meta"><span className="document-eyebrow"><span />为想法留一点空白</span><div><span><CalendarDays size={13} />{new Date(activeDoc.createdAt).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })}</span><span><Clock3 size={13} />约 {Math.max(1, Math.ceil(wordCount / 300))} 分钟阅读</span></div></div>
            </MarkdownEditor>
            <div className="page-end"><Feather size={16} strokeWidth={1.3} /><span>文字的力量，从落笔开始</span></div>
          </>}
        </section>
        {outlineVisible && <aside className="outline" aria-label="文档大纲"><div className="outline-heading"><span>文档大纲</span><AlignLeft size={15} /></div>
          <div className="outline-links">{headings.map((heading, index) => <button key={index} className={(activeHeading === index ? 'active' : '') + (heading.level === 1 ? ' outline-title' : '')} style={{ paddingLeft: 14 + Math.max(0, heading.level - 2) * 12 }} onClick={() => jumpToHeading(index)}><span>{heading.text}</span></button>)}
            {headings.length === 0 && <p>添加一个标题，<br />让思路变得更清晰。</p>}
          </div>
          <div className="writing-tip"><span className="tip-label">写作小提示</span><p>不用急着找到完美的词。<br />先写下来，再慢慢打磨。</p><span className="tip-line" /></div>
        </aside>}
      </div>

      <footer className="statusbar"><div><span className="status-dot" />{online ? '本地工作空间' : <><WifiOff size={12} />离线写作</>}<span className="status-divider" /><span>Markdown</span></div><div><span>{wordCount.toLocaleString('zh-CN')} 字</span><span className="status-divider" /><span className="status-reading">约 {Math.max(1, Math.ceil(wordCount / 300))} 分钟</span><span className="status-divider status-reading" /><span>UTF-8</span><button onClick={() => openDialog('help')} aria-label="写作帮助" className="status-help"><CircleHelp size={14} /></button></div></footer>
    </main>

    {toast && <div className="toast" role="status"><Check size={16} /><span>{toast}</span><button aria-label="关闭提示" onClick={() => setToast(null)}><X size={15} /></button></div>}

    {dialog && <Dialog title={dialogTitles[dialog]} onClose={closeDialog}>
      {['rename', 'link', 'image'].includes(dialog) && <form onSubmit={submitDialog}>
        <p className="dialog-description">{dialog === 'rename' ? '一个好名字，让每次回到这里都更轻松。' : dialog === 'link' ? '选中文字后插入链接，或直接添加链接地址。' : '使用公开的图片地址。图片需要联网加载。'}</p>
        <label className="dialog-label" htmlFor="dialog-input">{dialog === 'rename' ? '文档名称' : dialog === 'image' ? '图片地址' : '链接地址'}</label>
        <input autoFocus id="dialog-input" className="dialog-input" value={dialogValue} onChange={event => setDialogValue(event.target.value)} placeholder={dialog === 'rename' ? '给文档取个名字' : 'https://…'} maxLength={dialog === 'rename' ? 100 : 2000} />
        {dialogError && <p className="form-error" role="alert">{dialogError}</p>}
        <div className="dialog-buttons"><button type="button" className="secondary-button" onClick={closeDialog}>取消</button><button type="submit" className="primary-button">{dialog === 'rename' ? '保存名称' : '插入'}</button></div>
      </form>}
      {dialog === 'delete' && <><p className="dialog-description">「{activeDoc.title}」将从此浏览器的工作空间移除，删除后无法撤销。你可以先导出一份副本。</p><div className="dialog-buttons"><button className="secondary-button" onClick={exportDocument}>导出副本</button><button className="danger-button" onClick={deleteDocument}>确认删除</button></div></>}
      {dialog === 'help' && <><p className="dialog-description">墨记是一个所见即所得的 Markdown 编辑器。输入 <code>#</code>、<code>-</code> 或 <code>&gt;</code> 后按空格，即可开始标题、列表或引用。</p>
        <div className="shortcut-list">{[['加粗', 'Ctrl / ⌘ B'], ['斜体', 'Ctrl / ⌘ I'], ['打开 Markdown 文件', 'Ctrl / ⌘ O'], ['导出 Markdown', 'Ctrl / ⌘ S'], ['专注模式', 'Ctrl / ⌘ Shift F'], ['新建文档', 'Ctrl / ⌘ Alt N'], ['退出专注模式', 'Esc']].map(([label, key]) => <div key={label}><span>{label}</span><kbd>{key}</kbd></div>)}</div>
        <div className="help-note"><strong>关于你的文字</strong><p>自动保存仅保存在当前浏览器。跨设备使用时，请导出并打开 .md 文件。清除浏览器数据前记得备份。</p><p>生产版本支持离线写作，可通过浏览器安装到桌面。公式、脚注、HTML 和 YAML 目前使用源码编辑。</p></div>
        <div className="dialog-buttons"><button className="primary-button" onClick={closeDialog}>开始写作</button></div></>}
      {dialog === 'table' && <><p className="dialog-description">在表格中选中一个单元格，再选择操作。</p><div className="table-actions">{[['添加一行', 'addRowAfter'], ['添加一列', 'addColumnAfter'], ['删除当前行', 'deleteRow'], ['删除当前列', 'deleteColumn'], ['删除表格', 'deleteTable']].map(([label, command]) => <button key={command} className="secondary-button" onClick={() => { editorRef.current?.chain().focus()[command]().run(); closeDialog(); }}>{label}</button>)}</div></>}
    </Dialog>}
  </div>;
}
