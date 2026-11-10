import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowClockwise, CaretDown, CaretLeft, CaretRight, ChartBar, ChartLine,
  Coins, Receipt, Spinner, Trash, WarningCircle,
} from '@phosphor-icons/react'
import { ConfirmDialog } from './SharedComponents'

const RANGE_OPTIONS = [
  { id: 'today', label: '今日' },
  { id: '7d', label: '近 7 天' },
  { id: '30d', label: '近 30 天' },
  { id: 'all', label: '全部' },
]

const TABS = [
  { id: 'trend', label: '消耗趋势', icon: ChartLine },
  { id: 'models', label: '模型分布', icon: ChartBar },
  { id: 'logs', label: '请求日志', icon: Receipt },
]

const STATUS_OPTIONS = [
  { id: '', label: '全部状态' },
  { id: 'success', label: '成功' },
  { id: 'error', label: '失败' },
]

const PAGE_SIZE = 15

function apiUrl(path) {
  if (window.location.port === '5173') return `http://127.0.0.1:7327${path}`
  return path
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-US')
}

function formatCompact(value) {
  const n = Number(value) || 0
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function formatDuration(ms) {
  const n = Number(ms) || 0
  if (n <= 0) return '—'
  if (n < 1000) return `${n}ms`
  return `${(n / 1000).toFixed(1)}s`
}

function percent(part, total) {
  if (!total) return '0%'
  return `${((part / total) * 100).toFixed(1)}%`
}

const ACCENTS = {
  green: {
    icon: 'bg-brand-green-light text-brand-green-hover border-brand-green/20 dark:bg-brand-green/10 dark:text-brand-green dark:border-brand-green/20',
    color: '#18E299',
  },
  blue: {
    icon: 'bg-blue-500/10 text-[#3772cf] border-blue-500/20',
    color: '#3772cf',
  },
  amber: {
    icon: 'bg-amber-500/10 text-[#c37d0d] border-amber-500/20',
    color: '#c37d0d',
  },
  rose: {
    icon: 'bg-rose-500/10 text-[#d45656] border-rose-500/20',
    color: '#d45656',
  },
}

function StatCard({ icon: Icon, label, value, sub, accent = 'green', delay = 0 }) {
  const style = ACCENTS[accent]
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay }}
      className="bg-bg-card border border-border-main rounded-2xl p-5 shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none"
    >
      <div className="flex items-start justify-between mb-3">
        <p className="text-[11px] text-text-muted font-semibold font-mono uppercase tracking-[0.6px]">{label}</p>
        <div className={`w-8 h-8 rounded-full flex items-center justify-center border ${style.icon}`}>
          <Icon size={15} weight="fill" />
        </div>
      </div>
      <p className="text-2xl font-bold tracking-tight font-mono text-text-main tabular-nums">{value}</p>
      {sub && <p className="text-[11px] text-text-muted/85 font-medium font-mono mt-1">{sub}</p>}
    </motion.div>
  )
}

// ── 折线图 ──────────────────────────────────────────────────────────

function buildSmoothPath(points) {
  if (!points.length) return ''
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`
  let d = `M ${points[0].x} ${points[0].y}`
  for (let i = 0; i < points.length - 1; i += 1) {
    const curr = points[i]
    const next = points[i + 1]
    const midX = curr.x + (next.x - curr.x) / 2
    d += ` C ${midX} ${curr.y}, ${midX} ${next.y}, ${next.x} ${next.y}`
  }
  return d
}

function TrendChart({ points, granularity }) {
  const [hoverIndex, setHoverIndex] = useState(null)

  const W = 840
  const H = 260
  const pad = { top: 18, right: 18, bottom: 30, left: 56 }
  const plotW = W - pad.left - pad.right
  const plotH = H - pad.top - pad.bottom

  if (!points || points.length === 0) {
    return <ChartEmpty />
  }

  const maxValue = Math.max(...points.map(p => p.total_tokens), 1)
  const lastIndex = Math.max(points.length - 1, 1)
  const coords = points.map((p, i) => ({
    x: pad.left + (i / lastIndex) * plotW,
    y: pad.top + plotH - (p.total_tokens / maxValue) * plotH,
  }))
  const linePath = buildSmoothPath(coords)
  const areaPath = `${linePath} L ${coords[coords.length - 1].x} ${pad.top + plotH} L ${coords[0].x} ${pad.top + plotH} Z`

  const yTicks = Array.from({ length: 5 }, (_, i) => maxValue * (i / 4))
  const tickCount = Math.min(7, points.length)
  const xTickIndexes = tickCount <= 1
    ? [0]
    : Array.from(new Set(
      Array.from({ length: tickCount }, (_, i) =>
        Math.round((i * (points.length - 1)) / (tickCount - 1)))
    ))

  function labelText(label) {
    if (granularity === 'hour') return label.split(' ')[1] || label
    return label.slice(5)
  }

  function handleMove(e) {
    const rect = e.currentTarget.getBoundingClientRect()
    if (!rect.width) return
    const ratio = (e.clientX - rect.left) / rect.width
    const chartX = ratio * W
    const idx = Math.round(((chartX - pad.left) / plotW) * lastIndex)
    setHoverIndex(Math.min(points.length - 1, Math.max(0, idx)))
  }

  const hover = hoverIndex !== null ? points[hoverIndex] : null
  const hoverCoord = hoverIndex !== null ? coords[hoverIndex] : null
  const tooltipLeft = hoverCoord ? Math.min(88, Math.max(12, (hoverCoord.x / W) * 100)) : 0

  return (
    <div className="relative select-none">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverIndex(null)}
      >
        <defs>
          <linearGradient id="token-area-gradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#18E299" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#18E299" stopOpacity="0" />
          </linearGradient>
        </defs>

        {yTicks.map((value, i) => {
          const y = pad.top + (i / 4) * plotH
          return (
            <g key={i}>
              <line
                x1={pad.left} y1={y} x2={W - pad.right} y2={y}
                stroke="var(--border-main)" strokeWidth="1"
                strokeDasharray={i === 4 ? '0' : '3 4'}
              />
              <text
                x={pad.left - 10} y={y + 3.5}
                textAnchor="end" fontSize="10"
                fill="var(--text-muted)" fontFamily="monospace"
              >
                {formatCompact(Math.round(value))}
              </text>
            </g>
          )
        })}

        <path d={areaPath} fill="url(#token-area-gradient)" />
        <path
          d={linePath} fill="none" stroke="#18E299"
          strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        />

        {xTickIndexes.map(idx => (
          <text
            key={idx}
            x={coords[idx].x} y={H - 9}
            textAnchor={idx === 0 ? 'start' : (idx === points.length - 1 ? 'end' : 'middle')}
            fontSize="10" fill="var(--text-muted)" fontFamily="monospace"
          >
            {labelText(points[idx].label)}
          </text>
        ))}

        {hoverCoord && (
          <g>
            <line
              x1={hoverCoord.x} y1={pad.top}
              x2={hoverCoord.x} y2={pad.top + plotH}
              stroke="var(--text-muted)" strokeWidth="1" strokeDasharray="3 3" opacity="0.5"
            />
            <circle cx={hoverCoord.x} cy={hoverCoord.y} r="4.5" fill="#18E299" stroke="var(--bg-card)" strokeWidth="2" />
          </g>
        )}
      </svg>

      {hover && (
        <div
          className="absolute z-20 pointer-events-none -translate-x-1/2 -translate-y-full rounded-xl border border-border-main bg-bg-card shadow-lg px-3.5 py-2.5 font-mono text-[11px]"
          style={{ left: `${tooltipLeft}%`, top: 14 }}
        >
          <p className="text-text-main font-semibold mb-1.5">{hover.label}</p>
          <div className="space-y-0.5 text-text-muted whitespace-nowrap">
            <p>合计 <span className="text-text-main font-semibold">{formatNumber(hover.total_tokens)}</span></p>
            <p>输入 <span className="text-[#18E299]">{formatNumber(hover.prompt_tokens)}</span> · 输出 <span className="text-[#3772cf]">{formatNumber(hover.completion_tokens)}</span></p>
            <p>请求 <span className="text-text-main">{formatNumber(hover.requests)}</span> 次</p>
          </div>
        </div>
      )}
    </div>
  )
}

function ChartEmpty() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <ChartLine size={34} weight="duotone" className="text-text-muted/40 mb-3" />
      <p className="text-sm font-semibold text-text-main font-mono">暂无 Token 消耗记录</p>
      <p className="text-xs text-text-muted mt-1.5">启动机器人后，每次 AI 请求都会自动记录在这里</p>
    </div>
  )
}

// ── 模型柱状图 ──────────────────────────────────────────────────────

function ModelBars({ models }) {
  const total = models.reduce((sum, m) => sum + m.total_tokens, 0)
  if (!models.length) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <ChartBar size={34} weight="duotone" className="text-text-muted/40 mb-3" />
        <p className="text-sm font-semibold text-text-main font-mono">暂无模型消耗数据</p>
        <p className="text-xs text-text-muted mt-1.5">有 AI 请求后，这里会按模型统计消耗量</p>
      </div>
    )
  }

  return (
    <div className="space-y-5 pt-1">
      {models.map((item, i) => {
        const max = models[0].total_tokens || 1
        const barPercent = Math.max((item.total_tokens / max) * 100, item.total_tokens > 0 ? 1.5 : 0)
        const promptShare = item.total_tokens ? (item.prompt_tokens / item.total_tokens) * 100 : 0
        return (
          <motion.div
            key={`${item.provider}-${item.model}`}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.25, delay: i * 0.04 }}
          >
            <div className="flex items-center justify-between gap-4 mb-1.5">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-xs font-mono font-semibold text-text-main truncate" title={item.model}>
                  {item.model}
                </span>
                {item.provider && (
                  <span className="text-[10px] font-mono text-text-muted bg-bg-raised border border-border-main px-2 py-0.5 rounded-full shrink-0">
                    {item.provider}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 shrink-0 font-mono text-[11px]">
                <span className="text-text-muted">{formatNumber(item.requests)} 次</span>
                <span className="text-text-main font-semibold tabular-nums">{formatNumber(item.total_tokens)}</span>
                <span className="text-text-muted w-12 text-right">{percent(item.total_tokens, total)}</span>
              </div>
            </div>
            <div className="h-2.5 rounded-full bg-bg-raised border border-border-main/60 overflow-hidden">
              <motion.div
                className="h-full rounded-full overflow-hidden flex"
                initial={{ width: 0 }}
                animate={{ width: `${barPercent}%` }}
                transition={{ duration: 0.45, delay: i * 0.04, ease: 'easeOut' }}
              >
                <div className="h-full bg-[#18E299]" style={{ width: `${promptShare}%` }} />
                <div className="h-full bg-[#3772cf]" style={{ width: `${100 - promptShare}%` }} />
              </motion.div>
            </div>
            <div className="flex items-center gap-4 mt-1 font-mono text-[10px] text-text-muted">
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#18E299]" />输入 {formatNumber(item.prompt_tokens)}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#3772cf]" />输出 {formatNumber(item.completion_tokens)}
              </span>
              {item.errors > 0 && (
                <span className="flex items-center gap-1.5 text-[#d45656]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#d45656]" />失败 {item.errors}
                </span>
              )}
            </div>
          </motion.div>
        )
      })}
    </div>
  )
}

// ── 请求日志 ────────────────────────────────────────────────────────

function RequestLogs({
  logs, page, onPageChange, modelFilter, onModelChange,
  statusFilter, onStatusChange, modelOptions, loading,
}) {
  const items = logs?.items || []
  const total = logs?.total || 0
  const pages = logs?.pages || 1

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="relative inline-flex items-center">
          <select
            value={modelFilter}
            onChange={e => onModelChange(e.target.value)}
            className="bg-bg-card border border-border-main rounded-full pl-4 pr-8 py-1.5 text-xs font-mono text-text-main focus:outline-none focus:border-brand-green/60 cursor-pointer appearance-none"
          >
            <option value="">全部模型</option>
            {modelOptions.map(model => (
              <option key={model} value={model}>{model}</option>
            ))}
          </select>
          <CaretDown size={11} className="absolute right-3 pointer-events-none text-text-muted" />
        </span>
        <span className="relative inline-flex items-center">
          <select
            value={statusFilter}
            onChange={e => onStatusChange(e.target.value)}
            className="bg-bg-card border border-border-main rounded-full pl-4 pr-8 py-1.5 text-xs font-mono text-text-main focus:outline-none focus:border-brand-green/60 cursor-pointer appearance-none"
          >
            {STATUS_OPTIONS.map(opt => (
              <option key={opt.id} value={opt.id}>{opt.label}</option>
            ))}
          </select>
          <CaretDown size={11} className="absolute right-3 pointer-events-none text-text-muted" />
        </span>
        <span className="text-xs text-text-muted font-mono bg-bg-card border border-border-main px-3 py-1 rounded-full">
          {formatNumber(total)} 条请求
        </span>
        {loading && <Spinner size={14} weight="bold" className="animate-spin text-brand-green" />}
      </div>

      <div className="border border-border-main rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px]">
            <thead>
              <tr className="bg-bg-raised/70 border-b border-border-main">
                {['时间', '模型', '类型', '输入', '输出', '合计', '耗时', '状态'].map((head, i) => (
                  <th
                    key={head}
                    className={`px-4 py-2.5 text-[10px] font-mono font-semibold uppercase tracking-[0.6px] text-text-muted ${i >= 3 && i <= 6 ? 'text-right' : 'text-left'}`}
                  >
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-14 text-center text-xs text-text-muted font-mono">
                    暂无请求记录
                  </td>
                </tr>
              ) : items.map(item => (
                <tr key={item.id} className="border-b border-border-main/45 last:border-0 hover:bg-bg-raised/50 transition-colors">
                  <td className="px-4 py-2 text-[11px] font-mono text-text-muted whitespace-nowrap">{item.time}</td>
                  <td className="px-4 py-2 text-[11px] font-mono text-text-main">
                    <span className="inline-block max-w-[200px] truncate align-bottom" title={item.model}>{item.model || '—'}</span>
                  </td>
                  <td className="px-4 py-2 text-[11px] font-mono text-text-muted whitespace-nowrap">{item.call_type_label}</td>
                  <td className="px-4 py-2 text-[11px] font-mono text-text-main text-right tabular-nums">{formatNumber(item.prompt_tokens)}</td>
                  <td className="px-4 py-2 text-[11px] font-mono text-text-main text-right tabular-nums">{formatNumber(item.completion_tokens)}</td>
                  <td className="px-4 py-2 text-[11px] font-mono text-text-main font-semibold text-right tabular-nums">{formatNumber(item.total_tokens)}</td>
                  <td className="px-4 py-2 text-[11px] font-mono text-text-muted text-right whitespace-nowrap">{formatDuration(item.duration_ms)}</td>
                  <td className="px-4 py-2">
                    <span
                      title={item.error || ''}
                      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-semibold font-mono border ${
                        item.status === 'error'
                          ? 'bg-[#d45656]/10 text-[#d45656] border-[#d45656]/20'
                          : 'bg-brand-green-light text-brand-green-hover dark:text-brand-green border-brand-green/20'
                      }`}
                    >
                      <span className={`w-1 h-1 rounded-full ${item.status === 'error' ? 'bg-[#d45656]' : 'bg-brand-green'}`} />
                      {item.status === 'error' ? '失败' : '成功'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <span className="text-[11px] text-text-muted font-mono">
          第 {page} / {pages} 页
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="p-2 rounded-full border border-border-main bg-bg-card text-text-muted hover:text-text-main hover:border-text-muted/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
          >
            <CaretLeft size={14} />
          </button>
          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page >= pages}
            className="p-2 rounded-full border border-border-main bg-bg-card text-text-muted hover:text-text-main hover:border-text-muted/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
          >
            <CaretRight size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}

// ── 主面板 ──────────────────────────────────────────────────────────

export default function TokenStats() {
  const [range, setRange] = useState('7d')
  const [granularity, setGranularity] = useState('hour')
  const [tab, setTab] = useState('trend')
  const [summary, setSummary] = useState(null)
  const [models, setModels] = useState([])
  const [points, setPoints] = useState([])
  const [logs, setLogs] = useState(null)
  const [page, setPage] = useState(1)
  const [modelFilter, setModelFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [logsLoading, setLogsLoading] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [errorText, setErrorText] = useState('')
  const [confirmClear, setConfirmClear] = useState(false)
  const [clearing, setClearing] = useState(false)

  const fetchOverview = useCallback(async () => {
    try {
      const [summaryRes, seriesRes] = await Promise.all([
        fetch(apiUrl(`/api/token-stats/summary?range=${range}`)).then(r => r.json()),
        fetch(apiUrl(`/api/token-stats/timeseries?range=${range}&granularity=${granularity}`)).then(r => r.json()),
      ])
      if (summaryRes.ok) {
        setSummary(summaryRes.summary)
        setModels(summaryRes.models || [])
      }
      if (seriesRes.ok) setPoints(seriesRes.points || [])
      setLastUpdated(new Date())
      setErrorText('')
    } catch {
      setErrorText('无法加载 Token 统计数据')
    } finally {
      setLoading(false)
    }
  }, [range, granularity])

  const fetchLogs = useCallback(async () => {
    setLogsLoading(true)
    try {
      const params = new URLSearchParams({
        range,
        page: String(page),
        page_size: String(PAGE_SIZE),
      })
      if (modelFilter) params.set('model', modelFilter)
      if (statusFilter) params.set('status', statusFilter)
      const data = await fetch(apiUrl(`/api/token-stats/logs?${params.toString()}`)).then(r => r.json())
      if (data.ok) {
        setLogs(data)
        setErrorText('')
        if (data.page !== page) setPage(data.page)
      }
    } catch {
      setErrorText('无法加载请求日志')
    } finally {
      setLogsLoading(false)
    }
  }, [range, page, modelFilter, statusFilter])

  useEffect(() => {
    fetchOverview()
    const timer = setInterval(fetchOverview, 15000)
    return () => clearInterval(timer)
  }, [fetchOverview])

  useEffect(() => {
    if (tab !== 'logs') return
    fetchLogs()
    const timer = setInterval(fetchLogs, 15000)
    return () => clearInterval(timer)
  }, [fetchLogs, tab])

  function handleRangeChange(nextRange) {
    setRange(nextRange)
    setGranularity(nextRange === 'today' || nextRange === '7d' ? 'hour' : 'day')
    setModelFilter('')
    setStatusFilter('')
    setPage(1)
    setLoading(true)
  }

  async function performClear() {
    if (clearing) return
    setClearing(true)
    try {
      const res = await fetch(apiUrl('/api/token-stats/clear'), { method: 'POST' })
      const data = await res.json()
      if (!data.ok) throw new Error(data.error || '清空统计数据失败')
      setSummary(null)
      setModels([])
      setPoints([])
      setLogs(null)
      setPage(1)
      setLastUpdated(new Date())
      setErrorText('')
      fetchOverview()
      fetchLogs()
    } catch (e) {
      setErrorText(e?.message || '清空统计数据失败')
    } finally {
      setClearing(false)
      setConfirmClear(false)
    }
  }

  const modelOptions = Array.from(new Set(models.map(m => m.model))).filter(Boolean)
  const totalTokens = summary?.total_tokens || 0
  const totalRequests = summary?.requests || 0
  const promptTokens = summary?.prompt_tokens || 0
  const completionTokens = summary?.completion_tokens || 0
  const errors = summary?.errors || 0
  const avgDuration = summary?.avg_duration_ms || 0

  return (
    <div className="max-w-6xl space-y-5">
      {/* 顶部工具条：时间范围 + 刷新 + 清空 */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 bg-bg-card border border-border-main rounded-full p-1">
          {RANGE_OPTIONS.map(opt => (
            <button
              key={opt.id}
              onClick={() => handleRangeChange(opt.id)}
              className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                range === opt.id
                  ? 'bg-bg-raised text-text-main shadow-sm'
                  : 'text-text-muted hover:text-text-main'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1 bg-bg-card border border-border-main rounded-full p-1">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                tab === id
                  ? 'bg-brand-green-light text-brand-green-hover dark:text-brand-green'
                  : 'text-text-muted hover:text-text-main'
              }`}
            >
              <Icon size={13} weight={tab === id ? 'fill' : 'regular'} />
              {label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 ml-auto">
          {lastUpdated && (
            <span className="text-[10px] text-text-muted font-mono">
              更新于 {lastUpdated.toLocaleTimeString('zh-CN', { hour12: false })}
            </span>
          )}
          <button
            onClick={() => { fetchOverview(); fetchLogs() }}
            title="立即刷新"
            className="p-2 rounded-full border border-border-main bg-bg-card text-text-muted hover:text-brand-green hover:border-brand-green/30 transition-colors cursor-pointer"
          >
            <ArrowClockwise size={15} />
          </button>
          <button
            onClick={() => setConfirmClear(true)}
            disabled={clearing}
            title="清空全部统计记录"
            className="p-2 rounded-full border border-border-main bg-bg-card text-text-muted hover:text-[#d45656] hover:border-[#d45656]/25 hover:bg-[#d45656]/5 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Trash size={15} />
          </button>
        </div>
      </div>

      {errorText && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-[#d45656]/10 border border-[#d45656]/20 text-[#d45656] text-xs">
          <WarningCircle size={15} weight="fill" className="shrink-0" />
          <span className="font-medium">{errorText}</span>
        </div>
      )}

      {/* KPI 卡片 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Coins} accent="green" label="总 Token"
          value={loading && !summary ? '—' : formatNumber(totalTokens)}
          sub={`${formatNumber(totalRequests)} 次请求`}
        />
        <StatCard
          icon={ChartLine} accent="blue" label="输入 Token"
          value={loading && !summary ? '—' : formatNumber(promptTokens)}
          sub={`占比 ${percent(promptTokens, totalTokens)}`} delay={0.04}
        />
        <StatCard
          icon={ChartBar} accent="amber" label="输出 Token"
          value={loading && !summary ? '—' : formatNumber(completionTokens)}
          sub={`占比 ${percent(completionTokens, totalTokens)}`} delay={0.08}
        />
        <StatCard
          icon={ArrowClockwise} accent={errors > 0 ? 'rose' : 'green'} label="平均耗时"
          value={loading && !summary ? '—' : formatDuration(avgDuration)}
          sub={`失败 ${formatNumber(errors)} 次`} delay={0.12}
        />
      </div>

      {/* Tab 内容 */}
      <AnimatePresence mode="wait">
        <motion.div
          key={tab}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.18 }}
          className="bg-bg-card border border-border-main rounded-2xl p-6 shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none"
        >
          {tab === 'trend' && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-text-main tracking-tight">消耗趋势</h3>
                  <p className="text-[11px] text-text-muted font-mono mt-0.5">
                    {granularity === 'hour' ? '按小时' : '按天'}统计 Token 消耗量
                  </p>
                </div>
                <div className="flex items-center gap-1 bg-bg-raised border border-border-main rounded-full p-1">
                  {[
                    { id: 'hour', label: '按小时' },
                    { id: 'day', label: '按天' },
                  ].map(opt => (
                    <button
                      key={opt.id}
                      onClick={() => setGranularity(opt.id)}
                      className={`px-3 py-1 rounded-full text-[11px] font-semibold transition-all cursor-pointer ${
                        granularity === opt.id
                          ? 'bg-bg-card text-text-main shadow-sm'
                          : 'text-text-muted hover:text-text-main'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
              <TrendChart points={points} granularity={granularity} />
            </div>
          )}

          {tab === 'models' && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-text-main tracking-tight">各模型消耗量</h3>
                  <p className="text-[11px] text-text-muted font-mono mt-0.5">
                    {RANGE_OPTIONS.find(o => o.id === range)?.label}内按模型统计
                  </p>
                </div>
                <div className="flex items-center gap-4 text-[10px] font-mono text-text-muted">
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-sm bg-[#18E299]" />输入
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-sm bg-[#3772cf]" />输出
                  </span>
                </div>
              </div>
              <ModelBars models={models} />
            </div>
          )}

          {tab === 'logs' && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-text-main tracking-tight">请求日志</h3>
                  <p className="text-[11px] text-text-muted font-mono mt-0.5">
                    每次 AI 请求的 Token 明细，失败请求也会记录
                  </p>
                </div>
              </div>
              <RequestLogs
                logs={logs}
                page={page}
                onPageChange={setPage}
                modelFilter={modelFilter}
                onModelChange={(value) => { setModelFilter(value); setPage(1) }}
                statusFilter={statusFilter}
                onStatusChange={(value) => { setStatusFilter(value); setPage(1) }}
                modelOptions={modelOptions}
                loading={logsLoading}
              />
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      <p className="text-[10px] text-text-muted/70 font-mono flex items-center gap-1.5">
        <Coins size={12} />
        统计数据持久化保存在 SQLite（webot 数据目录 / token_usage.db），不随运行数据重置清除
      </p>

      <ConfirmDialog
        open={confirmClear}
        danger
        busy={clearing}
        title="确定要清空全部 Token 统计记录吗？"
        description="统计库中的消耗趋势、模型分布和请求日志都会被删除，且不可恢复。"
        confirmLabel="清空记录"
        onCancel={() => setConfirmClear(false)}
        onConfirm={performClear}
      />
    </div>
  )
}
