import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: '#0d1117',
            color: '#e2e8f0',
            border: '1px solid #1c2a3a',
            fontFamily: '"JetBrains Mono", monospace',
            fontSize: '13px',
          },
          success: { iconTheme: { primary: '#00ff88', secondary: '#0d1117' } },
          error: { iconTheme: { primary: '#ff3860', secondary: '#0d1117' } },
        }}
      />
    </BrowserRouter>
  </React.StrictMode>,
)
