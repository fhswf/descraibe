import React, { useRef, useState, useEffect } from 'react';
import { useJob } from './hooks/useJob.jsx';
import { VideoTimeline } from './components/features/VideoTimeline';
import './index.css';

import { StepUpload } from './components/features/StepUpload';
import { StepVAD } from './components/features/StepVAD';
import { StepTranscribe } from './components/features/StepTranscribe';
import { StepSlots } from './components/features/StepSlots';
import { StepImages } from './components/features/StepImages';
import { StepPrompts } from './components/features/StepPrompts';
import { StepGenerate } from './components/features/StepGenerate';
import { StepResults } from './components/features/StepResults';
import { SRTWidget } from './components/features/SRTWidget';

function App() {
  const {
    jobId,
    jobData,
    currentStep,
    setCurrentStep,
    doneSteps,
    sseConnected
  } = useJob();

  const videoRef = useRef(null);

  // We need to serve the video file.
  // Let's construct a video URL requesting the explicit 'video' key.
  const videoUrl = jobData?.video_path ? `/api/jobs/${jobId}/downloads/video` : null;

  return (
    <div className="app-shell">
      <header className="header">
        <div className="header-logo">🎬</div>
        <h1>Descr<span>AI</span>be Pipeline</h1>
        <span className="header-sub" id="job-badge">
          {jobId ? (sseConnected ? `🟢 Job: ${jobId}` : `🔴 Job: ${jobId} (Offline)`) : 'Kein aktiver Job'}
        </span>
      </header>

      <div className="main-layout">
        <aside className="sidebar">
          <StepNavigation currentStep={currentStep} setCurrentStep={setCurrentStep} doneSteps={doneSteps} />

          <div className="step-controls">
            <StepUpload />
            <StepVAD />
            <StepTranscribe />
            <StepSlots />
            <StepImages />
            <StepPrompts />
            <StepGenerate />
            <StepResults />
          </div>
        </aside>

        <main className="content">
          <div className="main-workspace">
            {videoUrl && (
              <div className="split-view">
                <div className="video-section" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                  <p className="card-title" style={{ margin: 0, marginBottom: '8px', flexShrink: 0 }}>Video Vorschau</p>
                  <div style={{ flex: 1, minHeight: 0, display: 'flex', justifyContent: 'center', backgroundColor: '#000', borderRadius: '8px', overflow: 'hidden' }}>
                    <video
                      ref={videoRef}
                      src={videoUrl}
                      controls
                      preload="auto"
                      style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                    />
                  </div>
                </div>

                <div className="srt-section">
                  <SRTWidget />
                </div>
              </div>
            )}

            {videoUrl && (
              <div className="timeline-section">
                <VideoTimeline videoRef={videoRef} />
              </div>
            )}

            {!videoUrl && (
              <div className="empty-workspace" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>
                <p>Bitte lade ein Video hoch (Schritt 1), um den Workspace anzuzeigen.</p>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

function StepNavigation({ currentStep, setCurrentStep, doneSteps }) {
  const steps = [
    { num: 1, label: 'Video hochladen' },
    { num: 2, label: 'Sprechpausen (VAD)' },
    { num: 3, label: 'Transkription' },
    { num: 4, label: 'AD-Slots' },
    { num: 5, label: 'Bilder extrahieren' },
    { num: 6, label: 'Prompts & Config' },
    { num: 7, label: 'Generieren' },
    { num: 8, label: 'Ergebnisse & Download' },
  ];

  return (
    <nav className="step-navigation">
      <p className="sidebar-title">Pipeline-Schritte</p>
      <div className="step-nav" id="step-nav">
        {steps.map((s, i) => (
          <button
            key={i}
            className={`step-btn ${currentStep === i ? 'active' : ''} ${doneSteps.has(i) ? 'done' : ''}`}
            onClick={() => setCurrentStep(i)}
          >
            <span className="step-num">{s.num}</span>
            <span className="step-label">{s.label}</span>
            <span className="step-status-dot"></span>
          </button>
        ))}
      </div>
    </nav>
  );
}

export default App;
