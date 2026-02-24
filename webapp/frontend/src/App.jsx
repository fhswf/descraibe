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
        <Sidebar currentStep={currentStep} setCurrentStep={setCurrentStep} doneSteps={doneSteps} />

        <main className="content">
          <div className="step-panel visible" style={{ paddingBottom: '2rem' }}>

            {/* Render the active step component */}
            <StepUpload />
            <StepVAD />
            <StepTranscribe />
            <StepSlots />
            <StepImages />
            <StepPrompts />
            <StepGenerate />
            <StepResults />

            {/* If video is uploaded, show the player and timeline */}
            {videoUrl && (
              <div className="card" style={{ marginTop: '20px' }}>
                <p className="card-title">Video Vorschau</p>
                <video
                  ref={videoRef}
                  src={videoUrl}
                  controls
                  preload="auto"
                  style={{ width: '100%', maxHeight: '400px', backgroundColor: '#000' }}
                />
                <VideoTimeline videoRef={videoRef} />
              </div>
            )}

            <SRTWidget />
          </div>
        </main>
      </div>
    </div>
  );
}

function Sidebar({ currentStep, setCurrentStep, doneSteps }) {
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
    <nav className="sidebar">
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
