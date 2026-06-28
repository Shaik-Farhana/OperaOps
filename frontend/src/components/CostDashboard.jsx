import { DollarSign, Zap, Activity, BarChart2, Brain } from 'lucide-react'

function StatCard({ label, value, sub, accent }) {
  const accentMap = {
    blue: 'text-blue-300 bg-blue-500/8 border-blue-500/20',
    green: 'text-emerald-300 bg-emerald-500/8 border-emerald-500/20',
    purple: 'text-purple-300 bg-purple-500/8 border-purple-500/20',
    yellow: 'text-yellow-300 bg-yellow-500/8 border-yellow-500/20',
    orange: 'text-orange-300 bg-orange-500/8 border-orange-500/20',
  }
  return (
    <div className={`border rounded-lg p-3 ${accentMap[accent] || accentMap.blue}`}>
      <p className="text-[10px] uppercase tracking-wider opacity-60 mb-1">{label}</p>
      <p className="text-xl font-bold font-mono">{value}</p>
      {sub && <p className="text-[10px] opacity-50 mt-0.5">{sub}</p>}
    </div>
  )
}

function AuditRow({ entry, index }) {
  const skipped = entry.llm_skipped
  const isStrong = entry.escalated && !skipped
  return (
    <div className="flex items-center gap-2 py-2 border-b border-border/40 last:border-0">
      <span className="text-[10px] font-mono text-muted w-5 shrink-0">#{index + 1}</span>
      <span className={`text-[10px] font-mono shrink-0 w-14 ${skipped ? 'text-emerald-300' : isStrong ? 'model-strong' : 'model-cheap'}`}>
        {skipped ? '0-token' : isStrong ? 'strong' : entry.model_used || 'nano'}
      </span>
      {entry.expert_id && (
        <span className="text-[10px] font-mono text-orange-300/80 shrink-0 w-16 truncate">{entry.expert_id}</span>
      )}
      <span className="text-[10px] text-muted flex-1 truncate">{entry.routing_reason}</span>
      <span className="text-[10px] font-mono text-emerald-400 shrink-0">${entry.cost_usd?.toFixed(5)}</span>
      <span className="text-[10px] font-mono text-muted shrink-0">{entry.latency_ms}ms</span>
    </div>
  )
}

export default function CostDashboard({ incidents, auditLog, moeStats }) {
  if (incidents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <BarChart2 size={28} className="text-border mb-3" />
        <p className="text-muted text-sm">Cost tracking starts here</p>
        <p className="text-muted/50 text-xs mt-1">DECA-IR MoE logs every routing decision</p>
      </div>
    )
  }

  const totalCost = incidents.reduce(
    (sum, i) => sum + (i.result?.routing?.cost_usd || 0), 0
  )
  const fastPathHits = (auditLog || []).filter(e => e.llm_skipped).length
  const llmCalls = (auditLog || []).filter(e => !e.llm_skipped).length
  const strongCalls = (auditLog || []).filter(e => e.escalated && !e.llm_skipped).length
  const totalCalls = auditLog?.length || 0
  const avgCost = incidents.length > 0 ? totalCost / incidents.length : 0
  const tokensSaved = moeStats?.tokens_saved_estimate || moeStats?.session_tokens_saved || 0

  const perIncident = incidents.map((inc, i) => ({
    label: `#${i + 1}`,
    cost: inc.result?.routing?.cost_usd || 0,
    escalated: inc.result?.routing?.escalated || false,
    skipped: inc.result?.moe?.llm_skipped || false,
  }))

  const maxCost = Math.max(...perIncident.map(p => p.cost), 0.001)
  const strongOnlyEstimate = Math.max(llmCalls, 1) * 0.0032
  const savings = Math.max(0, strongOnlyEstimate - totalCost)
  const savingsPct = strongOnlyEstimate > 0 ? Math.round((savings / strongOnlyEstimate) * 100) : 0

  const expertActivations = moeStats?.expert_activations || {}

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2">
        <StatCard label="Session Spend" value={`$${totalCost.toFixed(4)}`} sub={`${totalCalls} audit entries`} accent="blue" />
        <StatCard label="Avg per Incident" value={`$${avgCost.toFixed(5)}`} sub="DECA-IR routed" accent="green" />
        <StatCard label="Fast Path Hits" value={fastPathHits} sub="0-token memory recall" accent="green" />
        <StatCard label="Tokens Saved" value={tokensSaved} sub="est. via MoE compression" accent="orange" />
      </div>

      {savingsPct > 10 && (
        <div className="flex items-center gap-2 p-3 bg-emerald-500/8 border border-emerald-500/20 rounded-lg">
          <DollarSign size={14} className="text-emerald-400 shrink-0" />
          <div>
            <p className="text-xs font-semibold text-emerald-300">{savingsPct}% cheaper than always-strong baseline</p>
            <p className="text-[11px] text-emerald-300/60">Saved ~${savings.toFixed(4)} vs single-model routing</p>
          </div>
        </div>
      )}

      {Object.keys(expertActivations).length > 0 && (
        <div>
          <p className="text-[10px] text-muted uppercase tracking-wider mb-2">Expert Activations</p>
          <div className="space-y-1">
            {Object.entries(expertActivations).map(([expert, count]) => (
              <div key={expert} className="flex items-center gap-2 text-[10px]">
                <span className="font-mono text-orange-300 w-24 truncate">{expert}</span>
                <div className="flex-1 h-3 bg-border/40 rounded overflow-hidden">
                  <div className="h-full bg-orange-500/50 rounded" style={{ width: `${(count / Math.max(...Object.values(expertActivations))) * 100}%` }} />
                </div>
                <span className="font-mono text-muted w-4">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <p className="text-[10px] text-muted uppercase tracking-wider mb-2">Cost per Incident</p>
        <div className="space-y-1.5">
          {perIncident.map((item, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-[10px] font-mono text-muted w-6 shrink-0">{item.label}</span>
              <div className="flex-1 h-5 bg-border/40 rounded overflow-hidden">
                <div
                  className={`h-full rounded transition-all duration-500 ${
                    item.skipped ? 'bg-emerald-400/70' : item.escalated ? 'bg-purple-500/60' : 'bg-emerald-500/60'
                  }`}
                  style={{ width: `${Math.max(4, (item.cost / maxCost) * 100)}%` }}
                />
              </div>
              <span className="text-[10px] font-mono text-emerald-400 w-16 text-right shrink-0">
                ${item.cost.toFixed(5)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {auditLog && auditLog.length > 0 && (
        <div>
          <p className="text-[10px] text-muted uppercase tracking-wider mb-2">DECA-IR Audit Trail</p>
          <div className="bg-surface border border-border rounded-lg px-3 py-1 max-h-48 overflow-y-auto">
            {[...auditLog].reverse().slice(0, 20).map((entry, i) => (
              <AuditRow key={entry.id || i} entry={entry} index={auditLog.length - 1 - i} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
