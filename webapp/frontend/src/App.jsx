import React, { useRef } from 'react';
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
import { StepTTS } from './components/features/StepTTS';
import { StepResults } from './components/features/StepResults';
import { SRTWidget } from './components/features/SRTWidget';
import { GlobalProgress } from './components/features/GlobalProgress';

function App() {
  const {
    jobId,
    jobData,
    currentStep,
    setCurrentStep,
    doneSteps,
    sseConnected,
    isSavingSrt,
    handleSaveSrtTexts
  } = useJob();

  const videoRef = useRef(null);

  // We need to serve the video file.
  // Let's construct a video URL requesting the explicit 'video' key.
  const videoUrl = jobData?.video_path ? `/api/jobs/${jobId}/downloads/video` : null;

  return (
    <div className="grid grid-rows-[auto_1fr_auto] min-h-screen">
      <header className="h-14 border-b border-border-subtle flex items-center justify-between px-4 bg-bg-surface z-50 sticky top-0">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-violet-500 rounded-lg flex items-center justify-center text-white">
              <span className="material-icons-round text-lg">waves</span>
            </div>
            <h1 className="font-bold text-lg tracking-tight">Descr<span className="text-violet-500 text-xl">AI</span>be <span className="font-light opacity-60">Pipeline</span></h1>
          </div>
          {jobId && (
            <>
              <div className="h-6 w-px bg-border-subtle mx-2"></div>
              <div className="flex items-center gap-2 text-xs font-mono opacity-50">
                <span className={`w-2 h-2 rounded-full ${sseConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></span>
                <span>Job: {jobId}</span>
              </div>
            </>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            className="px-4 py-2 bg-violet-500 hover:bg-opacity-90 transition-all rounded-lg text-white text-sm font-medium flex items-center gap-2 disabled:opacity-50"
            onClick={handleSaveSrtTexts}
            disabled={isSavingSrt}
          >
            <span className="material-icons-round text-sm">save</span>
            {isSavingSrt ? 'Speichert...' : 'Änderungen speichern'}
          </button>
          <button className="p-2 hover:bg-bg-card rounded-full transition-colors flex items-center justify-center">
            <span className="material-icons-round text-text-secondary">settings</span>
          </button>
        </div>
      </header>

      <div className="grid grid-cols-[380px_1fr] gap-0 h-[calc(100vh-88px)]">
        <aside className="bg-bg-surface border-r border-border-subtle p-6 px-4 overflow-y-auto flex flex-col gap-6">
          <StepNavigation currentStep={currentStep} setCurrentStep={setCurrentStep} doneSteps={doneSteps} />

          <div className="flex flex-col gap-4">
            <StepUpload />
            <StepVAD />
            <StepTranscribe />
            <StepSlots />
            <StepImages />
            <StepPrompts />
            <StepGenerate />
            <StepTTS />
            <StepResults />
          </div>
        </aside>

        <main className="overflow-hidden p-6 flex flex-col gap-6">
          <div className="flex flex-col gap-5 h-full flex-1 min-h-0">
            {videoUrl && (
              <div className="grid grid-cols-2 gap-6 flex-1 min-h-0">
                <div className="flex flex-col h-full min-h-0">
                  <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-2 shrink-0">Video Vorschau</p>
                  <div className="flex-1 min-h-0 flex justify-center bg-black rounded-lg overflow-hidden">
                    <video
                      ref={videoRef}
                      src={videoUrl}
                      controls
                      preload="auto"
                      className="w-full h-full object-contain"
                    />
                  </div>
                </div>

                <div className="flex flex-col h-full min-h-0">
                  <SRTWidget />
                </div>
              </div>
            )}

            {videoUrl && (
              <div className="shrink-0">
                <VideoTimeline videoRef={videoRef} />
              </div>
            )}

            {!videoUrl && (
              <div className="flex items-center justify-center h-full text-text-muted">
                <p>Bitte lade ein Video hoch (Schritt 1), um den Workspace anzuzeigen.</p>
              </div>
            )}
          </div>
        </main>
      </div>

      <GlobalProgress />
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
    { num: 8, label: 'Vertonung (TTS)' },
    { num: 9, label: 'Ergebnisse & Download' },
  ];

  return (
    <nav className="p-4 space-y-1 mt-[-1rem]">
      <div className="text-[10px] font-bold text-text-muted uppercase tracking-widest px-2 mb-2">Workflow</div>
      <div className="flex flex-col gap-1" id="step-nav">
        {steps.map((s, i) => {
          const isCurrent = currentStep === i;
          const isDone = doneSteps.has(i);
          return (
            <button
              key={i}
              className={`flex items-center gap-3 p-2 rounded-lg transition-all group ${isCurrent
                ? 'bg-violet-500/10 text-violet-500'
                : 'hover:bg-bg-card text-text-primary'
                } ${!isCurrent && !isDone ? 'opacity-50' : ''}`}
              onClick={() => setCurrentStep(i)}
            >
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold transition-colors ${isCurrent ? 'bg-violet-500 text-white' :
                isDone ? 'border-2 border-green-500 text-green-500 group-hover:bg-green-500 group-hover:text-white' :
                  'border-2 border-text-muted text-text-secondary'
                }`}>
                {s.num}
              </div>
              <span className={`text-sm font-medium ${isDone && !isCurrent ? 'opacity-60' : ''}`}>{s.label}</span>
              {isDone && !isCurrent && (
                <span className="material-icons-round text-green-500 ml-auto text-sm">check_circle</span>
              )}
              {isCurrent && (
                <span className="w-1.5 h-1.5 rounded-full bg-violet-500 ml-auto"></span>
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
}

export default App;
