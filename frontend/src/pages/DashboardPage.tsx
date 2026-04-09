import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import {
  Activity, AlertTriangle, CheckCircle2, Clock, Shield,
  Bell, RefreshCw, TrendingUp, Zap, Server, Filter
} from 'lucide-react'
import { getIncidents, getStats, getTickets, resolveTicket, type Incident, type Stats, type Ticket } from '../api/client'
import toast from 'react-hot-toast'

const SEV_CONFIG = {
  P1: { color: 'text-severity-p1', bg: 'bg-severity-p1/10', border: 'border-severity-p1/40', dot: 'bg-severity-p1', label: 'CRITICAL' },
  P2: { color: 'text-severity-p2', bg: 'bg-severity-p2/10', border: 'border-severity-p2/40', dot: 'bg-severity-p2', label: 'HIGH' },
  P3: { color: 'text-severity-p3', bg: 'bg-severity-p3/10', border: 'border-severity-p3/40', dot: 'bg-severity-p3', label: 'MEDIUM' },
  P4: { color: 'text-severity-p4', bg: 'bg-severity-p4/10', border: 'border-severity-p4/40', dot: 'bg-severity-p4', label: 'LOW' },
}

const STATUS_CONFIG = {
  open:        { color: 'text-acid-red',    label: 'OPEN' },
  in_progress: { color: 'text-acid-amber',  label: 'IN PROGRESS' },
  resolved:    { color: 'text-acid-green',  label: 'RESOLVED' },
  duplicate:   { color: 'text-gray-500',    label: 'DUPLICATE' },
}

function SeverityBadge({ sev }: { sev?: string }) {
  if (!sev) return <span className="text-xs font-mono text-gray-600">TRIAGING...</span>
  const c = SEV_CONFIG[sev as keyof typeof SEV_CONFIG]
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-mono font-bold rounded border ${c.color} ${c.bg} ${c.border}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {sev}
    </span>
  )
}

function StatCard({ label, value, icon: Icon, color }: { label: string; value: number | string; icon: any; color: string }) {
  return (
    <div className="terminal-panel p-4 flex items-center gap-4">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center border ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <div className="text-2xl font-display font-bold text-white">{value}</div>
        <div className="text-xs font-mono text-gray-500 uppercase tracking-wider">{label}</div>
      </div>
    </div>
  )
}

function PipelineTrace({ traces }: { traces: Stats['pipeline_traces'] }) {
  const stages = ['ingest', 'triage', 'ticket', 'notify', 'resolve']
  const byStage = Object.fromEntries(
    traces.filter(t => t.status === 'success').map(t => [t.stage, t])
  )
  return (
    <div className="terminal-panel p-4">
      <div className="text-xs font-mono text-gray-500 uppercase tracking-wider mb-3">Pipeline Performance</div>
      <div className="flex items-center gap-1">
        {stages.map((stage, i) => {
          const t = byStage[stage]
          return (
            <div key={stage} className="flex items-center gap-1 flex-1">
              <div className={`flex-1 rounded p-2 text-center ${t ? 'bg-acid-green/10 border border-acid-green/30' : 'bg-terminal-bg border border-terminal-border'}`}>
                <div className={`text-xs font-mono uppercase tracking-wider ${t ? 'text-acid-green' : 'text-gray-600'}`}>
                  {stage}
                </div>
                {t && (
                  <div className="text-xs text-gray-400 mt-0.5">{t.avg_ms}ms avg</div>
                )}
              </div>
              {i < stages.length - 1 && (
                <div className={`text-xs ${t ? 'text-acid-cyan' : 'text-gray-700'}`}>→</div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async () => {
    try {
      const [inc, st, tix] = await Promise.all([
        getIncidents({ limit: 30 }),
        getStats(),
        getTickets(),
      ])
      setIncidents(inc)
      setStats(st)
      setTickets(tix)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-refresh every 10s
  useEffect(() => {
    const iv = setInterval(load, 10000)
    return () => clearInterval(iv)
  }, [load])

  const handleResolve = async (ticketId: string) => {
    try {
      await resolveTicket(ticketId, 'Resolved by SRE team via dashboard.')
      toast.success('Ticket resolved — Reporter notified!')
      load()
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Failed to resolve')
    }
  }

  const filteredIncidents = incidents.filter(i =>
    !filter ||
    i.severity === filter ||
    i.status === filter
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-acid-cyan/30 border-t-acid-cyan rounded-full animate-spin mx-auto mb-3" />
          <div className="text-xs font-mono text-gray-500">LOADING SRE DASHBOARD...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-6 animate-fade-up">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-gray-500 mb-2">
            <Zap className="w-3 h-3 text-acid-cyan" />
            <span>SRE OPERATIONS CENTER</span>
          </div>
          <h1 className="font-display text-2xl font-bold text-white">Incident Dashboard</h1>
        </div>
        <button
          onClick={() => { setRefreshing(true); load() }}
          className="flex items-center gap-2 px-3 py-2 text-xs font-mono text-gray-400 border border-terminal-border rounded hover:border-acid-cyan/40 hover:text-acid-cyan transition-all"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          REFRESH
        </button>
      </div>

      {/* Stats row */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Total Incidents"
            value={stats.total_incidents}
            icon={AlertTriangle}
            color="text-acid-amber border-acid-amber/30 bg-acid-amber/5"
          />
          <StatCard
            label="Guardrail Blocks"
            value={stats.guardrail_blocks}
            icon={Shield}
            color="text-acid-red border-acid-red/30 bg-acid-red/5"
          />
          <StatCard
            label="Notifications Sent"
            value={stats.notifications_sent}
            icon={Bell}
            color="text-acid-cyan border-acid-cyan/30 bg-acid-cyan/5"
          />
          <StatCard
            label="Open Tickets"
            value={tickets.filter(t => t.status === 'open').length}
            icon={Activity}
            color="text-acid-green border-acid-green/30 bg-acid-green/5"
          />
        </div>
      )}

      {/* Severity breakdown */}
      {stats && (
        <div className="terminal-panel p-4">
          <div className="text-xs font-mono text-gray-500 uppercase tracking-wider mb-3">Severity Distribution</div>
          <div className="flex gap-4">
            {(['P1', 'P2', 'P3', 'P4'] as const).map(sev => {
              const count = stats.by_severity[sev] || 0
              const c = SEV_CONFIG[sev]
              return (
                <button
                  key={sev}
                  onClick={() => setFilter(filter === sev ? '' : sev)}
                  className={`flex-1 p-3 rounded-lg border transition-all text-center ${
                    filter === sev ? `${c.bg} ${c.border}` : 'border-terminal-border hover:border-gray-600'
                  }`}
                >
                  <div className={`text-2xl font-display font-bold ${c.color}`}>{count}</div>
                  <div className={`text-xs font-mono mt-0.5 ${c.color}`}>{sev}</div>
                  <div className="text-xs text-gray-600">{c.label}</div>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Pipeline traces */}
      {stats && stats.pipeline_traces.length > 0 && (
        <PipelineTrace traces={stats.pipeline_traces} />
      )}

      {/* Main content: Incidents + Open Tickets */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Incidents list */}
        <div className="lg:col-span-2 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-xs font-mono text-gray-500 uppercase tracking-wider">
              Incidents ({filteredIncidents.length})
            </div>
            {filter && (
              <button
                onClick={() => setFilter('')}
                className="text-xs font-mono text-acid-cyan hover:underline"
              >
                Clear filter ×
              </button>
            )}
          </div>

          {filteredIncidents.length === 0 ? (
            <div className="terminal-panel p-12 text-center">
              <Activity className="w-8 h-8 text-gray-700 mx-auto mb-3" />
              <p className="text-sm text-gray-500 font-mono">No incidents yet</p>
              <Link to="/report" className="text-xs text-acid-cyan hover:underline mt-2 block">
                Submit the first incident →
              </Link>
            </div>
          ) : (
            filteredIncidents.map(inc => {
              const sc = STATUS_CONFIG[inc.status as keyof typeof STATUS_CONFIG]
              return (
                <Link
                  key={inc.id}
                  to={`/incidents/${inc.id}`}
                  className="terminal-panel p-4 flex gap-4 hover:border-acid-cyan/30 transition-all group block"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <SeverityBadge sev={inc.severity} />
                      {inc.ticket_key && (
                        <span className="text-xs font-mono text-acid-cyan/60">{inc.ticket_key}</span>
                      )}
                      <span className={`text-xs font-mono ml-auto ${sc?.color}`}>
                        {sc?.label}
                      </span>
                    </div>
                    <h3 className="text-sm font-semibold text-gray-100 group-hover:text-white truncate">
                      {inc.title}
                    </h3>
                    {inc.triage_summary && (
                      <p className="text-xs text-gray-500 mt-1 line-clamp-2">{inc.triage_summary}</p>
                    )}
                    <div className="flex items-center gap-3 mt-2 text-xs font-mono text-gray-600">
                      {inc.affected_service && <span><Server className="w-3 h-3 inline mr-1" />{inc.affected_service}</span>}
                      <span><Clock className="w-3 h-3 inline mr-1" />
                        {formatDistanceToNow(new Date(inc.created_at), { addSuffix: true })}
                      </span>
                    </div>
                  </div>
                </Link>
              )
            })
          )}
        </div>

        {/* Open tickets */}
        <div className="space-y-3">
          <div className="text-xs font-mono text-gray-500 uppercase tracking-wider">
            Open Tickets ({tickets.filter(t => t.status === 'open').length})
          </div>
          {tickets.filter(t => t.status !== 'resolved').slice(0, 8).map(ticket => {
            const sc = SEV_CONFIG[(ticket.priority || 'P4') as keyof typeof SEV_CONFIG]
            return (
              <div key={ticket.id} className="terminal-panel p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-acid-cyan">{ticket.ticket_key}</span>
                  <SeverityBadge sev={ticket.priority} />
                </div>
                <p className="text-xs text-gray-300 font-semibold line-clamp-2">{ticket.incident_title || ticket.title}</p>
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-mono ${
                    ticket.status === 'open' ? 'text-acid-red' : 'text-acid-amber'
                  }`}>
                    {ticket.status.toUpperCase()}
                  </span>
                  <button
                    onClick={() => handleResolve(ticket.id)}
                    className="ml-auto flex items-center gap-1 px-2 py-1 text-xs font-mono text-acid-green border border-acid-green/30 rounded hover:bg-acid-green/10 transition-all"
                  >
                    <CheckCircle2 className="w-3 h-3" />
                    RESOLVE
                  </button>
                </div>
              </div>
            )
          })}
          {tickets.filter(t => t.status !== 'resolved').length === 0 && (
            <div className="terminal-panel p-6 text-center">
              <CheckCircle2 className="w-6 h-6 text-acid-green mx-auto mb-2" />
              <p className="text-xs font-mono text-gray-500">All tickets resolved</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
