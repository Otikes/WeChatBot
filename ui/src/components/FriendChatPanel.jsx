import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  CheckCircle, Warning, FloppyDisk, Info, ChatCircleDots,
  ArrowRight, ArrowLeft, ArrowClockwise, MagnifyingGlass,
  Users, Robot, X, Check, Spinner,
} from '@phosphor-icons/react'
import { Field, friendlyError } from './SharedComponents'

const API = 'http://127.0.0.1:7327'
const ACCENT = '#4C9B72'

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

function PersonMeta({ name, sub, subClass = 'text-text-muted/80', badge }) {
  return (
    <span className="flex-1 min-w-0">
      <span className="flex items-center gap-1.5 min-w-0">
        <span className="text-[13.5px] text-text-main truncate" title={name}>{name}</span>
        {badge && (
          <span className="shrink-0 px-1 py-px rounded border border-[#c37d0d]/25 bg-[#c37d0d]/10 text-[10px] leading-4 text-[#a06a0a]">
            {badge}
          </span>
        )}
      </span>
      {sub && <span className={`block text-[11px] ${subClass} truncate`} title={sub}>{sub}</span>}
    </span>
  )
}

export default function FriendChatPanel() {
  // Friend checklist source (persisted by WcdbBackend as friend_names.json)
  const [friends, setFriends] = useState([])
  const [query, setQuery] = useState('')
  const [raw, setRaw] = useState('')
  const [friendChatEnabled, setFriendChatEnabled] = useState(true)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState('')

  // Staged checkboxes for the two panes (moved by the arrows in the middle).
  const [leftChecked, setLeftChecked] = useState(() => new Set())
  const [rightChecked, setRightChecked] = useState(() => new Set())

  async function loadAll() {
    setLoading(true)
    setLoadError('')
    try {
      const [friendsRes, configRes] = await Promise.all([
        fetch(`${API}/api/friends`),
        fetch(`${API}/api/load-config`),
      ])
      const friendsData = await friendsRes.json()
      const configData = await configRes.json()
      if (!friendsData.ok) throw new Error(friendsData.error || '好友列表加载失败')
      if (!configData.ok) throw new Error(configData.error || '配置加载失败')
      setFriends(friendsData.friends || [])
      setRaw(configData.config?.wechat_friends || '')
      setFriendChatEnabled(configData.config?.friend_chat_enabled !== false)
      setLeftChecked(new Set())
      setRightChecked(new Set())
    } catch (e) {
      setLoadError(friendlyError(e, '好友列表加载失败'))
    }
    setLoading(false)
  }

  useEffect(() => { loadAll() }, [])

  // 仅刷新好友列表，不影响尚未保存的勾选结果
  async function refreshFriends() {
    setLoading(true)
    setLoadError('')
    try {
      const res = await fetch(`${API}/api/friends`)
      const data = await res.json()
      if (!data.ok) throw new Error(data.error || '好友列表加载失败')
      setFriends(data.friends || [])
    } catch (e) {
      setLoadError(friendlyError(e, '好友列表加载失败'))
    }
    setLoading(false)
  }

  // "*" = every discovered friend; otherwise a URL-encoded comma list.
  const isAll = raw.trim() === '*'
  const friendKey = (f) => f.chat_id || f.name
  const friendKeys = friends.map(friendKey)
  const nameToKey = new Map(friends.map(f => [f.name, friendKey(f)]))

  // Normalize legacy entries stored by display name into chat ids.
  const selectedKeys = []
  ;(isAll
    ? friendKeys
    : raw.split(',').map(s => {
        const trimmed = s.trim()
        if (!trimmed) return ''
        try { return decodeURIComponent(trimmed) } catch { return trimmed }
      }).filter(Boolean)
  ).forEach(k => {
    const key = nameToKey.get(k) || k
    if (!selectedKeys.includes(key)) selectedKeys.push(key)
  })

  function setSelection(keys) {
    const unique = [...new Set(keys.filter(Boolean))]
    setRaw(unique.length ? unique.map(k => encodeURIComponent(k)).join(',') : '')
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

  function moveRight(keys) {
    const valid = keys.filter(Boolean)
    if (!valid.length) return
    setSelection([...selectedKeys, ...valid])
    setLeftChecked(prev => {
      const next = new Set(prev)
      valid.forEach(k => next.delete(k))
      return next
    })
  }

  function moveLeft(keys) {
    const valid = keys.filter(Boolean)
    if (!valid.length) return
    setSelection(selectedKeys.filter(k => !valid.includes(k)))
    setRightChecked(prev => {
      const next = new Set(prev)
      valid.forEach(k => next.delete(k))
      return next
    })
  }

  function clearRight() {
    setSelection([])
    setRightChecked(new Set())
  }

  const q = query.trim().toLowerCase()
  const rightFriends = friends.filter(f => selectedKeys.includes(friendKey(f)))
  const leftFriends = friends
    .filter(f => {
      if (selectedKeys.includes(friendKey(f))) return false
      if (!q) return true
      return (f.name || '').toLowerCase().includes(q)
        || (f.chat_id || '').toLowerCase().includes(q)
        || (f.alias || '').toLowerCase().includes(q)
    })
    // 已不是好友的条目排在最后，但仍保留展示
    .sort((a, b) => (a.active === false ? 1 : 0) - (b.active === false ? 1 : 0))

  const knownKeys = new Set(friendKeys)
  const orphanKeys = selectedKeys.filter(k => !knownKeys.has(k))
  const selectedCount = isAll ? friends.length : selectedKeys.length
  const rightTotal = rightFriends.length + orphanKeys.length

  const leftVisibleKeys = leftFriends.map(friendKey)
  const leftCheckedVisible = leftVisibleKeys.filter(k => leftChecked.has(k))
  const allLeftChecked = leftVisibleKeys.length > 0 && leftCheckedVisible.length === leftVisibleKeys.length
  const rightCheckedVisible = [
    ...rightFriends.map(friendKey).filter(k => rightChecked.has(k)),
    ...orphanKeys.filter(k => rightChecked.has(k)),
  ]

  async function handleSave() {
    setSaving(true)
    setSaveError('')
    setSaved(false)
    try {
      const res = await fetch(`${API}/api/friends/selection`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ friends: raw }),
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
            <span>好友配置已保存，运行中的机器人立即生效。</span>
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

      {!friendChatEnabled && (
        <div className="mb-4 flex items-center gap-2 px-4 py-2.5 bg-[#c37d0d]/10 border border-[#c37d0d]/20 rounded-xl text-[13px] text-[#a06a0a]">
          <Warning size={16} weight="fill" className="shrink-0" />
          <span>好友私聊 AI 对话当前已关闭，勾选不会产生回复。请到「功能开关 → AI 对话」开启。</span>
        </div>
      )}

      <div className="flex items-center gap-2.5 mb-5 pl-1">
        <div className="w-1.5 h-4.5 rounded-full shadow-sm" style={{ backgroundColor: ACCENT }} />
        <h3 className="text-sm font-semibold tracking-tight text-text-main">好友私聊</h3>
      </div>

      <div className="bg-bg-card border border-border-main rounded-2xl shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none">
        <div className="p-7">
          <div className="flex items-center gap-2.5 mb-5">
            <ChatCircleDots size={18} className="text-brand-green-hover dark:text-brand-green" />
            <p className="text-xs text-text-muted leading-relaxed">
              把需要 AI 自动回复的好友移到右侧「AI 回复名单」。名单内好友发来的文字 / 已转写语音消息会自动获得 AI 回复，
              其余好友不会被轮询，也不会收到任何 AI 回复。
            </p>
          </div>

          <Field
            label="选择好友"
            hint={
              selectedCount > 0
                ? `已选 ${selectedCount} 位好友用于 AI 自动回复`
                : 'AI 回复名单为空：好友私聊不会收到任何 AI 回复'
            }
          >
            <div className="grid grid-cols-[1fr_auto_1fr] gap-3 h-[400px]">

              {/* ── Left pane: all friends ─────────────────────────── */}
              <div className="flex flex-col min-h-0 rounded-xl border border-border-main bg-bg-raised overflow-hidden">
                <div className="flex items-center justify-between gap-2 px-3 h-10 shrink-0 border-b border-border-main/70">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Users size={15} className="text-text-muted shrink-0" />
                    <span className="text-[12.5px] font-semibold text-text-main truncate">全部好友</span>
                    <span className="px-1.5 py-px rounded-full bg-bg-card border border-border-main text-[10px] font-mono text-text-muted shrink-0">
                      {friends.length}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={refreshFriends}
                    disabled={loading}
                    title="刷新好友列表"
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
                    placeholder="搜索好友名称或微信号"
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
                  {leftFriends.length === 0 ? (
                    <p className="px-2.5 py-3 text-[12px] text-text-muted leading-relaxed">
                      {loading && friends.length === 0
                        ? '正在加载好友列表…'
                        : friends.length === 0
                          ? '暂无好友列表：启动一次机器人后会自动同步微信好友，再回到这里选择。'
                          : q
                            ? '没有匹配的好友'
                            : '全部好友都已在右侧 AI 回复名单中'}
                    </p>
                  ) : leftFriends.map(f => {
                    const key = friendKey(f)
                    const checked = leftChecked.has(key)
                    const sub = f.alias && f.alias !== f.name ? f.alias : (f.name && f.chat_id && f.name !== f.chat_id ? f.chat_id : '')
                    return (
                      <div
                        key={key}
                        onClick={() => toggleChecked(setLeftChecked, key)}
                        onDoubleClick={() => moveRight([key])}
                        className={`group flex items-center gap-2.5 px-2 py-1.5 rounded-lg cursor-pointer select-none transition-colors ${
                          checked ? 'bg-[#4C9B72]/10' : 'hover:bg-bg-card'
                        }`}
                      >
                        <CheckBox checked={checked} />
                        <PersonMeta
                          name={f.name || f.alias || key}
                          sub={sub}
                          badge={f.active === false ? '已不是好友' : ''}
                        />
                        <button
                          type="button"
                          onClick={e => { e.stopPropagation(); moveRight([key]) }}
                          onDoubleClick={e => e.stopPropagation()}
                          title="移入 AI 回复名单"
                          className="shrink-0 p-0.5 rounded-md text-text-muted/50 opacity-0 group-hover:opacity-100 hover:text-brand-green-hover transition-all cursor-pointer"
                        >
                          <ArrowRight size={13} weight="bold" />
                        </button>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* ── Middle: two-way transfer arrows ────────────────── */}
              <div className="flex flex-col items-center justify-center gap-3 w-11">
                <button
                  type="button"
                  onClick={() => moveRight(leftCheckedVisible)}
                  disabled={leftCheckedVisible.length === 0}
                  title="移入 AI 回复名单"
                  className={arrowClass}
                >
                  <ArrowRight size={16} weight="bold" />
                </button>
                <button
                  type="button"
                  onClick={() => moveLeft(rightCheckedVisible)}
                  disabled={rightCheckedVisible.length === 0}
                  title="移出 AI 回复名单"
                  className={arrowClass}
                >
                  <ArrowLeft size={16} weight="bold" />
                </button>
              </div>

              {/* ── Right pane: AI reply list ──────────────────────── */}
              <div className="flex flex-col min-h-0 rounded-xl border border-border-main bg-bg-raised overflow-hidden">
                <div className="flex items-center justify-between gap-2 px-3 h-10 shrink-0 border-b border-border-main/70">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Robot size={15} className="text-brand-green-hover dark:text-brand-green shrink-0" />
                    <span className="text-[12.5px] font-semibold text-text-main truncate">AI 回复名单</span>
                    <span className="px-1.5 py-px rounded-full bg-brand-green-light border border-brand-green/20 text-[10px] font-mono text-brand-green-hover dark:text-brand-green shrink-0">
                      {rightTotal}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={clearRight}
                    disabled={rightTotal === 0}
                    className="text-[11.5px] text-text-muted hover:text-[#d45656] transition-colors cursor-pointer disabled:opacity-35 disabled:cursor-not-allowed"
                  >
                    清空
                  </button>
                </div>

                <div className="flex items-center gap-2.5 px-2.5 h-8 shrink-0 border-b border-border-main/70 text-[11px] text-text-muted">
                  <span className="truncate">
                    {rightTotal > 0 ? '这些好友会收到 AI 自动回复' : '从左侧勾选好友后点击 → 移入'}
                  </span>
                  {rightCheckedVisible.length > 0 && (
                    <span className="ml-auto font-mono text-[10.5px] text-text-muted/80 shrink-0">
                      已勾选 {rightCheckedVisible.length}
                    </span>
                  )}
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto p-1.5">
                  {rightTotal === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center gap-2 px-4 text-center">
                      <Robot size={26} className="text-text-muted/25" />
                      <p className="text-[12px] text-text-muted/80 leading-relaxed">
                        名单为空<br />移入好友后才会自动回复
                      </p>
                    </div>
                  ) : (
                    <>
                      {rightFriends.map(f => {
                        const key = friendKey(f)
                        const checked = rightChecked.has(key)
                        const sub = f.alias && f.alias !== f.name ? f.alias : (f.name && f.chat_id && f.name !== f.chat_id ? f.chat_id : '')
                        return (
                          <div
                            key={key}
                            onClick={() => toggleChecked(setRightChecked, key)}
                            onDoubleClick={() => moveLeft([key])}
                            className={`group flex items-center gap-2.5 px-2 py-1.5 rounded-lg cursor-pointer select-none transition-colors ${
                              checked ? 'bg-[#4C9B72]/10' : 'hover:bg-bg-card'
                            }`}
                          >
                            <CheckBox checked={checked} />
                            <PersonMeta
                              name={f.name || f.alias || key}
                              sub={sub}
                              badge={f.active === false ? '已不是好友' : ''}
                            />
                            <button
                              type="button"
                              onClick={e => { e.stopPropagation(); moveLeft([key]) }}
                              onDoubleClick={e => e.stopPropagation()}
                              title="移出名单"
                              className="shrink-0 p-0.5 rounded-md text-text-muted/50 opacity-0 group-hover:opacity-100 hover:text-[#d45656] transition-all cursor-pointer"
                            >
                              <X size={13} weight="bold" />
                            </button>
                          </div>
                        )
                      })}
                      {orphanKeys.map(key => {
                        const checked = rightChecked.has(key)
                        return (
                          <div
                            key={key}
                            onClick={() => toggleChecked(setRightChecked, key)}
                            onDoubleClick={() => moveLeft([key])}
                            className={`group flex items-center gap-2.5 px-2 py-1.5 rounded-lg cursor-pointer select-none transition-colors ${
                              checked ? 'bg-[#4C9B72]/10' : 'hover:bg-bg-card'
                            }`}
                          >
                            <CheckBox checked={checked} />
                            <PersonMeta name={key} sub="不在当前好友列表中" subClass="text-[#c37d0d]/80" />
                            <button
                              type="button"
                              onClick={e => { e.stopPropagation(); moveLeft([key]) }}
                              onDoubleClick={e => e.stopPropagation()}
                              title="移出名单"
                              className="shrink-0 p-0.5 rounded-md text-text-muted/50 opacity-0 group-hover:opacity-100 hover:text-[#d45656] transition-all cursor-pointer"
                            >
                              <X size={13} weight="bold" />
                            </button>
                          </div>
                        )
                      })}
                    </>
                  )}
                </div>
              </div>
            </div>

            <p className="text-[11px] text-text-muted mt-2">
              好友列表来自最近一次机器人同步；新增好友后请先启动一次机器人，再点击刷新。
              标记「已不是好友」的联系人已不在当前微信通讯录中，机器人不会轮询。
            </p>
            {loadError && (
              <p className="text-[11px] text-[#d45656] mt-1">{loadError}</p>
            )}
          </Field>
        </div>
      </div>

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
    </div>
  )
}
