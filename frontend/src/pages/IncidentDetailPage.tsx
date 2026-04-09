import { useEffect, useState, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import {
  ChevronLeft, ChevronDown, ChevronRight,
  AlertTriangle, Server, Clock, User, Mail,
  FileText, CheckCircle2, Bell, Activity, Shield, Code2,
  Cpu, Loader2, Terminal, Database, Image, Video,
  Search, Layers, Sparkles, XCircle, CheckCheck,
} from 'lucide-react'
import {
  getIncident, getIncidentNotifications, getIncidentTraces,
  getIncidentReasoning, resolveTicket, type Incident, type Notification,
} from '../api/client'
import toast from 'react-hot-toast'

// ── Types ────────────────────────────────────────────────────────────────────
interface StreamStep {
  step: string
  detail: string
  stage: string
  icon: string
  ts: number
}

// ── Config maps ──────────────────────────────────────────────────────────────
const SEV_CONFIG = {
  P1: { color: 'text-severity-p1', bg: 'bg-severity-p1/10', border: 'border-severity-p1/40' },
  P2: { color: 'text-severity-p2', bg: 'bg-severity-p2/10', border: 'border-severity-p2/40' },
  P3: { color: 'text-severity-p3', bg: 'bg-severity-p3/10', border: 'border-severity-p3/40' },
  P4: { color: 'text-severity-p4', bg: 'bg-severity-p4/10', border: 'border-severity-p4/40' },
}

const STAGE_ICONS: Record<string, any> = {
  ingest: Shield, triage: Cpu, ticket: AlertTriangle,
  notify: Bell, resolve: CheckCircle2,
}

const STEP_ICON_MAP: Record<string, any> = {
  shield: Shield, check: CheckCircle2, 'check-circle': CheckCheck,
  search: Search, layers: Layers, code: Code2, 'file-code': Code2,
  'file-text': FileText, image: Image, video: Video,
  cpu: Cpu, sparkles: Sparkles, 'alert-triangle': AlertTriangle,
  database: Database, bell: Bell, mail: Mail, x: XCircle,
}

// Stage display metadata
const STAGE_META: Record<string, { label: string; color: string; bgColor: string; borderColor: string }> = {
  ingest:  { label: 'Security Scan',   color: 'text-acid-cyan',   bgColor: 'bg-acid-cyan/5',   borderColor: 'border-acid-cyan/20' },
  triage:  { label: 'AI Analysis',     color: 'text-acid-amber',  bgColor: 'bg-acid-amber/5',  borderColor: 'border-acid-amber/20' },
  ticket:  { label: 'Ticket Creation', color: 'text-acid-green',  bgColor: 'bg-acid-green/5',  borderColor: 'border-acid-green/20' },
  notify:  { label: 'Notifications',   color: 'text-acid-cyan',   bgColor: 'bg-acid-cyan/5',   borderColor: 'border-acid-cyan/20' },
  done:    { label: 'Complete',        color: 'text-acid-green',  bgColor: 'bg-acid-green/5',  borderColor: 'border-acid-green/20' },
  blocked: { label: 'Blocked',         color: 'text-severity-p1', bgColor: 'bg-severity-p1/5', borderColor: 'border-severity-p1/20' },
  working: { label: 'Processing',      color: 'text-gray-400',    bgColor: 'bg-white/2',       borderColor: 'border-white/5' },
}

// ── Single step row ──────────────────────────────────────────────────────────
function StepRow({ step, startTs }: { step: StreamStep; startTs: number }) {
  const Icon = STEP_ICON_MAP[step.icon] || Activity
  const meta = STAGE_META[step.stage] || STAGE_META.working
  const elapsed = ((step.ts - startTs) / 1000).toFixed(1)

  return (
    <div className={`flex items-start gap-2 px-2 py-1.5 rounded ${meta.bgColor}`}>
      <Icon className={`w-3 h-3 mt-0.5 flex-shrink-0 ${meta.color}`} />
      <div className="flex-1 min-w-0">
        <span className={`text-xs font-mono ${
          step.stage === 'done' ? 'text-acid-green font-bold' :
          step.stage === 'blocked' ? 'text-severity-p1 font-bold' :
          'text-gray-200'
        }`}>{step.step}</span>
        {step.detail && (
          <p className="text-[10px] font-mono text-gray-500 mt-0.5 break-words">{step.detail}</p>
        )}
      </div>
      <span className="text-[10px] font-mono text-gray-600 flex-shrink-0">+{elapsed}s</span>
    </div>
  )
}

// ── Collapsible stage section ────────────────────────────────────────────────
function StageSection({
  stageKey, steps, startTs, defaultOpen, active,
}: {
  stageKey: string
  steps: StreamStep[]
  startTs: number
  defaultOpen: boolean
  active: boolean  // currently streaming this stage
}) {
  const [open, setOpen] = useState(defaultOpen)
  const meta = STAGE_META[stageKey] || STAGE_META.working
  const Icon = STAGE_ICONS[stageKey] || Activity

  if (steps.length === 0) return null

  return (
    <div className={`rounded border ${meta.borderColor} overflow-hidden`}>
      {/* Section header — clickable */}
      <button
        onClick={() => setOpen(o => !o)}
        className={`w-full flex items-center gap-2 px-3 py-2 ${meta.bgColor} hover:brightness-110 transition-all text-left`}
      >
        <Icon className={`w-3.5 h-3.5 flex-shrink-0 ${meta.color}`} />
        <span className={`text-xs font-mono font-bold flex-1 ${meta.color}`}>{meta.label}</span>
        <span className="text-[10px] font-mono text-gray-500">{steps.length} step{steps.length !== 1 ? 's' : ''}</span>
        {active && <span className="w-1.5 h-1.5 rounded-full bg-acid-amber animate-pulse" />}
        {open
          ? <ChevronDown className="w-3 h-3 text-gray-500" />
          : <ChevronRight className="w-3 h-3 text-gray-500" />
        }
      </button>

      {/* Steps */}
      {open && (
        <div className="px-2 py-1.5 space-y-1 bg-terminal-bg/50">
          {steps.map((s, i) => (
            <StepRow key={i} step={s} startTs={startTs} />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Reasoning Panel ──────────────────────────────────────────────────────────
function ReasoningPanel({ steps, streaming }: { steps: StreamStep[]; streaming: boolean }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (streaming) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [steps.length, streaming])

  // Group steps by stage (preserving stage order)
  const stageOrder = ['ingest', 'triage', 'ticket', 'notify']
  const grouped: Record<string, StreamStep[]> = {}
  for (const s of steps) {
    const key = s.stage === 'done' || s.stage === 'working' ? 'triage' : s.stage
    if (!grouped[key]) grouped[key] = []
    grouped[key].push(s)
  }

  // Find the currently active stage
  const lastStage = steps.length > 0 ? steps[steps.length - 1].stage : ''
  const isDone = lastStage === 'done'
  const startTs = steps.length > 0 ? steps[0].ts : Date.now()

  return (
    <div className="terminal-panel flex flex-col" style={{ minHeight: '480px' }}>
      {/* Panel header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-terminal-border flex-shrink-0">
        <Terminal className="w-4 h-4 text-acid-cyan" />
        <span className="text-xs font-mono text-acid-cyan uppercase tracking-wider">Agent Reasoning</span>
        {streaming && (
          <span className="ml-auto flex items-center gap-1.5 text-xs font-mono text-acid-amber">
            <span className="w-1.5 h-1.5 rounded-full bg-acid-amber animate-pulse" />
            LIVE
          </span>
        )}
        {isDone && !streaming && (
          <span className="ml-auto flex items-center gap-1.5 text-xs font-mono text-acid-green">
            <CheckCircle2 className="w-3 h-3" />
            DONE
          </span>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">

        {/* Connecting state */}
        {steps.length === 0 && streaming && (
          <div className="flex items-center gap-2 text-gray-600 px-1 py-3">
            <Loader2 className="w-3 h-3 animate-spin text-acid-cyan" />
            <span className="text-xs font-mono">Connecting to agent stream...</span>
          </div>
        )}

        {/* Collapsible stage sections */}
        {stageOrder.map(stage => {
          const stageSteps = grouped[stage] || []
          const isActiveStage = streaming && lastStage === stage
          // Auto-open: ingest always open, triage open, others collapsed by default
          const defaultOpen = stage === 'ingest' || stage === 'triage' || isActiveStage
          return (
            <StageSection
              key={stage}
              stageKey={stage}
              steps={stageSteps}
              startTs={startTs}
              defaultOpen={defaultOpen}
              active={isActiveStage}
            />
          )
        })}

        {/* Live indicator while streaming */}
        {streaming && steps.length > 0 && !isDone && (
          <div className="flex items-center gap-2 text-acid-amber px-2 py-1">
            <Loader2 className="w-3 h-3 animate-spin" />
            <span className="text-xs font-mono">Processing...</span>
          </div>
        )}

        {/* Done banner */}
        {isDone && (
          <div className="flex items-center gap-2 px-3 py-2 bg-acid-green/10 border border-acid-green/30 rounded">
            <CheckCircle2 className="w-3.5 h-3.5 text-acid-green" />
            <span className="text-xs font-mono text-acid-green font-bold">TRIAGE COMPLETE</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}

// ── Investigating overlay ────────────────────────────────────────────────────
function InvestigatingOverlay({ steps }: { steps: StreamStep[] }) {
  const lastStep = steps.filter(s => s.stage !== 'done').pop()
  return (
    <div className="terminal-panel p-8 flex flex-col items-center justify-center text-center min-h-[200px]">
      <div className="relative mb-4">
        <div className="w-14 h-14 rounded-full border-2 border-acid-cyan/20 border-t-acid-cyan animate-spin" />
        <Cpu className="absolute inset-0 m-auto w-6 h-6 text-acid-cyan/70" />
      </div>
      <p className="text-xs font-mono text-acid-cyan uppercase tracking-widest mb-2">INVESTIGATING</p>
      {lastStep && (
        <p className="text-xs font-mono text-gray-500 max-w-sm px-4">{lastStep.step}</p>
      )}
      <p className="text-xs text-gray-700 mt-3 font-mono">Gemini 2.5 Flash analyzing...</p>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────
export default function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [incident, setIncident] = useState<Incident | null>(null)
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [traces, setTraces] = useState<any[]>([])
  const [resolving, setResolving] = useState(false)
  const [loading, setLoading] = useState(true)
  const [streamSteps, setStreamSteps] = useState<StreamStep[]>([])
  const [streaming, setStreaming] = useState(true)

  // ── Load reasoning: DB first, fall back to live SSE ───────────────────────
  useEffect(() => {
    if (!id) return
    let es: EventSource | null = null

    const init = async () => {
      // Try DB first — if steps already persisted, show immediately
      try {
        const saved = await getIncidentReasoning(id)
        if (saved.length > 0) {
          const now = Date.now()
          setStreamSteps(saved.map((s, i) => ({ ...s, ts: now + i })))
          setStreaming(false)
          return   // no SSE needed
        }
      } catch { /* fall through to SSE */ }

      // No DB steps yet → open live SSE stream
      const BASE = import.meta.env.VITE_API_URL || '/api/v1'
      es = new EventSource(`${BASE}/incidents/${id}/stream`)

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          setStreamSteps(prev => [...prev, { ...data, ts: Date.now() }])
          if (data.stage === 'done' || data.stage === 'blocked') {
            setStreaming(false)
            es?.close()
          }
        } catch { /* ignore */ }
      }

      es.onerror = () => { setStreaming(false); es?.close() }
    }

    init()
    return () => es?.close()
  }, [id])

  // ── Polling ────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!id) return
    const load = async () => {
      try {
        const [inc, notifs, tr] = await Promise.all([
          getIncident(id),
          getIncidentNotifications(id),
          getIncidentTraces(id),
        ])
        setIncident(inc)
        setNotifications(notifs)
        setTraces(tr)
      } catch (e) { console.error(e) }
      finally { setLoading(false) }
    }
    load()
    const iv = setInterval(load, streaming ? 4000 : 10000)
    return () => clearInterval(iv)
  }, [id, streaming])

  const handleResolve = async () => {
    if (!incident?.ticket_id) return
    setResolving(true)
    try {
      await resolveTicket(incident.ticket_id, 'Resolved by SRE team.')
      toast.success('Incident resolved — Reporter notified!')
      const inc = await getIncident(id!)
      setIncident(inc)
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Failed')
    } finally { setResolving(false) }
  }

  if (loading && !incident) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="w-8 h-8 border-2 border-acid-cyan/30 border-t-acid-cyan rounded-full animate-spin" />
      </div>
    )
  }

  const isTriaging = streaming || (incident?.status === 'open' && !incident?.triage_summary)
  const sev = incident?.severity as keyof typeof SEV_CONFIG | undefined
  const sc = sev ? SEV_CONFIG[sev] : null

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 animate-fade-up">
      <Link to="/" className="flex items-center gap-2 text-xs font-mono text-gray-500 hover:text-acid-cyan transition-colors mb-6">
        <ChevronLeft className="w-4 h-4" />
        BACK TO DASHBOARD
      </Link>

      <div className="grid grid-cols-1 xl:grid-cols-[360px_1fr] gap-6">

        {/* LEFT: Reasoning Panel */}
        <div className="xl:sticky xl:top-20 xl:self-start">
          <ReasoningPanel steps={streamSteps} streaming={streaming} />
        </div>

        {/* RIGHT: Incident content */}
        <div className="space-y-5">

          {/* Header */}
          {incident && (
            <div className="terminal-panel p-6">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-3 flex-wrap">
                    {sev && sc && (
                      <span className={`px-2.5 py-1 text-xs font-mono font-bold rounded border ${sc.color} ${sc.bg} ${sc.border}`}>
                        {sev} — {sev === 'P1' ? 'CRITICAL' : sev === 'P2' ? 'HIGH' : sev === 'P3' ? 'MEDIUM' : 'LOW'}
                      </span>
                    )}
                    {incident.ticket_key && (
                      <span className="text-xs font-mono text-acid-cyan border border-acid-cyan/30 px-2 py-1 rounded">
                        {incident.ticket_key}
                      </span>
                    )}
                    <span className={`text-xs font-mono px-2 py-1 rounded border ${
                      incident.status === 'resolved'   ? 'text-acid-green border-acid-green/30 bg-acid-green/10' :
                      incident.status === 'in_progress'? 'text-acid-amber border-acid-amber/30 bg-acid-amber/10' :
                      incident.status === 'duplicate'  ? 'text-gray-400 border-gray-600/30 bg-gray-800/30' :
                      'text-acid-red border-acid-red/30 bg-acid-red/10'
                    }`}>
                      {incident.status.toUpperCase().replace('_', ' ')}
                    </span>
                    {isTriaging && (
                      <span className="flex items-center gap-1.5 text-xs font-mono text-acid-amber border border-acid-amber/30 bg-acid-amber/10 px-2 py-1 rounded">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        ANALYZING
                      </span>
                    )}
                  </div>
                  <h1 className="text-xl font-display font-bold text-white mb-4">{incident.title}</h1>
                  <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs font-mono text-gray-500">
                    {incident.affected_service && (
                      <span><Server className="w-3.5 h-3.5 inline mr-1.5" />{incident.affected_service}</span>
                    )}
                    <span><User className="w-3.5 h-3.5 inline mr-1.5" />{incident.reporter_name || 'Anonymous'}</span>
                    <span><Mail className="w-3.5 h-3.5 inline mr-1.5" />{incident.reporter_email}</span>
                    <span><Clock className="w-3.5 h-3.5 inline mr-1.5" />
                      {formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}
                    </span>
                  </div>
                </div>
                {incident.status !== 'resolved' && incident.ticket_id && !isTriaging && (
                  <button
                    onClick={handleResolve}
                    disabled={resolving}
                    className="flex items-center gap-2 px-4 py-2.5 bg-acid-green/10 border border-acid-green/40 rounded-lg text-acid-green text-xs font-mono font-bold hover:bg-acid-green/20 transition-all disabled:opacity-50 whitespace-nowrap"
                  >
                    <CheckCircle2 className="w-4 h-4" />
                    {resolving ? 'RESOLVING...' : 'RESOLVE TICKET'}
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Investigating overlay while triage runs */}
          {isTriaging && <InvestigatingOverlay steps={streamSteps} />}

          {/* Results — shown once triage done */}
          {!isTriaging && incident && (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                {incident.triage_summary && (
                  <div className="terminal-panel p-5">
                    <div className="flex items-center gap-2 mb-3">
                      <Activity className="w-4 h-4 text-acid-cyan" />
                      <span className="text-xs font-mono text-acid-cyan uppercase tracking-wider">AI Triage Summary</span>
                    </div>
                    <p className="text-sm text-gray-300 leading-relaxed">{incident.triage_summary}</p>
                  </div>
                )}
                {incident.root_cause && (
                  <div className="terminal-panel p-5">
                    <div className="flex items-center gap-2 mb-3">
                      <Code2 className="w-4 h-4 text-acid-amber" />
                      <span className="text-xs font-mono text-acid-amber uppercase tracking-wider">Root Cause</span>
                    </div>
                    <p className="text-sm text-gray-300 leading-relaxed">{incident.root_cause}</p>
                  </div>
                )}
              </div>

              {incident.runbook && (
                <div className="terminal-panel p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <FileText className="w-4 h-4 text-acid-green" />
                    <span className="text-xs font-mono text-acid-green uppercase tracking-wider">Generated Runbook</span>
                  </div>
                  <pre className="text-xs font-mono text-gray-300 leading-relaxed whitespace-pre-wrap bg-terminal-bg rounded p-4 border border-terminal-border overflow-auto max-h-64">
                    {incident.runbook}
                  </pre>
                </div>
              )}
            </>
          )}

          {/* Original report */}
          {incident && (
            <div className="terminal-panel p-5">
              <div className="flex items-center gap-2 mb-3">
                <FileText className="w-4 h-4 text-gray-500" />
                <span className="text-xs font-mono text-gray-500 uppercase tracking-wider">Original Report</span>
              </div>
              <p className="text-sm text-gray-400 leading-relaxed whitespace-pre-wrap">{incident.description}</p>
              {incident.attachment_name && (
                <div className="mt-3 pt-3 border-t border-terminal-border">
                  <span className="text-xs font-mono text-gray-600">
                    Attachment: {incident.attachment_name} ({incident.attachment_type})
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Pipeline Traces */}
          {traces.length > 0 && (
            <div className="terminal-panel p-5">
              <div className="flex items-center gap-2 mb-4">
                <Activity className="w-4 h-4 text-acid-cyan" />
                <span className="text-xs font-mono text-acid-cyan uppercase tracking-wider">Agent Pipeline Traces</span>
                {incident?.langfuse_trace_id && (
                  <span className="ml-auto text-xs font-mono text-gray-600">
                    trace: {incident.langfuse_trace_id.slice(0, 8)}...
                  </span>
                )}
              </div>
              <div className="space-y-2">
                {traces.map((trace, i) => {
                  const Icon = STAGE_ICONS[trace.stage] || Activity
                  return (
                    <div key={i} className="flex items-center gap-3 p-2.5 bg-terminal-bg rounded border border-terminal-border">
                      <Icon className={`w-4 h-4 ${trace.status === 'success' ? 'text-acid-green' : 'text-acid-red'}`} />
                      <span className="text-xs font-mono text-gray-300 uppercase w-16">{trace.stage}</span>
                      <span className={`text-xs font-mono ${trace.status === 'success' ? 'text-acid-green' : 'text-acid-red'}`}>
                        {trace.status}
                      </span>
                      {trace.duration_ms > 0 && (
                        <span className="text-xs font-mono text-gray-600 ml-auto">{trace.duration_ms}ms</span>
                      )}
                      {trace.input_tokens > 0 && (
                        <span className="text-xs font-mono text-gray-600">
                          {trace.input_tokens}↑ {trace.output_tokens}↓ tokens
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Notifications */}
          {notifications.length > 0 && (
            <div className="terminal-panel p-5">
              <div className="flex items-center gap-2 mb-4">
                <Bell className="w-4 h-4 text-acid-cyan" />
                <span className="text-xs font-mono text-acid-cyan uppercase tracking-wider">
                  Notifications ({notifications.length})
                </span>
              </div>
              <div className="space-y-3">
                {notifications.map(n => (
                  <div key={n.id} className="bg-terminal-bg rounded border border-terminal-border p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`text-xs font-mono font-bold ${n.channel === 'slack' ? 'text-acid-green' : 'text-acid-cyan'}`}>
                        [{n.channel.toUpperCase()}]
                      </span>
                      <span className="text-xs font-mono text-gray-500">{n.type}</span>
                      <span className="ml-auto text-xs font-mono text-gray-600">→ {n.recipient}</span>
                    </div>
                    {n.subject && <p className="text-xs font-semibold text-gray-300 mb-1">{n.subject}</p>}
                    <pre className="text-xs text-gray-500 font-mono whitespace-pre-wrap line-clamp-4">{n.body}</pre>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
