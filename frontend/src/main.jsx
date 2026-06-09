import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { JobProvider } from './hooks/useJob.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <JobProvider>
      <App />
    </JobProvider>
  </React.StrictMode>,
)
