import React, { useEffect, useRef, useState } from 'react';
import { useJob } from './hooks/useJob.jsx';
import { useCachedVideoUrl } from './hooks/useCachedVideoUrl.jsx';
import { VideoTimeline } from './components/features/VideoTimeline';
import { uploadVideoInChunks } from './utils/uploadVideo.js';
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

const APP_VERSION = import.meta.env.VITE_APP_VERSION;
const BUILD_CHANNEL = import.meta.env.VITE_APP_BUILD_CHANNEL;
const COMMIT_SHA = import.meta.env.VITE_APP_COMMIT_SHA;
const REPOSITORY_URL = import.meta.env.VITE_APP_REPOSITORY_URL?.replace(/\/$/, '') || '';
const VERSION_LABEL = import.meta.env.VITE_APP_VERSION_LABEL;
const SHA_TAG = COMMIT_SHA ? `sha-${COMMIT_SHA.slice(0, 7)}` : '';
const COMMIT_URL = COMMIT_SHA && REPOSITORY_URL ? `${REPOSITORY_URL}/commit/${COMMIT_SHA}` : '';
const SHOW_STAGING_SHA = BUILD_CHANNEL === 'staging' && Boolean(SHA_TAG);
const LINK_STAGING_SHA = SHOW_STAGING_SHA && Boolean(COMMIT_URL);
const SHOW_VERSION_LABEL = !SHOW_STAGING_SHA && Boolean(VERSION_LABEL);
const THEME_STORAGE_KEY = 'descraibe-theme-mode';
const THEME_OPTIONS = ['system', 'light', 'dark'];

function getInitialThemeMode() {
  if (typeof window === 'undefined') return 'system';
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return THEME_OPTIONS.includes(stored) ? stored : 'system';
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return 'unbekannt';
  if (bytes === 0) return '0 B';

  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** unitIndex;
  const precision = value >= 10 || unitIndex === 0 ? 0 : 1;

  return `${value.toFixed(precision)} ${units[unitIndex]}`;
}

function StorageQuotaFooter() {
  const [storageEstimate, setStorageEstimate] = useState({
    status: navigator.storage?.estimate ? 'loading' : 'unsupported',
    usage: null,
    quota: null,
    opfsUsage: null
  });

  useEffect(() => {
    let isMounted = true;

    const updateStorageEstimate = async () => {
      if (!navigator.storage?.estimate) {
        if (isMounted) {
          setStorageEstimate(prev => ({ ...prev, status: 'unsupported' }));
        }
        return;
      }

      try {
        const estimate = await navigator.storage.estimate();
        if (!isMounted) return;

        setStorageEstimate({
          status: 'ready',
          usage: estimate.usage ?? null,
          quota: estimate.quota ?? null,
          opfsUsage: estimate.usageDetails?.fileSystem ?? null
        });
      } catch {
        if (isMounted) {
          setStorageEstimate(prev => ({ ...prev, status: 'error' }));
        }
      }
    };

    updateStorageEstimate();
    const intervalId = window.setInterval(updateStorageEstimate, 15_000);

    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
    };
  }, []);

  const originText = storageEstimate.status === 'ready'
    ? `${formatBytes(storageEstimate.usage)} / ${formatBytes(storageEstimate.quota)}`
    : storageEstimate.status === 'loading'
      ? 'wird geladen...'
      : 'nicht verfügbar';
  const opfsText = storageEstimate.opfsUsage !== null
    ? `OPFS ${formatBytes(storageEstimate.opfsUsage)}`
    : 'OPFS im Ursprung enthalten';

  return (
    <footer className="h-8 border-t border-border-subtle bg-bg-surface px-4 flex items-center justify-end gap-3 text-[10px] text-text-muted">
      <span className="font-semibold uppercase tracking-wider">Origin Storage</span>
      <span className="font-mono">{originText}</span>
      {storageEstimate.status === 'ready' && (
        <>
          <span className="h-3 w-px bg-border-subtle"></span>
          <span>{opfsText}</span>
        </>
      )}
    </footer>
  );
}

function App() {
  const {
    jobId,
    jobData,
    currentStep,
    setCurrentStep,
    doneSteps,
    sseConnected,
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
    updateSavedJobMeta,
    authState,
    login,
    logout
  } = useJob();

  const uploadInputRef = useRef(null);
  const userMenuRef = useRef(null);
  const [themeMode, setThemeMode] = useState(getInitialThemeMode);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode;
    window.localStorage.setItem(THEME_STORAGE_KEY, themeMode);
  }, [themeMode]);

  useEffect(() => {
    if (!isUserMenuOpen) return;
    const handlePointerDown = (event) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setIsUserMenuOpen(false);
      }
    };
    const handleEscape = (event) => {
      if (event.key === 'Escape') setIsUserMenuOpen(false);
    };
    window.addEventListener('mousedown', handlePointerDown);
    window.addEventListener('keydown', handleEscape);
    return () => {
      window.removeEventListener('mousedown', handlePointerDown);
      window.removeEventListener('keydown', handleEscape);
    };
  }, [isUserMenuOpen]);

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
    try {
      const data = await uploadVideoInChunks({
        jobId: activeJobId,
        file,
        onProgress: ({ percent, chunkIndex, totalChunks }) => {
          const msg = `Lade Datei hoch... (${chunkIndex + 1}/${totalChunks})`;
          setProgressData(prev => ({ ...prev, upload: { msg, percent } }));
          updateSavedJobMeta(activeJobId, {
            name: file.name,
            status: 'uploading',
            progressPercent: percent,
            progressMessage: 'Upload'
          });
        }
      });

      if (data?.complete) {
        updateSavedJobMeta(activeJobId, {
          name: file.name,
          status: 'idle',
          progressPercent: null,
          progressMessage: null
        });
        await fetchJobData(activeJobId);
      }
    } catch (err) {
      console.error(err);
      updateSavedJobMeta(activeJobId, {
        status: 'error',
        progressPercent: null,
        progressMessage: err.message
      });
      alert('Upload error: ' + err.message);
    }
    setProgressData(prev => ({ ...prev, upload: null }));
  };

  const videoRef = useRef(null);

  const videoVersion = jobData?.video_cache_key ? encodeURIComponent(jobData.video_cache_key) : null;
  const remoteVideoUrl = jobData?.video_path
    ? `/api/jobs/${jobId}/downloads/video${videoVersion ? `?v=${videoVersion}` : ''}`
    : null;
  const [displayedVideo, setDisplayedVideo] = useState(null);

  useEffect(() => {
    if (!jobId || !jobData?.video_path || !remoteVideoUrl) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setDisplayedVideo({
        jobId,
        jobData,
        remoteVideoUrl,
        cacheKey: jobData?.video_cache_key ? `${jobId}-${jobData.video_cache_key}` : null
      });
    });
    return () => {
      cancelled = true;
    };
  }, [jobId, jobData, remoteVideoUrl]);

  const { videoUrl, cacheStatus } = useCachedVideoUrl(
    displayedVideo?.remoteVideoUrl || null,
    displayedVideo?.cacheKey || null
  );
  const hasVideo = Boolean(displayedVideo?.remoteVideoUrl);
  const userDisplayName = authState.user?.name || authState.user?.email || 'Gast';
  const userSubtitle = authState.user?.email || authState.user?.sub || (authState.enabled ? 'Nicht angemeldet' : 'Login deaktiviert');
  const avatarLetter = String(userDisplayName || 'G').trim().charAt(0).toUpperCase() || 'G';

  return (
    <div className="grid grid-rows-[auto_1fr_auto] min-h-screen">
      <header className="h-14 border-b border-border-subtle flex items-center justify-between px-4 bg-bg-surface z-50 sticky top-0">
        <div className="flex items-center gap-5 min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            <img src="/favicon.png" alt="DescrAIbe Logo" className="w-8 h-8 rounded-[8px] object-cover shadow-sm ring-1 ring-border-subtle" />
            <div className="flex flex-col leading-none min-w-0">
              <h1 className="font-bold text-[15px] tracking-tight text-text-primary truncate">
                Descr<span className="text-violet-500">AI</span>be <span className="font-normal text-text-muted text-xs">Pipeline</span>
              </h1>
              <span className="text-[10px] text-text-muted mt-1 truncate">
                v{APP_VERSION}
                {SHOW_STAGING_SHA && (
                  <>
                    {' '}
                    {LINK_STAGING_SHA ? (
                      <a
                        href={COMMIT_URL}
                        target="_blank"
                        rel="noreferrer"
                        className="underline decoration-dotted underline-offset-2 transition-colors hover:text-text-secondary"
                        title={`Open ${SHA_TAG}`}
                      >
                        ({SHA_TAG})
                      </a>
                    ) : (
                      <>({SHA_TAG})</>
                    )}
                  </>
                )}
                {SHOW_VERSION_LABEL && <> ({VERSION_LABEL})</>}
              </span>
            </div>
          </div>
          {jobId && (
            <>
              <div className="h-6 w-px bg-border-subtle"></div>
              <div className="hidden md:flex items-center gap-2 text-xs font-mono text-text-secondary truncate">
                <span className={`w-2 h-2 rounded-full ${sseConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></span>
                <span className="truncate">Job: {jobId}</span>
              </div>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          <label className="sr-only" htmlFor="theme-mode">Theme</label>
          <select
            id="theme-mode"
            value={themeMode}
            onChange={(event) => setThemeMode(event.target.value)}
            className="px-2 py-1.5 rounded-lg text-xs font-medium border border-border-subtle bg-bg-base text-text-secondary hover:text-text-primary transition-colors focus:outline-none focus:ring-2 focus:ring-violet-500/35"
            title="Theme auswählen"
          >
            <option value="system">System</option>
            <option value="light">Hell</option>
            <option value="dark">Dunkel</option>
          </select>
          <div className="h-6 w-px bg-border-subtle mx-1"></div>
          <div className="relative" ref={userMenuRef}>
            <button
              className="w-9 h-9 rounded-full border border-border-subtle bg-bg-card hover:bg-bg-base transition-colors overflow-hidden flex items-center justify-center text-sm font-semibold text-text-primary"
              onClick={() => setIsUserMenuOpen(prev => !prev)}
              title={authState.authenticated ? userDisplayName : 'Benutzermenü'}
              aria-label="Benutzermenü öffnen"
            >
              {authState.authenticated && authState.user?.picture ? (
                <img src={authState.user.picture} alt={userDisplayName} className="w-full h-full object-cover" />
              ) : (
                <span>{avatarLetter}</span>
              )}
            </button>
            {isUserMenuOpen && (
              <div className="absolute right-0 mt-2 w-72 rounded-xl border border-border-subtle bg-bg-surface shadow-xl shadow-black/20 overflow-hidden z-50">
                <div className="px-4 py-3 border-b border-border-subtle">
                  <p className="text-sm font-semibold text-text-primary truncate" title={userDisplayName}>{userDisplayName}</p>
                  <p className="text-xs text-text-secondary truncate" title={userSubtitle}>{userSubtitle}</p>
                </div>
                <div className="p-2 flex flex-col gap-1">
                  <button
                    className="w-full text-left px-3 py-2 rounded-lg text-sm text-text-secondary hover:text-text-primary hover:bg-bg-card transition-colors flex items-center gap-2"
                    onClick={() => {
                      setIsConfigModalOpen(true);
                      setIsUserMenuOpen(false);
                    }}
                    title="Prompts & Konfiguration"
                  >
                    <span className="material-icons-round text-[18px]">settings</span>
                    <span>Einstellungen</span>
                  </button>
                  {authState.enabled ? (
                    authState.authenticated ? (
                      <button
                        className="w-full text-left px-3 py-2 rounded-lg text-sm text-text-secondary hover:text-text-primary hover:bg-bg-card transition-colors flex items-center gap-2"
                        onClick={() => {
                          setIsUserMenuOpen(false);
                          logout();
                        }}
                      >
                        <span className="material-icons-round text-[18px]">logout</span>
                        <span>Logout</span>
                      </button>
                    ) : (
                      <button
                        className="w-full text-left px-3 py-2 rounded-lg text-sm text-violet-500 hover:bg-violet-500/10 transition-colors flex items-center gap-2"
                        onClick={() => {
                          setIsUserMenuOpen(false);
                          login();
                        }}
                      >
                        <span className="material-icons-round text-[18px]">login</span>
                        <span>Login</span>
                      </button>
                    )
                  ) : (
                    <div className="px-3 py-2 text-xs text-text-muted">Login ist für diese Instanz nicht aktiviert.</div>
                  )}
                </div>
              </div>
            )}
          </div>
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
            {hasVideo && (
              <div className="grid grid-cols-2 gap-6 flex-1 min-h-0">
                <div className="flex flex-col h-full min-h-0">
                  <div className="mb-2 flex shrink-0 items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider">Video Vorschau</p>
                    <span className="rounded-md bg-bg-card px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted border border-border-subtle">
                      {cacheStatus === 'opfs' ? 'OPFS Cache' : cacheStatus === 'loading' ? 'Caching...' : 'Netzwerk'}
                    </span>
                  </div>
                  <div className="flex-1 min-h-0 flex justify-center bg-bg-card rounded-lg overflow-hidden border border-border-subtle">
                    {videoUrl ? (
                      <video
                        ref={videoRef}
                        src={videoUrl}
                        controls
                        preload="auto"
                        className="w-full h-full object-contain"
                      />
                    ) : (
                      <div className="flex h-full w-full items-center justify-center text-sm text-text-muted">
                        Video wird gecacht...
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex flex-col h-full min-h-0">
                  <SRTWidget />
                </div>
              </div>
            )}

            {videoUrl && (
              <div className="shrink-0">
                <VideoTimeline
                  videoRef={videoRef}
                  videoUrl={videoUrl}
                  timelineJobData={displayedVideo?.jobData}
                />
              </div>
            )}

            {!hasVideo && (
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

      <StorageQuotaFooter />
      <ConfigModal />
    </div>
  );
}

function JobList({ jobId, jobData, savedJobIds, savedJobMeta, createJob, selectJob, removeSavedJobId }) {
  const activeName = jobData?.original_video_filename || jobData?.video_path?.split(/[\\/]/).filter(Boolean).pop();
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
          <div className="rounded-lg border border-border-subtle bg-bg-card px-3 py-2 text-xs text-text-secondary">
            Noch keine Jobs gespeichert.
          </div>
        ) : (
          savedJobIds.map(savedJobId => {
            const isActive = savedJobId === jobId;
            const meta = savedJobMeta[savedJobId] || {};
            const displayName = isActive
              ? activeName || meta.name || `Job ${savedJobId.slice(0, 8)}`
              : meta.name || `Job ${savedJobId.slice(0, 8)}`;
            const status = isActive && meta.status === 'uploading'
              ? meta.status
              : isActive ? activeStatus || meta.status : meta.status;
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
                            : 'bg-bg-card text-text-secondary'
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
                        <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-bg-card border border-border-subtle">
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
