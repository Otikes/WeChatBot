import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { MagnifyingGlass, CheckCircle, Trash, ArrowUUpLeft, X, ListChecks, FloppyDisk, Info, Warning, Gear, UsersThree, Spinner } from '@phosphor-icons/react'
import { Toggle, Input, Field } from './SharedComponents'

const API = 'http://127.0.0.1:7327'

const tabTransition = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
}

const configPanel = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } },
  exit: { opacity: 0, y: 20, transition: { duration: 0.2 } },
}

function ParamRow({ label, hint, children }) {
  return (
    <div>
      <p className="text-[14px] text-text-main font-medium">{label}</p>
      <p className="text-xs text-text-muted mt-0.5 mb-2">{hint}</p>
      {children}
    </div>
  )
}

function KeywordChips({ keywords, update, minItems = 1 }) {
  const [inputValue, setInputValue] = useState('')

  function addKeyword() {
    const val = inputValue.trim()
    if (val && !keywords.includes(val)) {
      update([...keywords, val])
      setInputValue('')
    }
  }

  function handleKeyDown(e) {
    if (e.key !== 'Enter') return
    if (e.nativeEvent.isComposing) return  // 中文输入法组合输入中，跳过
    e.preventDefault()
    addKeyword()
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2 mb-2">
        {(keywords || []).map((kw, i) => (
          <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green">
            {kw}
            <button type="button" disabled={keywords.length <= minItems}
              onClick={() => { const next = keywords.filter((_, idx) => idx !== i); update(next) }}
              className={`ml-0.5 leading-none text-base transition-colors ${keywords.length <= minItems ? 'text-text-muted cursor-not-allowed' : 'text-brand-green-hover/60 hover:text-[#d45656] cursor-pointer'}`}>&times;</button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input type="text" value={inputValue} onChange={e => setInputValue(e.target.value)}
          placeholder="输入新触发词，回车添加"
          className="flex-1 bg-bg-raised border border-border-main rounded-lg px-3 py-2 text-[14px] text-text-main placeholder:text-text-muted/65 focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all"
          onKeyDown={handleKeyDown} />
        <button type="button" onClick={addKeyword}
          className="px-4 py-2 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green hover:bg-brand-green/10 transition-colors font-medium cursor-pointer">添加</button>
      </div>
    </div>
  )
}

export default function TodoManager() {
  // ── Todo config state ──────────────────────────────────────────
  const [configOpen, setConfigOpen] = useState(false)
  const [configSaved, setConfigSaved] = useState(false)
  const [configSaving, setConfigSaving] = useState(false)
  const [configSaveError, setConfigSaveError] = useState('')
  const [groupQuery, setGroupQuery] = useState('')
  const [todoEnabled, setTodoEnabled] = useState(true)
  const [todoGroups, setTodoGroups] = useState(['*'])
  const [todoMaxPerGroup, setTodoMaxPerGroup] = useState(50)
  const [todoCompletedRetention, setTodoCompletedRetention] = useState(30)
  const [todoDeletedRetention, setTodoDeletedRetention] = useState(30)
  const [todoAddKeywords, setTodoAddKeywords] = useState(['记一下', '添加待办', '新建待办', '帮我记', '待办'])
  const [todoCompleteKeywords, setTodoCompleteKeywords] = useState(['搞定', '做完了', '完成', '完成了', 'done'])
  const [todoDeleteKeywords, setTodoDeleteKeywords] = useState(['删掉', '删除', '取消', '不要了'])

  // ── Todo management state ──────────────────────────────────────
  const [activeTab, setActiveTab] = useState('active')
  const [items, setItems] = useState([])
  const [groups, setGroups] = useState([])
  const [selectedGroup, setSelectedGroup] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionMsg, setActionMsg] = useState('')
  const [availableGroups, setAvailableGroups] = useState([])  // {chat_id, group_name, member_count}[]
  const [tabCounts, setTabCounts] = useState({ active: 0, completed: 0, deleted: 0 })

  // ── 待办配置：加载与回滚 ──────────────────────────────────────
  /** 从服务端重新加载待办配置（弹窗取消时也用它丢弃未保存的改动） */
  async function loadConfig() {
    try {
      const res = await fetch(`${API}/api/load-config`)
      const data = await res.json()
      if (data.ok && data.config) {
        const c = data.config
        if (typeof c.todo_enabled === 'boolean') setTodoEnabled(c.todo_enabled)
        if (c.todo_groups) setTodoGroups(Array.isArray(c.todo_groups) ? c.todo_groups : ['*'])
        if (c.todo_max_per_group != null) setTodoMaxPerGroup(c.todo_max_per_group)
        if (c.todo_completed_retention_days != null) setTodoCompletedRetention(c.todo_completed_retention_days)
        if (c.todo_deleted_retention_days != null) setTodoDeletedRetention(c.todo_deleted_retention_days)
        if (c.todo_add_keywords) setTodoAddKeywords(Array.isArray(c.todo_add_keywords) ? c.todo_add_keywords : String(c.todo_add_keywords).split(','))
        if (c.todo_complete_keywords) setTodoCompleteKeywords(Array.isArray(c.todo_complete_keywords) ? c.todo_complete_keywords : String(c.todo_complete_keywords).split(','))
        if (c.todo_delete_keywords) setTodoDeleteKeywords(Array.isArray(c.todo_delete_keywords) ? c.todo_delete_keywords : String(c.todo_delete_keywords).split(','))
      }
    } catch {}
  }

  /** 关闭配置弹窗，并丢弃未保存的改动 */
  function closeConfig() {
    setConfigOpen(false)
    loadConfig()
  }

  // 首次进入时加载配置
  useEffect(() => { loadConfig() }, [])

  // 弹窗关闭时清空搜索与保存提示
  useEffect(() => {
    if (!configOpen) {
      setGroupQuery('')
      setConfigSaved(false)
      setConfigSaveError('')
    }
  }, [configOpen])

  // 弹窗打开时支持 Esc 关闭，并锁定页面滚动
  useEffect(() => {
    if (!configOpen) return
    const onKeyDown = e => { if (e.key === 'Escape') closeConfig() }
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = prevOverflow
    }
  }, [configOpen])

  // ── 可选群聊（配置弹窗与筛选下拉共用） ───────────────────────────
  async function loadAvailableGroups() {
    try {
      const res = await fetch(`${API}/api/groups`)
      const data = await res.json()
      if (data.ok) setAvailableGroups(data.groups || [])
    } catch {}
  }

  useEffect(() => { loadAvailableGroups() }, [])

  // 每次打开配置弹窗时同步最新群列表，新建群后无需刷新页面
  useEffect(() => { if (configOpen) loadAvailableGroups() }, [configOpen])

  // ── Save todo config ──────────────────────────────────────────
  async function handleSaveConfig() {
    setConfigSaved(false)
    setConfigSaveError('')
    setConfigSaving(true)
    try {
      const res = await fetch(`${API}/api/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          todo_enabled: todoEnabled,
          todo_groups: todoGroups,
          todo_max_per_group: todoMaxPerGroup,
          todo_completed_retention_days: todoCompletedRetention,
          todo_deleted_retention_days: todoDeletedRetention,
          todo_add_keywords: todoAddKeywords,
          todo_complete_keywords: todoCompleteKeywords,
          todo_delete_keywords: todoDeleteKeywords,
        }),
      })
      const data = await res.json()
      if (data.ok) { setConfigSaved(true); setTimeout(() => setConfigSaved(false), 3000) }
      else { setConfigSaveError(data.error || '保存失败'); setTimeout(() => setConfigSaveError(''), 5000) }
    } catch { setConfigSaveError('无法连接到服务器，请确认机器人已启动'); setTimeout(() => setConfigSaveError(''), 5000) }
    setConfigSaving(false)
  }

  // ── 待办群聊开关 ──────────────────────────────────────────────
  const todoAllGroups = todoGroups.includes('*')

  /** 合并「已发现群聊」与配置中残留的群，历史配置也能正常展示 */
  const configGroups = (() => {
    const list = [...availableGroups]
    todoGroups
      .filter(id => id !== '*' && !list.some(g => g.chat_id === id))
      .forEach(id => list.push({ chat_id: id, group_name: id, member_count: 0 }))
    return list
  })()

  const visibleConfigGroups = configGroups.filter(g => {
    const q = groupQuery.trim().toLowerCase()
    if (!q) return true
    return (g.group_name || '').toLowerCase().includes(q)
      || (g.chat_id || '').toLowerCase().includes(q)
  })

  function isTodoGroupEnabled(chatId) {
    return todoAllGroups || todoGroups.includes(chatId)
  }

  function toggleAllGroups(on) {
    setConfigSaved(false)
    setTodoGroups(on ? ['*'] : [])
  }

  function toggleTodoGroup(chatId) {
    setConfigSaved(false)
    if (todoAllGroups) {
      // 从「全部群聊」切换为显式名单，仅排除当前群
      setTodoGroups(configGroups.filter(g => g.chat_id !== chatId).map(g => g.chat_id))
    } else if (todoGroups.includes(chatId)) {
      setTodoGroups(todoGroups.filter(id => id !== chatId))
    } else {
      setTodoGroups([...todoGroups, chatId])
    }
  }

  // ── Todo management ────────────────────────────────────────────

  const retryRef = useRef(0)  // 跟踪重试次数

  useEffect(() => { loadData(); loadCounts() }, [activeTab, selectedGroup])

  // 初始加载失败后自动重试
  useEffect(() => {
    if (!error) return
    if (retryRef.current >= 5) return  // 最多重试 5 次
    const delay = Math.min(1000 * Math.pow(2, retryRef.current), 16000)
    const timer = setTimeout(() => { retryRef.current++; loadData(); loadCounts() }, delay)
    return () => clearTimeout(timer)
  }, [error])

  function retryLoad() { retryRef.current = 0; loadData(); loadCounts() }

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const status = search.trim() ? 'all' : activeTab
      const params = new URLSearchParams({ status })
      if (selectedGroup) params.set('chat_id', selectedGroup)
      if (search.trim()) params.set('search', search.trim())
      const res = await fetch(`${API}/api/todos?${params}`)
      const d = await res.json()
      if (d.ok) {
        setItems(d.items || [])
        setGroups(d.groups || [])
        retryRef.current = 0
      } else {
        setError(d.error || '加载失败')
      }
    } catch { setError('无法连接到服务器，请确认机器人已启动') }
    setLoading(false)
  }

  async function loadCounts() {
    try {
      const params = new URLSearchParams()
      if (selectedGroup) params.set('chat_id', selectedGroup)
      const res = await fetch(`${API}/api/todos/counts?${params}`)
      const d = await res.json()
      if (d.ok && d.counts) setTabCounts(d.counts)
    } catch {}
  }

  // 搜索时用 debounce 触发跨状态查询
  useEffect(() => {
    if (!search.trim()) { loadData(); return }
    const timer = setTimeout(() => loadData(), 300)
    return () => clearTimeout(timer)
  }, [search])

  async function doAction(action, chatId, target) {
    setActionMsg('')
    try {
      const res = await fetch(`${API}/api/todos/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, chat_id: chatId, target: String(target) }),
      })
      const d = await res.json()
      if (d.ok) {
        setActionMsg(d.reply || '操作成功')
        setTimeout(() => setActionMsg(''), 3000)
        loadData()
      } else {
        setActionMsg(d.reply || d.error || '操作失败')
        setTimeout(() => setActionMsg(''), 5000)
      }
    } catch {
      setActionMsg('网络错误')
      setTimeout(() => setActionMsg(''), 5000)
    }
  }

  const filtered = items.filter(item =>
    !search || item.content.toLowerCase().includes(search.toLowerCase())
  )

  const managementTabs = [
    { id: 'active', label: '群聊待办' },
    { id: 'deleted', label: '已删除' },
    { id: 'completed', label: '已完成' },
  ]

  return (
    <div className="max-w-3xl">

      {/* ── 待办管理 ─────────────────────────────────────────────── */}
      <div className="bg-bg-card border border-border-main rounded-2xl shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none p-7">
        <div className="flex items-center justify-between gap-3 mb-5 pl-1">
          <div className="flex items-center gap-2.5">
            <div className="w-1.5 h-4.5 rounded-full shadow-sm" style={{ backgroundColor: '#18E299' }} />
            <h3 className="text-sm font-semibold tracking-tight text-text-main">待办管理</h3>
            <span className={`text-[10.5px] px-2 py-0.5 rounded-full border font-medium ${
              todoEnabled
                ? 'bg-brand-green-light border-brand-green/20 text-brand-green-hover dark:text-brand-green'
                : 'bg-bg-raised border-border-main text-text-muted'
            }`}>
              {todoEnabled
                ? todoAllGroups
                  ? '已开启 · 全部群聊'
                  : todoGroups.length > 0
                    ? `已开启 · ${todoGroups.length} 个群`
                    : '已开启 · 未选群聊'
                : '已关闭'}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setConfigOpen(true)}
            className="flex items-center gap-1.5 px-3.5 py-2 bg-bg-raised border border-border-main rounded-full text-[12.5px] font-medium text-text-main hover:border-brand-green hover:text-brand-green-hover transition-colors cursor-pointer"
          >
            <Gear size={15} /> 配置
          </button>
        </div>

        {/* Action message toast */}
        <AnimatePresence>
          {actionMsg && (
            <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
              className="mb-4 flex items-center gap-2 px-5 py-2.5 bg-brand-green-light border border-brand-green/20 rounded-full text-sm text-brand-green-hover dark:text-brand-green font-medium shadow-sm">
              <CheckCircle size={18} weight="fill" /> {actionMsg}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Search + Group filter */}
        <div className="flex items-center gap-3 mb-5">
          <div className="flex-1 relative">
            <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input type="text" value={search} onChange={e => setSearch(e.target.value)}
              placeholder="搜索待办内容..."
              className="w-full bg-bg-card border border-border-main rounded-xl pl-9 pr-4 py-2.5 text-[14px] text-text-main placeholder:text-text-muted/60 focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all" />
          </div>
          <select value={selectedGroup} onChange={e => setSelectedGroup(e.target.value)}
            className="bg-bg-card border border-border-main rounded-xl px-3 py-2.5 text-[14px] text-text-main focus:outline-none focus:border-brand-green cursor-pointer max-w-[200px] truncate">
            <option value="">全部群聊</option>
            {availableGroups.map(ag => (
              <option key={ag.chat_id} value={ag.chat_id}>
                {(ag.group_name || ag.chat_id).length > 16
                  ? (ag.group_name || ag.chat_id).slice(0, 16) + '...'
                  : (ag.group_name || ag.chat_id)}
              </option>
            ))}
          </select>
        </div>

        {/* Tab switcher */}
        <div className="flex gap-1 mb-5 bg-bg-card border border-border-main rounded-xl p-1 w-fit">
          {managementTabs.map(tab => {
            const active = activeTab === tab.id
            const count = tabCounts[tab.id]
            return (
              <button key={tab.id} onClick={() => { setActiveTab(tab.id); setSearch('') }}
                className={`relative px-4 py-2 rounded-lg text-[13px] font-medium transition-all cursor-pointer ${
                  active ? 'text-brand-green-hover dark:text-brand-green' : 'text-text-muted hover:text-text-main'
                }`}>
                {active && (
                  <motion.div layoutId="todoMgmtTabBg" className="absolute inset-0 bg-brand-green-light rounded-lg"
                    transition={{ type: 'spring', stiffness: 400, damping: 30 }} />
                )}
                <span className="relative z-10">
                  {tab.label}
                  <span className="ml-1.5 text-[11px] opacity-60">({count != null ? count : '-'})</span>
                </span>
              </button>
            )})}
        </div>

        {/* Content area */}
        <div style={{ minHeight: 300 }}>
          <AnimatePresence mode="wait">
            {loading ? (
              <motion.div key="loading" variants={tabTransition} initial="initial" animate="animate" exit="exit"
                className="flex items-center justify-center py-20">
                <svg className="animate-spin h-5 w-5 text-brand-green" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              </motion.div>
            ) : error ? (
              <motion.div key="error" variants={tabTransition} initial="initial" animate="animate" exit="exit"
                className="text-center py-20">
                <p className="text-sm text-[#d45656] mb-3">{error}</p>
                <button onClick={retryLoad}
                  className="px-4 py-2 text-[13px] bg-bg-raised border border-border-main rounded-lg text-text-main hover:border-brand-green hover:text-brand-green-hover transition-colors cursor-pointer font-medium">
                  重新连接
                </button>
              </motion.div>
            ) : filtered.length === 0 ? (
              <motion.div key="empty" variants={tabTransition} initial="initial" animate="animate" exit="exit"
                className="text-center py-20">
                <ListChecks size={40} className="mx-auto mb-3 text-text-muted/40" />
                <p className="text-sm text-text-muted">
                  {search.trim() ? '未找到匹配的待办事项' :
                   activeTab === 'active' ? '暂无待办事项。@机器人说"记一下 xxx"即可添加' :
                   activeTab === 'deleted' ? '暂无已删除事项' : '暂无已完成事项'}
                </p>
              </motion.div>
            ) : (
              <motion.div key={`${activeTab}-${filtered.length}`} variants={tabTransition} initial="initial" animate="animate" exit="exit"
                className="space-y-3">
                {filtered.map(item => {
                  const isSearchResult = search.trim() && item.status !== activeTab
                  const groupInfo = availableGroups.find(ag => ag.chat_id === item.chat_id)
                  const groupLabel = groupInfo?.group_name || item.chat_id
                  const statusBadge = {
                    active:   { label: '待办', cls: 'text-brand-green-hover bg-brand-green-light border-brand-green/20' },
                    completed:{ label: '已完成', cls: 'text-[#c37d0d] bg-[#c37d0d]/10 border-[#c37d0d]/20' },
                    deleted:  { label: '已删除', cls: 'text-[#d45656] bg-[#d45656]/5 border-[#d45656]/20' },
                  }[item.status] || { label: item.status, cls: 'text-text-muted bg-bg-raised border-border-main' }

                  return (
                  <div key={item.id}
                    className={`bg-bg-card border rounded-2xl shadow-sm p-5 transition-colors ${
                      isSearchResult ? 'border-[#c37d0d]/40 bg-[#c37d0d]/[0.03] cursor-pointer hover:bg-[#c37d0d]/[0.06]' : 'border-border-main'
                    }`}
                    onClick={() => { if (isSearchResult) { setActiveTab(item.status); setSearch('') } }}>
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-[11px] font-mono text-text-muted bg-bg-raised border border-border-main px-2 py-0.5 rounded-full">
                            #{item.display_order}
                          </span>
                          {item.status !== activeTab && (
                            <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full border ${statusBadge.cls}`}>
                              {statusBadge.label}
                            </span>
                          )}
                          {!selectedGroup && item.chat_id && (
                            <span className="text-[11px] text-text-muted/60 truncate max-w-[160px]">
                              {groupLabel.length > 20 ? groupLabel.slice(0, 20) + '...' : groupLabel}
                            </span>
                          )}
                          {isSearchResult && (
                            <span className="text-[11px] text-[#c37d0d] ml-auto">点击跳转至对应列表</span>
                          )}
                        </div>
                        <p className="text-[15px] text-text-main">{item.content}</p>
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-xs text-text-muted">
                          {item.creator_name && <span>创建者: @{item.creator_name}</span>}
                          {item.created_at > 0 && (
                            <span>创建时间: {new Date(item.created_at * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                          )}
                          {item.completed_by_name && <span>完成者: @{item.completed_by_name}</span>}
                          {item.completed_at > 0 && (
                            <span>完成时间: {new Date(item.completed_at * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                          )}
                          {item.deleted_by_name && <span>删除者: @{item.deleted_by_name}</span>}
                          {item.deleted_at > 0 && (
                            <span>删除时间: {new Date(item.deleted_at * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                          )}
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="flex items-center gap-1.5 shrink-0">
                        {item.status === 'active' && (
                          <>
                            <button onClick={() => doAction('complete', item.chat_id, String(item.display_order))}
                              className="px-3 py-1.5 text-[12px] bg-brand-green-light border border-brand-green/20 rounded-lg text-brand-green-hover dark:text-brand-green hover:bg-brand-green/10 transition-colors cursor-pointer font-medium flex items-center gap-1">
                              <CheckCircle size={14} /> 完成
                            </button>
                            <button onClick={() => doAction('delete', item.chat_id, String(item.display_order))}
                              className="px-3 py-1.5 text-[12px] bg-bg-raised border border-border-main rounded-lg text-text-muted hover:text-[#d45656] hover:border-[#d45656]/20 hover:bg-[#d45656]/5 transition-colors cursor-pointer font-medium flex items-center gap-1">
                              <Trash size={14} /> 删除
                            </button>
                          </>
                        )}
                        {item.status === 'deleted' && (
                          <>
                            <button onClick={() => doAction('restore', item.chat_id, String(item.display_order))}
                              className="px-3 py-1.5 text-[12px] bg-brand-green-light border border-brand-green/20 rounded-lg text-brand-green-hover dark:text-brand-green hover:bg-brand-green/10 transition-colors cursor-pointer font-medium flex items-center gap-1">
                              <ArrowUUpLeft size={14} /> 恢复
                            </button>
                            <button onClick={() => doAction('clear_deleted', item.chat_id, '')}
                              className="px-3 py-1.5 text-[12px] bg-bg-raised border border-border-main rounded-lg text-text-muted hover:text-[#d45656] hover:border-[#d45656]/20 hover:bg-[#d45656]/5 transition-colors cursor-pointer font-medium flex items-center gap-1">
                              <X size={14} /> 彻底删除
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                )})}

                {/* Clear all button for completed tab */}
                {activeTab === 'completed' && filtered.length > 0 && (
                  <div className="pt-2">
                    <button onClick={() => {
                      const cid = selectedGroup || (filtered[0]?.chat_id || '')
                      doAction('clear_completed', cid, '')
                    }}
                      className="px-4 py-2 text-[12px] bg-bg-raised border border-border-main rounded-lg text-text-muted hover:text-[#d45656] hover:border-[#d45656]/20 hover:bg-[#d45656]/5 transition-colors cursor-pointer font-medium flex items-center gap-1.5">
                      <Trash size={14} /> 清空已完成
                    </button>
                  </div>
                )}

                {/* Footer */}
                <div className="pt-2 text-xs text-text-muted/60">
                  共 {filtered.length} 项
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* ── 群聊待办配置弹窗 ─────────────────────────────────────── */}
      <AnimatePresence>
        {configOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closeConfig}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/45 backdrop-blur-sm"
          >
            <motion.div
              initial={{ opacity: 0, y: 16, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 16, scale: 0.98 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              onClick={e => e.stopPropagation()}
              className="w-full max-w-lg max-h-[85vh] flex flex-col bg-bg-card border border-border-main rounded-2xl shadow-2xl overflow-hidden"
            >
              {/* 弹窗标题 */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-border-main shrink-0">
                <div className="flex items-center gap-2.5">
                  <Gear size={18} className="text-brand-green-hover dark:text-brand-green" />
                  <div>
                    <h3 className="text-[15px] font-semibold text-text-main">群聊待办配置</h3>
                    <p className="text-[11px] text-text-muted mt-0.5">开启功能并选择生效的群聊</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={closeConfig}
                  title="关闭"
                  className="p-1.5 rounded-lg text-text-muted hover:text-text-main hover:bg-bg-raised transition-colors cursor-pointer"
                >
                  <X size={16} weight="bold" />
                </button>
              </div>

              {/* 弹窗内容 */}
              <div className="px-6 py-5 overflow-y-auto space-y-5">
                {/* 功能总开关 */}
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-[14px] text-text-main font-medium">启用群聊待办</p>
                    <p className="text-[11.5px] text-text-muted mt-0.5">关闭后所有群都不再响应待办命令</p>
                  </div>
                  <Toggle enabled={todoEnabled} onChange={v => { setTodoEnabled(v); setConfigSaved(false) }} />
                </div>

                {todoEnabled && (
                  <>
                    {/* 生效群聊 */}
                    <div>
                      <div className="flex items-center justify-between gap-3 mb-1.5">
                        <p className="text-[14px] text-text-main font-medium">开启待办的群聊</p>
                        <span className="text-[10.5px] font-mono text-text-muted">
                          {todoAllGroups ? '全部群聊' : `已选 ${todoGroups.length} 个`}
                        </span>
                      </div>
                      <p className="text-xs text-text-muted mb-2">未开启的群不会响应任何待办命令</p>

                      <div className="rounded-xl border border-border-main bg-bg-raised overflow-hidden">
                        {/* 全部群聊 */}
                        <div className="flex items-center justify-between gap-3 px-3.5 py-2.5 border-b border-border-main/70">
                          <div className="flex items-center gap-2">
                            <UsersThree size={15} className="text-text-muted" />
                            <span className="text-[13px] text-text-main font-medium">全部群聊</span>
                          </div>
                          <Toggle enabled={todoAllGroups} onChange={toggleAllGroups} />
                        </div>

                        {configGroups.length > 4 && (
                          <div className="flex items-center gap-1.5 px-3 py-2 border-b border-border-main/70">
                            <MagnifyingGlass size={13} className="text-text-muted/70 shrink-0" />
                            <input
                              type="text"
                              value={groupQuery}
                              onChange={e => setGroupQuery(e.target.value)}
                              placeholder="搜索群聊"
                              className="flex-1 min-w-0 bg-transparent text-[12.5px] text-text-main placeholder:text-text-muted/60 focus:outline-none"
                            />
                          </div>
                        )}

                        <div className="max-h-56 overflow-y-auto divide-y divide-border-main/40">
                          {configGroups.length === 0 ? (
                            <p className="px-3.5 py-3 text-[12px] text-text-muted">
                              暂无群聊，启动机器人同步后再来配置
                            </p>
                          ) : visibleConfigGroups.length === 0 ? (
                            <p className="px-3.5 py-3 text-[12px] text-text-muted">没有匹配的群聊</p>
                          ) : visibleConfigGroups.map(g => (
                            <div
                              key={g.chat_id}
                              className="flex items-center justify-between gap-3 px-3.5 py-2 hover:bg-bg-card transition-colors"
                            >
                              <span className="flex-1 min-w-0">
                                <span
                                  className="block text-[13px] text-text-main truncate"
                                  title={g.group_name || g.chat_id}
                                >
                                  {g.group_name || g.chat_id}
                                </span>
                                {g.chat_id !== g.group_name && (
                                  <span className="block text-[10.5px] text-text-muted/70 truncate font-mono">
                                    {g.chat_id}
                                  </span>
                                )}
                              </span>
                              <Toggle
                                enabled={isTodoGroupEnabled(g.chat_id)}
                                onChange={() => toggleTodoGroup(g.chat_id)}
                              />
                            </div>
                          ))}
                        </div>
                      </div>
                      {!todoAllGroups && todoGroups.length === 0 ? (
                        <p className="flex items-center gap-1.5 text-[10.5px] text-[#c37d0d] mt-1.5">
                          <Warning size={12} weight="fill" />
                          当前没有开启任何群，待办功能不会生效
                        </p>
                      ) : (
                        <p className="text-[10.5px] text-text-muted/70 mt-1.5">
                          关闭「全部群聊」后可以逐个群开启；一个都不选则等同于不生效。
                        </p>
                      )}
                    </div>

                    {/* 参数设置 */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                      <ParamRow label="每群待办上限" hint="1-200">
                        <Input type="number" value={String(todoMaxPerGroup)}
                          onChange={v => { setTodoMaxPerGroup(Math.max(1, Math.min(200, parseInt(v) || 50))); setConfigSaved(false) }} />
                      </ParamRow>
                      <ParamRow label="已完成保留天数" hint="0 = 永久">
                        <Input type="number" value={String(todoCompletedRetention)}
                          onChange={v => { setTodoCompletedRetention(Math.max(0, parseInt(v) || 0)); setConfigSaved(false) }} />
                      </ParamRow>
                      <ParamRow label="已删除保留天数" hint="0 = 永久">
                        <Input type="number" value={String(todoDeletedRetention)}
                          onChange={v => { setTodoDeletedRetention(Math.max(0, parseInt(v) || 0)); setConfigSaved(false) }} />
                      </ParamRow>
                    </div>

                    {/* 触发词配置 */}
                    <div className="space-y-4">
                      <div>
                        <p className="text-[13.5px] text-text-main font-medium">添加待办触发词</p>
                        <p className="text-[11.5px] text-text-muted mt-0.5 mb-2">@机器人 + 触发词 + 内容</p>
                        <KeywordChips keywords={todoAddKeywords} update={v => { setTodoAddKeywords(v); setConfigSaved(false) }} />
                      </div>
                      <div>
                        <p className="text-[13.5px] text-text-main font-medium">完成待办触发词</p>
                        <p className="text-[11.5px] text-text-muted mt-0.5 mb-2">@机器人 + 触发词 + 编号</p>
                        <KeywordChips keywords={todoCompleteKeywords} update={v => { setTodoCompleteKeywords(v); setConfigSaved(false) }} />
                      </div>
                      <div>
                        <p className="text-[13.5px] text-text-main font-medium">删除待办触发词</p>
                        <p className="text-[11.5px] text-text-muted mt-0.5 mb-2">@机器人 + 触发词 + 编号</p>
                        <KeywordChips keywords={todoDeleteKeywords} update={v => { setTodoDeleteKeywords(v); setConfigSaved(false) }} />
                      </div>
                    </div>

                    <div className="p-3 bg-bg-main/60 border border-border-main rounded-xl">
                      <p className="text-[11px] text-text-muted leading-relaxed">
                        💡 群内使用：@机器人 <code>查看待办</code> · <code>记一下 xxx</code> · <code>搞定 N</code>
                        · <code>删掉 N</code> · <code>恢复待办 N</code>（管理员）
                      </p>
                    </div>
                  </>
                )}
              </div>

              {/* 弹窗底部操作 */}
              <div className="flex items-center justify-between gap-3 px-6 py-4 border-t border-border-main bg-bg-raised/40 shrink-0">
                <div className="min-w-0 text-[11.5px]">
                  {configSaved ? (
                    <span className="flex items-center gap-1.5 text-brand-green-hover dark:text-brand-green font-medium">
                      <CheckCircle size={15} weight="fill" /> 已保存，重启机器人后生效
                    </span>
                  ) : configSaveError ? (
                    <span className="flex items-center gap-1.5 text-[#d45656]">
                      <Warning size={15} weight="fill" /> {configSaveError}
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-text-muted">
                      <Info size={14} /> 保存后需重启机器人生效
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={closeConfig}
                    className="px-4 py-2 rounded-full text-[12.5px] font-medium text-text-muted border border-border-main hover:text-text-main hover:border-text-muted/40 transition-colors cursor-pointer"
                  >
                    取消
                  </button>
                  <motion.button
                    whileTap={{ scale: 0.97 }}
                    onClick={handleSaveConfig}
                    disabled={configSaved || configSaving}
                    className="px-5 py-2 rounded-full text-[12.5px] font-semibold bg-[#0d0d0d] dark:bg-white text-white dark:text-[#0d0d0d] hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-60 flex items-center gap-1.5"
                  >
                    {configSaving ? (
                      <><Spinner size={15} weight="bold" className="animate-spin" /> 保存中…</>
                    ) : (
                      <><FloppyDisk size={15} /> 保存配置</>
                    )}
                  </motion.button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
