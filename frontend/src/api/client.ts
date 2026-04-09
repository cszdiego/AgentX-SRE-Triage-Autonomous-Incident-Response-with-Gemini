import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 60000,
})

export interface Incident {
  id: string
  title: string
  description: string
  reporter_email: string
  reporter_name?: string
  severity?: 'P1' | 'P2' | 'P3' | 'P4'
  status: 'open' | 'in_progress' | 'resolved' | 'duplicate'
  affected_service?: string
  environment?: string
  triage_summary?: string
  root_cause?: string
  runbook?: string
  attachment_path?: string
  attachment_type?: string
  attachment_name?: string
  duplicate_of?: string
  similarity_score?: number
  langfuse_trace_id?: string
  ticket_key?: string
  ticket_status?: string
  ticket_id?: string
  assigned_to?: string
  jira_key?: string
  jira_url?: string
  resolved_at?: string
  created_at: string
  updated_at: string
}

export interface Stats {
  total_incidents: number
  by_severity: Record<string, number>
  by_status: Record<string, number>
  pipeline_traces: Array<{
    stage: string
    status: string
    avg_ms: number
    c: number
  }>
  guardrail_blocks: number
  notifications_sent: number
}

export interface Notification {
  id: string
  type: string
  channel: string
  recipient: string
  subject: string
  body: string
  status: string
  created_at: string
}

export interface Ticket {
  id: string
  incident_id: string
  ticket_key: string
  title: string
  description: string
  priority?: string
  status: string
  assigned_to?: string
  incident_title?: string
  severity?: string
  affected_service?: string
  reporter_email?: string
  triage_summary?: string
  root_cause?: string
  runbook?: string
  created_at: string
  updated_at: string
  resolved_at?: string
}

// ── Incidents ────────────────────────────────────────────────────────────

export const submitIncident = async (formData: FormData) => {
  const res = await api.post('/incidents', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export const getIncidents = async (params?: {
  status?: string
  severity?: string
  limit?: number
}): Promise<Incident[]> => {
  const res = await api.get('/incidents', { params })
  return res.data
}

export const getIncident = async (id: string): Promise<Incident> => {
  const res = await api.get(`/incidents/${id}`)
  return res.data
}

export const getIncidentNotifications = async (id: string): Promise<Notification[]> => {
  const res = await api.get(`/incidents/${id}/notifications`)
  return res.data
}

export const getIncidentTraces = async (id: string) => {
  const res = await api.get(`/incidents/${id}/traces`)
  return res.data
}

export const getIncidentReasoning = async (id: string): Promise<Array<{
  step: string; detail: string; stage: string; icon: string; step_order: number
}>> => {
  const res = await api.get(`/incidents/${id}/reasoning`)
  return res.data
}

export const getStats = async (): Promise<Stats> => {
  const res = await api.get('/incidents/stats')
  return res.data
}

// ── Tickets ─────────────────────────────────────────────────────────────

export const getTickets = async (status?: string): Promise<Ticket[]> => {
  const res = await api.get('/tickets', { params: { status } })
  return res.data
}

export const resolveTicket = async (ticketId: string, resolution_note?: string) => {
  const res = await api.patch(`/tickets/${ticketId}/resolve`, { resolution_note })
  return res.data
}

export const assignTicket = async (ticketId: string, assignee: string) => {
  const res = await api.patch(`/tickets/${ticketId}/assign`, null, {
    params: { assignee },
  })
  return res.data
}
