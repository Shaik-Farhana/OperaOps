import { useState, useEffect, useCallback } from 'react'
import { AlertTriangle, Play, Zap, Brain, BarChart2, RefreshCw, Activity, ChevronDown } from 'lucide-react'
import IncidentFeed from './components/IncidentFeed'
import MemoryTimeline from './components/MemoryTimeline'
import CostDashboard from './components/CostDashboard'
import { getSyntheticIncidents, triggerIncident, getAuditLog, getMoeStats } from './lib/api'

const TABS = [
  { id: 'feed', label: 'Incident Feed', icon: Activity },
  { id: 'memory', label: 'Memory', icon: Brain },
  { id: 'costs', label: 'Cost Intelligence', icon: BarChart2 },
]

export default function App() {
  const [syntheticIncidents, setSyntheticIncidents] = useState([])
  const [selectedIncident, setSelectedIncident] = useState(null)
  const [resolvedIncidents, setResolvedIncidents] = useState([])
  const [auditLog, setAuditLog] = useState([])
  const [moeStats, setMoeStats] = useState(null)
  const [loading, setLoading] = useState(false)
  const [demoLoading, setDemoLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('feed')
  const [newestId, setNewestId] = useState(null)
  const [error, setError] = useState(null)
  const [showPicker, setShowPicker] = useState(false)

  useEffect(() => {
    getSyntheticIncidents()
      .then(data => {
        setSyntheticIncidents(data)
        setSelectedIncident(data[0])
      })
      .catch(() => setError('Cannot reach backend. Make sure FastAPI is running on :8000'))
  }, [])

  const refreshAudit = useCallback(async () => {
    try {
      const [audit, moe] = await Promise.all([getAuditLog(), getMoeStats()])
      setAuditLog(audit.audit_log || [])
      setMoeStats(moe)
    } catch {}
  }, [])

  const handleTrigger = async () => {
    if (!selectedIncident || loading) return
    setLoading(true)
    setError(null)
    try {
      const result = await triggerIncident({ synthetic_id: selectedIncident.id })
      setResolvedIncidents(prev => [...prev, result])
      setNewestId(result.incident?.id)
      setActiveTab('feed')
      await refreshAudit()
    } catch (e) {
      setError(e?.response?.data?.detail || 'Failed to trigger incident. Is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  const handleDemoSequence = async () => {
    if (demoLoading) return
    setDemoLoading(true)
    setError(null)
    setResolvedIncidents([])
    setAuditLog([])
    try {
      // Run 5 incidents sequentially to show memory learning
      const demoIds = ['inc_001', 'inc_006', 'inc_011', 'inc_001', 'inc_006']
      for (const id of demoIds) {
        const result = await triggerIncident({ synthetic_id: id })
        setResolvedIncidents(prev => [...prev, result])
        setNewestId(result.incident?.id)
        await refreshAudit()
        await new Promise(r => setTimeout(r, 400))
      }
    } catch (e) {
      setError(e?.response?.data?.detail || 'Demo sequence failed')
    } finally {
      setDemoLoading(false)
    }
  }

  const severityColor = (s) => ({
    P1: 'text-red-400', P2: 'text-yellow-400', P3: 'text-blue-400'
  })[s] || 'text-gray-400'

  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="border-b border-border bg-surface/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center">
              <Activity size={14} className="text-white" />
            </div>
            <div>
              <span className="font-semibold text-sm tracking-tight">OperaOps</span>
              <span className="text-muted text-xs ml-2 hidden sm:inline">DECA-IR Agent</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-full">
              <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse-slow" />
              Live
            </span>
            <span className="text-xs text-muted hidden sm:block">{resolvedIncidents.length} incidents resolved</span>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {error && (
          <div className="mb-4 flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-sm text-red-300">
            <AlertTriangle size={14} className="shrink-0" />{error}
          </div>
        )}

        {/* Trigger panel */}
        <div className="bg-card border border-border rounded-xl p-5 mb-6">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h2 className="text-sm font-semibold mb-1">Trigger Incident</h2>
              <p className="text-xs text-muted">Select a realistic incident and run it through the full agent pipeline</p>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={handleDemoSequence}
                disabled={demoLoading || loading}
                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-purple-500/15 border border-purple-500/30 text-purple-300 text-xs font-medium hover:bg-purple-500/25 transition-colors disabled:opacity-50"
              >
                <Zap size={13} />
                {demoLoading ? 'Running 5-incident demo...' : 'Demo Sequence (×5)'}
              </button>
              <button
                onClick={handleTrigger}
                disabled={loading || demoLoading || !selectedIncident}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent hover:bg-accent-dim text-white text-xs font-semibold transition-colors disabled:opacity-50"
              >
                {loading ? <RefreshCw size={13} className="animate-spin" /> : <Play size={13} />}
                {loading ? 'Diagnosing...' : 'Trigger Incident'}
              </button>
            </div>
          </div>

          <div className="mt-4 relative">
            <button
              onClick={() => setShowPicker(!showPicker)}
              className="w-full flex items-center justify-between gap-3 p-3 bg-surface border border-border rounded-lg text-left hover:border-accent/40 transition-colors"
            >
              {selectedIncident ? (
                <div className="flex items-center gap-3 min-w-0">
                  <span className={`text-xs font-mono font-bold shrink-0 ${severityColor(selectedIncident.severity)}`}>{selectedIncident.severity}</span>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-text truncate">{selectedIncident.title}</p>
                    <p className="text-xs text-muted truncate font-mono">{selectedIncident.error_message?.slice(0, 70)}...</p>
                  </div>
                </div>
              ) : <span className="text-muted text-sm">Select an incident...</span>}
              <ChevronDown size={14} className={`text-muted shrink-0 transition-transform ${showPicker ? 'rotate-180' : ''}`} />
            </button>

            {showPicker && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-card border border-border rounded-lg shadow-xl z-20 max-h-72 overflow-y-auto">
                {syntheticIncidents.map(inc => (
                  <button
                    key={inc.id}
                    onClick={() => { setSelectedIncident(inc); setShowPicker(false) }}
                    className={`w-full flex items-start gap-3 p-3 text-left hover:bg-white/[0.03] transition-colors border-b border-border/50 last:border-0 ${selectedIncident?.id === inc.id ? 'bg-accent/10' : ''}`}
                  >
                    <span className={`text-xs font-mono font-bold shrink-0 mt-0.5 ${severityColor(inc.severity)}`}>{inc.severity}</span>
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-text leading-tight">{inc.title}</p>
                      <p className="text-[11px] text-muted mt-0.5 font-mono truncate">{inc.error_message?.slice(0, 60)}...</p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* 3-panel layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            {/* Mobile tabs */}
            <div className="flex lg:hidden gap-1 mb-4 bg-surface border border-border rounded-lg p-1">
              {TABS.map(tab => {
                const Icon = tab.icon
                return (
                  <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                    className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-medium transition-colors ${activeTab === tab.id ? 'bg-accent text-white' : 'text-muted hover:text-text'}`}>
                    <Icon size={12} /><span className="hidden sm:inline">{tab.label}</span>
                  </button>
                )
              })}
            </div>

            <div className="hidden lg:flex items-center gap-2 mb-4">
              <Activity size={14} className="text-accent" />
              <h2 className="text-sm font-semibold">Incident Feed</h2>
              <span className="text-xs text-muted bg-border/60 px-2 py-0.5 rounded-full">{resolvedIncidents.length} resolved</span>
            </div>
            {(activeTab === 'feed' || window.innerWidth >= 1024) && (
              <IncidentFeed incidents={resolvedIncidents} newestId={newestId} />
            )}
          </div>

          <div className="space-y-6">
            {(activeTab === 'memory' || activeTab === 'feed') && (
              <div className="bg-card border border-border rounded-xl p-4">
                <div className="flex items-center gap-2 mb-4">
                  <Brain size={14} className="text-blue-400" />
                  <h2 className="text-sm font-semibold">Hindsight Memory</h2>
                  <span className="text-xs text-muted bg-border/60 px-2 py-0.5 rounded-full">{resolvedIncidents.length} stored</span>
                </div>
                <MemoryTimeline incidents={resolvedIncidents} />
              </div>
            )}
            {(activeTab === 'costs' || activeTab === 'feed') && (
              <div className="bg-card border border-border rounded-xl p-4">
                <div className="flex items-center gap-2 mb-4">
                  <BarChart2 size={14} className="text-emerald-400" />
                  <h2 className="text-sm font-semibold">cascadeflow Intelligence</h2>
                </div>
                <CostDashboard incidents={resolvedIncidents} auditLog={auditLog} moeStats={moeStats} />
              </div>
            )}
          </div>
        </div>
      </div>

      <footer className="border-t border-border mt-12 py-4 px-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between flex-wrap gap-2">
          <p className="text-xs text-muted">
            OperaOps · powered by{' '}
            <a href="https://hindsight.vectorize.io/" target="_blank" rel="noreferrer" className="text-blue-400 hover:underline">Hindsight</a>
            {' '}&{' '}
            <a href="https://docs.cascadeflow.ai/" target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">cascadeflow</a>
          </p>
          <p className="text-xs text-muted">HackwithHyderabad 2.0 · June 2026</p>
        </div>
      </footer>
    </div>
  )
}
