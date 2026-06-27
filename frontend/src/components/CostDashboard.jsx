import { DollarSign, Zap, ArrowUp, Activity, BarChart2 } from 'lucide-react'

function StatCard({ label, value, sub, accent }) {
  const accentMap = {
    blue: 'text-blue-300 bg-blue-500/8 border-blue-500/20',
    green: 'text-emerald-300 bg-emerald-500/8 border-emerald-500/20',
    purple: 'text-purple-300 bg-purple-500/8 border-purple-500/20',
    yellow: 'text-yellow-300 bg-yellow-500/8 border-yellow-500/20',
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
  const isStrong = entry.escalated
  return (
    <div className="flex items-center gap-2 py-2 border-b border-border/40 last:border-0">
      <span className="text-[10px] font-mono text-muted w-5 shrink-0">#{index + 1}</span>
      <span className={`text-[10px] font-mono shrink-0 ${isStrong ? 'model-strong' : 'model-cheap'}`}>
        {isStrong ? '⬆ strong' : '⚡ cheap'}
      </span>
      <span className="text-[10px] text-muted flex-1 truncate">{entry.routing_reason}</span>
      <span className="text-[10px] font-mono text-emerald-400 shrink-0">${entry.cost_usd?.toFixed(5)}</span>
      <span className="text-[10px] font-mono text-muted shrink-0">{entry.latency_ms}ms</span>
    </div>
  )
}

export default function CostDashboard({ incidents, auditLog }) {
  if (incidents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <BarChart2 size={28} className="text-border mb-3" />
        <p className="text-muted text-sm">Cost tracking starts here</p>
        <p className="text-muted/50 text-xs mt-1">cascadeflow logs every model decision</p>
      </div>
    )
  }

  // Compute stats from incidents
  const totalCost = incidents.reduce(
    (sum, i) => sum + (i.result?.routing?.cost_usd || 0), 0
  )
  const cheapCalls = (auditLog || []).filter(e => !e.escalated).length
  const strongCalls = (auditLog || []).filter(e => e.escalated).length
  const totalCalls = auditLog?.length || 0
  const avgCost = totalCalls > 0 ? totalCost / incidents.length : 0

  // Cost per incident for bar chart
  const perIncident = incidents.map((inc, i) => ({
    label: `#${i + 1}`,
    cost: inc.result?.routing?.cost_usd || 0,
    escalated: inc.result?.routing?.escalated || false,
  }))

  const maxCost = Math.max(...perIncident.map(p => p.cost), 0.001)

  // Savings vs all-strong-model baseline
  const strongOnlyEstimate = totalCalls * 0.0032 // avg strong model cost
  const savings = Math.max(0, strongOnlyEstimate - totalCost)
  const savingsPct = strongOnlyEstimate > 0
    ? Math.round((savings / strongOnlyEstimate) * 100)
    : 0

  return (
    <div className="space-y-4">
      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-2">
        <StatCard
          label="Session Spend"
          value={`$${totalCost.toFixed(4)}`}
          sub={`${totalCalls} total calls`}
          accent="blue"
        />
        <StatCard
          label="Avg per Incident"
          value={`$${avgCost.toFixed(5)}`}
          sub="with cascadeflow"
          accent="green"
        />
        <StatCard
          label="Cheap Calls"
          value={cheapCalls}
          sub={`${totalCalls > 0 ? Math.round(cheapCalls / totalCalls * 100) : 0}% of calls`}
          accent="green"
        />
        <StatCard
          label="Escalations"
          value={strongCalls}
          sub="to strong model"
          accent="purple"
        />
      </div>

      {/* Savings callout */}
      {savingsPct > 10 && (
        <div className="flex items-center gap-2 p-3 bg-emerald-500/8 border border-emerald-500/20 rounded-lg">
          <DollarSign size={14} className="text-emerald-400 shrink-0" />
          <div>
            <p className="text-xs font-semibold text-emerald-300">
              {savingsPct}% cheaper than single-model baseline
            </p>
            <p className="text-[11px] text-emerald-300/60">
              Saved ~${savings.toFixed(4)} vs always using strong model
            </p>
          </div>
        </div>
      )}

      {/* Per-incident cost bar chart */}
      <div>
        <p className="text-[10px] text-muted uppercase tracking-wider mb-2">Cost per Incident</p>
        <div className="space-y-1.5">
          {perIncident.map((item, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-[10px] font-mono text-muted w-6 shrink-0">{item.label}</span>
              <div className="flex-1 h-5 bg-border/40 rounded overflow-hidden">
                <div
                  className={`h-full rounded transition-all duration-500 ${item.escalated ? 'bg-purple-500/60' : 'bg-emerald-500/60'}`}
                  style={{ width: `${Math.max(4, (item.cost / maxCost) * 100)}%` }}
                />
              </div>
              <span className="text-[10px] font-mono text-emerald-400 w-16 text-right shrink-0">
                ${item.cost.toFixed(5)}
              </span>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-3 mt-2">
          <span className="flex items-center gap-1 text-[10px] text-emerald-300">
            <span className="w-2.5 h-2.5 bg-emerald-500/60 rounded-sm" />Cheap model
          </span>
          <span className="flex items-center gap-1 text-[10px] text-purple-300">
            <span className="w-2.5 h-2.5 bg-purple-500/60 rounded-sm" />Strong model
          </span>
        </div>
      </div>

      {/* Audit log */}
      {auditLog && auditLog.length > 0 && (
        <div>
          <p className="text-[10px] text-muted uppercase tracking-wider mb-2">
            cascadeflow Audit Trail
          </p>
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
