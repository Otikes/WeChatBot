import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowLeft, ArrowRight, ArrowClockwise, Check, CheckCircle, FloppyDisk,
  Info, MagnifyingGlass, PencilSimple, Spinner, Users, UsersThree,
  Warning, X,
} from '@phosphor-icons/react'
import { Field, friendlyError } from './SharedComponents'

const API = 'http://127.0.0.1:7327'
const ACCENT = '#4C9B72'

/** 选框（与好友私聊面板保持一致的视觉） */
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

export default function GroupChatPanel() {
  // ── 群聊名单（参与群聊，对应 .env 的 WECHAT_GROUPS） ──────────────
  const [groups, setGroups] = useState([])
  const [raw, setRaw] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState('')

  // 左右两栏的勾选状态（点击中间箭头后才会真正移动）
  const [leftChecked, setLeftChecked] = useState(() => new Set())
  const [rightChecked, setRightChecked] = useState(() => new Set())

  // ── 群成员备注弹窗 ───────────────────────────────────────────────
  // remarkGroup 为 null 表示弹窗关闭；否则为 { chat_id, group_name }
  const [remarkGroup, setRemarkGroup] = useState(null)
  const [members, setMembers] = useState([])
  const [membersLoading, setMembersLoading] = useState(false)
  const [membersError, setMembersError] = useState('')
  const [memberQuery, setMemberQuery] = useState('')
  const [editingWxid, setEditingWxid] = useState(null)
  const [draft, setDraft] = useState('')
  const [savingWxid, setSavingWxid] = useState(null)
  const [savedWxid, setSavedWxid] = useState(null)
  // 用 ref 同步记录「当前正在编辑的成员」，避免 Enter / Esc / blur 互相干扰
  const editingRef = useRef(null)

  /** 加载群列表与当前 WECHAT_GROUPS 配置 */
  async function loadAll() {
    setLoading(true)
    setLoadError('')
    try {
      const [groupsRes, configRes] = await Promise.all([
        fetch(`${API}/api/groups`),
        fetch(`${API}/api/load-config`),
      ])
      const groupsData = await groupsRes.json()
      const configData = await configRes.json()
      if (!groupsData.ok) throw new Error(groupsData.error || '群列表加载失败')
      if (!configData.ok) throw new Error(configData.error || '配置加载失败')

      const nextGroups = groupsData.groups || []
      setGroups(nextGroups)
      setRaw(configData.config?.wechat_groups || '')
      setLeftChecked(new Set())
      setRightChecked(new Set())
    } catch (e) {
      setLoadError(friendlyError(e, '群聊列表加载失败'))
    }
    setLoading(false)
  }

  useEffect(() => { loadAll() }, [])

  // 仅刷新群列表，不影响尚未保存的勾选结果
  async function refreshGroups() {
    setLoading(true)
    setLoadError('')
    try {
      const res = await fetch(`${API}/api/groups`)
      const data = await res.json()
      if (!data.ok) throw new Error(data.error || '群列表加载失败')
      setGroups(data.groups || [])
    } catch (e) {
      setLoadError(friendlyError(e, '群列表加载失败'))
    }
    setLoading(false)
  }

  // 弹窗打开时支持 Esc 关闭，并锁定页面滚动
  useEffect(() => {
    if (!remarkGroup) return
    const onKeyDown = e => {
      if (e.key === 'Escape' && !editingRef.current) setRemarkGroup(null)
    }
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = prevOverflow
    }
  }, [remarkGroup])

  // 打开备注弹窗时重置编辑状态
  useEffect(() => {
    editingRef.current = null
    setEditingWxid(null)
    setDraft('')
    setMembersError('')
    setMemberQuery('')
  }, [remarkGroup])

  // ── 群聊名单的派生数据 ───────────────────────────────────────────
  const groupNameOf = (g) => g.group_name || g.chat_id

  /**
   * 把 .env 中保存的条目（群名或 @chatroom ID）解析为右栏条目。
   * 每条记录保留原始写入值 value，便于原样保存未知/历史条目。
   */
  function resolveSelected(allGroups, rawValue) {
    const isWildcard = (rawValue || '').trim() === '*'
    const values = isWildcard
      ? allGroups.map(groupNameOf)
      : (rawValue || '').split(',').map(s => {
          const trimmed = s.trim()
          if (!trimmed) return ''
          try { return decodeURIComponent(trimmed) } catch { return trimmed }
        }).filter(Boolean)

    const entries = []
    const usedKeys = new Set()
    values.forEach(v => {
      const group = allGroups.find(g => groupNameOf(g) === v || g.chat_id === v)
      const key = group ? group.chat_id : v
      if (usedKeys.has(key)) return
      usedKeys.add(key)
      entries.push({ key, value: group ? groupNameOf(group) : v, group: group || null })
    })
    return entries
  }

  const selectedEntries = resolveSelected(groups, raw)
  const selectedKeys = new Set(selectedEntries.map(e => e.key))

  /** 写回名单：统一保存为 URL 编码的群名列表；空表示不监控任何群 */
  function setSelection(values) {
    const unique = [...new Set(values.filter(Boolean))]
    setRaw(unique.length ? unique.map(v => encodeURIComponent(v)).join(',') : '')
    setSaved(false)
    setSaveError('')
  }

  function toggleChecked(setter, key) {
    setter(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  function moveRight(groupList) {
    if (!groupList.length) return
    setSelection([...selectedEntries.map(e => e.value), ...groupList.map(groupNameOf)])
    setLeftChecked(prev => {
      const next = new Set(prev)
      groupList.forEach(g => next.delete(g.chat_id))
      return next
    })
  }

  function moveLeft(keys) {
    const valid = keys.filter(Boolean)
    if (!valid.length) return
    setSelection(selectedEntries.filter(e => !valid.includes(e.key)).map(e => e.value))
    setRightChecked(prev => {
      const next = new Set(prev)
      valid.forEach(k => next.delete(k))
      return next
    })
  }

  // 左栏：未被选中的群 + 搜索过滤
  const q = query.trim().toLowerCase()
  const leftGroups = groups
    .filter(g => {
      if (selectedKeys.has(g.chat_id)) return false
      if (!q) return true
      return (g.group_name || '').toLowerCase().includes(q)
        || (g.chat_id || '').toLowerCase().includes(q)
    })
    // 已退出的群排在最后，但仍保留展示
    .sort((a, b) => (a.active === false ? 1 : 0) - (b.active === false ? 1 : 0))

  const leftVisibleKeys = leftGroups.map(g => g.chat_id)
  const leftCheckedVisible = leftVisibleKeys.filter(k => leftChecked.has(k))
  const allLeftChecked = leftVisibleKeys.length > 0 && leftCheckedVisible.length === leftVisibleKeys.length
  const rightCheckedVisible = selectedEntries.map(e => e.key).filter(k => rightChecked.has(k))

  async function handleSave() {
    setSaving(true)
    setSaveError('')
    setSaved(false)
    try {
      const res = await fetch(`${API}/api/groups/selection`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ groups: raw }),
      })
      const data = await res.json()
      if (!data.ok) throw new Error(data.error || '保存失败')
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setSaveError(friendlyError(e, '保存失败'))
    }
    setSaving(false)
  }

  // ── 群成员备注：打开弹窗后按群加载成员 ───────────────────────────
  useEffect(() => {
    if (!remarkGroup?.chat_id) {
      setMembers([])
      return
    }
    let cancelled = false
    setMembersLoading(true)
    setMembersError('')
    fetch(`${API}/api/nicknames?chat_id=${encodeURIComponent(remarkGroup.chat_id)}`)
      .then(res => res.json())
      .then(data => {
        if (cancelled) return
        if (data.ok) setMembers(data.members || [])
        else setMembersError(data.error || '加载群成员失败')
      })
      .catch(() => { if (!cancelled) setMembersError('加载群成员失败') })
      .finally(() => { if (!cancelled) setMembersLoading(false) })
    return () => { cancelled = true }
  }, [remarkGroup?.chat_id])

  function startEdit(member) {
    editingRef.current = member.wxid
    setEditingWxid(member.wxid)
    setDraft(member.nickname || '')
    setMembersError('')
  }

  function cancelEdit() {
    editingRef.current = null
    setEditingWxid(null)
    setDraft('')
  }

  /** 提交备注：空备注表示清除覆盖，恢复使用群内显示名 */
  async function commitEdit(member, value) {
    if (editingRef.current !== member.wxid) return
    editingRef.current = null
    setEditingWxid(null)

    const next = (value || '').trim()
    if (next === (member.nickname || '')) return

    setSavingWxid(member.wxid)
    setMembersError('')
    try {
      const res = await fetch(`${API}/api/nicknames`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wxid: member.wxid, nickname: next }),
      })
      const data = await res.json()
      if (!data.ok) throw new Error(data.error || '保存备注失败')

      setMembers(prev => prev.map(m => (
        m.wxid === member.wxid ? { ...m, nickname: next } : m
      )))
      setSavedWxid(member.wxid)
      setTimeout(() => setSavedWxid(prev => (prev === member.wxid ? null : prev)), 1500)
    } catch (e) {
      setMembersError(friendlyError(e, '保存备注失败'))
    } finally {
      setSavingWxid(null)
    }
  }

  const memberQ = memberQuery.trim().toLowerCase()
  const filteredMembers = memberQ
    ? members.filter(m =>
        (m.nickname || '').toLowerCase().includes(memberQ)
        || (m.display_name || '').toLowerCase().includes(memberQ)
        || (m.wxid || '').toLowerCase().includes(memberQ))
    : members

  const arrowClass = 'w-9 h-9 rounded-full flex items-center justify-center border transition-all duration-200 cursor-pointer shrink-0 ' +
    'border-border-main bg-bg-card text-text-main hover:text-white hover:border-transparent hover:bg-[#4C9B72] active:scale-95 ' +
    'disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:text-text-main disabled:hover:border-border-main disabled:hover:bg-bg-card'

  return (
    <div className="max-w-4xl">
      <AnimatePresence>
        {saved && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="mb-4 flex items-center gap-2 px-5 py-2.5 bg-brand-green-light border border-brand-green/20 rounded-full text-sm text-brand-green-hover dark:text-brand-green font-medium shadow-sm"
          >
            <CheckCircle size={18} weight="fill" className="text-brand-green-hover dark:text-brand-green" />
            <span>群聊配置已保存，运行中的机器人立即生效。</span>
          </motion.div>
        )}
        {saveError && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="mb-4 flex items-center gap-2 px-5 py-2.5 bg-[#d45656]/5 border border-[#d45656]/20 rounded-full text-sm text-[#d45656] font-medium shadow-sm"
          >
            <Warning size={18} weight="fill" className="text-[#d45656]" />
            <span>{saveError}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex items-center gap-2.5 mb-5 pl-1">
        <div className="w-1.5 h-4.5 rounded-full shadow-sm" style={{ backgroundColor: ACCENT }} />
        <h3 className="text-sm font-semibold tracking-tight text-text-main">群聊配置</h3>
      </div>

      {/* ── 区块一：参与群聊名单（左右穿梭） ─────────────────────── */}
      <div className="bg-bg-card border border-border-main rounded-2xl shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none">
        <div className="p-7">
          <div className="flex items-center gap-2.5 mb-5">
            <UsersThree size={18} className="text-brand-green-hover dark:text-brand-green" />
            <p className="text-xs text-text-muted leading-relaxed">
              只有右侧「参与群聊」中的群会被轮询并触发对应的 AI 功能（总结、对话、待办等）。
              未加入的群不会产生任何 AI 回复。
            </p>
          </div>

          <Field
            label="群聊名单"
            hint={
              selectedEntries.length > 0
                ? `已选 ${selectedEntries.length} 个群聊参与 AI 处理`
                : '名单为空：机器人不会处理任何群消息'
            }
          >
            <div className="grid grid-cols-[1fr_auto_1fr] gap-3 h-[400px]">

              {/* 左栏：全部群聊 */}
              <div className="flex flex-col min-h-0 rounded-xl border border-border-main bg-bg-raised overflow-hidden">
                <div className="flex items-center justify-between gap-2 px-3 h-10 shrink-0 border-b border-border-main/70">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Users size={15} className="text-text-muted shrink-0" />
                    <span className="text-[12.5px] font-semibold text-text-main truncate">全部群聊</span>
                    <span className="px-1.5 py-px rounded-full bg-bg-card border border-border-main text-[10px] font-mono text-text-muted shrink-0">
                      {groups.length}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={refreshGroups}
                    disabled={loading}
                    title="刷新群聊列表"
                    className="p-1.5 rounded-lg text-text-muted hover:text-text-main hover:bg-bg-card transition-colors cursor-pointer disabled:opacity-50"
                  >
                    <ArrowClockwise size={14} weight="bold" className={loading ? 'animate-spin' : ''} />
                  </button>
                </div>

                <div className="flex items-center gap-1.5 px-2.5 h-9 shrink-0 border-b border-border-main/70">
                  <MagnifyingGlass size={14} className="text-text-muted/70 shrink-0" />
                  <input
                    type="text"
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    placeholder="搜索群名称或群 ID"
                    className="flex-1 min-w-0 bg-transparent text-[12.5px] text-text-main placeholder:text-text-muted/60 focus:outline-none"
                  />
                  {query && (
                    <button
                      type="button"
                      onClick={() => setQuery('')}
                      title="清空搜索"
                      className="text-text-muted/70 hover:text-text-main transition-colors cursor-pointer"
                    >
                      <X size={12} weight="bold" />
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-2.5 px-2.5 h-8 shrink-0 border-b border-border-main/70 text-[11.5px]">
                  <button
                    type="button"
                    onClick={() => setLeftChecked(new Set(allLeftChecked ? [] : leftVisibleKeys))}
                    disabled={leftVisibleKeys.length === 0}
                    className="text-brand-green-hover dark:text-brand-green hover:opacity-75 transition-opacity cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {allLeftChecked ? '取消全选' : '全选'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setLeftChecked(new Set())}
                    disabled={leftCheckedVisible.length === 0}
                    className="text-text-muted hover:text-text-main transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    清空勾选
                  </button>
                  <span className="ml-auto font-mono text-[10.5px] text-text-muted/80">
                    {leftCheckedVisible.length > 0 ? `已勾选 ${leftCheckedVisible.length}` : '双击可移入'}
                  </span>
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto p-1.5">
                  {leftGroups.length === 0 ? (
                    <div className="px-2.5 py-3">
                      <p className="text-[12px] text-text-muted leading-relaxed">
                        {loading && groups.length === 0
                          ? '正在加载群聊…'
                          : groups.length === 0
                            ? '暂无群聊：启动一次机器人后会自动同步微信群，再回到这里选择。'
                            : q
                              ? '没有匹配的群聊'
                              : '全部群聊都已在右侧参与名单中'}
                      </p>
                      {groups.length === 0 && (
                        <button
                          type="button"
                          onClick={refreshGroups}
                          disabled={loading}
                          className="mt-2 flex items-center gap-1.5 text-[11.5px] text-brand-green-hover dark:text-brand-green hover:opacity-75 transition-opacity cursor-pointer disabled:opacity-50"
                        >
                          <ArrowClockwise size={13} weight="bold" className={loading ? 'animate-spin' : ''} />
                          重新同步
                        </button>
                      )}
                    </div>
                  ) : leftGroups.map(g => {
                    const checked = leftChecked.has(g.chat_id)
                    return (
                      <div
                        key={g.chat_id}
                        onClick={() => toggleChecked(setLeftChecked, g.chat_id)}
                        onDoubleClick={() => moveRight([g])}
                        className={`group flex items-center gap-2.5 px-2 py-1.5 rounded-lg cursor-pointer select-none transition-colors ${
                          checked ? 'bg-[#4C9B72]/10' : 'hover:bg-bg-card'
                        }`}
                      >
                        <CheckBox checked={checked} />
                        <span className="flex-1 min-w-0">
                          <span className="flex items-center gap-1.5 min-w-0">
                            <span className="text-[13.5px] text-text-main truncate" title={groupNameOf(g)}>
                              {groupNameOf(g)}
                            </span>
                            {g.active === false && (
                              <span className="shrink-0 px-1 py-px rounded border border-[#c37d0d]/25 bg-[#c37d0d]/10 text-[10px] leading-4 text-[#a06a0a]">
                                已退出
                              </span>
                            )}
                          </span>
                          <span className="block text-[11px] text-text-muted/80 truncate font-mono" title={g.chat_id}>
                            {g.active === false
                              ? '已退出该群'
                              : (g.member_count > 0 ? `${g.member_count} 人` : g.chat_id)}
                          </span>
                        </span>
                        <button
                          type="button"
                          onClick={e => { e.stopPropagation(); moveRight([g]) }}
                          onDoubleClick={e => e.stopPropagation()}
                          title="移入参与群聊"
                          className="shrink-0 p-0.5 rounded-md text-text-muted/50 opacity-0 group-hover:opacity-100 hover:text-brand-green-hover transition-all cursor-pointer"
                        >
                          <ArrowRight size={13} weight="bold" />
                        </button>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* 中间：双向移入 / 移出 */}
              <div className="flex flex-col items-center justify-center gap-3 w-11">
                <button
                  type="button"
                  onClick={() => moveRight(leftGroups.filter(g => leftChecked.has(g.chat_id)))}
                  disabled={leftCheckedVisible.length === 0}
                  title="加入参与群聊"
                  className={arrowClass}
                >
                  <ArrowRight size={16} weight="bold" />
                </button>
                <button
                  type="button"
                  onClick={() => moveLeft(rightCheckedVisible)}
                  disabled={rightCheckedVisible.length === 0}
                  title="移出参与群聊"
                  className={arrowClass}
                >
                  <ArrowLeft size={16} weight="bold" />
                </button>
              </div>

              {/* 右栏：参与群聊 */}
              <div className="flex flex-col min-h-0 rounded-xl border border-border-main bg-bg-raised overflow-hidden">
                <div className="flex items-center justify-between gap-2 px-3 h-10 shrink-0 border-b border-border-main/70">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <UsersThree size={15} className="text-brand-green-hover dark:text-brand-green shrink-0" />
                    <span className="text-[12.5px] font-semibold text-text-main truncate">参与群聊</span>
                    <span className="px-1.5 py-px rounded-full bg-brand-green-light border border-brand-green/20 text-[10px] font-mono text-brand-green-hover dark:text-brand-green shrink-0">
                      {selectedEntries.length}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelection([])}
                    disabled={selectedEntries.length === 0}
                    title="清空全部参与群聊"
                    className="text-[11.5px] text-text-muted hover:text-[#d45656] transition-colors cursor-pointer disabled:opacity-35 disabled:cursor-not-allowed"
                  >
                    清空
                  </button>
                </div>

                <div className="flex items-center gap-2.5 px-2.5 h-8 shrink-0 border-b border-border-main/70 text-[11px] text-text-muted">
                  <span className="truncate">
                    {selectedEntries.length > 0 ? '这些群会触发 AI 功能' : '从左侧勾选群聊后点击 → 移入'}
                  </span>
                  {rightCheckedVisible.length > 0 && (
                    <span className="ml-auto font-mono text-[10.5px] text-text-muted/80 shrink-0">
                      已勾选 {rightCheckedVisible.length}
                    </span>
                  )}
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto p-1.5">
                  {selectedEntries.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center gap-2 px-4 text-center">
                      <UsersThree size={26} className="text-text-muted/25" />
                      <p className="text-[12px] text-text-muted/80 leading-relaxed">
                        名单为空<br />机器人不会处理任何群消息
                      </p>
                    </div>
                  ) : selectedEntries.map(entry => {
                    const checked = rightChecked.has(entry.key)
                    return (
                      <div
                        key={entry.key}
                        onClick={() => toggleChecked(setRightChecked, entry.key)}
                        onDoubleClick={() => moveLeft([entry.key])}
                        className={`group flex items-center gap-2.5 px-2 py-1.5 rounded-lg cursor-pointer select-none transition-colors ${
                          checked ? 'bg-[#4C9B72]/10' : 'hover:bg-bg-card'
                        }`}
                      >
                        <CheckBox checked={checked} />
                        <span className="flex-1 min-w-0">
                          <span className="flex items-center gap-1.5 min-w-0">
                            <span className="text-[13.5px] text-text-main truncate" title={entry.group ? groupNameOf(entry.group) : entry.value}>
                              {entry.group ? groupNameOf(entry.group) : entry.value}
                            </span>
                            {entry.group?.active === false && (
                              <span className="shrink-0 px-1 py-px rounded border border-[#c37d0d]/25 bg-[#c37d0d]/10 text-[10px] leading-4 text-[#a06a0a]">
                                已退出
                              </span>
                            )}
                          </span>
                          <span className={`block text-[11px] truncate font-mono ${
                            !entry.group || entry.group.active === false
                              ? 'text-[#c37d0d]/80'
                              : 'text-text-muted/80'
                          }`}>
                            {!entry.group
                              ? '不在当前群列表中'
                              : entry.group.active === false
                                ? '已退出该群'
                                : (entry.group.member_count > 0 ? `${entry.group.member_count} 人` : entry.group.chat_id)}
                          </span>
                        </span>
                        <button
                          type="button"
                          onClick={e => {
                            e.stopPropagation()
                            if (entry.group && entry.group.active !== false) {
                              setRemarkGroup({ chat_id: entry.group.chat_id, group_name: groupNameOf(entry.group) })
                            }
                          }}
                          onDoubleClick={e => e.stopPropagation()}
                          disabled={!entry.group || entry.group.active === false}
                          title={
                            !entry.group
                              ? '该群不在当前列表中，无法配置'
                              : entry.group.active === false
                                ? '该群已退出，无法配置群友备注'
                                : '配置群友备注'
                          }
                          className="shrink-0 p-1 rounded-md text-text-muted/60 opacity-70 group-hover:opacity-100 hover:text-brand-green-hover hover:bg-brand-green-light transition-all cursor-pointer disabled:cursor-not-allowed disabled:opacity-0"
                        >
                          <PencilSimple size={13} />
                        </button>
                        <button
                          type="button"
                          onClick={e => { e.stopPropagation(); moveLeft([entry.key]) }}
                          onDoubleClick={e => e.stopPropagation()}
                          title="移出名单"
                          className="shrink-0 p-0.5 rounded-md text-text-muted/50 opacity-0 group-hover:opacity-100 hover:text-[#d45656] transition-all cursor-pointer"
                        >
                          <X size={13} weight="bold" />
                        </button>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>

            <p className="text-[11px] text-text-muted mt-2">
              群列表来自最近一次机器人同步；新建群后请先启动一次机器人，再点击刷新。
              标记「已退出」的群已不在当前微信账号中（退群或群解散），机器人不会轮询。
            </p>
            {loadError && (
              <p className="text-[11px] text-[#d45656] mt-1">{loadError}</p>
            )}
          </Field>
        </div>
      </div>

      {/* 保存区（与「好友私聊」页保持一致：放在卡片外） */}
      <div className="mt-8 flex items-center gap-4">
        <motion.button
          whileTap={{ scale: 0.97 }}
          whileHover={{ scale: 1.02 }}
          onClick={handleSave}
          disabled={saving}
          className={`w-48 py-2.5 rounded-full text-[14px] font-semibold tracking-wide shadow-sm transition-all duration-300 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-60 ${
            saved
              ? 'bg-brand-green-light border border-brand-green/20 text-brand-green-hover dark:text-brand-green font-semibold'
              : 'bg-[#0d0d0d] dark:bg-white text-white dark:text-[#0d0d0d] border border-[#0d0d0d] dark:border-border-main hover:opacity-90'
          }`}
        >
          {saved ? (
            <><CheckCircle size={18} weight="fill" className="text-brand-green-hover dark:text-brand-green" /> 已保存</>
          ) : saving ? (
            <><Spinner size={17} weight="bold" className="animate-spin" /> 保存中…</>
          ) : (
            <><FloppyDisk size={18} /> 保存配置</>
          )}
        </motion.button>
        <span className="flex items-center gap-1.5 text-xs text-text-muted bg-bg-raised border border-border-main px-4 py-1.5 rounded-full font-medium">
          <Info size={14} className="text-text-muted opacity-80" />
          保存后立即生效，无需重启
        </span>
      </div>

      {/* ── 群成员备注弹窗（从参与群聊行的铅笔按钮打开） ─────────── */}
      <AnimatePresence>
        {remarkGroup && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setRemarkGroup(null)}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/45 backdrop-blur-sm"
          >
            <motion.div
              initial={{ opacity: 0, y: 16, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 16, scale: 0.98 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              onClick={e => e.stopPropagation()}
              className="w-full max-w-2xl max-h-[85vh] flex flex-col bg-bg-card border border-border-main rounded-2xl shadow-2xl overflow-hidden"
            >
              {/* 弹窗标题 */}
              <div className="flex items-center justify-between gap-3 px-6 py-4 border-b border-border-main shrink-0">
                <div className="flex items-center gap-2.5 min-w-0">
                  <PencilSimple size={18} className="text-brand-green-hover dark:text-brand-green shrink-0" />
                  <div className="min-w-0">
                    <h3 className="text-[15px] font-semibold text-text-main truncate">
                      {remarkGroup.group_name}
                    </h3>
                    <p className="text-[11px] text-text-muted mt-0.5">
                      {membersLoading ? '正在加载群成员…' : `群成员备注 · ${members.length} 人`}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setRemarkGroup(null)}
                  title="关闭"
                  className="p-1.5 rounded-lg text-text-muted hover:text-text-main hover:bg-bg-raised transition-colors cursor-pointer shrink-0"
                >
                  <X size={16} weight="bold" />
                </button>
              </div>

              {/* 弹窗内容 */}
              <div className="px-6 py-4 flex-1 min-h-0 flex flex-col">
                <p className="text-[11.5px] text-text-muted leading-relaxed mb-3 shrink-0">
                  双击成员行，或点击行尾的铅笔按钮修改备注。AI 回复中会自动把微信 ID（wxid_xxx）替换为这里设置的备注。
                </p>

                {membersError && (
                  <div className="mb-3 px-4 py-2.5 bg-[#d45656]/5 border border-[#d45656]/20 rounded-lg text-[12.5px] text-[#d45656] shrink-0">
                    {membersError}
                  </div>
                )}

                <div className="rounded-xl border border-border-main overflow-hidden flex-1 min-h-0 flex flex-col">
                  <div className="flex items-center gap-2 px-3 h-10 bg-bg-raised border-b border-border-main/70 shrink-0">
                    <MagnifyingGlass size={14} className="text-text-muted/70 shrink-0" />
                    <input
                      type="text"
                      value={memberQuery}
                      onChange={e => setMemberQuery(e.target.value)}
                      placeholder="搜索群昵称或微信号"
                      className="flex-1 min-w-0 bg-transparent text-[12.5px] text-text-main placeholder:text-text-muted/60 focus:outline-none"
                    />
                    {memberQuery ? (
                      <>
                        <span className="text-[10.5px] font-mono text-text-muted shrink-0">
                          {filteredMembers.length}/{members.length}
                        </span>
                        <button
                          type="button"
                          onClick={() => setMemberQuery('')}
                          title="清空搜索"
                          className="text-text-muted/70 hover:text-text-main transition-colors cursor-pointer shrink-0"
                        >
                          <X size={12} weight="bold" />
                        </button>
                      </>
                    ) : (
                      <span className="text-[11px] font-mono text-text-muted shrink-0">{members.length} 人</span>
                    )}
                  </div>

                  {membersLoading ? (
                    <div className="flex items-center justify-center py-12">
                      <Spinner size={22} weight="bold" className="animate-spin text-brand-green" />
                    </div>
                  ) : members.length === 0 ? (
                    <p className="text-center text-[12.5px] text-text-muted/70 py-10">
                      该群暂无成员记录
                    </p>
                  ) : filteredMembers.length === 0 ? (
                    <p className="text-center text-[12.5px] text-text-muted/70 py-10">
                      没有匹配的成员
                    </p>
                  ) : (
                    <div className="flex-1 min-h-0 overflow-y-auto">
                      {filteredMembers.map(m => {
                        const editing = editingWxid === m.wxid
                        const rowSaving = savingWxid === m.wxid
                        // 上：备注优先，其次群内昵称（两者都没有就留空）；下：微信号
                        const topName = m.nickname || m.display_name || ''
                        return (
                          <div
                            key={m.wxid}
                            onDoubleClick={() => { if (!editing) startEdit(m) }}
                            className={`group flex items-center gap-3 px-4 py-2.5 border-b border-border-main/40 last:border-0 transition-colors select-none ${
                              editing ? 'bg-bg-raised' : 'hover:bg-bg-raised/60'
                            }`}
                          >
                            <div className="flex-1 min-w-0">
                              {editing ? (
                                <input
                                  autoFocus
                                  value={draft}
                                  onChange={e => setDraft(e.target.value)}
                                  onKeyDown={e => {
                                    if (e.nativeEvent.isComposing) return  // 中文输入法组合中，跳过回车
                                    if (e.key === 'Enter') commitEdit(m, e.target.value)
                                    if (e.key === 'Escape') cancelEdit()
                                  }}
                                  onBlur={e => commitEdit(m, e.target.value)}
                                  placeholder="设置备注"
                                  className="w-full bg-bg-card border border-brand-green/40 rounded-lg px-2.5 py-1 text-[13px] text-text-main placeholder:text-text-muted/60 focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/20"
                                />
                              ) : (
                                <p className={`text-[13px] truncate ${topName ? 'text-text-main' : 'text-transparent'}`}>
                                  {topName || '\u00A0'}
                                </p>
                              )}
                              <p className="text-[11px] text-text-muted/80 font-mono truncate mt-0.5">
                                {m.wxid}
                              </p>
                            </div>
                            {rowSaving ? (
                              <Spinner size={14} weight="bold" className="animate-spin text-text-muted shrink-0" />
                            ) : savedWxid === m.wxid ? (
                              <Check size={14} weight="bold" className="text-brand-green-hover dark:text-brand-green shrink-0" />
                            ) : (
                              <button
                                type="button"
                                onClick={() => startEdit(m)}
                                title="编辑备注"
                                className="shrink-0 p-1 rounded-md text-text-muted/50 opacity-0 group-hover:opacity-100 hover:text-brand-green-hover hover:bg-brand-green-light transition-all cursor-pointer"
                              >
                                <PencilSimple size={14} />
                              </button>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* 弹窗底部 */}
              <div className="flex items-center justify-between gap-3 px-6 py-4 border-t border-border-main bg-bg-raised/40 shrink-0">
                <span className="flex items-center gap-1.5 text-[11.5px] text-text-muted">
                  <Info size={14} /> 备注修改后即时保存
                </span>
                <button
                  type="button"
                  onClick={() => setRemarkGroup(null)}
                  className="px-5 py-2 rounded-full text-[12.5px] font-semibold bg-[#0d0d0d] dark:bg-white text-white dark:text-[#0d0d0d] hover:opacity-90 transition-opacity cursor-pointer"
                >
                  完成
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
