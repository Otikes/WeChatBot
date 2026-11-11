import { useCallback, useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowSquareOut, ArrowsClockwise, CaretDown, CheckCircle, DownloadSimple,
  GithubLogo, Spinner, Tag, WarningCircle, X,
} from '@phosphor-icons/react'
import { friendlyError } from './SharedComponents'

function apiUrl(path) {
  if (window.location.port === '5173') return `http://127.0.0.1:7327${path}`
  return path
}

// 后端不可用时也要能点开 GitHub / Releases
const FALLBACK_REPO = 'https://github.com/Otikes/WeChatBot'
const FALLBACK_RELEASES = `${FALLBACK_REPO}/releases`

function formatDate(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

const iconBtn = 'p-2 rounded-full bg-bg-main border border-border-main text-text-muted hover:text-text-main hover:border-text-muted/30 transition-colors cursor-pointer'
const linkBtn = 'inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg border border-border-main bg-bg-raised text-[11px] font-medium text-text-main hover:bg-bg-main transition-colors cursor-pointer'

export default function UpdateChecker() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)

  const check = useCallback(async (force = false) => {
    setLoading(true)
    try {
      const res = await fetch(apiUrl(`/api/update/check${force ? '?refresh=1' : ''}`))
      const json = await res.json()
      setData(json)
    } catch (e) {
      setData({
        ok: false,
        error: friendlyError(e),
        current_version: '', latest_version: '', has_update: false,
        published_at: '', notes: '', download_url: '',
        repo_url: FALLBACK_REPO, releases_url: FALLBACK_RELEASES,
        release_url: FALLBACK_RELEASES,
      })
    } finally {
      setLoading(false)
    }
  }, [])

  // 静默检查一次，只用于点亮「有更新」小圆点
  useEffect(() => { check(false) }, [check])

  useEffect(() => {
    if (!open) return undefined
    const onDown = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const repoUrl = data?.repo_url || FALLBACK_REPO
  const releasesUrl = data?.releases_url || FALLBACK_RELEASES
  const releaseUrl = data?.release_url || releasesUrl
  const downloadUrl = data?.download_url || releaseUrl
  const current = data?.current_version || ''
  const latest = data?.latest_version || ''
  const hasUpdate = !!data?.has_update
  const failed = !!data && !data.ok

  return (
    <div className="relative" ref={wrapRef} data-testid="update-checker">
      <div className="flex items-center gap-2">
        <a
          href={repoUrl}
          target="_blank"
          rel="noopener noreferrer"
          title="在 GitHub 上查看 WeChatBot"
          data-testid="github-link"
          className={iconBtn}
        >
          <GithubLogo size={16} weight="fill" />
        </a>
        <button
          type="button"
          onClick={() => setOpen((prev) => !prev)}
          title="版本与更新"
          data-testid="version-chip"
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-full bg-bg-main border border-border-main text-[11px] text-text-muted hover:text-text-main hover:border-text-muted/30 transition-colors cursor-pointer"
        >
          <Tag size={12} />
          <span className="font-mono" data-testid="current-version">
            {current ? `v${current}` : '版本'}
          </span>
          {hasUpdate && (
            <span
              data-testid="update-dot"
              title="发现新版本"
              className="w-1.5 h-1.5 rounded-full bg-[#c37d0d] animate-pulse"
            />
          )}
          <CaretDown size={10} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.15 }}
            data-testid="update-popover"
            className="absolute right-0 top-full mt-2 w-[310px] z-50 rounded-xl border border-border-main bg-bg-card shadow-[0_12px_36px_rgba(0,0,0,0.18)] dark:shadow-[0_12px_36px_rgba(0,0,0,0.5)] overflow-hidden"
          >
            <div className="flex items-center gap-2 px-3.5 h-10 border-b border-border-main/70">
              <Tag size={14} className="text-brand-green-hover dark:text-brand-green" />
              <span className="text-[12px] font-semibold text-text-main">版本与更新</span>
              <button
                type="button" onClick={() => setOpen(false)} title="关闭"
                className="ml-auto p-1 text-text-muted hover:text-text-main cursor-pointer"
              ><X size={13} weight="bold" /></button>
            </div>

            <div className="p-3.5 space-y-2.5">
              <div className="grid grid-cols-[72px_1fr] gap-y-1.5 text-[11.5px]">
                <span className="text-text-muted">当前版本</span>
                <span className="font-mono text-text-main" data-testid="popover-current">
                  {current ? `v${current}` : '—'}
                </span>
                <span className="text-text-muted">最新版本</span>
                <span className="font-mono text-text-main" data-testid="popover-latest">
                  {latest ? `v${latest}` : '—'}
                </span>
                {data?.published_at && (
                  <>
                    <span className="text-text-muted">发布时间</span>
                    <span className="font-mono text-text-muted">
                      {formatDate(data.published_at)}
                    </span>
                  </>
                )}
              </div>

              {loading && !data ? (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-bg-raised text-[11px] text-text-muted">
                  <Spinner size={13} className="animate-spin" /> 正在检查更新…
                </div>
              ) : hasUpdate ? (
                <div
                  data-testid="update-available"
                  className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-[#c37d0d]/10 border border-[#c37d0d]/25 text-[11px] text-[#a06a0a] leading-relaxed"
                >
                  <WarningCircle size={14} className="shrink-0 mt-0.5" />
                  <span>发现新版本 <strong>v{latest}</strong>，建议前往 Release 页下载最新安装包。</span>
                </div>
              ) : failed ? (
                <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-[#d45656]/10 border border-[#d45656]/25 text-[11px] text-[#d45656] leading-relaxed">
                  <WarningCircle size={14} className="shrink-0 mt-0.5" />
                  <span>{data.error || '检查更新失败'}，可直接打开 Releases 页查看。</span>
                </div>
              ) : data ? (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-brand-green/10 border border-brand-green/25 text-[11px] text-brand-green-hover dark:text-brand-green">
                  <CheckCircle size={14} /> 已是最新版本
                </div>
              ) : null}

              {hasUpdate && (
                <a
                  href={downloadUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid="download-latest"
                  className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-brand-green-light border border-brand-green/25 text-[11.5px] font-semibold text-brand-green-hover dark:text-brand-green hover:opacity-80 transition-opacity cursor-pointer"
                >
                  <DownloadSimple size={14} weight="bold" /> 下载最新安装包
                </a>
              )}

              <div className="flex items-center gap-2 pt-0.5">
                <button
                  type="button" onClick={() => check(true)} disabled={loading}
                  data-testid="refresh-update"
                  className={`${linkBtn} disabled:opacity-50`}
                >
                  <ArrowsClockwise size={13} className={loading ? 'animate-spin' : ''} />
                  {loading ? '检查中' : '检查更新'}
                </button>
                <a
                  href={releaseUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid="release-link"
                  className={linkBtn}
                >
                  Release <ArrowSquareOut size={12} />
                </a>
                <a
                  href={releasesUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="查看所有版本"
                  data-testid="all-releases-link"
                  className="ml-auto text-[10.5px] text-text-muted hover:text-text-main transition-colors cursor-pointer"
                >
                  所有版本
                </a>
              </div>
            </div>

            <div className="px-3.5 py-2 border-t border-border-main/70 text-[10px] text-text-muted leading-relaxed">
              版本信息来自 GitHub Releases，检查失败不影响机器人运行。
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
