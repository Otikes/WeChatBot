import { useState, useEffect, lazy, Suspense, memo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Gear, ChartLine, Scroll, Users, Spinner, Sun, Moon, Sliders, CheckSquare, ChatCircleDots, Coins, PlugsConnected, Tag } from '@phosphor-icons/react'
import Dashboard from './components/Dashboard'
import UpdateChecker from './components/UpdateChecker'

// 非首屏面板按需加载，避免启动时解析全部面板代码
// 这些面板不依赖实时状态，memo 后不会被状态推送触发重渲染
const ConfigPanel = memo(lazy(() => import('./components/ConfigPanel')))
const FeaturesPanel = memo(lazy(() => import('./components/FeaturesPanel')))
const FriendChatPanel = memo(lazy(() => import('./components/FriendChatPanel')))
const GroupChatPanel = memo(lazy(() => import('./components/GroupChatPanel')))
const LogViewer = memo(lazy(() => import('./components/LogViewer')))
const TodoManager = memo(lazy(() => import('./components/TodoManager')))
const TokenStats = memo(lazy(() => import('./components/TokenStats')))
const McpPanel = memo(lazy(() => import('./components/McpPanel')))
const WeChatLabelsPanel = memo(lazy(() => import('./components/WeChatLabelsPanel')))
const Onboarding = memo(lazy(() => import('./components/Onboarding')))

function PanelFallback() {
  return (
    <div className="flex items-center justify-center py-24 text-text-muted">
      <Spinner size={22} weight="bold" className="animate-spin text-brand-green mr-3" />
      <span className="text-xs font-mono">正在加载...</span>
    </div>
  )
}

const iconVariants = {
  hover: { y: -1.5, scale: 1.05, transition: { type: 'spring', stiffness: 300, damping: 15 } }
}

const TABS = [
  { id: 'dashboard', label: '运行状态', icon: ChartLine },
  { id: 'token-stats', label: 'Token 统计', icon: Coins },
  { id: 'mcp', label: 'MCP 服务', icon: PlugsConnected },
  {
    id: 'config', label: '系统配置', icon: Gear,
    subs: [
      { id: 'ai', label: 'LLM模型配置' },
      { id: 'voice', label: '语音模型配置' },
      { id: 'imagegen', label: '生图模型配置' },
      { id: 'identity', label: '机器人身份' },
      { id: 'data', label: '数据路径' },
      { id: 'broadcast', label: '群发分组' },
      { id: 'sandbox', label: '提示词沙箱' },
    ],
  },
  {
    id: 'features', label: '功能开关', icon: Sliders,
    subs: [
      { id: 'summarize', label: '总结功能' },
      { id: 'chat', label: 'AI 对话' },
      { id: 'feishu', label: '飞书同步' },
      { id: 'fun', label: '趣味抽签' },
      { id: 'proactive', label: '主动发言' },
      { id: 'sticky', label: '粘性提及' },
      { id: 'welcome', label: '欢迎新人' },
      { id: 'log', label: '日志级别' },
    ],
  },
  { id: 'friend-chat', label: '好友私聊', icon: ChatCircleDots },
  { id: 'wechat-labels', label: '通讯录标签', icon: Tag },
  { id: 'nicknames', label: '群聊配置', icon: Users },
  { id: 'todo-manager', label: '群聊待办', icon: CheckSquare },
  { id: 'logs', label: '运行日志', icon: Scroll },
]

function apiUrl(path) {
  if (window.location.port === '5173') return `http://127.0.0.1:7327${path}`
  return path
}

function wsUrl(path) {
  const host = window.location.port === '5173' ? '127.0.0.1:7327' : window.location.host
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${host}${path}`
}

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard')
  const [configSection, setConfigSection] = useState('ai')
  const [featuresSection, setFeaturesSection] = useState('summarize')
  const [botStatus, setBotStatus] = useState(null)
  const [onboardingDone, setOnboardingDone] = useState(null) // null = loading
  const [wsConnected, setWsConnected] = useState(false)

  // Theme state: default to 'dark' (Version 1: 夜航控制台) but can toggle to 'light' (正常模式)
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')

  // Apply theme class to HTML root
  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
    localStorage.setItem('theme', theme)
  }, [theme])

  // Check onboarding status on mount
  useEffect(() => {
    async function check() {
      try {
        const res = await fetch(apiUrl('/api/onboarding/status'))
        const d = await res.json()
        setOnboardingDone(d.onboarding_done)
      } catch {
        setTimeout(check, 1000) // Retry every 1s until server is ready
      }
    }
    check()
  }, [])

  // Connect WebSocket only after onboarding is confirmed
  useEffect(() => {
    if (!onboardingDone) return
    let reconnectTimer = null
    let socket = null

    function connectWS() {
      socket = new WebSocket(wsUrl('/ws'))
      socket.onopen = () => {
        setWsConnected(true)
      }
      socket.onmessage = (e) => {
        try { setBotStatus(JSON.parse(e.data)) } catch {}
      }
      socket.onclose = () => {
        setWsConnected(false)
        reconnectTimer = setTimeout(connectWS, 3000)
      }
      socket.onerror = () => {
        setWsConnected(false)
        socket?.close()
      }
    }
    connectWS()

    return () => {
      clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [onboardingDone])

  const status = botStatus || {
    running: false,
    uptime_sec: 0,
    messages_processed: 0,
    wechat_backend: 'wcdb',
    ai_backend: 'openai_compatible',
    db_ok: false,
    last_api_call_sec_ago: -1,
    last_api_call_time: 0,
    timestamp: '',
    error: '',
  }

  const activeTabMeta = TABS.find(t => t.id === activeTab)
  const activeSubMeta = activeTabMeta?.subs?.find(
    sub => sub.id === (activeTab === 'config' ? configSection : featuresSection)
  )

  function handleResetComplete() {
    setBotStatus(null)
    setActiveTab('dashboard')
  }

  // Loading state
  if (onboardingDone === null) {
    return (
      <div className="min-h-[100dvh] bg-bg-main flex items-center justify-center">
        <div className="text-center">
          <Spinner size={32} weight="bold" className="animate-spin text-brand-green mx-auto mb-4" />
          <p className="text-sm text-text-muted font-mono">正在加载...</p>
        </div>
      </div>
    )
  }

  // Onboarding
  if (!onboardingDone) {
    return (
      <Suspense fallback={<PanelFallback />}>
        <Onboarding onComplete={() => setOnboardingDone(true)} />
      </Suspense>
    )
  }

  return (
    <div className="min-h-[100dvh] bg-bg-main text-text-main font-sans transition-colors duration-200 relative overflow-hidden">
      {/* Ambient Radial Background Glow */}
      <div
        className="absolute top-0 right-0 w-[600px] h-[600px] pointer-events-none opacity-[0.03] dark:opacity-[0.04] blur-3xl select-none"
        style={{ backgroundImage: 'radial-gradient(circle, #18E299 0%, transparent 70%)' }}
      />

      {/* Sidebar */}
      <div className="fixed left-0 top-0 h-full w-56 bg-bg-main border-r border-border-main z-40">
        <div className="p-5 flex flex-col h-full">
          <div className="flex items-center gap-3 mb-8 shrink-0">
              <div className="relative">
                <img src="/logo-128.png" alt="WeChatBot" className="w-9 h-9 rounded-full border border-border-main" />
                <div className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full ring-2 ring-bg-main transition-colors duration-300 ${!wsConnected ? 'bg-[#d45656] animate-pulse' : (status.running ? 'bg-brand-green' : 'bg-slate-500')}`} />
              </div>
              <div>
                <h1 className="text-sm font-semibold tracking-tight text-text-main">WeChatBot</h1>
                <p className="text-xs text-text-muted font-mono font-medium">{!wsConnected ? '连接已断开' : (status.running ? '运行中' : '已停止')}</p>
              </div>
            </div>

            <nav className="space-y-1 flex-1 min-h-0 overflow-y-auto pr-1 -mr-2">
              {TABS.map(({ id, label, icon: Icon, subs }) => (
                <div key={id}>
                  <motion.button
                    whileHover="hover"
                    whileTap={{ scale: 0.98 }}
                    onClick={() => setActiveTab(id)}
                    className={`w-full flex items-center gap-3 px-4 py-2 text-[14px] rounded-full transition-all duration-200 cursor-pointer relative ${
                      activeTab === id
                        ? 'text-brand-green-hover dark:text-brand-green font-semibold'
                        : 'text-text-muted font-medium hover:text-text-main hover:bg-bg-raised/60'
                    }`}
                  >
                    {activeTab === id && (
                      <motion.div
                        layoutId="activeTabBackground"
                        className="absolute inset-0 bg-brand-green-light rounded-full -z-10"
                        transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                      />
                    )}
                    <motion.div variants={iconVariants} className="flex items-center z-10">
                      <Icon weight={activeTab === id ? 'fill' : 'regular'} size={18} className={activeTab === id ? 'text-brand-green-hover dark:text-brand-green' : 'text-text-muted'} />
                    </motion.div>
                    <span className="z-10">{label}</span>
                  </motion.button>
                  {/* Config sub-nav: animates height and opacity on toggle */}
                  {subs && (
                    <AnimatePresence initial={false}>
                      {activeTab === id && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.2, ease: 'easeInOut' }}
                          className="ml-6 mt-1 border-l border-border-main pl-4 space-y-0.5 overflow-hidden font-mono"
                        >
                          {subs.map(sub => (
                            <button
                              key={sub.id}
                              onClick={() => { setActiveTab(id); id === 'config' ? setConfigSection(sub.id) : setFeaturesSection(sub.id) }}
                              className={`w-full text-left py-1.5 text-xs transition-all cursor-pointer relative pl-3.5 ${
                                activeTab === id && (id === 'config' ? configSection : featuresSection) === sub.id
                                  ? 'text-brand-green-hover dark:text-brand-green font-semibold'
                                  : 'text-text-muted hover:text-text-main'
                              }`}
                            >
                              {activeTab === id && (id === 'config' ? configSection : featuresSection) === sub.id && (
                                <motion.div
                                  layoutId="activeConfigSub"
                                  className="absolute left-0 top-1.5 w-1 h-3 bg-brand-green rounded-full"
                                  transition={{ type: 'spring', stiffness: 300, damping: 20 }}
                                />
                              )}
                              <span className="pl-1.5">{sub.label}</span>
                            </button>
                          ))}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  )}
                </div>
              ))}
            </nav>

          <div className="border-t border-border-main pt-4 mt-4 shrink-0">
            <div className="flex items-center gap-2.5 px-4 py-2 bg-bg-raised/80 rounded-full border border-border-main">
              <div className={`w-2 h-2 rounded-full relative ${!wsConnected ? 'bg-[#d45656]' : (status.running ? 'bg-brand-green' : 'bg-slate-500')}`}>
                {!wsConnected && <span className="absolute inset-0 rounded-full bg-[#d45656] animate-ping opacity-75" />}
                {wsConnected && status.running && <span className="absolute inset-0 rounded-full bg-brand-green animate-ping opacity-75" />}
              </div>
              <span className="text-[11px] text-text-muted font-semibold font-mono tracking-wider">
                {!wsConnected ? 'OFFLINE' : (status.running ? `ONLINE ${status.uptime_sec ? Math.floor(status.uptime_sec / 60) : 0}M` : 'STOPPED')}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="ml-56">
        <div className="sticky top-0 z-30 bg-bg-main/80 backdrop-blur-md px-8 py-4 flex items-center justify-between border-b border-border-main transition-colors duration-300">
          <h2 className="text-sm font-semibold tracking-tight text-text-main flex items-center gap-2">
            {activeTabMeta?.label}
            {activeSubMeta && (
              <>
                <span className="text-text-muted/35 font-normal">/</span>
                <span className="text-text-muted font-normal">{activeSubMeta.label}</span>
              </>
            )}
          </h2>
          <div className="flex items-center gap-3">
            {/* GitHub 仓库入口 + 版本 / 检查更新 */}
            <UpdateChecker />

            {/* Theme switcher toggle button */}
            <button
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className="p-2 rounded-full bg-bg-main border border-border-main text-text-muted hover:text-text-main hover:border-text-muted/30 transition-colors cursor-pointer"
              title={theme === 'dark' ? '切换到正常模式 (Light Mode)' : '切换到夜航控制台 (Dark Mode)'}
            >
              {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            </button>

            <span className="text-xs text-text-muted font-mono bg-bg-main border border-border-main px-4 py-1.5 rounded-full">
              已处理 {status.messages_processed.toLocaleString()} 条消息
            </span>
            {!wsConnected ? (
              <div className="flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-semibold bg-[#d45656]/10 text-[#d45656] border border-[#d45656]/20 animate-pulse">
                <div className="w-1.5 h-1.5 rounded-full bg-[#d45656]" />
                服务器离线
              </div>
            ) : (
              <div className={`flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-semibold transition-all border ${
                  status.running
                    ? 'bg-brand-green-light text-brand-green-hover dark:text-brand-green border-brand-green/20'
                    : 'bg-bg-raised text-text-muted border-border-main'
                }`}>
                <div className={`w-1.5 h-1.5 rounded-full ${status.running ? 'bg-brand-green animate-pulse' : 'bg-slate-500'}`} />
                {status.running ? '运行中' : '未启动'}
              </div>
            )}
          </div>
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className="p-8"
          >
            <Suspense fallback={<PanelFallback />}>
            {activeTab === 'dashboard' && <Dashboard status={status} onResetComplete={handleResetComplete} />}
            {activeTab === 'token-stats' && <TokenStats />}
            {activeTab === 'mcp' && <McpPanel />}
            {activeTab === 'wechat-labels' && <WeChatLabelsPanel />}
            {activeTab === 'config' && <ConfigPanel activeSection={configSection} onNavigate={setConfigSection} />}
            {activeTab === 'features' && <FeaturesPanel activeSection={featuresSection} onNavigate={setFeaturesSection} />}
            {activeTab === 'friend-chat' && <FriendChatPanel />}
            {activeTab === 'nicknames' && <GroupChatPanel />}
            {activeTab === 'todo-manager' && <TodoManager />}
            {activeTab === 'logs' && <LogViewer />}
            </Suspense>
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  )
}
