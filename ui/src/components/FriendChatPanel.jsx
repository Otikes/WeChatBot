import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, Warning, FloppyDisk, Info, ChatCircleDots } from '@phosphor-icons/react'
import { Field } from './SharedComponents'

const API = 'http://127.0.0.1:7327'

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
    } catch (e) {
      setLoadError(e.message || '无法连接本地服务，请确认应用正在运行')
    }
    setLoading(false)
  }

  useEffect(() => { loadAll() }, [])

  // "*" = every discovered friend; otherwise a URL-encoded comma list.
  const isAll = raw.trim() === '*'
  const selected = isAll
    ? friends.map(f => f.chat_id)
    : raw.split(',').map(s => {
        const trimmed = s.trim()
        if (!trimmed) return ''
        try { return decodeURIComponent(trimmed) } catch { return trimmed }
      }).filter(Boolean)

  function setSelection(keys) {
    if (!keys.length) {
      setRaw('')
    } else {
      setRaw(keys.map(k => encodeURIComponent(k)).join(','))
    }
    setSaved(false)
    setSaveError('')
  }

  function toggleFriend(friend) {
    const chatId = friend.chat_id || friend.name
    const checked = isAll
      || selected.includes(chatId)
      || selected.includes(friend.name)

    if (isAll) {
      // Expand "*" into the concrete list so individual friends can be unchecked.
      const next = friends
        .map(f => f.chat_id || f.name)
        .filter(id => id !== chatId)
      setSelection(next)
      return
    }
    if (checked) {
      setSelection(selected.filter(id => id !== chatId && id !== friend.name))
    } else {
      setSelection([...selected, chatId])
    }
  }

  const knownKeys = new Set()
  friends.forEach(f => {
    knownKeys.add(f.name)
    knownKeys.add(f.chat_id)
  })
  const orphanSelected = isAll ? [] : selected.filter(k => !knownKeys.has(k))

  const q = query.trim().toLowerCase()
  const visibleFriends = friends.filter(f => {
    if (!q) return true
    return (f.name || '').toLowerCase().includes(q)
      || (f.chat_id || '').toLowerCase().includes(q)
  })

  const selectedCount = isAll ? friends.length : selected.length

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
      setSaveError(e.message || '无法连接到服务器，请确认机器人已启动')
    }
    setSaving(false)
  }

  return (
    <div className="max-w-2xl">
      <AnimatePresence>
        {saved && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="mb-4 flex items-center gap-2 px-5 py-2.5 bg-brand-green-light border border-brand-green/20 rounded-full text-sm text-brand-green-hover dark:text-brand-green font-medium shadow-sm"
          >
            <CheckCircle size={18} weight="fill" className="text-brand-green-hover dark:text-brand-green" />
            <span>好友配置已保存。重启机器人后生效。</span>
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
        <div className="w-1.5 h-4.5 rounded-full shadow-sm" style={{ backgroundColor: '#4C9B72' }} />
        <h3 className="text-sm font-semibold tracking-tight text-text-main">好友私聊</h3>
      </div>

      <div className="bg-bg-card border border-border-main rounded-2xl shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none">
        <div className="p-7">
          <div className="flex items-center gap-2.5 mb-5">
            <ChatCircleDots size={18} className="text-brand-green-hover dark:text-brand-green" />
            <p className="text-xs text-text-muted leading-relaxed">
              勾选后，这些好友发来的文字 / 已转写语音消息会自动获得 AI 回复。
              未勾选的好友不会被轮询，也不会收到任何 AI 回复。
            </p>
          </div>

          <Field
            label="选择好友"
            hint={
              isAll
                ? `已勾选全部好友（${friends.length} 位）`
                : selectedCount > 0
                  ? `已勾选 ${selectedCount} 位好友`
                  : '未勾选任何好友：好友私聊不会收到任何 AI 回复'
            }
          >
            <div className="rounded-xl border border-border-main bg-bg-raised overflow-hidden">
              <div className="flex items-center gap-2 px-3 py-2 border-b border-border-main/70">
                <input
                  type="text"
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  placeholder="搜索好友名称或微信号"
                  className="flex-1 min-w-0 bg-transparent text-[13.5px] text-text-main placeholder:text-text-muted/60 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={loadAll}
                  disabled={loading}
                  className="shrink-0 px-2.5 py-1 text-[12px] rounded-lg border border-border-main text-text-muted hover:border-brand-green hover:text-brand-green-hover transition-colors cursor-pointer disabled:opacity-50"
                >
                  {loading ? '刷新中…' : '刷新'}
                </button>
              </div>
              <div className="flex items-center gap-3 px-3 py-1.5 border-b border-border-main/70 text-[12px]">
                <button
                  type="button"
                  onClick={() => { setRaw('*'); setSaved(false); setSaveError('') }}
                  className="text-[#6E9FCF] hover:text-[#1F6C9F] transition-colors cursor-pointer"
                >
                  全选
                </button>
                <button
                  type="button"
                  onClick={() => setSelection([])}
                  className="text-text-muted hover:text-[#d45656] transition-colors cursor-pointer"
                >
                  清空
                </button>
              </div>
              <div className="max-h-96 overflow-y-auto p-1.5">
                {visibleFriends.length === 0 ? (
                  <p className="px-2.5 py-3 text-[12px] text-text-muted leading-relaxed">
                    {friends.length === 0
                      ? '暂无好友列表：启动一次机器人后会自动同步微信好友，再回到这里勾选。'
                      : '没有匹配的好友'}
                  </p>
                ) : visibleFriends.map(f => {
                  const chatId = f.chat_id || f.name
                  const checked = isAll
                    || selected.includes(chatId)
                    || selected.includes(f.name)
                  return (
                    <label
                      key={chatId}
                      className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-bg-main cursor-pointer transition-colors"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleFriend(f)}
                        className="w-4 h-4 accent-[#4C9B72] cursor-pointer"
                      />
                      <span className="flex-1 min-w-0">
                        <span className="block text-[13.5px] text-text-main truncate">{f.name || chatId}</span>
                        {f.name && f.chat_id && f.name !== f.chat_id && (
                          <span className="block text-[11px] text-text-muted/80 truncate">{f.chat_id}</span>
                        )}
                      </span>
                    </label>
                  )
                })}
              </div>
            </div>

            {orphanSelected.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {orphanSelected.map((name, i) => (
                  <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green">
                    {name}
                    <button
                      type="button"
                      onClick={() => setSelection(selected.filter(k => k !== name))}
                      className="ml-0.5 text-brand-green-hover/60 hover:text-[#d45656] transition-colors leading-none text-base"
                    >
                      &times;
                    </button>
                  </span>
                ))}
              </div>
            )}

            <p className="text-[11px] text-text-muted mt-1.5">
              好友列表来自最近一次机器人同步；新增好友后请先启动一次机器人，再点击刷新。
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
          ) : (
            <><FloppyDisk size={18} /> {saving ? '保存中…' : '保存配置'}</>
          )}
        </motion.button>
        <span className="flex items-center gap-1.5 text-xs text-text-muted bg-bg-raised border border-border-main px-4 py-1.5 rounded-full font-medium">
          <Info size={14} className="text-text-muted opacity-80" />
          保存后需重启机器人才能生效
        </span>
      </div>
    </div>
  )
}
