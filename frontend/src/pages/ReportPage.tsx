import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import {
  AlertTriangle, Upload, X, FileText, Image, Video,
  Send, ChevronRight, Loader2, Shield
} from 'lucide-react'
import { submitIncident } from '../api/client'

const ENVIRONMENTS = ['production', 'staging', 'development', 'qa']
const SERVICES = [
  'Catalog.API', 'Basket.API', 'Ordering.API', 'Identity.API',
  'WebApp', 'EventBus', 'PaymentProcessor', 'Webhooks.API', 'Unknown'
]

type FileInfo = { file: File; preview?: string; type: 'image' | 'log' | 'video' }

function FileIcon({ type }: { type: string }) {
  if (type === 'image') return <Image className="w-4 h-4 text-acid-cyan" />
  if (type === 'video') return <Video className="w-4 h-4 text-acid-amber" />
  return <FileText className="w-4 h-4 text-acid-green" />
}

export default function ReportPage() {
  const navigate = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)
  const [submitting, setSubmitting] = useState(false)
  const [fileInfo, setFileInfo] = useState<FileInfo | null>(null)
  const [dragOver, setDragOver] = useState(false)

  const [form, setForm] = useState({
    title: '',
    description: '',
    reporter_email: '',
    reporter_name: '',
    environment: 'production',
    affected_service: '',
  })

  const handleFile = (file: File) => {
    const ct = file.type
    let type: FileInfo['type'] = 'log'
    if (ct.startsWith('image/')) type = 'image'
    else if (ct.startsWith('video/')) type = 'video'

    let preview: string | undefined
    if (type === 'image') {
      preview = URL.createObjectURL(file)
    }
    setFileInfo({ file, preview, type })
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.title || !form.description || !form.reporter_email) {
      toast.error('Please fill in required fields')
      return
    }

    setSubmitting(true)
    try {
      const fd = new FormData()
      Object.entries(form).forEach(([k, v]) => { if (v) fd.append(k, v) })
      if (fileInfo) fd.append('attachment', fileInfo.file)

      const result = await submitIncident(fd)
      toast.success(`Incident submitted — AI triage starting now!`)
      navigate(`/incidents/${result.incident_id}`)
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Submission failed'
      if (msg.includes('prompt_injection') || msg.includes('guardrail')) {
        toast.error('Input blocked by security guardrails')
      } else {
        toast.error(msg)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 animate-fade-up">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-2 text-xs font-mono text-gray-500 mb-3">
          <ChevronRight className="w-3 h-3" />
          <span>INCIDENT</span>
          <ChevronRight className="w-3 h-3" />
          <span className="text-acid-cyan">NEW REPORT</span>
        </div>
        <h1 className="font-display text-2xl font-bold text-white mb-1">
          Report Incident
        </h1>
        <p className="text-sm text-gray-400">
          Submit an incident report. The AI agent will triage, classify, and route it automatically.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Title */}
        <div className="terminal-panel p-5">
          <label className="block text-xs font-mono text-acid-cyan mb-2 uppercase tracking-wider">
            Incident Title *
          </label>
          <input
            type="text"
            value={form.title}
            onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
            placeholder="e.g. Checkout failure — orders not processing"
            className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2.5 text-sm font-mono text-gray-100 placeholder-gray-600 transition-all"
            maxLength={200}
            required
          />
        </div>

        {/* Description */}
        <div className="terminal-panel p-5">
          <label className="block text-xs font-mono text-acid-cyan mb-2 uppercase tracking-wider">
            Description *
          </label>
          <textarea
            value={form.description}
            onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            placeholder="Describe what's happening, when it started, error messages, affected users, steps to reproduce..."
            className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2.5 text-sm font-mono text-gray-100 placeholder-gray-600 transition-all resize-none"
            rows={6}
            maxLength={5000}
            required
          />
          <div className="mt-1.5 flex justify-between">
            <span className="text-xs text-gray-600 font-mono">
              Supports: technical details, error logs, stack traces
            </span>
            <span className="text-xs text-gray-600 font-mono">
              {form.description.length}/5000
            </span>
          </div>
        </div>

        {/* Metadata row */}
        <div className="grid grid-cols-2 gap-4">
          <div className="terminal-panel p-5">
            <label className="block text-xs font-mono text-acid-cyan mb-2 uppercase tracking-wider">
              Environment
            </label>
            <select
              value={form.environment}
              onChange={e => setForm(f => ({ ...f, environment: e.target.value }))}
              className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2.5 text-sm font-mono text-gray-100"
            >
              {ENVIRONMENTS.map(e => <option key={e} value={e}>{e}</option>)}
            </select>
          </div>
          <div className="terminal-panel p-5">
            <label className="block text-xs font-mono text-acid-cyan mb-2 uppercase tracking-wider">
              Affected Service
            </label>
            <select
              value={form.affected_service}
              onChange={e => setForm(f => ({ ...f, affected_service: e.target.value }))}
              className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2.5 text-sm font-mono text-gray-100"
            >
              <option value="">Auto-detect</option>
              {SERVICES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>

        {/* Reporter */}
        <div className="terminal-panel p-5">
          <label className="block text-xs font-mono text-acid-cyan mb-3 uppercase tracking-wider">
            Reporter Information
          </label>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1.5 font-mono">Email *</label>
              <input
                type="email"
                value={form.reporter_email}
                onChange={e => setForm(f => ({ ...f, reporter_email: e.target.value }))}
                placeholder="you@company.com"
                className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2 text-sm font-mono text-gray-100 placeholder-gray-600 transition-all"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1.5 font-mono">Name</label>
              <input
                type="text"
                value={form.reporter_name}
                onChange={e => setForm(f => ({ ...f, reporter_name: e.target.value }))}
                placeholder="Your name"
                className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2 text-sm font-mono text-gray-100 placeholder-gray-600 transition-all"
              />
            </div>
          </div>
        </div>

        {/* File attachment */}
        <div className="terminal-panel p-5">
          <label className="block text-xs font-mono text-acid-cyan mb-3 uppercase tracking-wider">
            Attachment (optional)
          </label>
          <p className="text-xs text-gray-500 mb-3">
            Attach screenshots, log files, or video recordings. The AI will analyze them as part of triage.
          </p>

          {!fileInfo ? (
            <div
              className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-all ${
                dragOver
                  ? 'border-acid-cyan/60 bg-acid-cyan/5'
                  : 'border-terminal-border hover:border-acid-cyan/30 hover:bg-acid-cyan/5'
              }`}
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileRef.current?.click()}
            >
              <Upload className="w-8 h-8 text-gray-600 mx-auto mb-3" />
              <p className="text-sm text-gray-400 font-mono">Drop file here or click to browse</p>
              <p className="text-xs text-gray-600 mt-1">PNG, JPG, MP4, TXT, LOG — max 20MB</p>
            </div>
          ) : (
            <div className="flex items-center gap-3 bg-terminal-bg border border-terminal-border rounded-lg p-3">
              {fileInfo.preview ? (
                <img src={fileInfo.preview} alt="preview" className="w-16 h-16 object-cover rounded" />
              ) : (
                <div className="w-16 h-16 bg-terminal-surface rounded flex items-center justify-center">
                  <FileIcon type={fileInfo.type} />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-mono text-gray-200 truncate">{fileInfo.file.name}</p>
                <p className="text-xs text-gray-500 font-mono mt-0.5">
                  {fileInfo.type.toUpperCase()} · {(fileInfo.file.size / 1024).toFixed(0)} KB
                </p>
              </div>
              <button
                type="button"
                onClick={() => setFileInfo(null)}
                className="p-1.5 hover:bg-terminal-border rounded transition-colors"
              >
                <X className="w-4 h-4 text-gray-500" />
              </button>
            </div>
          )}
          <input
            ref={fileRef}
            type="file"
            className="hidden"
            accept="image/*,video/mp4,.txt,.log,.csv"
            onChange={e => { if (e.target.files?.[0]) handleFile(e.target.files[0]) }}
          />
        </div>

        {/* Security notice */}
        <div className="flex items-start gap-2 px-4 py-3 bg-acid-cyan/5 border border-acid-cyan/20 rounded-lg">
          <Shield className="w-4 h-4 text-acid-cyan mt-0.5 flex-shrink-0" />
          <p className="text-xs text-gray-400">
            Input is scanned for prompt injection and malicious content before processing.
            All submissions are logged and traceable via Langfuse.
          </p>
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={submitting}
          className="w-full flex items-center justify-center gap-3 py-3.5 bg-acid-green/10 border border-acid-green/40 rounded-lg text-acid-green font-mono text-sm font-bold tracking-wider hover:bg-acid-green/20 hover:border-acid-green/60 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              SUBMITTING...
            </>
          ) : (
            <>
              <Send className="w-4 h-4" />
              SUBMIT INCIDENT REPORT
            </>
          )}
        </button>
      </form>
    </div>
  )
}
