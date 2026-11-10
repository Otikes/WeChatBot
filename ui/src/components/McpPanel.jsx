import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  ArrowClockwise, ArrowLeft, ArrowRight, ChatCircleDots, Check, CheckCircle,
  Copy, Eye, EyeSlash, Key, ListChecks, MagnifyingGlass, Plug, Spinner,
  Terminal, Users, WarningCircle, X, XCircle,
} from '@phosphor-icons/react'
import { ConfirmDialog, Toggle, friendlyError } from './SharedComponents'

function apiUrl(path) {
  if (window.location.port === '5173') return `http://127.0.0.1:7327${path}`
  return path
}

function CopyButton({ text, copied, onCopy }) {
  return (
    <button
      onClick={() => onCopy(text)}
      className="p-1.5 rounded-lg text-text-muted hover:text-text-main hover:bg-bg-raised transition-colors cursor-pointer"
      title="复制"
    >
      {copied ? <CheckCircle size={15} weight="fill" className="text-brand-green" /> : <Copy size={15} />}
    </button>
  )
}

function InfoRow({ label, value, copied, onCopy, mono = true }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 border-b border-border-main last:border-b-0">
      <span className="text-[11px] text-text-muted font-semibold font-mono uppercase tracking-wide shrink-0">{label}</span>
      <div className="flex items-center gap-2 min-w-0">
        <code className={`text-xs text-text-main truncate ${mono ? 'font-mono' : 'font-sans'}`} title={value}>{value}</code>
        <CopyButton text={value} copied={copied} onCopy={onCopy} />
      </div>
    </div>
  )
}

function CodeBlock({ code, copied, onCopy }) {
  return (
    <div className="relative group">
      <pre className="bg-bg-main border border-border-main rounded-xl p-4 text-[11.5px] leading-relaxed font-mono text-text-main overflow-x-auto whitespace-pre">
        {code}
      </pre>
      <div className="absolute top-2 right-2 bg-bg-card border border-border-main rounded-lg shadow-sm">
        <CopyButton text={code} copied={copied} onCopy={onCopy} />
      </div>
    </div>
  )
}

export default function McpPanel() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [showKey, setShowKey] = useState(false)
  const [copied, setCopied] = useState('')
  const [configTab, setConfigTab] = useState('json')
  const [panelTab, setPanelTab] = useState('overview')
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [confirmRegen, setConfirmRegen] = useState(false)
  const [keyNotice, setKeyNotice] = useState('')
  const [scopeTab, setScopeTab] = useState('groups')
  const [groupsAll, setGroupsAll] = useState(true)
  const [friendsAll, setFriendsAll] = useState(true)
  const [selectedGroups, setSelectedGroups] = useState(new Set())
  const [selectedFriends, setSelectedFriends] = useState(new Set())
  const [scopeQuery, setScopeQuery] = useState('')
  const [scopeRightQuery, setScopeRightQuery] = useState('')
  const [scopeNotice, setScopeNotice] = useState('')
  const [syncError, setSyncError] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [leftChecked, setLeftChecked] = useState(new Set())
  const [rightChecked, setRightChecked] = useState(new Set())

  const applyScope = useCallback((scope) => {
    const decode = (raw) => {
      try {
        return decodeURIComponent(raw)
      } catch {
        return raw
      }
    }
    const parse = (raw) => new Set(
      raw && raw !== '*' && raw !== 'none'
        ? raw.split(',').map(decode).filter(Boolean)
        : []
    )
    setGroupsAll((scope?.groups || '*') === '*')
    setFriendsAll((scope?.friends || '*') === '*')
    setSelectedGroups(parse(scope?.groups))
    setSelectedFriends(parse(scope?.friends))
  }, [])

  const load = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/mcp'))
      const json = await res.json()
      if (!json.ok) throw new Error(json.error || '加载失败')
      setData(json)
      applyScope(json.scope)
      setError('')
    } catch (e) {
      setError(friendlyError(e, '无法连接后端服务'))
    } finally {
      setLoading(false)
    }
  }, [applyScope])

  useEffect(() => { load() }, [load])

  const copyText = useCallback(async (text) => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      const area = document.createElement('textarea')
      area.value = text
      document.body.appendChild(area)
      area.select()
      document.execCommand('copy')
      document.body.removeChild(area)
    }
    setCopied(text)
    setTimeout(() => setCopied(''), 1500)
  }, [])

  async function save(payload) {
    setSaving(true)
    try {
      const res = await fetch(apiUrl('/api/mcp'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const json = await res.json()
      if (!json.ok) throw new Error(json.error || '保存失败')
      setData(json)
      setError('')
      setTestResult(null)
      return json
    } catch (e) {
      setError(friendlyError(e, '保存失败'))
      return null
    } finally {
      setSaving(false)
    }
  }

  async function regenerateKey() {
    setConfirmRegen(false)
    const json = await save({ regenerate: true })
    if (json?.api_key) {
      setShowKey(true)
      copyText(json.api_key)
      setKeyNotice('已生成并复制新密钥，旧密钥立即失效')
      setTimeout(() => setKeyNotice(''), 6000)
    }
  }

  function buildScopeValue(all, selected) {
    if (all) return '*'
    if (selected.size === 0) return 'none'
    return [...selected].map((id) => encodeURIComponent(id)).join(',')
  }

  async function saveScope() {
    const json = await save({
      groups: buildScopeValue(groupsAll, selectedGroups),
      friends: buildScopeValue(friendsAll, selectedFriends),
    })
    if (json) {
      applyScope(json.scope)
      setScopeNotice('数据范围已保存，智能体下次调用立即生效')
      setTimeout(() => setScopeNotice(''), 5000)
    }
  }

  async function syncWechatData() {
    setSyncing(true)
    setSyncError('')
    try {
      const res = await fetch(apiUrl('/api/wechat/sync'), { method: 'POST' })
      const json = await res.json()
      if (!json.ok) {
        setSyncError(
          json.need_key
            ? '未获取到微信数据库密钥：请先到「运行状态」点击「重新获取密钥」（无需启动机器人），再回来同步。'
            : (json.error || '同步失败，请稍后重试')
        )
        return
      }
      await load()
      setScopeNotice(`已同步：${json.groups} 个群聊、${json.friends} 位好友`)
      setTimeout(() => setScopeNotice(''), 6000)
    } catch (e) {
      setSyncError(friendlyError(e, '同步失败'))
    } finally {
      setSyncing(false)
    }
  }

  async function testConnection() {
    if (!data?.endpoint || !data?.api_key) {
      setTestResult({ ok: false, message: '请先生成 API Key' })
      return
    }
    setTesting(true)
    setTestResult(null)
    const headers = {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
      Authorization: `Bearer ${data.api_key}`,
    }
    try {
      const initRes = await fetch(data.endpoint, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: 1,
          method: 'initialize',
          params: {
            protocolVersion: '2025-06-18',
            capabilities: {},
            clientInfo: { name: 'WeChatBot-ui', version: '1.0.0' },
          },
        }),
      })
      const init = await initRes.json()
      if (!initRes.ok || init.error) {
        throw new Error(init.error?.message || init.error || `HTTP ${initRes.status}`)
      }
      const listRes = await fetch(data.endpoint, {
        method: 'POST',
        headers,
        body: JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/list', params: {} }),
      })
      const list = await listRes.json()
      if (!listRes.ok || list.error) {
        throw new Error(list.error?.message || list.error || `HTTP ${listRes.status}`)
      }
      setTestResult({
        ok: true,
        message: `连接成功：${init.result?.serverInfo?.name || 'MCP'}，可用工具 ${list.result?.tools?.length || 0} 个`,
      })
    } catch (e) {
      setTestResult({ ok: false, message: `连接失败：${e.message || e}` })
    } finally {
      setTesting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-text-muted">
        <Spinner size={22} weight="bold" className="animate-spin text-brand-green mr-3" />
        <span className="text-xs font-mono">正在加载 MCP 配置...</span>
      </div>
    )
  }

  const endpoint = data?.endpoint || 'http://127.0.0.1:7327/mcp'
  const sseEndpoint = data?.sse_endpoint || 'http://127.0.0.1:7327/mcp/sse'
  const apiKey = data?.api_key || '<API_KEY>'
  const tools = data?.tools || []
  const displayedKey = showKey || !data?.api_key ? apiKey : data?.api_key_masked

  const scopeIsGroups = scopeTab === 'groups'
  const scopeGroups = data?.scope_options?.groups || []
  const scopeFriends = data?.scope_options?.friends || []
  const scopeItems = scopeIsGroups ? scopeGroups : scopeFriends
  const scopeAll = scopeIsGroups ? groupsAll : friendsAll
  const setScopeAll = scopeIsGroups ? setGroupsAll : setFriendsAll
  const scopeSelection = scopeIsGroups ? selectedGroups : selectedFriends
  const setScopeSelection = scopeIsGroups ? setSelectedGroups : setSelectedFriends
  const scopeItemId = (item) => (scopeIsGroups ? item.chat_id : item.wxid)
  const scopeKeyword = scopeQuery.trim().toLowerCase()
  const scopeRightKeyword = scopeRightQuery.trim().toLowerCase()
  const matchScopeKeyword = (item, keyword) => {
    if (!keyword) return true
    const text = scopeIsGroups
      ? `${item.name || ''} ${item.chat_id || ''}`
      : `${item.name || ''} ${item.alias || ''} ${item.wxid || ''}`
    return text.toLowerCase().includes(keyword)
  }

  const scopeLeftItems = (scopeAll ? [] : scopeItems)
    .filter((item) => !scopeSelection.has(scopeItemId(item)))
    .filter((item) => matchScopeKeyword(item, scopeKeyword))
  const scopeRightItems = scopeAll
    ? scopeItems
    : scopeItems.filter((item) => scopeSelection.has(scopeItemId(item)))
  const scopeOrphans = scopeAll
    ? []
    : [...scopeSelection].filter((id) => !scopeItems.some((item) => scopeItemId(item) === id))
  const scopeRightVisibleItems = scopeRightItems.filter((item) => matchScopeKeyword(item, scopeRightKeyword))
  const scopeRightVisibleOrphans = scopeOrphans
    .filter((id) => !scopeRightKeyword || id.toLowerCase().includes(scopeRightKeyword))
  const scopeLeftKeys = scopeLeftItems.map(scopeItemId)
  const scopeRightKeys = [...scopeRightItems.map(scopeItemId), ...scopeOrphans]
  const scopeRightVisibleKeys = [...scopeRightVisibleItems.map(scopeItemId), ...scopeRightVisibleOrphans]
  const scopeLeftCheckedVisible = scopeLeftKeys.filter((id) => leftChecked.has(id))
  const scopeRightCheckedVisible = scopeRightVisibleKeys.filter((id) => rightChecked.has(id))
  const scopeAllLeftChecked = scopeLeftKeys.length > 0
    && scopeLeftCheckedVisible.length === scopeLeftKeys.length

  function moveToAllowed(ids) {
    if (!ids.length) return
    setScopeSelection((prev) => {
      const next = new Set(prev)
      ids.forEach((id) => next.add(id))
      return next
    })
    setLeftChecked(new Set())
  }

  function moveToBlocked(ids) {
    if (!ids.length) return
    if (scopeAll) {
      setScopeAll(false)
      const blocked = new Set(ids)
      setScopeSelection(new Set(scopeItems.map(scopeItemId).filter((id) => !blocked.has(id))))
    } else {
      setScopeSelection((prev) => {
        const next = new Set(prev)
        ids.forEach((id) => next.delete(id))
        return next
      })
    }
    setRightChecked(new Set())
  }

  function toggleAllVisible(next) {
    setScopeAll(next)
    setLeftChecked(new Set())
    setRightChecked(new Set())
    if (!next && scopeSelection.size === 0) {
      setScopeSelection(new Set(scopeItems.map(scopeItemId)))
    }
  }

  function clearAllowed() {
    setScopeAll(false)
    setScopeSelection(new Set())
    setRightChecked(new Set())
  }

  const jsonConfig = JSON.stringify({
    mcpServers: {
      WeChatBot: {
        url: endpoint,
        headers: { Authorization: `Bearer ${apiKey}` },
      },
    },
  }, null, 2)

  const sseConfig = JSON.stringify({
    mcpServers: {
      WeChatBot: {
        url: sseEndpoint,
        headers: { Authorization: `Bearer ${apiKey}` },
      },
    },
  }, null, 2)

  const stdioConfig = JSON.stringify({
    mcpServers: {
      WeChatBot: {
        command: 'npx',
        args: [
          '-y', 'mcp-remote', endpoint,
          '--header', `Authorization: Bearer ${apiKey}`,
        ],
      },
    },
  }, null, 2)

  const codexConfig = [
    '# ~/.codex/config.toml',
    '[mcp_servers.WeChatBot]',
    'command = "npx"',
    'args = [',
    '  "-y", "mcp-remote",',
    `  "${endpoint}",`,
    `  "--header", "Authorization: Bearer ${apiKey}",`,
    ']',
  ].join('\n')

  const curlConfig = [
    `curl -X POST "${endpoint}" \\`,
    `  -H "Authorization: Bearer ${apiKey}" \\`,
    '  -H "Content-Type: application/json" \\',
    '  -H "Accept: application/json, text/event-stream" \\',
    `  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'`,
  ].join('\n')

  const toolNames = tools.map((tool) => tool.name).join(', ')
  const fullConfig = [
    '# Webot MCP 配置（粘贴到其他智能体即可使用）',
    '',
    '## 连接信息',
    `请求地址（Streamable HTTP）：${endpoint}`,
    `兼容 SSE 地址：${sseEndpoint}`,
    `API Key：${apiKey}`,
    `请求头：Authorization: Bearer ${apiKey}（或 X-API-Key: ${apiKey}）`,
    `可用工具（${tools.length} 个）：${toolNames}`,
    '',
    '## Trae / Claude Code / Cursor 等（mcpServers JSON）',
    jsonConfig,
    '',
    '## Claude Desktop 等仅支持 stdio 的客户端（mcp-remote 桥接）',
    stdioConfig,
    '',
    '## Codex（~/.codex/config.toml）',
    codexConfig,
    '',
    '## 旧版 SSE 客户端',
    sseConfig,
    '',
    '## curl 自测',
    curlConfig,
  ].join('\n')

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold text-text-main flex items-center gap-2">
            <Plug size={18} weight="fill" className="text-brand-green" />
            MCP 服务
          </h3>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-4 py-2 rounded-full border border-border-main bg-bg-card text-xs font-semibold text-text-muted hover:text-text-main transition-colors cursor-pointer"
        >
          <ArrowClockwise size={14} /> 刷新
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-[#d45656]/10 border border-[#d45656]/20 text-[#d45656] text-xs">
          <WarningCircle size={16} weight="fill" /> {error}
        </div>
      )}

      <div className="flex items-center gap-1 bg-bg-card border border-border-main rounded-full p-1 w-fit">
        {[
          { id: 'overview', label: '概览' },
          { id: 'scope', label: '数据范围' },
          { id: 'clients', label: '客户端配置' },
          { id: 'tools', label: '工具清单', count: tools.length },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setPanelTab(tab.id)}
            className={`px-4 py-2 rounded-full text-[11.5px] font-semibold transition-colors cursor-pointer ${
              panelTab === tab.id
                ? 'bg-brand-green-light text-brand-green-hover dark:text-brand-green'
                : 'text-text-muted hover:text-text-main'
            }`}
          >
            {tab.label}
            {tab.count != null && <span className="ml-1.5 font-mono text-[10px] opacity-70">{tab.count}</span>}
          </button>
        ))}
      </div>

      {panelTab === 'overview' && (<>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          className="bg-bg-card border border-border-main rounded-2xl p-5"
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[11px] text-text-muted font-mono font-semibold uppercase tracking-wide">服务状态</p>
              <p className={`text-lg font-bold mt-1 ${data?.enabled ? 'text-brand-green' : 'text-text-muted'}`}>
                {data?.enabled ? '已启用' : '已停用'}
              </p>
            </div>
            <Toggle
              enabled={!!data?.enabled}
              disabled={saving}
              onChange={(next) => save({ enabled: next })}
            />
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
          className="bg-bg-card border border-border-main rounded-2xl p-5"
        >
          <p className="text-[11px] text-text-muted font-mono font-semibold uppercase tracking-wide">传输协议</p>
          <p className="text-lg font-bold mt-1 text-text-main">Streamable HTTP</p>
          <p className="text-[11px] text-text-muted font-mono mt-1">兼容旧版 SSE</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
          className="bg-bg-card border border-border-main rounded-2xl p-5"
        >
          <p className="text-[11px] text-text-muted font-mono font-semibold uppercase tracking-wide">可用工具</p>
          <p className="text-lg font-bold mt-1 text-text-main">{tools.length} 个</p>
          <p className="text-[11px] text-text-muted font-mono mt-1">群聊 / 成员 / 好友 / 消息 / 活跃度</p>
        </motion.div>
      </div>

      <div className="bg-bg-card border border-border-main rounded-2xl p-6">
        <h4 className="text-sm font-semibold text-text-main mb-2 flex items-center gap-2">
          <Key size={16} weight="fill" className="text-brand-green" /> 连接信息
        </h4>
        <InfoRow label="请求地址" value={endpoint} copied={copied === endpoint} onCopy={copyText} />
        <InfoRow label="SSE 地址（兼容）" value={sseEndpoint} copied={copied === sseEndpoint} onCopy={copyText} />
        <div className="flex items-center justify-between gap-4 py-3">
          <span className="text-[11px] text-text-muted font-semibold font-mono uppercase tracking-wide shrink-0">API Key</span>
          <div className="flex items-center gap-1.5 min-w-0">
            <code className="text-xs text-text-main font-mono truncate" title={displayedKey}>{displayedKey || '未生成'}</code>
            <button
              onClick={() => setShowKey((v) => !v)}
              className="p-1.5 rounded-lg text-text-muted hover:text-text-main hover:bg-bg-raised transition-colors cursor-pointer"
              title={showKey ? '隐藏' : '显示'}
            >
              {showKey ? <EyeSlash size={15} /> : <Eye size={15} />}
            </button>
            {data?.api_key && <CopyButton text={data.api_key} copied={copied === data.api_key} onCopy={copyText} />}
            <button
              onClick={() => setConfirmRegen(true)}
              disabled={saving}
              title="生成一组新的随机密钥，旧密钥立即失效"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border-main text-[11px] font-semibold text-text-muted hover:text-text-main transition-colors cursor-pointer disabled:opacity-50"
            >
              <ArrowClockwise size={13} /> 轮换密钥
            </button>
          </div>
        </div>
        <p className="text-[11px] text-text-muted/90 leading-relaxed mt-2">
          请求头使用 <code className="font-mono">Authorization: Bearer &lt;API_KEY&gt;</code> 或
          <code className="font-mono"> X-API-Key: &lt;API_KEY&gt;</code>。服务仅建议在本机或可信内网使用。
        </p>
        {keyNotice && (
          <p className="flex items-center gap-1.5 text-[11px] font-semibold text-brand-green mt-2">
            <CheckCircle size={13} weight="fill" /> {keyNotice}
          </p>
        )}
      </div>
      </>)}

      {panelTab === 'scope' && (
      <div className="bg-bg-card border border-border-main rounded-2xl p-6">
        <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
          <div>
            <h4 className="text-sm font-semibold text-text-main flex items-center gap-2">
              <ListChecks size={16} weight="fill" className="text-brand-green" /> 数据范围
            </h4>
            <p className="text-[11px] text-text-muted mt-1 leading-relaxed">
              控制智能体通过 MCP 能读取哪些群聊和好友的聊天内容，默认全部可见；
              未勾选的会话不会出现在任何工具结果中。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3 shrink-0">
            <button
              type="button"
              onClick={syncWechatData}
              disabled={syncing}
              title="不启动机器人，读取微信通讯录并刷新群聊/好友列表"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-border-main bg-bg-main text-[11px] font-semibold text-text-muted hover:text-text-main transition-colors cursor-pointer disabled:opacity-50"
            >
              {syncing ? <Spinner size={13} weight="bold" className="animate-spin" /> : <ArrowClockwise size={13} />}
              {syncing ? '同步中...' : '同步微信数据'}
            </button>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-semibold text-text-muted">全部可见</span>
              <Toggle enabled={scopeAll} disabled={saving} onChange={toggleAllVisible} />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1 bg-bg-main border border-border-main rounded-full p-1 w-fit mb-4">
          {[
            { id: 'groups', label: '群聊', count: scopeGroups.length },
            { id: 'friends', label: '好友', count: scopeFriends.length },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                setScopeTab(tab.id)
                setScopeQuery('')
                setScopeRightQuery('')
                setLeftChecked(new Set())
                setRightChecked(new Set())
              }}
              className={`px-4 py-1.5 rounded-full text-[11px] font-semibold transition-colors cursor-pointer ${
                scopeTab === tab.id
                  ? 'bg-brand-green-light text-brand-green-hover dark:text-brand-green'
                  : 'text-text-muted hover:text-text-main'
              }`}
            >
              {tab.label}
              <span className="ml-1.5 font-mono text-[10px] opacity-70">{tab.count}</span>
            </button>
          ))}
        </div>

        {syncError && (
          <p className="mb-3 px-3 py-2 rounded-lg bg-[#d45656]/10 border border-[#d45656]/20 text-[11px] text-[#d45656] leading-relaxed">
            {syncError}
          </p>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto_1fr] gap-3">
          {/* 左侧：未允许 */}
          <div className="rounded-xl border border-border-main bg-bg-raised overflow-hidden flex flex-col h-[360px]">
            <div className="flex items-center gap-2 px-3 h-10 border-b border-border-main/70 shrink-0">
              {scopeIsGroups
                ? <ChatCircleDots size={14} weight="fill" className="text-text-muted/70" />
                : <Users size={14} weight="fill" className="text-text-muted/70" />}
              <span className="text-[11.5px] font-semibold text-text-main">
                可选{scopeIsGroups ? '群聊' : '好友'}
              </span>
              <span className="font-mono text-[10px] text-text-muted">{scopeLeftItems.length}</span>
              <button
                type="button"
                onClick={() => {
                  setLeftChecked((prev) => {
                    const next = new Set(prev)
                    scopeLeftKeys.forEach((id) => {
                      if (scopeAllLeftChecked) next.delete(id)
                      else next.add(id)
                    })
                    return next
                  })
                }}
                disabled={scopeAll || scopeLeftKeys.length === 0}
                className="ml-auto text-[11px] text-brand-green-hover dark:text-brand-green hover:opacity-75 transition-opacity cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {scopeAllLeftChecked ? '取消全选' : '全选'}
              </button>
            </div>
            <div className="flex items-center gap-2 px-3 h-9 border-b border-border-main/70 shrink-0">
              <MagnifyingGlass size={13} className="text-text-muted/70 shrink-0" />
              <input
                type="text"
                value={scopeQuery}
                onChange={(e) => setScopeQuery(e.target.value)}
                placeholder={scopeIsGroups ? '搜索群名或群 ID' : '搜索昵称、备注或 wxid'}
                className="flex-1 min-w-0 bg-transparent text-[12px] text-text-main placeholder:text-text-muted/60 focus:outline-none"
              />
              {scopeQuery && (
                <button
                  type="button"
                  onClick={() => setScopeQuery('')}
                  title="清空搜索"
                  className="text-text-muted/70 hover:text-text-main transition-colors cursor-pointer"
                >
                  <X size={12} weight="bold" />
                </button>
              )}
            </div>
            <div className="flex-1 overflow-y-auto p-1.5">
              {scopeAll ? (
                <p className="px-2 py-4 text-[11px] text-text-muted leading-relaxed text-center">
                  全部{scopeIsGroups ? '群聊' : '好友'}已允许，无需选择
                </p>
              ) : scopeLeftItems.length === 0 ? (
                <p className="px-2 py-4 text-[11px] text-text-muted leading-relaxed text-center">
                  {scopeItems.length === 0
                    ? `暂无${scopeIsGroups ? '群聊' : '好友'}数据：点击右上角「同步微信数据」拉取通讯录`
                    : scopeKeyword
                      ? `没有匹配的${scopeIsGroups ? '群聊' : '好友'}`
                      : '已全部移到右侧'}
                </p>
              ) : scopeLeftItems.map((item) => {
                const id = scopeItemId(item)
                const checked = leftChecked.has(id)
                const primary = scopeIsGroups ? (item.name || id) : (item.name || item.alias || id)
                const sub = scopeIsGroups
                  ? `${item.chat_id}${item.member_count ? ` · ${item.member_count} 人` : ''}`
                  : [item.alias && item.alias !== item.name ? item.alias : '', item.wxid].filter(Boolean).join(' · ')
                return (
                  <div
                    key={id}
                    onClick={() => {
                      setLeftChecked((prev) => {
                        const next = new Set(prev)
                        if (next.has(id)) next.delete(id)
                        else next.add(id)
                        return next
                      })
                    }}
                    onDoubleClick={() => moveToAllowed([id])}
                    className={`flex items-center gap-2.5 px-2 py-1.5 rounded-lg cursor-pointer select-none transition-colors ${
                      checked ? 'bg-[#4C9B72]/10' : 'hover:bg-bg-card'
                    }`}
                  >
                    <span className={`w-4 h-4 shrink-0 rounded border flex items-center justify-center ${
                      checked ? 'bg-brand-green border-brand-green text-[#04130d]' : 'border-border-main'
                    }`}>
                      {checked && <Check size={10} weight="bold" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5 min-w-0">
                        <span className="text-[12.5px] text-text-main truncate">{primary}</span>
                        {item.active === false && (
                          <span className="shrink-0 px-1 py-px rounded border border-[#c37d0d]/25 bg-[#c37d0d]/10 text-[10px] leading-4 text-[#a06a0a]">
                            {scopeIsGroups ? '已退出' : '已不是好友'}
                          </span>
                        )}
                      </span>
                      {sub && <span className="block text-[10.5px] text-text-muted/80 font-mono truncate">{sub}</span>}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* 中间：移动按钮 */}
          <div className="flex lg:flex-col items-center justify-center gap-2">
            <button
              type="button"
              onClick={() => moveToAllowed(scopeLeftCheckedVisible)}
              disabled={scopeLeftCheckedVisible.length === 0}
              title="加入允许名单"
              className="w-9 h-9 rounded-full border border-border-main bg-bg-card text-text-main flex items-center justify-center hover:border-brand-green hover:text-brand-green transition-colors cursor-pointer disabled:opacity-35 disabled:cursor-not-allowed"
            >
              <ArrowRight size={15} weight="bold" />
            </button>
            <button
              type="button"
              onClick={() => moveToBlocked(scopeRightCheckedVisible)}
              disabled={scopeRightCheckedVisible.length === 0}
              title="移出允许名单"
              className="w-9 h-9 rounded-full border border-border-main bg-bg-card text-text-main flex items-center justify-center hover:border-brand-green hover:text-brand-green transition-colors cursor-pointer disabled:opacity-35 disabled:cursor-not-allowed"
            >
              <ArrowLeft size={15} weight="bold" />
            </button>
          </div>

          {/* 右侧：已允许 */}
          <div className="rounded-xl border border-border-main bg-bg-raised overflow-hidden flex flex-col h-[360px]">
            <div className="flex items-center gap-2 px-3 h-10 border-b border-border-main/70 shrink-0">
              <CheckCircle size={14} weight="fill" className="text-brand-green" />
              <span className="text-[11.5px] font-semibold text-text-main">允许访问</span>
              <span className="font-mono text-[10px] text-text-muted">
                {scopeAll ? `全部 ${scopeItems.length}` : scopeRightKeys.length}
              </span>
              <button
                type="button"
                onClick={clearAllowed}
                disabled={scopeRightKeys.length === 0}
                className="ml-auto text-[11px] text-text-muted hover:text-text-main transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              >
                清空
              </button>
            </div>
            <div className="flex items-center gap-2 px-3 h-9 border-b border-border-main/70 shrink-0">
              <MagnifyingGlass size={13} className="text-text-muted/70 shrink-0" />
              <input
                type="text"
                value={scopeRightQuery}
                onChange={(e) => setScopeRightQuery(e.target.value)}
                placeholder={scopeIsGroups ? '搜索已允许的群名或群 ID' : '搜索昵称、备注或 wxid'}
                className="flex-1 min-w-0 bg-transparent text-[12px] text-text-main placeholder:text-text-muted/60 focus:outline-none"
              />
              {scopeRightQuery && (
                <button
                  type="button"
                  onClick={() => setScopeRightQuery('')}
                  title="清空搜索"
                  className="text-text-muted/70 hover:text-text-main transition-colors cursor-pointer"
                >
                  <X size={12} weight="bold" />
                </button>
              )}
            </div>
            <div className="flex-1 overflow-y-auto p-1.5">
              {scopeRightKeys.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center gap-1.5 px-4 text-center">
                  <ListChecks size={22} className="text-text-muted/40" />
                  <p className="text-[11.5px] font-semibold text-text-muted">名单为空</p>
                  <p className="text-[10.5px] text-text-muted/70 leading-relaxed">
                    保存后智能体将无法读取任何{scopeIsGroups ? '群聊' : '好友'}内容
                  </p>
                </div>
              ) : scopeRightVisibleKeys.length === 0 ? (
                <p className="px-2 py-4 text-[11px] text-text-muted leading-relaxed text-center">
                  没有匹配的{scopeIsGroups ? '群聊' : '好友'}
                </p>
              ) : (<>
                {scopeRightVisibleItems.map((item) => {
                  const id = scopeItemId(item)
                  const checked = rightChecked.has(id)
                  const primary = scopeIsGroups ? (item.name || id) : (item.name || item.alias || id)
                  const sub = scopeIsGroups
                    ? `${item.chat_id}${item.member_count ? ` · ${item.member_count} 人` : ''}`
                    : [item.alias && item.alias !== item.name ? item.alias : '', item.wxid].filter(Boolean).join(' · ')
                  return (
                    <div
                      key={id}
                      onClick={() => {
                        setRightChecked((prev) => {
                          const next = new Set(prev)
                          if (next.has(id)) next.delete(id)
                          else next.add(id)
                          return next
                        })
                      }}
                      onDoubleClick={() => moveToBlocked([id])}
                      className={`group flex items-center gap-2.5 px-2 py-1.5 rounded-lg cursor-pointer select-none transition-colors ${
                        checked ? 'bg-[#d45656]/10' : 'hover:bg-bg-card'
                      }`}
                    >
                      <span className={`w-4 h-4 shrink-0 rounded border flex items-center justify-center ${
                        checked ? 'bg-[#d45656] border-[#d45656] text-white' : 'bg-brand-green border-brand-green text-[#04130d]'
                      }`}>
                        {checked ? <X size={9} weight="bold" /> : <Check size={10} weight="bold" />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5 min-w-0">
                          <span className="text-[12.5px] text-text-main truncate">{primary}</span>
                          {item.active === false && (
                            <span className="shrink-0 px-1 py-px rounded border border-[#c37d0d]/25 bg-[#c37d0d]/10 text-[10px] leading-4 text-[#a06a0a]">
                              {scopeIsGroups ? '已退出' : '已不是好友'}
                            </span>
                          )}
                        </span>
                        {sub && <span className="block text-[10.5px] text-text-muted/80 font-mono truncate">{sub}</span>}
                      </span>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); moveToBlocked([id]) }}
                        title="移出允许名单"
                        className="p-1 rounded text-text-muted/50 hover:text-[#d45656] transition-colors cursor-pointer"
                      >
                        <X size={12} weight="bold" />
                      </button>
                    </div>
                  )
                })}
                {scopeRightVisibleOrphans.map((id) => {
                  const checked = rightChecked.has(id)
                  return (
                    <div
                      key={id}
                      onClick={() => {
                        setRightChecked((prev) => {
                          const next = new Set(prev)
                          if (next.has(id)) next.delete(id)
                          else next.add(id)
                          return next
                        })
                      }}
                      onDoubleClick={() => moveToBlocked([id])}
                      className={`flex items-center gap-2.5 px-2 py-1.5 rounded-lg cursor-pointer select-none transition-colors ${
                        checked ? 'bg-[#d45656]/10' : 'hover:bg-bg-card'
                      }`}
                    >
                      <span className="w-4 h-4 shrink-0 rounded border bg-brand-green border-brand-green text-[#04130d] flex items-center justify-center">
                        <Check size={10} weight="bold" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-[12.5px] text-text-main truncate font-mono">{id}</span>
                        <span className="block text-[10.5px] text-text-muted/80">不在当前列表中，仍被允许</span>
                      </span>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); moveToBlocked([id]) }}
                        title="移出允许名单"
                        className="p-1 rounded text-text-muted/50 hover:text-[#d45656] transition-colors cursor-pointer"
                      >
                        <X size={12} weight="bold" />
                      </button>
                    </div>
                  )
                })}
              </>)}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 mt-4">
          <p className="text-[11px] text-text-muted leading-relaxed">
            群聊：{groupsAll ? `全部 ${scopeGroups.length} 个` : `已选 ${selectedGroups.size} / ${scopeGroups.length} 个`}
            <span className="mx-2 opacity-40">·</span>
            好友：{friendsAll ? `全部 ${scopeFriends.length} 个` : `已选 ${selectedFriends.size} / ${scopeFriends.length} 个`}
            {((!groupsAll && selectedGroups.size === 0) || (!friendsAll && selectedFriends.size === 0)) && (
              <span className="text-[#d45656] font-semibold ml-2">未勾选的类别将不可访问</span>
            )}
          </p>
          <div className="flex items-center gap-3">
            {scopeNotice && (
              <span className="flex items-center gap-1.5 text-[11px] font-semibold text-brand-green">
                <CheckCircle size={13} weight="fill" /> {scopeNotice}
              </span>
            )}
            <button
              onClick={saveScope}
              disabled={saving}
              className="flex items-center gap-2 px-4 py-2 rounded-full bg-brand-green text-[#04130d] text-xs font-bold hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50"
            >
              {saving ? <Spinner size={14} weight="bold" className="animate-spin" /> : <CheckCircle size={14} weight="fill" />}
              保存数据范围
            </button>
          </div>
        </div>
      </div>
      )}

      {panelTab === 'clients' && (
      <div className="bg-bg-card border border-border-main rounded-2xl p-6">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h4 className="text-sm font-semibold text-text-main flex items-center gap-2">
            <Terminal size={16} weight="fill" className="text-brand-green" /> 客户端配置
          </h4>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 bg-bg-main border border-border-main rounded-full p-1">
              {[
                { id: 'json', label: 'Trae / 通用 JSON' },
                { id: 'stdio', label: 'Claude Desktop' },
                { id: 'codex', label: 'Codex TOML' },
                { id: 'sse', label: '旧版 SSE' },
                { id: 'curl', label: 'curl 自测' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setConfigTab(tab.id)}
                  className={`px-3 py-1.5 rounded-full text-[11px] font-semibold transition-colors cursor-pointer ${
                    configTab === tab.id ? 'bg-brand-green-light text-brand-green-hover dark:text-brand-green' : 'text-text-muted hover:text-text-main'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <button
              onClick={() => copyText(fullConfig)}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-brand-green text-[#04130d] text-[11px] font-bold hover:opacity-90 transition-opacity cursor-pointer"
              title="复制地址、API Key 与各客户端完整配置"
            >
              {copied === fullConfig ? <CheckCircle size={14} weight="fill" /> : <Copy size={14} weight="bold" />}
              {copied === fullConfig ? '已复制' : '一键复制全部配置'}
            </button>
          </div>
        </div>
        {configTab === 'json' && <CodeBlock code={jsonConfig} copied={copied === jsonConfig} onCopy={copyText} />}
        {configTab === 'stdio' && <CodeBlock code={stdioConfig} copied={copied === stdioConfig} onCopy={copyText} />}
        {configTab === 'codex' && <CodeBlock code={codexConfig} copied={copied === codexConfig} onCopy={copyText} />}
        {configTab === 'sse' && <CodeBlock code={sseConfig} copied={copied === sseConfig} onCopy={copyText} />}
        {configTab === 'curl' && <CodeBlock code={curlConfig} copied={copied === curlConfig} onCopy={copyText} />}
        <p className="text-[11px] text-text-muted/90 mt-3 leading-relaxed">
          点「一键复制全部配置」可一次拿到地址、密钥与全部客户端配置，直接粘贴给 Codex、Trae 等智能体。
          Trae 可把 JSON 合并到项目 <code className="font-mono">.trae/mcp.json</code> 或全局 MCP 配置；
          Claude Desktop 等仅支持 stdio 的客户端使用 <code className="font-mono">mcp-remote</code> 桥接；
          Codex 把 TOML 追加到 <code className="font-mono">~/.codex/config.toml</code> 后运行
          <code className="font-mono"> codex mcp list</code> 验证。
        </p>
      </div>
      )}

      {panelTab === 'overview' && (
      <div className="bg-bg-card border border-border-main rounded-2xl p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold text-text-main flex items-center gap-2">
              <CheckCircle size={16} weight="fill" className="text-brand-green" /> 连接测试
            </h4>
            <p className="text-[11px] text-text-muted mt-1">使用当前地址与密钥发起一次真实的 MCP 握手。</p>
          </div>
          <button
            onClick={testConnection}
            disabled={testing}
            className="flex items-center gap-2 px-4 py-2 rounded-full bg-brand-green text-[#04130d] text-xs font-bold hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50"
          >
            {testing ? <Spinner size={14} weight="bold" className="animate-spin" /> : <Plug size={14} weight="fill" />}
            {testing ? '测试中...' : '测试连接'}
          </button>
        </div>
        {testResult && (
          <div className={`flex items-center gap-2 mt-3 text-xs font-medium ${
            testResult.ok ? 'text-brand-green' : 'text-[#d45656]'
          }`}>
            {testResult.ok ? <CheckCircle size={15} weight="fill" /> : <XCircle size={15} weight="fill" />}
            {testResult.message}
          </div>
        )}
      </div>
      )}

      {panelTab === 'tools' && (
      <div className="bg-bg-card border border-border-main rounded-2xl p-6">
        <h4 className="text-sm font-semibold text-text-main flex items-center gap-2 mb-1">
          <ListChecks size={16} weight="fill" className="text-brand-green" /> 工具清单
        </h4>
        <p className="text-[11px] text-text-muted mb-4 leading-relaxed">
          智能体可在 <code className="font-mono">tools/list</code> 中发现这些工具。建议先调用
          <code className="font-mono"> get_data_overview</code> 了解数据范围。
        </p>
        <div className="divide-y divide-border-main">
          {tools.map((tool) => {
            const props = tool.input_schema?.properties || {}
            const required = tool.input_schema?.required || []
            return (
              <details key={tool.name} className="group py-3">
                <summary className="flex items-center gap-2 cursor-pointer list-none">
                  <code className="text-xs font-mono font-semibold text-brand-green">{tool.name}</code>
                  <span className="text-[11px] text-text-muted flex-1 truncate">{tool.description}</span>
                  <span className="text-[10px] text-text-muted/70 font-mono shrink-0 group-open:hidden">展开</span>
                  <span className="text-[10px] text-text-muted/70 font-mono shrink-0 hidden group-open:inline">收起</span>
                </summary>
                <div className="mt-2 pl-1">
                  <p className="text-[11px] text-text-muted leading-relaxed">{tool.description}</p>
                  {Object.keys(props).length > 0 ? (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {Object.entries(props).map(([name, schema]) => (
                        <span
                          key={name}
                          className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${
                            required.includes(name)
                              ? 'border-brand-green/30 text-brand-green bg-brand-green/5'
                              : 'border-border-main text-text-muted'
                          }`}
                          title={schema.description || ''}
                        >
                          {name}{required.includes(name) ? '*' : ''}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[10px] text-text-muted/70 font-mono mt-1">无参数</p>
                  )}
                </div>
              </details>
            )
          })}
        </div>
      </div>
      )}

      <ConfirmDialog
        open={confirmRegen}
        danger
        busy={saving}
        title="轮换 API Key？"
        description="将立即生成一组新的随机密钥，旧密钥马上失效；所有已配置的智能体需要更新为新密钥，新密钥会自动复制到剪贴板。"
        confirmLabel="生成新密钥"
        onCancel={() => setConfirmRegen(false)}
        onConfirm={regenerateKey}
      />
    </div>
  )
}
