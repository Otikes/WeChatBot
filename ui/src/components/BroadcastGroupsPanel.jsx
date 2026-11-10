import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  ArrowClockwise, Check, CheckCircle, ChatCircleDots, Info, MagnifyingGlass,
  PencilSimple, Plus, Spinner, Trash, Users, WarningCircle, X,
} from '@phosphor-icons/react'
import { friendlyError } from './SharedComponents'

function apiUrl(path) {
  if (window.location.port === '5173') return `http://127.0.0.1:7327${path}`
  return path
}

const targetKey = (item) => `${item.type}:${item.id}`

export default function BroadcastGroupsPanel() {
  const [groups, setGroups] = useState([])
  const [options, setOptions] = useState({ groups: [], friends: [] })
  const [activeName, setActiveName] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [dirty, setDirty] = useState(false)
  const [query, setQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
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

  const candidates = useMemo(() => {
    const all = [
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
    ]
    return all.filter((c) => c.id)
  }, [options])

  const activeGroup = groups.find((g) => g.name === activeName) || null
  const selectedKeys = useMemo(
    () => new Set((activeGroup?.targets || []).map(targetKey)),
    [activeGroup]
  )

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return candidates.filter((c) => {
      if (typeFilter !== 'all' && c.type !== typeFilter) return false
      if (!q) return true
      return `${c.name} ${c.sub} ${c.id}`.toLowerCase().includes(q)
    })
  }, [candidates, query, typeFilter])

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
  }

  const removeGroup = (name) => {
    const rest = groups.filter((g) => g.name !== name)
    mutate(() => rest)
    if (activeName === name) setActiveName(rest[0]?.name || '')
    if (editingName === name) setEditingName('')
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

  const toggleTarget = (candidate) => {
    if (!activeGroup) return
    const key = targetKey(candidate)
    const exists = selectedKeys.has(key)
    updateActive((g) => ({
      ...g,
      targets: exists
        ? (g.targets || []).filter((t) => targetKey(t) !== key)
        : [...(g.targets || []), {
            type: candidate.type, id: candidate.id, name: candidate.name,
          }],
    }))
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

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-border-main bg-bg-raised px-4 py-3.5 leading-relaxed">
        <p className="text-[12px] text-text-main font-semibold mb-1">系统群发分组</p>
        <p className="text-[11px] text-text-muted">
          一个分组里可以同时放<strong className="text-text-main">好友和群聊</strong>，
          供 MCP 的 <code className="font-mono text-brand-green-hover dark:text-brand-green">batch_send_messages</code> 按分组名调用。
          配置存在数据目录 <code className="font-mono">broadcast_groups.json</code>，保存后立即生效，无需重启。
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

      <div className="grid grid-cols-1 lg:grid-cols-[230px_1fr] gap-4">
        {/* 左：分组列表 */}
        <div className="rounded-xl border border-border-main bg-bg-card overflow-hidden flex flex-col">
          <div className="flex items-center justify-between px-3 h-10 border-b border-border-main/70 shrink-0">
            <span className="text-[11.5px] font-semibold text-text-main">分组</span>
            <span className="font-mono text-[10px] text-text-muted">{groups.length}</span>
          </div>
          <div className="p-2.5 border-b border-border-main/70 flex gap-1.5">
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
          <div className="flex-1 overflow-y-auto max-h-[360px] p-1.5 space-y-0.5">
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
                  className={`group flex items-center gap-1.5 rounded-lg px-2 py-1.5 transition-colors ${
                    selected ? 'bg-brand-green-light' : 'hover:bg-bg-raised'
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
                      type="button" onClick={() => setActiveName(g.name)}
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
                    type="button"
                    title="重命名"
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
        </div>

        {/* 右：目标编辑 */}
        <div className="space-y-4 min-w-0">
          <div className="rounded-xl border border-border-main bg-bg-card overflow-hidden">
            <div className="flex items-center gap-2 px-3.5 h-10 border-b border-border-main/70">
              <span className="text-[11.5px] font-semibold text-text-main">
                {activeGroup ? `「${activeGroup.name}」的目标` : '当前分组'}
              </span>
              <span className="font-mono text-[10px] text-text-muted">
                {(activeGroup?.targets || []).length}
              </span>
              {activeGroup && (activeGroup.targets || []).length > 0 && (
                <button
                  type="button"
                  onClick={() => updateActive((g) => ({ ...g, targets: [] }))}
                  className="ml-auto text-[10.5px] text-text-muted hover:text-[#d45656] transition-colors cursor-pointer"
                >清空</button>
              )}
            </div>
            <div className="p-3 min-h-[76px] max-h-[150px] overflow-y-auto">
              {!activeGroup ? (
                <p className="text-[11px] text-text-muted py-4 text-center">请先在左侧新建或选择一个分组</p>
              ) : (activeGroup.targets || []).length === 0 ? (
                <p className="text-[11px] text-text-muted py-4 text-center">从下方候选列表点击添加好友或群聊</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {activeGroup.targets.map((t) => (
                    <span
                      key={targetKey(t)}
                      className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-bg-raised border border-border-main text-[11px] text-text-main"
                    >
                      {t.type === 'group'
                        ? <ChatCircleDots size={12} className="text-brand-green" />
                        : <Users size={12} className="text-[#8b5cf6]" />}
                      <span className="max-w-[160px] truncate">{t.name || t.id}</span>
                      <span className="text-[9.5px] font-mono text-text-muted">
                        {t.type === 'group' ? '群' : '好友'}
                      </span>
                      <button
                        type="button" title="移除"
                        onClick={() => updateActive((g) => ({
                          ...g, targets: g.targets.filter((x) => targetKey(x) !== targetKey(t)),
                        }))}
                        className="text-text-muted hover:text-[#d45656] cursor-pointer"
                      ><X size={11} weight="bold" /></button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-border-main bg-bg-card overflow-hidden">
            <div className="flex items-center gap-2 px-3.5 h-10 border-b border-border-main/70">
              <span className="text-[11.5px] font-semibold text-text-main">添加目标</span>
              <span className="font-mono text-[10px] text-text-muted">{filtered.length}</span>
              <button
                type="button" onClick={syncContacts} disabled={syncing}
                className="ml-auto inline-flex items-center gap-1 text-[10.5px] text-text-muted hover:text-text-main transition-colors cursor-pointer disabled:opacity-50"
              >
                <ArrowClockwise size={12} className={syncing ? 'animate-spin' : ''} />
                {syncing ? '同步中' : '同步微信通讯录'}
              </button>
            </div>
            <div className="flex items-center gap-2 px-3.5 py-2 border-b border-border-main/70">
              <div className="flex items-center gap-0.5 bg-bg-main border border-border-main rounded-full p-0.5 shrink-0">
                {[
                  { id: 'all', label: '全部' }, { id: 'friend', label: '好友' }, { id: 'group', label: '群聊' },
                ].map((tab) => (
                  <button
                    key={tab.id} type="button" onClick={() => setTypeFilter(tab.id)}
                    className={`px-2.5 py-1 rounded-full text-[10.5px] font-semibold transition-colors cursor-pointer ${
                      typeFilter === tab.id
                        ? 'bg-brand-green-light text-brand-green-hover dark:text-brand-green'
                        : 'text-text-muted hover:text-text-main'
                    }`}
                  >{tab.label}</button>
                ))}
              </div>
              <div className="flex items-center gap-1.5 flex-1 min-w-0">
                <MagnifyingGlass size={13} className="text-text-muted/70 shrink-0" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索群名、昵称、备注或 ID"
                  className="flex-1 min-w-0 bg-transparent text-[11.5px] text-text-main placeholder:text-text-muted/60 focus:outline-none"
                />
                {query && (
                  <button type="button" onClick={() => setQuery('')} className="text-text-muted cursor-pointer">
                    <X size={12} weight="bold" />
                  </button>
                )}
              </div>
            </div>
            <div className="max-h-[260px] overflow-y-auto">
              {filtered.length === 0 ? (
                <p className="text-[11px] text-text-muted text-center py-8">
                  没有匹配的联系人，可先点「同步微信通讯录」
                </p>
              ) : filtered.map((c) => {
                const key = targetKey(c)
                const picked = selectedKeys.has(key)
                return (
                  <button
                    key={key} type="button" onClick={() => toggleTarget(c)} disabled={!activeGroup}
                    className={`w-full flex items-center gap-2.5 px-3.5 py-2 border-b border-border-main/50 last:border-b-0 text-left transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
                      picked ? 'bg-brand-green/5' : 'hover:bg-bg-raised'
                    }`}
                  >
                    <span className={`shrink-0 w-4 h-4 rounded flex items-center justify-center border ${
                      picked ? 'bg-brand-green border-brand-green text-[#0d0d0d]' : 'border-border-main'
                    }`}>
                      {picked && <Check size={10} weight="bold" />}
                    </span>
                    {c.type === 'group'
                      ? <ChatCircleDots size={14} className="shrink-0 text-brand-green" />
                      : <Users size={14} className="shrink-0 text-[#8b5cf6]" />}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[11.5px] text-text-main">{c.name}</span>
                      <span className="block truncate text-[10px] font-mono text-text-muted">{c.sub}</span>
                    </span>
                    <span className="shrink-0 text-[9.5px] font-mono text-text-muted">
                      {c.type === 'group' ? '群' : '好友'}
                    </span>
                    {!c.active && (
                      <span className="shrink-0 text-[9.5px] text-[#c37d0d]">已失效</span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
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
