import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const api = axios.create({ baseURL: BASE })

export const getSyntheticIncidents = () => api.get('/incidents/synthetic').then(r => r.data)
export const triggerIncident = (payload) => api.post('/incidents/trigger', payload).then(r => r.data)
export const listIncidents = () => api.get('/incidents').then(r => r.data)
export const getCostSummary = () => api.get('/costs/summary').then(r => r.data)
export const getAuditLog = () => api.get('/costs/audit').then(r => r.data)
export const getMemoryStats = () => api.get('/memory/stats').then(r => r.data)
export const runDemoSequence = () => api.post('/demo/run-sequence').then(r => r.data)
