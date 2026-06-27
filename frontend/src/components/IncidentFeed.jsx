import { useState } from 'react'
import { AlertCircle, Zap, Clock, ChevronDown, ChevronUp, Brain, DollarSign } from 'lucide-react'

const SeverityBadge = ({ severity }) => (
  <span className={`px-2 py-0.5 rounded text-xs font-mono font-semibold severity-${severity.toLowerCase()}`}>
    {severity}
  </span>
)

const StatusDot = ({ status }) => {
  const colors = {
    diagnosing: 'bg-yellow-400 animate-pulse',
    resolved: 'bg-emerald-400',
    escalated: 'bg-purple-400',
  }
  return <span className={`inline-block w-2 h-2 rounded-full ${colors[status] || 'bg-gray-400'}`} />
}

function IncidentCard({ incident, result, isNew }) {
  const [expanded, setExpanded] = useState(isNew)

  const diagnosis = result?.result?.diagnosis
  const routing = result?.result?.routing
  const memoryCount = diagnosis?.memories_recalled || 0

  return (
    <div className={`bg-card border border-border rounded-lg overflow-hidden transition-all duration-300 ${isNew ? 'animate-slide-in' : ''}`}>
      {/* Header */}
      <div
        className="flex items-start gap-3 p-4 cursor-pointer hover:bg-white/[0.02] transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="mt-0.5">
          <StatusDot status={incident.status} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <SeverityBadge severity={incident.severity} />
            <span className="text-xs font-mono text-muted bg-border/60 px-2 py-0.5 rounded">
              {incident.service}
            </span>
            {memoryCount > 0 && (
              <span className="flex items-center gap-1 text-xs text-blue-400 bg-blue-500/10 border border-blue-500/20 px-2 py-0.5 rounded">
                <Brain size={10} />
                {memoryCount} recalled
              </span>
            )}
          </div>
          <p className="text-sm font-medium text-text truncate">{incident.title}</p>
          <p className="text-xs text-muted mt-0.5 font-mono truncate">{incident.error_message}</p>
        </div>
        <div className="flex items-center gap-3 shrink-0 ml-2">
          {routing && (
            <span className={`text-xs font-mono ${routing.escalated ? 'model-strong' : 'model-cheap'}`}>
              ${routing.cost_usd?.toFixed(4)}
            </span>
          )}
          {expanded ? <ChevronUp size={14} className="text-muted" /> : <ChevronDown size={14} className="text-muted" />}
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && result && (
        <div className="border-t border-border bg-bg/40 p-4 space-y-4">

          {/* Memory recall banner */}
          {memoryCount > 0 && (
            <div className="flex items-start gap-2 p-3 bg-blue-500/8 border border-blue-500/20 rounded-lg">
              <Brain size={14} className="text-blue-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-xs font-semibold text-blue-300 mb-0.5">Memory Informed</p>
                <p className="text-xs text-blue-200/70">
                  Agent recalled {memoryCount} similar past incident{memoryCount > 1 ? 's' : ''} from Hindsight memory.
                  {diagnosis?.memory_informed && ' Diagnosis was shaped by this context.'}
                </p>
              </div>
            </div>
          )}

          {/* Diagnosis */}
          {diagnosis && (
            <div className="space-y-3">
              <div>
                <p className="text-xs text-muted uppercase tracking-wider mb-1">Root Cause</p>
                <p className="text-sm text-text">{diagnosis.root_cause}</p>
                <div className="mt-1 flex items-center gap-2">
                  <div className="h-1 flex-1 bg-border rounded-full overflow-hidden">
                    <div
                      className="h-full bg-accent rounded-full transition-all"
                      style={{ width: `${(diagnosis.confidence || 0) * 100}%` }}
                    />
                  </div>
                  <span className="text-xs text-muted font-mono">
                    {((diagnosis.confidence || 0) * 100).toFixed(0)}% confidence
                  </span>
                </div>
              </div>

              <div>
                <p className="text-xs text-muted uppercase tracking-wider mb-1">Suggested Fix</p>
                <p className="text-sm text-text/80 font-mono text-xs leading-relaxed bg-surface border border-border rounded p-3">
                  {diagnosis.fix}
                </p>
              </div>

              <div>
                <p className="text-xs text-muted uppercase tracking-wider mb-1">RCA Summary</p>
                <p className="text-sm text-text/80 italic">{diagnosis.rca_summary}</p>
              </div>
            </div>
          )}

          {/* Routing info */}
          {routing && (
            <div className="pt-3 border-t border-border grid grid-cols-2 gap-3 text-xs">
              <div>
                <p className="text-muted mb-0.5">Model Used</p>
                <p className={`font-mono font-medium ${routing.escalated ? 'model-strong' : 'model-cheap'}`}>
                  {routing.escalated ? '⬆ Strong model' : '⚡ Cheap model'}
                </p>
                <p className="text-muted/60 font-mono text-[10px] mt-0.5">{routing.groq_model}</p>
              </div>
              <div>
                <p className="text-muted mb-0.5">Routing Reason</p>
                <p className="text-text/70">{routing.routing_reason}</p>
              </div>
              <div>
                <p className="text-muted mb-0.5">Cost</p>
                <p className="font-mono text-emerald-400">${routing.cost_usd?.toFixed(5)}</p>
              </div>
              <div>
                <p className="text-muted mb-0.5">Latency</p>
                <p className="font-mono text-text/70">{routing.latency_ms}ms</p>
              </div>
            </div>
          )}

          {/* Pattern insight */}
          {result?.result?.pattern_insight && (
            <div className="flex items-start gap-2 p-3 bg-yellow-500/8 border border-yellow-500/20 rounded-lg">
              <AlertCircle size={14} className="text-yellow-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-xs font-semibold text-yellow-300 mb-0.5">Pattern Detected</p>
                <p className="text-xs text-yellow-200/70">{result.result.pattern_insight}</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function IncidentFeed({ incidents, newestId }) {
  if (incidents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <AlertCircle size={32} className="text-border mb-3" />
        <p className="text-muted text-sm">No incidents yet</p>
        <p className="text-muted/50 text-xs mt-1">Trigger one from the panel above</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {[...incidents].reverse().map((inc) => (
        <IncidentCard
          key={inc.incident.id}
          incident={inc.incident}
          result={inc}
          isNew={inc.incident.id === newestId}
        />
      ))}
    </div>
  )
}
