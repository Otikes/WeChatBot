import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  ArrowClockwise, ArrowLeft, ArrowRight, Check, CheckCircle, ChatCircleDots,
  Info, MagnifyingGlass, PencilSimple, Plus, Spinner, Trash, Users,
  WarningCircle, X,
} from '@phosphor-icons/react'
import { friendlyError } from './SharedComponents'

function apiUrl(path) {
  if (window.location.port === '5173') return `http://127.0.0.1:7327${path}`
  return path
}

const targetKey = (item) => `${item.type}:${item.id}`
const ACCENT = '#4C9B72'
const MAX_TARGETS = 500
const TABS = [
  { id: 'friend', label: '好友', icon: Users },
  { id: 'group', label: '群聊', icon: ChatCircleDots },
]

function CheckBox({ checked }) {
  return (
    <span
      className={`w-4 h-4 rounded-[5px] border flex items-center justify-center shrink-0 transition-colors duration-150 ${
        checked ? 'border-transparent' : 'border-text-muted/35'
      }`}
      style={checked ? { backgroundColor: ACCENT } : undefined}
    >
      {checked && <Check size={11} weight="bold" className="text-white" />}
    </span>
  )
}

/** 一行候选/已选目标：单击勾选、双击移动、hover 显示快捷移动按钮。 */
function TargetRow({ item, checked, onToggle, onMove, direction, disabled }) {
  const isGroup = item.type === 'group'
  const Icon = isGroup ? ChatCircleDots : Users
  const MoveIcon = direction === 'right' ? ArrowRight : X
  return (
    <div
      data-testid={direction === 'right' ? 'broadcast-candidate-row' : 'broadcast-selected-row'}
      data-target-key={targetKey(item)}
      onClick={disabled ? undefined : onToggle}
      onDoubleClick={disabled ? undefined : onMove}
      className={`group flex items-center gap-2.5 px-2 py-1.5 rounded-lg select-none transition-colors ${
        disabled ? 'opacity-55 cursor-not-allowed' : 'cursor-pointer'
      } ${checked ? 'bg-[#4C9B72]/10' : 'hover:bg-bg-card'}`}
    >
      <CheckBox checked={checked} />
      <Icon size={14} className={`shrink-0 ${isGroup ? 'text-brand-green-hover dark:text-brand-green' : 'text-[#8b5cf6]'}`} />
      <span className="flex-1 min-w-0">
        <span className="flex items-center gap-1.5 min-w-0">
          <span className="text-[12px] text-text-main truncate" title={item.name}>{item.name}</span>
          {!item.known && (
            <span className="shrink-0 px-1 py-px rounded border border-[#c37d0d]/25 bg-[#c37d0d]/10 text-[10px] leading-4 text-[#a06a0a]">
              不在通讯录
            </span>
          )}
          {item.active === false && item.known && (
            <span className="shrink-0 px-1 py-px rounded border border-[#c37d0d]/25 bg-[#c37d0d]/10 text-[10px] leading-4 text-[#a06a0a]">
              已失效
            </span>
          )}
        </span>
        {item.sub && (
          <span className="block truncate text-[10.5px] font-mono text-text-muted/80" title={item.sub}>
            {item.sub}
          </span>
        )}
      </span>
      <button
        type="button"
        disabled={disabled}
        onClick={(e) => { e.stopPropagation(); onMove() }}
        onDoubleClick={(e) => e.stopPropagation()}
        title={direction === 'right' ? '移入当前分组' : '移出当前分组'}
        className="shrink-0 p-0.5 rounded-md text-text-muted/50 opacity-0 group-hover:opacity-100 hover:text-brand-green-hover transition-all cursor-pointer disabled:cursor-not-allowed"
      >
        <MoveIcon size={13} weight="bold" />
      </button>
    </div>
  )
}

export default function BroadcastGroupsPanel() {
  const [groups, setGroups] = useState([])
  const [options, setOptions] = useState({ groups: [], friends: [] })
  const [activeName, setActiveName] = useState('')
  const [tab, setTab] = useState('friend')
  const [query, setQuery] = useState('')
  const [leftChecked, setLeftChecked] = useState(() => new Set())
  const [rightChecked, setRightChecked] = useState(() => new Set())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [dirty, setDirty] = useState(false)
  const [newName, setNewName] = useState('')
  const [editingName, setEditingName] = useState('')
  const [renameValue, setRenameValue] = useState('')

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    setError('')
    try {
      const res = await fetch(apiUrl('/api/broadcast/groups'))
      const data = await res.json()
      if (!data.ok) throw new Error(data.error || '加载分组失败')
      const list = Array.isArray(data.groups) ? data.groups : []
      setGroups(list)
      setOptions(data.options || { groups: [], friends: [] })
      setActiveName((prev) =>
        prev && list.some((g) => g.name === prev) ? prev : (list[0]?.name || '')
      )
      setDirty(false)
    } catch (e) {
      setError(friendlyError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // 全部候选：群聊 / 好友统一成 {type, id, name, sub, active}
  const candidates = useMemo(() => [
    ...(options.groups || []).map((g) => ({
      type: 'group',
      id: String(g.chat_id || ''),
      name: String(g.name || g.chat_id || ''),
      sub: String(g.chat_id || ''),
      active: g.active !== false,
    })),
    ...(options.friends || []).map((f) => ({
      type: 'friend',
      id: String(f.wxid || ''),
      name: String(f.name || f.wxid || ''),
      sub: [f.alias, f.wxid].filter(Boolean).join(' · '),
      active: f.active !== false,
    })),
  ].filter((c) => c.id), [options])

  const candidateMap = useMemo(
    () => new Map(candidates.map((c) => [targetKey(c), c])),
    [candidates]
  )

  const activeGroup = groups.find((g) => g.name === activeName) || null
  const selectedKeys = useMemo(
    () => new Set((activeGroup?.targets || []).map(targetKey)),
    [activeGroup]
  )

  // 已选目标补上通讯录里的展示信息；不在通讯录里的仍保留，标记为失效
  const selectedItems = useMemo(() => (activeGroup?.targets || []).map((t) => {
    const c = candidateMap.get(targetKey(t))
    return {
      type: t.type, id: t.id,
      name: t.name || c?.name || t.id,
      sub: c?.sub || t.id,
      known: !!c,
      active: c ? c.active !== false : false,
    }
  }), [activeGroup, candidateMap])

  const friendCount = selectedItems.filter((t) => t.type === 'friend').length
  const groupCount = selectedItems.filter((t) => t.type === 'group').length
  const rightItems = selectedItems.filter((t) => t.type === tab)
  const q = query.trim().toLowerCase()
  const leftItems = candidates.filter((c) => {
    if (c.type !== tab || selectedKeys.has(targetKey(c))) return false
    if (!q) return true
    return `${c.name} ${c.sub} ${c.id}`.toLowerCase().includes(q)
  })
  const tabCandidates = candidates.filter((c) => c.type === tab)

  const leftVisibleKeys = leftItems.map(targetKey)
  const rightVisibleKeys = rightItems.map(targetKey)
  const leftCheckedVisible = leftVisibleKeys.filter((k) => leftChecked.has(k))
  const rightCheckedVisible = rightVisibleKeys.filter((k) => rightChecked.has(k))
  const allLeftChecked = leftVisibleKeys.length > 0
    && leftCheckedVisible.length === leftVisibleKeys.length

  const mutate = (updater) => {
    setGroups(updater)
    setDirty(true)
    setNotice('')
    setError('')
  }
  const updateActive = (fn) =>
    mutate((prev) => prev.map((g) => (g.name === activeName ? fn(g) : g)))

  const addGroup = () => {
    const name = newName.trim()
    if (!name) return
    if (groups.some((g) => g.name === name)) {
      setError('分组名已存在，请换一个')
      return
    }
    mutate((prev) => [...prev, { name, targets: [] }])
    setActiveName(name)
    setNewName('')
    setLeftChecked(new Set())
    setRightChecked(new Set())
  }

  const removeGroup = (name) => {
    const rest = groups.filter((g) => g.name !== name)
    mutate(() => rest)
    if (activeName === name) setActiveName(rest[0]?.name || '')
    if (editingName === name) setEditingName('')
    setLeftChecked(new Set())
    setRightChecked(new Set())
  }

  const commitRename = () => {
    const next = renameValue.trim()
    const old = editingName
    setEditingName('')
    if (!next || next === old) return
    if (groups.some((g) => g.name === next)) {
      setError('分组名已存在，请换一个')
      return
    }
    mutate((prev) => prev.map((g) => (g.name === old ? { ...g, name: next } : g)))
    if (activeName === old) setActiveName(next)
  }

  const toggleChecked = (setter, key) => setter((prev) => {
    const next = new Set(prev)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return next
  })

  const moveRight = (keys) => {
    if (!activeGroup || !keys.length) return
    const picked = keys.map((k) => candidateMap.get(k)).filter(Boolean)
    if (!picked.length) return
    if ((activeGroup.targets || []).length + picked.length > MAX_TARGETS) {
      setError(`单个分组最多 ${MAX_TARGETS} 个目标`)
      return
    }
    updateActive((g) => {
      const existing = new Set((g.targets || []).map(targetKey))
      const additions = picked
        .filter((p) => !existing.has(targetKey(p)))
        .map((p) => ({ type: p.type, id: p.id, name: p.name }))
      return { ...g, targets: [...(g.targets || []), ...additions] }
    })
    setLeftChecked((prev) => {
      const next = new Set(prev)
      keys.forEach((k) => next.delete(k))
      return next
    })
  }

  const moveLeft = (keys) => {
    if (!activeGroup || !keys.length) return
    const removing = new Set(keys)
    updateActive((g) => ({
      ...g,
      targets: (g.targets || []).filter((t) => !removing.has(targetKey(t))),
    }))
    setRightChecked((prev) => {
      const next = new Set(prev)
      keys.forEach((k) => next.delete(k))
      return next
    })
  }

  const clearCurrentTab = () => {
    if (!activeGroup) return
    updateActive((g) => ({
      ...g,
      targets: (g.targets || []).filter((t) => t.type !== tab),
    }))
    setRightChecked(new Set())
  }

  const switchGroup = (name) => {
    setActiveName(name)
    setQuery('')
    setLeftChecked(new Set())
    setRightChecked(new Set())
  }

  const save = async () => {
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const res = await fetch(apiUrl('/api/broadcast/groups'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ groups }),
      })
      const data = await res.json()
      if (!data.ok) throw new Error(data.error || '保存失败')
      setGroups(data.groups || groups)
      setActiveName((prev) =>
        prev && (data.groups || []).some((g) => g.name === prev)
          ? prev : (data.groups?.[0]?.name || '')
      )
      setDirty(false)
      setNotice('分组已保存，智能体下次调用立即生效')
    } catch (e) {
      setError(friendlyError(e))
    } finally {
      setSaving(false)
    }
  }

  const syncContacts = async () => {
    setSyncing(true)
    setError('')
    try {
      const res = await fetch(apiUrl('/api/wechat/sync'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      await load(true)
    } catch (e) {
      setError(`同步通讯录失败：${friendlyError(e)}`)
    } finally {
      setSyncing(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        <Spinner size={20} className="animate-spin text-brand-green mr-3" />
        <span className="text-xs font-mono">正在加载群发分组...</span>
      </div>
    )
  }

  const arrowClass = 'w-9 h-9 rounded-full flex items-center justify-center border transition-all duration-200 cursor-pointer shrink-0 ' +
    'border-border-main bg-bg-card text-text-main hover:text-white hover:border-transparent hover:bg-[#4C9B72] active:scale-95 ' +
    'disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:text-text-main disabled:hover:border-border-main disabled:hover:bg-bg-card'
  const paneClass = 'flex flex-col min-h-0 rounded-xl border border-border-main bg-bg-raised overflow-hidden'
  const disabled = !activeGroup

  return (
    <div className="space-y-4" data-testid="broadcast-groups-panel">
      <div className="rounded-xl border border-border-main bg-bg-raised px-4 py-3 leading-relaxed">
        <p className="text-[12px] text-text-main font-semibold mb-1">系统群发分组</p>
        <p className="text-[11px] text-text-muted">
          左侧选中一个分组，右侧把<strong className="text-text-main">好友或群聊</strong>移入即成为该分组成员；
          一个分组可同时包含两类目标。供 MCP 的{' '}
          <code className="font-mono text-brand-green-hover dark:text-brand-green">batch_send_messages</code> 按分组名调用，
          配置存在 <code className="font-mono">broadcast_groups.json</code>，保存后立即生效，无需重启。
        </p>
        <p className="text-[11px] text-text-muted mt-1.5 flex items-start gap-1.5">
          <Info size={13} className="shrink-0 mt-0.5 text-brand-green" />
          这是 WeChatBot 自己的分组，与微信自带的通讯录标签<strong className="text-text-main">完全独立</strong>，
          不会读取、导入或同步微信标签。查看微信标签请用侧边栏「通讯录标签」。
        </p>
      </div>

      {error && (
        <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-[#d45656]/10 border border-[#d45656]/25 text-[11.5px] text-[#d45656]">
          <WarningCircle size={14} className="shrink-0 mt-0.5" /><span>{error}</span>
        </div>
      )}
      {notice && (
        <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-brand-green/10 border border-brand-green/25 text-[11.5px] text-brand-green-hover dark:text-brand-green">
          <CheckCircle size={14} className="shrink-0 mt-0.5" /><span>{notice}</span>
        </div>
      )}

      <div className="bg-bg-card border border-border-main rounded-2xl shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none p-5">
        <div className="flex items-center gap-2.5 mb-4 pl-1">
          <div className="w-1.5 h-4 rounded-full" style={{ backgroundColor: ACCENT }} />
          <h4 className="text-[12.5px] font-semibold tracking-tight text-text-main">选择目标</h4>
          <span className="text-[11px] text-text-muted">
            {activeGroup
              ? `当前编辑「${activeGroup.name}」· 共 ${selectedItems.length} 个目标（好友 ${friendCount} / 群聊 ${groupCount}）`
              : '请先在左侧新建一个分组'}
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)] gap-3 lg:h-[470px]">
          {/* ── 最左：分组列表 ───────────────────────────────────── */}
          <aside className={`${paneClass} max-h-[240px] lg:max-h-none`}>
            <div className="flex items-center justify-between gap-2 px-3 h-9 shrink-0 border-b border-border-main/70">
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-[12.5px] font-semibold text-text-main">分组</span>
                <span className="px-1.5 py-px rounded-full bg-bg-card border border-border-main text-[10px] font-mono text-text-muted">
                  {groups.length}
                </span>
              </div>
              <span className="text-[10.5px] text-text-muted">选中后编辑</span>
            </div>
            <div className="p-2.5 border-b border-border-main/70 flex gap-1.5 shrink-0">
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') addGroup() }}
                placeholder="新建分组名"
                className="flex-1 min-w-0 bg-bg-main border border-border-main rounded-lg px-2.5 py-1.5 text-[11.5px] text-text-main placeholder:text-text-muted/60 focus:outline-none focus:border-brand-green/50"
              />
              <button
                type="button" onClick={addGroup} title="新建分组"
                className="shrink-0 w-8 h-8 flex items-center justify-center rounded-lg bg-brand-green-light text-brand-green-hover dark:text-brand-green hover:opacity-80 transition-opacity cursor-pointer"
              ><Plus size={15} weight="bold" /></button>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto p-1.5 space-y-0.5">
              {groups.length === 0 && (
                <p className="text-[11px] text-text-muted text-center py-8 leading-relaxed">
                  还没有分组<br />在上方输入名称后回车新建
                </p>
              )}
              {groups.map((g) => {
                const selected = g.name === activeName
                const isEditing = editingName === g.name
                return (
                  <div
                    key={g.name}
                    data-testid="broadcast-group-row"
                    data-group-name={g.name}
                    className={`group flex items-center gap-1.5 rounded-lg px-2 py-1.5 transition-colors ${
                      selected ? 'bg-brand-green-light' : 'hover:bg-bg-card'
                    }`}
                  >
                    {isEditing ? (
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onBlur={commitRename}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') commitRename()
                          if (e.key === 'Escape') setEditingName('')
                        }}
                        className="flex-1 min-w-0 bg-bg-main border border-brand-green/40 rounded px-1.5 py-1 text-[11.5px] text-text-main focus:outline-none"
                      />
                    ) : (
                      <button
                        type="button" onClick={() => switchGroup(g.name)}
                        className="flex-1 min-w-0 text-left cursor-pointer"
                      >
                        <span className={`block truncate text-[11.5px] font-medium ${selected ? 'text-brand-green-hover dark:text-brand-green' : 'text-text-main'}`}>
                          {g.name}
                        </span>
                        <span className="block text-[10px] font-mono text-text-muted">
                          {(g.targets || []).length} 个目标
                        </span>
                      </button>
                    )}
                    <button
                      type="button" title="重命名"
                      onClick={() => { setEditingName(g.name); setRenameValue(g.name) }}
                      className="opacity-0 group-hover:opacity-100 p-1 text-text-muted hover:text-text-main transition-all cursor-pointer"
                    ><PencilSimple size={12} /></button>
                    <button
                      type="button" title="删除分组" onClick={() => removeGroup(g.name)}
                      className="opacity-0 group-hover:opacity-100 p-1 text-text-muted hover:text-[#d45656] transition-all cursor-pointer"
                    ><Trash size={12} /></button>
                  </div>
                )
              })}
            </div>
          </aside>

          {/* ── 右侧：Tab + 穿梭选择 ─────────────────────────────── */}
          <section className="flex flex-col min-w-0 min-h-0 gap-2.5">
            <div className="flex items-center gap-2 h-9 shrink-0">
              <div className="flex items-center gap-0.5 bg-bg-main border border-border-main rounded-full p-0.5">
                {TABS.map(({ id, label, icon: Icon }) => (
                  <button
                    key={id} type="button" onClick={() => setTab(id)}
                    data-testid={`broadcast-tab-${id}`}
                    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11.5px] font-semibold transition-colors cursor-pointer ${
                      tab === id
                        ? 'bg-brand-green-light text-brand-green-hover dark:text-brand-green'
                        : 'text-text-muted hover:text-text-main'
                    }`}
                  >
                    <Icon size={13} />
                    {label}
                    <span className="font-mono text-[10px] opacity-80">
                      {id === 'friend' ? friendCount : groupCount}
                    </span>
                  </button>
                ))}
              </div>
              <span className="text-[10.5px] text-text-muted truncate ml-auto">
                Tab 只切换编辑视图，好友和群聊会一起保存
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_44px_minmax(0,1fr)] gap-3 flex-1 min-h-0 h-[400px] lg:h-auto">
              {/* 候选池 */}
              <div className={paneClass}>
                <div className="flex items-center justify-between gap-2 px-3 h-10 shrink-0 border-b border-border-main/70">
                  <div className="flex items-center gap-1.5 min-w-0">
                    {tab === 'group'
                      ? <ChatCircleDots size={15} className="text-brand-green-hover dark:text-brand-green shrink-0" />
                      : <Users size={15} className="text-[#8b5cf6] shrink-0" />}
                    <span className="text-[12.5px] font-semibold text-text-main truncate">
                      全部{tab === 'group' ? '群聊' : '好友'}
                    </span>
                    <span className="px-1.5 py-px rounded-full bg-bg-card border border-border-main text-[10px] font-mono text-text-muted shrink-0">
                      {tabCandidates.length}
                    </span>
                  </div>
                  <button
                    type="button" onClick={syncContacts} disabled={syncing}
                    title="同步微信通讯录"
                    className="p-1.5 rounded-lg text-text-muted hover:text-text-main hover:bg-bg-card transition-colors cursor-pointer disabled:opacity-50"
                  >
                    <ArrowClockwise size={14} weight="bold" className={syncing ? 'animate-spin' : ''} />
                  </button>
                </div>

                <div className="flex items-center gap-1.5 px-2.5 h-9 shrink-0 border-b border-border-main/70">
                  <MagnifyingGlass size={14} className="text-text-muted/70 shrink-0" />
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder={`搜索${tab === 'group' ? '群名' : '昵称、备注'}或 ID`}
                    className="flex-1 min-w-0 bg-transparent text-[12px] text-text-main placeholder:text-text-muted/60 focus:outline-none"
                  />
                  {query && (
                    <button type="button" onClick={() => setQuery('')} title="清空搜索" className="text-text-muted/70 hover:text-text-main cursor-pointer">
                      <X size={12} weight="bold" />
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-2.5 px-2.5 h-8 shrink-0 border-b border-border-main/70 text-[11px]">
                  <button
                    type="button"
                    onClick={() => setLeftChecked(new Set(allLeftChecked ? [] : leftVisibleKeys))}
                    disabled={disabled || leftVisibleKeys.length === 0}
                    className="text-brand-green-hover dark:text-brand-green hover:opacity-75 transition-opacity cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                  >{allLeftChecked ? '取消全选' : '全选'}</button>
                  <button
                    type="button" onClick={() => setLeftChecked(new Set())}
                    disabled={disabled || leftCheckedVisible.length === 0}
                    className="text-text-muted hover:text-text-main transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                  >清空勾选</button>
                  <span className="ml-auto font-mono text-[10.5px] text-text-muted/80">
                    {leftCheckedVisible.length > 0 ? `已勾选 ${leftCheckedVisible.length}` : '双击可移入'}
                  </span>
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto p-1.5">
                  {leftItems.length === 0 ? (
                    <p className="px-2.5 py-3 text-[11.5px] text-text-muted leading-relaxed">
                      {tabCandidates.length === 0
                        ? `暂无${tab === 'group' ? '群聊' : '好友'}列表：启动一次机器人或点击右上角同步通讯录。`
                        : q ? '没有匹配的目标' : `全部${tab === 'group' ? '群聊' : '好友'}都已在当前分组中`}
                    </p>
                  ) : leftItems.map((c) => {
                    const key = targetKey(c)
                    return (
                      <TargetRow
                        key={key}
                        item={{ ...c, known: true }}
                        checked={leftChecked.has(key)}
                        direction="right"
                        disabled={disabled}
                        onToggle={() => toggleChecked(setLeftChecked, key)}
                        onMove={() => moveRight([key])}
                      />
                    )
                  })}
                </div>
              </div>

              {/* 中间箭头 */}
              <div className="hidden sm:flex flex-col items-center justify-center gap-3">
                <button
                  type="button" onClick={() => moveRight(leftCheckedVisible)}
                  disabled={disabled || leftCheckedVisible.length === 0}
                  title="将勾选目标移入当前分组" className={arrowClass}
                ><ArrowRight size={16} weight="bold" /></button>
                <button
                  type="button" onClick={() => moveLeft(rightCheckedVisible)}
                  disabled={disabled || rightCheckedVisible.length === 0}
                  title="将勾选目标移出当前分组" className={arrowClass}
                ><ArrowLeft size={16} weight="bold" /></button>
              </div>

              {/* 当前分组成员 */}
              <div className={paneClass}>
                <div className="flex items-center justify-between gap-2 px-3 h-10 shrink-0 border-b border-border-main/70">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <CheckCircle size={15} className="text-brand-green-hover dark:text-brand-green shrink-0" />
                    <span className="text-[12.5px] font-semibold text-text-main truncate">
                      {activeGroup ? `「${activeGroup.name}」` : '当前分组'}
                    </span>
                    <span
                      data-testid="broadcast-selected-count"
                      className="px-1.5 py-px rounded-full bg-brand-green-light border border-brand-green/20 text-[10px] font-mono text-brand-green-hover dark:text-brand-green shrink-0"
                    >
                      {rightItems.length}
                    </span>
                  </div>
                  <button
                    type="button" onClick={clearCurrentTab}
                    disabled={disabled || rightItems.length === 0}
                    className="text-[11px] text-text-muted hover:text-[#d45656] transition-colors cursor-pointer disabled:opacity-35 disabled:cursor-not-allowed"
                  >清空{tab === 'group' ? '群聊' : '好友'}</button>
                </div>

                <div className="flex items-center gap-2 px-2.5 h-9 shrink-0 border-b border-border-main/70 text-[11px] text-text-muted">
                  <span className="truncate">
                    {disabled
                      ? '请先在左侧新建或选择一个分组'
                      : rightItems.length > 0
                        ? `这里${tab === 'group' ? '的群聊' : '的好友'}属于该分组`
                        : '从左侧勾选后点击 → 移入'}
                  </span>
                  {rightCheckedVisible.length > 0 && (
                    <span className="ml-auto font-mono text-[10.5px] shrink-0">
                      已勾选 {rightCheckedVisible.length}
                    </span>
                  )}
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto p-1.5">
                  {rightItems.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center gap-2 px-4 text-center">
                      {tab === 'group'
                        ? <ChatCircleDots size={26} className="text-text-muted/25" />
                        : <Users size={26} className="text-text-muted/25" />}
                      <p className="text-[11.5px] text-text-muted/80 leading-relaxed">
                        {disabled ? '还没有选中分组' : '该分组下暂无此类目标'}<br />
                        {disabled ? '在左侧新建后即可添加' : '从左侧勾选并点击 → 移入'}
                      </p>
                    </div>
                  ) : rightItems.map((t) => {
                    const key = targetKey(t)
                    return (
                      <TargetRow
                        key={key}
                        item={t}
                        checked={rightChecked.has(key)}
                        direction="left"
                        disabled={disabled}
                        onToggle={() => toggleChecked(setRightChecked, key)}
                        onMove={() => moveLeft([key])}
                      />
                    )
                  })}
                </div>
              </div>
            </div>
          </section>
        </div>

        <p className="text-[11px] text-text-muted mt-2.5">
          候选列表来自最近一次机器人同步；新增好友/群聊后请点候选池右上角刷新。
          标记「不在通讯录」的目标是历史残留，仍会保留在分组里，可勾选后移出。
        </p>
      </div>

      <div className="flex items-center gap-3 pt-1">
        <motion.button
          type="button" whileTap={{ scale: 0.97 }} onClick={save}
          disabled={saving || !dirty}
          className="px-6 py-2.5 rounded-full text-[12.5px] font-semibold bg-[#0d0d0d] dark:bg-white text-white dark:text-[#0d0d0d] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        >
          {saving ? '保存中...' : dirty ? '保存分组' : '已保存'}
        </motion.button>
        {dirty && <span className="text-[11px] text-[#c37d0d]">有未保存的修改</span>}
        <span className="text-[11px] text-text-muted ml-auto">
          智能体调用 <code className="font-mono">{`batch_send_messages({"group": "分组名"})`}</code>
        </span>
      </div>
    </div>
  )
}
