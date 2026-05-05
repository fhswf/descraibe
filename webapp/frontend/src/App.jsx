import React, { useRef } from 'react';
import { useJob } from './hooks/useJob.jsx';
import { VideoTimeline } from './components/features/VideoTimeline';
import './index.css';


import { StepVAD } from './components/features/StepVAD';
import { StepTranscribe } from './components/features/StepTranscribe';
import { StepSlots } from './components/features/StepSlots';
import { StepImages } from './components/features/StepImages';
import { ConfigModal } from './components/features/ConfigModal';
import { StepGenerate } from './components/features/StepGenerate';
import { StepTTS } from './components/features/StepTTS';
import { StepResults } from './components/features/StepResults';
import { SRTWidget } from './components/features/SRTWidget';

function App() {
  const {
    jobId,
    jobData,
    currentStep,
    setCurrentStep,
    doneSteps,
    sseConnected,
    isSavingSrt,
    handleSaveSrtTexts,
    setIsConfigModalOpen,
    runAllSteps,
    isRunAllActive,
    stopRunAll,
    createJob,
    fetchJobData,
    setProgressData,
    savedJobIds,
    savedJobMeta,
    selectJob,
    removeSavedJobId,
    updateSavedJobMeta
  } = useJob();

  const uploadInputRef = useRef(null);

  const handleUpload = async (file) => {
    setProgressData(prev => ({ ...prev, upload: { msg: 'Starte Upload...', percent: 0 } }));
    let activeJobId = jobId;
    if (!activeJobId) activeJobId = await createJob();
    updateSavedJobMeta(activeJobId, {
      name: file.name,
      status: 'uploading',
      progressPercent: 0,
      progressMessage: 'Upload'
    });
    const CHUNK_SIZE = 5 * 1024 * 1024;
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    for (let i = 0; i < totalChunks; i++) {
      const start = i * CHUNK_SIZE;
      const chunk = file.slice(start, Math.min(file.size, start + CHUNK_SIZE));
      const formData = new FormData();
      formData.append('filename', file.name);
      formData.append('chunkIndex', i);
      formData.append('totalChunks', totalChunks);
      formData.append('chunk', chunk);
      try {
        const res = await fetch(`/api/jobs/${activeJobId}/video`, { method: 'POST', body: formData });
        if (!res.ok) throw new Error('Upload failed');
        const data = await res.json();
        const uploadPercent = Math.round(((i + 1) / totalChunks) * 100);
        setProgressData(prev => ({ ...prev, upload: { msg: 'Lade Datei hoch...', percent: uploadPercent } }));
        updateSavedJobMeta(activeJobId, {
          name: file.name,
          status: data.complete ? 'idle' : 'uploading',
          progressPercent: data.complete ? null : uploadPercent,
          progressMessage: data.complete ? null : 'Upload'
        });
        if (data.complete) await fetchJobData(activeJobId);
      } catch (err) {
        console.error(err);
        updateSavedJobMeta(activeJobId, {
          status: 'error',
          progressPercent: null,
          progressMessage: err.message
        });
        alert('Upload error: ' + err.message);
        break;
      }
    }
    setProgressData(prev => ({ ...prev, upload: null }));
  };

  const videoRef = useRef(null);

  // We need to serve the video file.
  // Let's construct a video URL requesting the explicit 'video' key.
  const videoUrl = jobData?.video_path ? `/api/jobs/${jobId}/downloads/video` : null;

  return (
    <div className="grid grid-rows-[auto_1fr_auto] min-h-screen">
      <header className="h-14 border-b border-border-subtle flex items-center justify-between px-4 bg-bg-surface z-50 sticky top-0">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <img src="/favicon.png" alt="DescrAIbe Logo" className="w-8 h-8 rounded-[8px] object-cover shadow-sm" />
            <div className="flex flex-col">
              <h1 className="font-bold text-lg tracking-tight leading-none">Descr<span className="text-violet-500 text-xl">AI</span>be <span className="font-light opacity-60">Pipeline</span></h1>
              <span className="text-[10px] text-text-muted mt-0.5">v{import.meta.env.VITE_APP_VERSION}</span>
            </div>
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
          <button 
            className="p-2 hover:bg-bg-card rounded-full transition-colors flex items-center justify-center"
            onClick={() => setIsConfigModalOpen(true)}
            title="Prompts & Konfiguration"
          >
            <span className="material-icons-round text-text-secondary">settings</span>
          </button>
        </div>
      </header>

      <div className="grid grid-cols-[380px_1fr] gap-0 h-[calc(100vh-88px)]">
        <aside className="bg-bg-surface border-r border-border-subtle p-6 px-4 overflow-y-auto flex flex-col gap-6">
          <JobList
            jobId={jobId}
            jobData={jobData}
            savedJobIds={savedJobIds}
            savedJobMeta={savedJobMeta}
            createJob={createJob}
            selectJob={selectJob}
            removeSavedJobId={removeSavedJobId}
          />

          <StepNavigation currentStep={currentStep} setCurrentStep={setCurrentStep} doneSteps={doneSteps} />

          <div className="flex flex-col gap-2 mt-[-1rem] px-2">
            {!isRunAllActive ? (
              <button
                className="w-full flex justify-center items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm transition-all bg-violet-600 hover:bg-violet-500 text-white shadow-md shadow-violet-500/20 disabled:opacity-50"
                onClick={runAllSteps}
                disabled={!jobId}
              >
                <span className="material-icons-round text-[1.1rem]">play_arrow</span>
                Alle Schritte ausführen
              </button>
            ) : (
              <button
                className="w-full flex justify-center items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm transition-all bg-red-500/20 hover:bg-red-500/30 text-red-500 border border-red-500/30"
                onClick={stopRunAll}
              >
                <span className="material-icons-round text-[1.1rem]">stop</span>
                Ausführung anhalten
              </button>
            )}
            
            <button
                className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors bg-white/5 hover:bg-white/10 text-text-primary border border-border-subtle"
                onClick={() => setIsConfigModalOpen(true)}
              >
                <span className="material-icons-round text-[1.1rem]">settings</span>
                Konfiguration ändern
            </button>
          </div>

          <div className="flex flex-col gap-4">
            <StepVAD />
            <StepTranscribe />
            <StepSlots />
            <StepImages />
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
                <VideoTimeline videoRef={videoRef} videoUrl={videoUrl} />
              </div>
            )}

            {!videoUrl && (
              <div
                className="flex-1 flex flex-col items-center justify-center h-full border-2 border-dashed border-border-subtle rounded-2xl transition-all hover:border-violet-500 hover:bg-violet-500/5 group cursor-pointer"
                onClick={() => uploadInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files?.[0]) handleUpload(e.dataTransfer.files[0]); }}
              >
                <input
                  type="file"
                  ref={uploadInputRef}
                  accept="video/mp4,video/*"
                  style={{ display: 'none' }}
                  onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
                />
                <div className="text-[4rem] mb-4 group-hover:scale-110 transition-transform">🎞️</div>
                <p className="text-[1.3rem] font-semibold mb-2 text-text-primary">MP4 per Drag &amp; Drop hier ablegen</p>
                <p className="text-sm text-text-muted">oder klicken zum Auswählen einer Videodatei</p>
              </div>
            )}
          </div>
        </main>
      </div>

      <ConfigModal />
    </div>
  );
}

function JobList({ jobId, jobData, savedJobIds, savedJobMeta, createJob, selectJob, removeSavedJobId }) {
  const activeName = jobData?.video_path?.split(/[\\/]/).filter(Boolean).pop();
  const activeStatus = jobData?.status || (jobId ? 'lädt...' : null);

  return (
    <section className="px-2 mt-[-0.5rem]">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[10px] font-bold text-text-muted uppercase tracking-widest">Jobs</div>
        <button
          className="w-7 h-7 flex items-center justify-center rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-card transition-colors"
          onClick={createJob}
          title="Neuen Job erstellen"
        >
          <span className="material-icons-round text-[1.1rem]">add</span>
        </button>
      </div>

      <div className="flex flex-col gap-1" aria-label="Gespeicherte Jobs">
        {savedJobIds.length === 0 ? (
          <div className="rounded-lg border border-border-subtle bg-white/5 px-3 py-2 text-xs text-text-secondary">
            Noch keine Jobs gespeichert.
          </div>
        ) : (
          savedJobIds.map(savedJobId => {
            const isActive = savedJobId === jobId;
            const meta = savedJobMeta[savedJobId] || {};
            const displayName = isActive
              ? activeName || meta.name || `Job ${savedJobId.slice(0, 8)}`
              : meta.name || `Job ${savedJobId.slice(0, 8)}`;
            const status = isActive ? activeStatus || meta.status : meta.status;
            const percent = Number.isFinite(meta.progressPercent) ? meta.progressPercent : null;
            const showPercent = (status === 'running' || status === 'uploading') && percent !== null;
            const showProgress = status === 'running' || status === 'uploading';
            return (
              <div
                key={savedJobId}
                className={`group flex items-start gap-1 rounded-lg border transition-all ${isActive
                  ? 'border-violet-500/50 bg-violet-500/10 text-text-primary'
                  : 'border-transparent hover:border-border-subtle hover:bg-bg-card text-text-secondary'
                  }`}
              >
                <button
                  className="min-w-0 flex flex-1 items-start gap-2 px-3 py-2 text-left"
                  onClick={() => selectJob(savedJobId)}
                  title={savedJobId}
                >
                  <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${isActive ? 'bg-violet-500' : 'bg-text-muted'}`}></span>
                  <span className="min-w-0 flex-1">
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="block min-w-0 flex-1 truncate text-sm font-medium">{displayName}</span>
                      {status && (
                        <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${showProgress
                          ? 'bg-violet-500/15 text-violet-300'
                          : status === 'error'
                            ? 'bg-red-500/15 text-red-300'
                            : 'bg-white/5 text-text-secondary'
                          }`}>
                          {showPercent ? `${percent}%` : status}
                        </span>
                      )}
                    </span>
                    <span className="block truncate font-mono text-[10px] text-text-muted">{savedJobId}</span>
                    {showProgress && (
                      <span className="mt-1.5 block">
                        <span className="flex items-center justify-between gap-2 text-[10px] text-text-muted">
                          <span className="truncate">{meta.progressMessage || (status === 'uploading' ? 'Upload' : 'In Bearbeitung')}</span>
                          {showPercent && <span className="shrink-0 font-mono">{percent}%</span>}
                        </span>
                        <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-white/10">
                          <span
                            className={`block h-full rounded-full ${showPercent ? 'bg-violet-400' : 'bg-violet-400/60'}`}
                            style={{ width: showPercent ? `${percent}%` : '100%' }}
                          ></span>
                        </span>
                      </span>
                    )}
                  </span>
                </button>
                <button
                  className="mr-1 mt-2 w-6 h-6 shrink-0 opacity-0 group-hover:opacity-100 focus:opacity-100 flex items-center justify-center rounded-md text-text-muted hover:text-red-400 hover:bg-red-500/10 transition-all"
                  onClick={() => removeSavedJobId(savedJobId)}
                  title="Aus Liste entfernen"
                >
                  <span className="material-icons-round text-[1rem]">close</span>
                </button>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}

function StepNavigation({ currentStep, setCurrentStep, doneSteps }) {
  const { jobData, progressData, handleRunVAD, handleRunTranscribe, handleRunSlots, handleRunImages, handleRunGPT, handleRunTTS } = useJob();
  
  const steps = [
    { num: 1, label: 'Video hochladen' },
    { num: 2, key: 'vad', label: 'Sprechpausen (VAD)', action: handleRunVAD },
    { num: 3, key: 'transcribe', label: 'Transkription', action: handleRunTranscribe },
    { num: 4, key: 'slots', label: 'AD-Slots', action: handleRunSlots },
    { num: 5, key: 'images', label: 'Bilder extrahieren', action: handleRunImages },
    { num: 6, key: 'gpt', label: 'Generieren', action: handleRunGPT },
    { num: 7, key: 'tts', label: 'Vertonung (TTS)', action: handleRunTTS },
    { num: 8, label: 'Ergebnisse & Download' },
  ];
  const runningStep = jobData?.status === 'running'
    ? jobData?.latest_progress?.step || Object.entries(progressData || {}).find(([, data]) => data !== null)?.[0]
    : null;

  return (
    <nav className="p-4 space-y-1 mt-[-1rem]">
      <div className="text-[10px] font-bold text-text-muted uppercase tracking-widest px-2 mb-2">Workflow</div>
      <div className="flex flex-col gap-1" id="step-nav">
        {steps.map((s, i) => {
          const isCurrent = currentStep === i;
          const isDone = doneSteps.has(i);
          const isRunning = s.key && runningStep === s.key;
          return (
            <button
              key={i}
              className={`flex items-center gap-3 p-2 rounded-lg transition-all group ${isRunning
                ? 'bg-amber-500/10 text-amber-300 border border-amber-500/20'
                : isCurrent
                  ? 'bg-violet-500/10 text-violet-500'
                : 'hover:bg-bg-card text-text-primary'
                } ${!isCurrent && !isDone && !isRunning ? 'opacity-50' : ''}`}
              onClick={() => setCurrentStep(i)}
            >
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold transition-colors ${isRunning ? 'bg-amber-500 text-black' :
                isCurrent ? 'bg-violet-500 text-white' :
                isDone ? 'border-2 border-green-500 text-green-500 group-hover:bg-green-500 group-hover:text-white' :
                  'border-2 border-text-muted text-text-secondary'
                }`}>
                {isRunning ? <span className="material-icons-round text-[0.95rem] animate-spin">progress_activity</span> : s.num}
              </div>
              <span className={`text-sm font-medium ${isDone && !isCurrent && !isRunning ? 'opacity-60' : ''}`}>{s.label}</span>
              {isRunning ? (
                <span className="ml-auto text-[10px] font-bold uppercase tracking-wider text-amber-300 shrink-0">läuft</span>
              ) : isCurrent && s.action ? (
                <button
                   className="w-6 h-6 flex shrink-0 items-center justify-center rounded-full bg-violet-600 hover:bg-violet-500 text-white ml-auto shadow-sm shadow-violet-500/20 disabled:opacity-50 transition-all hover:scale-110"
                   onClick={(e) => { e.stopPropagation(); s.action(); }}
                   disabled={jobData?.status === 'running'}
                   title="Schritt ausführen"
                >
                   <span className="material-icons-round text-[1.1rem]">play_arrow</span>
                </button>
              ) : isDone && !isCurrent ? (
                <span className="material-icons-round text-green-500 ml-auto text-sm shrink-0">check_circle</span>
              ) : isCurrent ? (
                <span className="w-1.5 h-1.5 shrink-0 rounded-full bg-violet-500 ml-auto"></span>
              ) : null}
            </button>
          );
        })}
      </div>
    </nav>
  );
}

export default App;
