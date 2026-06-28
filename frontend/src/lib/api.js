import axios from 'axios'

const BASE =
  import.meta.env.VITE_API_URL ??
  (import.meta.env.DEV ? 'http://localhost:8000' : '')

export const api = axios.create({ baseURL: BASE })

export const getSyntheticIncidents = () => api.get('/incidents/synthetic').then(r => r.data)
export const triggerIncident = (payload) => api.post('/incidents/trigger', payload).then(r => r.data)
export const listIncidents = () => api.get('/incidents').then(r => r.data)
export const getCostSummary = () => api.get('/costs/summary').then(r => r.data)
export const getAuditLog = () => api.get('/costs/audit').then(r => r.data)
export const getMemoryStats = () => api.get('/memory/stats').then(r => r.data)
export const runDemoSequence = () => api.post('/demo/run-sequence').then(r => r.data)
export const getMoeStats = () => api.get('/moe/stats').then(r => r.data)
export const getMoeExperts = () => api.get('/moe/experts').then(r => r.data)
export const runEval = (payload = { runs: 1 }) => api.post('/eval/run', payload).then(r => r.data)
export const getEvalResults = () => api.get('/eval/results').then(r => r.data)
export const getFlywheelTrajectories = () => api.get('/flywheel/trajectories').then(r => r.data)
