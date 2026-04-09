import { Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { Activity, AlertTriangle, LayoutDashboard, Plus, Shield, Zap } from 'lucide-react'
import ReportPage from './pages/ReportPage'
import DashboardPage from './pages/DashboardPage'
import IncidentDetailPage from './pages/IncidentDetailPage'

function NavBar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-terminal-border bg-terminal-surface/95 backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-8 h-8 rounded border border-acid-cyan/40 flex items-center justify-center">
              <Zap className="w-4 h-4 text-acid-cyan" />
            </div>
            <div className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-acid-green rounded-full animate-pulse" />
          </div>
          <div>
            <span className="font-display text-sm font-bold text-white tracking-wider">
              AGENTX
            </span>
            <span className="font-mono text-xs text-acid-cyan/60 ml-2">SRE-TRIAGE</span>
          </div>
        </div>

        {/* Nav links */}
        <div className="flex items-center gap-1">
          <NavLink
            to="/"
            className={({ isActive }) =>
              `flex items-center gap-2 px-3 py-1.5 rounded text-xs font-mono transition-all ${
                isActive
                  ? 'bg-acid-cyan/10 text-acid-cyan border border-acid-cyan/30'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
              }`
            }
          >
            <LayoutDashboard className="w-3.5 h-3.5" />
            DASHBOARD
          </NavLink>
          <NavLink
            to="/report"
            className={({ isActive }) =>
              `flex items-center gap-2 px-3 py-1.5 rounded text-xs font-mono transition-all ${
                isActive
                  ? 'bg-acid-green/10 text-acid-green border border-acid-green/30'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
              }`
            }
          >
            <Plus className="w-3.5 h-3.5" />
            REPORT INCIDENT
          </NavLink>
        </div>

        {/* Status */}
        <div className="flex items-center gap-2 text-xs font-mono text-gray-500">
          <span className="status-dot active" />
          <span className="text-acid-green/70">AGENT ONLINE</span>
        </div>
      </div>
    </nav>
  )
}

export default function App() {
  return (
    <div className="min-h-screen bg-terminal-bg bg-ops-grid">
      <NavBar />
      <main className="pt-14">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/report" element={<ReportPage />} />
          <Route path="/incidents/:id" element={<IncidentDetailPage />} />
        </Routes>
      </main>
    </div>
  )
}
