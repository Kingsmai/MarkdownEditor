import { Feather, Plus, Search, Files, Star, FileText, FolderOpen, Keyboard, Sun, Moon, HardDrive, ChevronRight, X } from 'lucide-react';

export default function Sidebar({ documents, activeId, query, setQuery, filter, setFilter, onSelect, onNew, onOpen, onHelp, theme, onTheme, isOpen, onClose, storageError }) {
  const visibleDocs = documents.filter(doc => (filter !== 'favorites' || doc.favorite) && (doc.title + ' ' + doc.markdown).toLowerCase().includes(query.toLowerCase()));
  return <>
    {isOpen && <button className="sidebar-scrim" aria-label="关闭文档列表" onClick={onClose} />}
    <aside className={'sidebar' + (isOpen ? ' mobile-open' : '')} aria-label="文档导航">
      <div className="brand"><span className="brand-mark"><Feather size={22} strokeWidth={1.5} /></span><span className="brand-name">墨记<span>INKNOTE</span></span><button className="icon-button mobile-close" aria-label="关闭文档列表" onClick={onClose}><X size={20} /></button></div>
      <button className="new-document" onClick={onNew}><Plus size={18} /><span>新建文档</span><span className="shortcut">N</span></button>
      <label className="document-search"><Search size={15} /><input aria-label="搜索文档" placeholder="搜索你的文档…" value={query} onChange={event => setQuery(event.target.value)} /><kbd>⌕</kbd></label>
      <div className="sidebar-label">工作空间</div>
      <nav className="workspace-nav">
        <button className={filter === 'all' ? 'selected' : ''} onClick={() => setFilter('all')}><Files size={17} /><span>所有文档</span><span className="nav-count">{documents.length}</span></button>
        <button className={filter === 'favorites' ? 'selected' : ''} onClick={() => setFilter('favorites')}><Star size={17} /><span>我的收藏</span><span className="nav-count">{documents.filter(doc => doc.favorite).length}</span></button>
      </nav>
      <div className="sidebar-rule" />
      <div className="document-list-heading"><span className="sidebar-label">{query ? '搜索结果' : filter === 'favorites' ? '收藏文档' : '最近文档'}</span><span>{String(visibleDocs.length).padStart(2, '0')}</span></div>
      <div className="document-list">
        {visibleDocs.map(doc => <button key={doc.id} className={'document-item' + (doc.id === activeId ? ' active' : '')} onClick={() => onSelect(doc.id)}>
          <FileText size={17} strokeWidth={1.7} /><span><strong>{doc.title}</strong><small>{new Date(doc.updatedAt).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })} · Markdown</small></span>{doc.favorite && <Star size={12} className="document-star" />}
        </button>)}
        {visibleDocs.length === 0 && <p className="empty-documents">{query ? '没有找到相关文档' : '点击文档上方的星标，收藏喜欢的文字。'}</p>}
      </div>
      <button className="open-file" onClick={onOpen}><FolderOpen size={17} /><span>打开本地文件</span><ChevronRight size={15} /></button>
      <div className={'local-note' + (storageError ? ' has-error' : '')}><HardDrive size={16} /><div><strong>{storageError ? '本地保存需要处理' : '只属于你的写作空间'}</strong><p>{storageError ? '请及时导出文档备份' : '文档保存在此设备，安心书写。'}</p></div></div>
      <footer className="sidebar-footer"><span className="version"><i />MVP 0.1</span><button className="icon-button" onClick={onHelp} title="快捷键与帮助" aria-label="快捷键与帮助"><Keyboard size={17} /></button><button className="icon-button" onClick={onTheme} title={theme === 'light' ? '切换深色主题' : '切换浅色主题'} aria-label={theme === 'light' ? '切换深色主题' : '切换浅色主题'}>{theme === 'light' ? <Moon size={17} /> : <Sun size={17} />}</button></footer>
    </aside>
  </>;
}
