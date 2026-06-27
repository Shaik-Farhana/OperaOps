import { Brain, Link, Clock, TrendingUp } from 'lucide-react'

function MemoryNode({ item, index }) {
  const memCount = item.result?.diagnosis?.memories_recalled || 0
  const memInformed = item.result?.diagnosis?.memory_informed || false

  return (
    <div className="relative flex gap-3">
      {/* Timeline line */}
      <div className="flex flex-col items-center">
        <div className={`w-7 h-7 rounded-full border-2 flex items-center justify-center shrink-0 z-10
          ${memInformed
            ? 'border-blue-400 bg-blue-500/20'
            : 'border-border bg-surface'}`}>
          <span className="text-xs font-mono font-bold text-text/70">#{index + 1}</span>
        </div>
        <div className="w-px flex-1 bg-border mt-1" />
      </div>

      {/* Content */}
      <div className="pb-5 flex-1 min-w-0">
        <div className="bg-card border border-border rounded-lg p-3">
          <div className="flex items-start justify-between gap-2 mb-2">
            <p className="text-xs font-medium text-text leading-tight line-clamp-2">
              {item.incident?.title}
            </p>
            <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-mono
              severity-${item.incident?.severity?.toLowerCase()}`}>
              {item.incident?.severity}
            </span>
          </div>

          {/* Memory status */}
          <div className="flex items-center gap-2 mt-2">
            {memCount > 0 ? (
              <div className="flex items-center gap-1.5 text-[11px] text-blue-300">
                <Brain size={11} className="text-blue-400" />
                <span>Recalled {memCount} past incident{memCount > 1 ? 's' : ''}</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 text-[11px] text-muted">
                <Brain size={11} />
                <span>No memory available</span>
              </div>
            )}
          </div>

          {/* Recalled IDs */}
          {item.result?.diagnosis?.recalled_incidents?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {item.result.diagnosis.recalled_incidents.map((id, i) => (
                <span key={i} className="flex items-center gap-1 text-[10px] text-blue-400/70
                  bg-blue-500/10 border border-blue-500/20 rounded px-1.5 py-0.5 font-mono">
                  <Link size={8} />
                  {id.slice(0, 12)}
                </span>
              ))}
            </div>
          )}

          {/* Cost comparison */}
          <div className="mt-2 pt-2 border-t border-border/50 flex items-center justify-between">
            <span className="text-[10px] text-muted">Cost</span>
            <span className="text-[11px] font-mono text-emerald-400">
              ${item.result?.routing?.cost_usd?.toFixed(5) || '0.00000'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function MemoryTimeline({ incidents }) {
  if (incidents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <Brain size={28} className="text-border mb-3" />
        <p className="text-muted text-sm">Memory builds over time</p>
        <p className="text-muted/50 text-xs mt-1">Each resolved incident teaches the agent</p>
      </div>
    )
  }

  const memoryInformedCount = incidents.filter(
    i => i.result?.diagnosis?.memory_informed
  ).length

  const totalRecalls = incidents.reduce(
    (sum, i) => sum + (i.result?.diagnosis?.memories_recalled || 0), 0
  )

  return (
    <div>
      {/* Stats bar */}
      {incidents.length >= 2 && (
        <div className="grid grid-cols-2 gap-2 mb-4">
          <div className="bg-blue-500/8 border border-blue-500/20 rounded-lg p-2.5 text-center">
            <p className="text-lg font-bold font-mono text-blue-300">{memoryInformedCount}</p>
            <p className="text-[10px] text-blue-300/60">Memory-informed</p>
          </div>
          <div className="bg-emerald-500/8 border border-emerald-500/20 rounded-lg p-2.5 text-center">
            <p className="text-lg font-bold font-mono text-emerald-300">{totalRecalls}</p>
            <p className="text-[10px] text-emerald-300/60">Total recalls</p>
          </div>
        </div>
      )}

      {/* Learning curve callout */}
      {incidents.length >= 3 && (
        <div className="flex items-center gap-2 p-2.5 bg-surface border border-border rounded-lg mb-4">
          <TrendingUp size={13} className="text-accent shrink-0" />
          <p className="text-[11px] text-text/70">
            Agent is learning — incident #{incidents.length} has {' '}
            <span className="text-blue-300 font-medium">
              {incidents[incidents.length - 1]?.result?.diagnosis?.memories_recalled || 0}x
            </span>{' '}
            more context than incident #1
          </p>
        </div>
      )}

      {/* Timeline */}
      <div>
        {incidents.map((inc, i) => (
          <MemoryNode key={inc.incident?.id || i} item={inc} index={i} />
        ))}
        {/* End node */}
        <div className="flex gap-3 items-center">
          <div className="w-7 flex justify-center">
            <div className="w-3 h-3 rounded-full bg-border" />
          </div>
          <p className="text-[11px] text-muted">Next incident will recall {incidents.length} stored memories</p>
        </div>
      </div>
    </div>
  )
}
