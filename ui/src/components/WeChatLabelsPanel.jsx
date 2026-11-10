import { useCallback, useEffect, useState } from 'react'
import {
  ArrowClockwise, CheckCircle, Info, Spinner, Tag, Users, WarningCircle,
} from '@phosphor-icons/react'
import { friendlyError } from './SharedComponents'

function apiUrl(path) {
  if (window.location.port === '5173') return `http://127.0.0.1:7327${path}`
  return path
}

export default function WeChatLabelsPanel() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(apiUrl('/api/wechat/labels'))
      const json = await res.json()
      if (!json.ok) throw new Error(json.error || '读取标签失败')
      setData(json)
    } catch (e) {
      setError(friendlyError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const labels = data?.labels || []
  const totalFriends = new Set(
    labels.flatMap((label) => (label.members || []).map((m) => m.wxid)),
  ).size

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-border-main bg-bg-raised px-4 py-3.5">
        <p className="text-[12px] text-text-main font-semibold mb-1">微信通讯录标签（只读）</p>
        <p className="text-[11px] text-text-muted leading-relaxed">
          直接读取微信本地数据库中的通讯录标签及其好友，用于查看你在微信里已有的分组。
          微信 4.x 把标签归属存在 contact.extra_buffer 里（没有独立关联表），这里会自动解析；
          旧版本则回退到关联表探测，读不到时会给出说明。
        </p>
        <p className="text-[11px] text-text-muted mt-1.5 flex items-start gap-1.5">
          <Info size={13} className="shrink-0 mt-0.5 text-brand-green" />
          这里只是<strong className="text-text-main">只读视图</strong>，与 WeChatBot 的「群发分组」完全独立，
          不会导入、不会同步，也不会影响群发。群聊通常没有微信原生标签。
        </p>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button" onClick={load} disabled={loading}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full border border-border-main bg-bg-card text-[11.5px] font-semibold text-text-main hover:bg-bg-raised transition-colors cursor-pointer disabled:opacity-50"
        >
          <ArrowClockwise size={13} className={loading ? 'animate-spin' : ''} />
          重新读取
        </button>
        {data && (
          <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10.5px] font-medium border ${
            data.available
              ? 'bg-brand-green/10 border-brand-green/25 text-brand-green-hover dark:text-brand-green'
              : 'bg-[#c37d0d]/10 border-[#c37d0d]/25 text-[#c37d0d]'
          }`}>
            {data.available
              ? <><CheckCircle size={12} /> 读取成功 · {labels.length} 个标签 · {totalFriends} 位好友</>
              : <><WarningCircle size={12} /> 暂不可用</>}
          </span>
        )}
        {data?.source && (
          <span className="text-[10px] font-mono text-text-muted truncate" title={data.source}>
            来源 {data.source}
          </span>
        )}
      </div>

      {loading && !data && (
        <div className="flex items-center justify-center py-16 text-text-muted">
          <Spinner size={20} className="animate-spin text-brand-green mr-3" />
          <span className="text-xs font-mono">正在读取微信通讯录标签...</span>
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-[#d45656]/10 border border-[#d45656]/25 text-[11.5px] text-[#d45656]">
          <WarningCircle size={14} className="shrink-0 mt-0.5" /><span>{error}</span>
        </div>
      )}

      {data?.note && (
        <div className="px-3 py-2.5 rounded-lg bg-bg-raised border border-border-main text-[11px] text-text-muted leading-relaxed">
          {data.note}
          {data.tables?.length > 0 && (
            <span className="block mt-1 font-mono text-[10px] opacity-80">
              检测到的标签相关表：{data.tables.join('、')}
            </span>
          )}
        </div>
      )}

      {!loading && labels.length === 0 && !error && (
        <div className="rounded-xl border border-dashed border-border-main bg-bg-card/40 py-14 text-center">
          <Tag size={26} className="mx-auto text-text-muted/50 mb-3" />
          <p className="text-[12px] text-text-muted">没有读取到通讯录标签</p>
          <p className="text-[11px] text-text-muted/70 mt-1.5">
            请确认微信已登录并保持运行；部分微信版本可能没有对应的本地标签表。
          </p>
        </div>
      )}

      {labels.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {labels.map((label) => (
            <div key={label.label_id} className="rounded-xl border border-border-main bg-bg-card overflow-hidden">
              <div className="flex items-center gap-2 px-3.5 h-10 border-b border-border-main/70">
                <Tag size={14} className="text-brand-green" />
                <span className="text-[12px] font-semibold text-text-main truncate">{label.name || '(未命名标签)'}</span>
                <span className="ml-auto inline-flex items-center gap-1 text-[10.5px] font-mono text-text-muted">
                  <Users size={11} />{label.member_count ?? (label.members || []).length}
                </span>
              </div>
              <div className="p-3 max-h-[190px] overflow-y-auto">
                {(label.members || []).length === 0 ? (
                  <p className="text-[11px] text-text-muted py-3 text-center">
                    该标签下没有好友（微信里可能是空标签）
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {label.members.map((m) => (
                      <span
                        key={m.wxid}
                        title={m.wxid}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-bg-raised border border-border-main text-[11px] text-text-main"
                      >
                        <Users size={11} className="text-[#8b5cf6]" />
                        <span className="max-w-[150px] truncate">{m.name || m.wxid}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
