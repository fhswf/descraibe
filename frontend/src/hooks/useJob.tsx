/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef, ReactNode } from 'react';
import type {
  JobContextValue,
  GPTParams,
  VADParams,
  TranscribeParams,
  SlotsParams,
  TTSParams,
  ImagesParams,
  SavedJobMeta,
  AuthState,
  JobData,
  ProgressInfo,
  GPTRecord,
  ProgressData,
} from '../types';

const JobContext = createContext<JobContextValue | null>(null);
const SAVED_JOBS_STORAGE_KEY = 'descrAIbe.savedJobIds';
const SAVED_JOB_META_STORAGE_KEY = 'descrAIbe.savedJobMeta';
const USER_SETTINGS_STORAGE_KEY = 'descrAIbe.userSettings';

const DEFAULT_GPT_PARAMS: GPTParams = {
    system_prompt: "",
    user_prompt: "",
    ad_rules: "",
    few_shots: "",
    model: "",
    temperature: 0.2,
    max_tokens: 1024,
    detail: "low" as const,
    cut: "broadcast" as const,
    syllables_per_second: 6.0
};

const DEFAULT_VAD_PARAMS = {
    threshold: 0.5,
    min_speech_duration_ms: 1500,
    min_silence_duration_ms: 400,
    min_pause_duration_s: 0.3
};

const DEFAULT_TRANSCRIBE_PARAMS = {
    model_size: "small",
    language: "de",
    use_fw_vad: true
};

const DEFAULT_SLOTS_PARAMS = {
    min_slot_s: 1.0,
    pad_in_s: 0.0,
    pad_out_s: 0.0,
    filter_whisper: false
};

const DEFAULT_TTS_PARAMS = {
    apiKey: '',
    voice: 'alloy',
    duckingVolume: '0.4'
};

const DEFAULT_IMAGES_PARAMS = {
    threshold: 24,
    blur_threshold: 80,
    min_scene_length: 20,
    short_scene_s: 3.0
};

function readSavedJobIds(): string[] {
    try {
        const raw = window.localStorage.getItem(SAVED_JOBS_STORAGE_KEY);
        const parsed: unknown = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string' && id.trim() !== '') : [];
    } catch (err) {
        console.warn("Could not read saved jobs from localStorage:", err);
        return [];
    }
}

function writeSavedJobIds(jobIds: string[]): void {
    try {
        window.localStorage.setItem(SAVED_JOBS_STORAGE_KEY, JSON.stringify(jobIds));
    } catch (err) {
        console.warn("Could not write saved jobs to localStorage:", err);
    }
}

function readSavedJobMeta(): Record<string, SavedJobMeta> {
    try {
        const raw = window.localStorage.getItem(SAVED_JOB_META_STORAGE_KEY);
        const parsed = raw ? JSON.parse(raw) : {};
        return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, SavedJobMeta> : {};
    } catch (err) {
        console.warn("Could not read saved job metadata from localStorage:", err);
        return {};
    }
}

function writeSavedJobMeta(meta: Record<string, SavedJobMeta>): void {
    try {
        window.localStorage.setItem(SAVED_JOB_META_STORAGE_KEY, JSON.stringify(meta));
    } catch (err) {
        console.warn("Could not write saved job metadata to localStorage:", err);
    }
}

function readUserSettings(): { gptParams?: Partial<GPTParams>; vadParams?: Partial<VADParams>; transcribeParams?: Partial<TranscribeParams>; slotsParams?: Partial<SlotsParams>; ttsParams?: Partial<TTSParams>; imagesParams?: Partial<ImagesParams> } {
    try {
        const raw = window.localStorage.getItem(USER_SETTINGS_STORAGE_KEY);
        const parsed = raw ? JSON.parse(raw) : {};
        return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as ReturnType<typeof readUserSettings> : {} as ReturnType<typeof readUserSettings>;
    } catch (err) {
        console.warn("Could not read user settings from localStorage:", err);
        return {} as ReturnType<typeof readUserSettings>;
    }
}

function writeUserSettings(settings: Record<string, unknown>): void {
    try {
        window.localStorage.setItem(USER_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
    } catch (err) {
        console.warn("Could not write user settings to localStorage:", err);
    }
}

function basename(path: string | null | undefined): string {
    if (!path) return '';
    return String(path).split(/[\\/]/).filter(Boolean).pop() || '';
}

function progressPercent(progress: ProgressInfo | undefined | null): number | null {
    if (!progress?.total) return null;
    return Math.max(0, Math.min(100, Math.round(((progress.current ?? 0) / progress.total) * 100)));
}

function jobMetaFromData(data: JobData): SavedJobMeta {
    const percent = data.status === 'running' ? progressPercent(data.latest_progress) : null;
    return {
        name: data.original_video_filename || basename(data.video_path) || `Job ${String(data.job_id || '').slice(0, 8)}`,
        status: data.status || null,
        progressPercent: percent,
        progressMessage: data.latest_progress?.message || null,
        updatedAt: new Date().toISOString()
    };
}

function mergeSummaryMeta(existing: SavedJobMeta | null | undefined, summary: JobData): SavedJobMeta {
    const incoming = jobMetaFromData(summary);
    if (existing?.status === 'uploading' && !summary.video_path && summary.status !== 'error') {
        return {
            ...existing,
            updatedAt: new Date().toISOString()
        };
    }
    return incoming;
}

interface JobProviderProps {
    children: ReactNode;
}

export function JobProvider({ children }: JobProviderProps) {
    const initialSettings = useMemo(() => readUserSettings(), []);
    const [jobId, setJobId] = useState<string | null>(() => {
        const params = new URLSearchParams(window.location.search);
        return params.get('job') || null;
    });
    const [savedJobIds, setSavedJobIds] = useState<string[]>(readSavedJobIds);
    const [savedJobMeta, setSavedJobMeta] = useState<Record<string, SavedJobMeta>>(readSavedJobMeta);
    const [jobData, setJobData] = useState<JobData | null>(null);
    const [sseConnected, setSseConnected] = useState<boolean>(false);
    const [gptRecords, setGptRecords] = useState<GPTRecord[]>([]);
    const [currentStep, setCurrentStep] = useState<number>(0);
    const [doneSteps, setDoneSteps] = useState<Set<number>>(new Set());
    const [progressData, setProgressData] = useState<ProgressData>({});
    const [focusedSlot, setFocusedSlot] = useState<number | null>(null);
    const [srtTexts, setSrtTexts] = useState<Record<string, string>>({});
    const [isSavingSrt, setIsSavingSrt] = useState<boolean>(false);
    const lastSavedSrtPayloadRef = useRef<string>('');
    const [isRunAllActive, setIsRunAllActive] = useState<boolean>(false);
    
    // Global Config Modal State
    const [isConfigModalOpen, setIsConfigModalOpen] = useState<boolean>(false);
    const [availableModels, setAvailableModels] = useState<string[]>([]);
    const [gptParams, setGptParams] = useState<GPTParams>(() => ({ ...DEFAULT_GPT_PARAMS, ...(initialSettings.gptParams || {}) }));
    const [vadParams, setVadParams] = useState<VADParams>(() => ({ ...DEFAULT_VAD_PARAMS, ...(initialSettings.vadParams || {}) }));
    const [transcribeParams, setTranscribeParams] = useState<TranscribeParams>(() => ({ ...DEFAULT_TRANSCRIBE_PARAMS, ...(initialSettings.transcribeParams || {}) }));
    const [slotsParams, setSlotsParams] = useState<SlotsParams>(() => ({ ...DEFAULT_SLOTS_PARAMS, ...(initialSettings.slotsParams || {}) }));
    const [ttsParams, setTtsParams] = useState<TTSParams>(() => ({ ...DEFAULT_TTS_PARAMS, ...(initialSettings.ttsParams || {}) }));
    const [imagesParams, setImagesParams] = useState<ImagesParams>(() => ({ ...DEFAULT_IMAGES_PARAMS, ...(initialSettings.imagesParams || {}) }));
    const [authState, setAuthState] = useState<AuthState>({
        loading: true,
        enabled: false,
        authenticated: false,
        user: null
    });
    const [remoteConfigLoaded, setRemoteConfigLoaded] = useState<boolean>(false);

    const refreshAuthState = useCallback(async () => {
        try {
            const res = await fetch('/api/auth/status', {
                cache: 'no-store',
                headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' }
            });
            if (!res.ok) throw new Error('Could not load auth status');
            const data = await res.json();
            setAuthState({
                loading: false,
                enabled: Boolean(data.enabled),
                authenticated: Boolean(data.enabled && data.authenticated),
                user: data.enabled && data.authenticated ? data.user : null
            });
        } catch {
            setAuthState({
                loading: false,
                enabled: false,
                authenticated: false,
                user: null
            });
        }
    }, []);

    const login = useCallback(() => {
        const nextPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
        window.location.href = `/api/auth/login?next=${encodeURIComponent(nextPath || '/')}`;
    }, []);

    const logout = useCallback(async () => {
        try {
            await fetch('/api/auth/logout', { method: 'POST' });
        } finally {
            await refreshAuthState();
        }
    }, [refreshAuthState]);

    const addSavedJobId = useCallback((id: string) => {
        if (!id) return;
        setSavedJobIds(prev => {
            const next = prev.includes(id) ? prev : [id, ...prev];
            writeSavedJobIds(next);
            return next;
        });
    }, []);

    const updateSavedJobMeta = useCallback((id: string, updates: Partial<SavedJobMeta>) => {
        if (!id) return;
        setSavedJobMeta(prev => {
            const existing = prev[id];
            const next: Record<string, SavedJobMeta> = {
                ...prev,
                [id]: {
                    name: existing?.name || '',
                    status: updates.status !== undefined ? updates.status : existing?.status ?? null,
                    progressPercent: updates.progressPercent !== undefined ? updates.progressPercent : existing?.progressPercent ?? null,
                    progressMessage: updates.progressMessage !== undefined ? updates.progressMessage : existing?.progressMessage ?? null,
                    updatedAt: new Date().toISOString()
                }
            };
            writeSavedJobMeta(next);
            return next;
        });
    }, []);

    const removeSavedJobId = useCallback((id: string) => {
        setSavedJobIds(prev => {
            const next = prev.filter(savedId => savedId !== id);
            writeSavedJobIds(next);
            return next;
        });
        setSavedJobMeta(prev => {
            const next = { ...prev };
            delete next[id];
            writeSavedJobMeta(next);
            return next;
        });
    }, []);

    const resetJobView = useCallback(() => {
        setJobData(null);
        setDoneSteps(new Set());
        setCurrentStep(0);
        setProgressData({});
        setFocusedSlot(null);
        setSrtTexts({});
    }, []);

    const selectJob = useCallback((id: string) => {
        if (!id) return;
        addSavedJobId(id);
        resetJobView();
        setJobId(id);
        window.history.pushState({}, '', `?job=${id}`);
    }, [addSavedJobId, resetJobView]);

    useEffect(() => {
        const handlePopState = () => {
            const params = new URLSearchParams(window.location.search);
            const nextJobId = params.get('job') || null;
            resetJobView();
            setJobId(nextJobId);
            if (nextJobId) addSavedJobId(nextJobId);
        };

        window.addEventListener('popstate', handlePopState);
        return () => window.removeEventListener('popstate', handlePopState);
    }, [addSavedJobId, resetJobView]);

    // Populate configuration defaults on mount
    useEffect(() => {
        fetch('/api/system_info')
            .then(res => res.json())
            .then(data => {
                setGptParams(p => {
                    const newP = { ...p };
                    if (data.default_prompts) {
                        newP.system_prompt = data.default_prompts.system_instruction || p.system_prompt;
                        newP.user_prompt = data.default_prompts.user_instruction || p.user_prompt;
                        newP.ad_rules = data.default_prompts.ad_rules || p.ad_rules;
                        newP.few_shots = data.default_prompts.few_shots || p.few_shots;
                    }
                    if (data.available_models && data.available_models.length > 0) {
                        setAvailableModels(data.available_models);
                        const firstModel = data.available_models[0];
                        if (!newP.model) {
                            newP.model = firstModel.model;
                        }
                        if (newP.temperature === undefined || newP.temperature === null) {
                            newP.temperature = firstModel.temperature !== undefined ? firstModel.temperature : 0.2;
                        }
                        if (newP.max_tokens === undefined || newP.max_tokens === null) {
                            newP.max_tokens = firstModel.max_tokens !== undefined ? firstModel.max_tokens : 1024;
                        }
                        if (!newP.detail) {
                            newP.detail = firstModel.detail !== undefined ? firstModel.detail : "low";
                        }
                    }
                    return newP;
                });
            })
            .catch(console.error);
    }, []);

    useEffect(() => {
        refreshAuthState();
    }, [refreshAuthState]);

    useEffect(() => {
        writeUserSettings({
            gptParams,
            vadParams,
            transcribeParams,
            slotsParams,
            ttsParams,
            imagesParams
        });
    }, [gptParams, vadParams, transcribeParams, slotsParams, ttsParams, imagesParams]);

    useEffect(() => {
        if (!authState.authenticated) {
            setRemoteConfigLoaded(false);
            return;
        }

        let cancelled = false;
        const loadRemoteConfig = async () => {
            try {
                const res = await fetch('/api/user/config', {
                    cache: 'no-store',
                    headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' }
                });
                if (!res.ok) return;
                const payload = await res.json();
                const remoteConfig = payload?.config && typeof payload.config === 'object' ? payload.config : {};
                const remoteIds = Array.isArray(remoteConfig.saved_job_ids)
                    ? remoteConfig.saved_job_ids.filter((id: unknown): id is string => typeof id === 'string' && Boolean(id.trim()))
                    : [];
                const remoteMeta = remoteConfig.saved_job_meta && typeof remoteConfig.saved_job_meta === 'object' && !Array.isArray(remoteConfig.saved_job_meta)
                    ? remoteConfig.saved_job_meta
                    : {};
                const remoteSettings = remoteConfig.settings && typeof remoteConfig.settings === 'object' && !Array.isArray(remoteConfig.settings)
                    ? remoteConfig.settings
                    : {};

                if (cancelled) return;

                if (remoteIds.length > 0) {
                    setSavedJobIds(prev => {
                        const next = [...new Set([...remoteIds, ...prev])];
                        writeSavedJobIds(next);
                        return next;
                    });
                }
                if (Object.keys(remoteMeta).length > 0) {
                    setSavedJobMeta(prev => {
                        const next = { ...prev, ...remoteMeta };
                        writeSavedJobMeta(next);
                        return next;
                    });
                }

                if (remoteSettings.gptParams) setGptParams(prev => ({ ...prev, ...remoteSettings.gptParams }));
                if (remoteSettings.vadParams) setVadParams(prev => ({ ...prev, ...remoteSettings.vadParams }));
                if (remoteSettings.transcribeParams) setTranscribeParams(prev => ({ ...prev, ...remoteSettings.transcribeParams }));
                if (remoteSettings.slotsParams) setSlotsParams(prev => ({ ...prev, ...remoteSettings.slotsParams }));
                if (remoteSettings.ttsParams) setTtsParams(prev => ({ ...prev, ...remoteSettings.ttsParams }));
                if (remoteSettings.imagesParams) setImagesParams(prev => ({ ...prev, ...remoteSettings.imagesParams }));
            } catch (err) {
                console.warn("Could not load remote user config:", err);
            } finally {
                if (!cancelled) setRemoteConfigLoaded(true);
            }
        };

        loadRemoteConfig();
        return () => {
            cancelled = true;
        };
    }, [authState.authenticated]);

    useEffect(() => {
        if (!authState.authenticated || !remoteConfigLoaded) return;
        const controller = new AbortController();
        const timeoutId = window.setTimeout(async () => {
            try {
                await fetch('/api/user/config', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    signal: controller.signal,
                    body: JSON.stringify({
                        config: {
                            saved_job_ids: savedJobIds,
                            saved_job_meta: savedJobMeta,
                            settings: {
                                gptParams,
                                vadParams,
                                transcribeParams,
                                slotsParams,
                                ttsParams,
                                imagesParams
                            }
                        }
                    })
                });
            } catch (err: unknown) {
                if ((err as Error)?.name !== 'AbortError') {
                    console.warn("Could not store remote user config:", err);
                }
            }
        }, 800);

        return () => {
            controller.abort();
            window.clearTimeout(timeoutId);
        };
    }, [
        authState.authenticated,
        remoteConfigLoaded,
        savedJobIds,
        savedJobMeta,
        gptParams,
        vadParams,
        transcribeParams,
        slotsParams,
        ttsParams,
        imagesParams
    ]);

    useEffect(() => {
        if (jobData?.gpt_records) {
            const initialTexts: Record<string, string> = {};
            jobData.gpt_records.forEach(rec => {
                initialTexts[String(rec.slot_id)] = rec.text || '';
            });
            setSrtTexts(initialTexts);
            lastSavedSrtPayloadRef.current = JSON.stringify(initialTexts);
        }
    }, [jobData?.gpt_records]);

    useEffect(() => {
        if (!jobId) return;
        if (!jobData?.gpt_records || jobData.gpt_records.length === 0) return;

        const currentPayload = JSON.stringify(srtTexts);
        if (currentPayload === lastSavedSrtPayloadRef.current) return;

        let cancelled = false;
        const controller = new AbortController();
        const timeoutId = window.setTimeout(async () => {
            setIsSavingSrt(true);
            try {
                const res = await fetch(`/api/jobs/${jobId}/texts`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    signal: controller.signal,
                    body: JSON.stringify({ texts: srtTexts })
                });
                if (!res.ok) return;
                lastSavedSrtPayloadRef.current = currentPayload;
            } catch (err: unknown) {
                if ((err as Error)?.name !== 'AbortError') {
                    console.warn("Could not auto-save SRT texts:", err);
                }
            } finally {
                if (!cancelled) setIsSavingSrt(false);
            }
        }, 800);

        return () => {
            cancelled = true;
            controller.abort();
            window.clearTimeout(timeoutId);
        };
    }, [jobId, jobData?.gpt_records, srtTexts]);

    const handleSaveSrtTexts = useCallback(async (): Promise<void> => {
        if (!jobId) return;
        setIsSavingSrt(true);
        try {
            const res = await fetch(`/api/jobs/${jobId}/texts`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ texts: srtTexts })
            });
            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.error || 'Failed to save texts');
            }
            lastSavedSrtPayloadRef.current = JSON.stringify(srtTexts);
            alert("Änderungen erfolgreich gespeichert! Die Ausgabedateien wurden aktualisiert.");
        } catch (err) {
            alert("Error: " + (err as Error).message);
        } finally {
            setIsSavingSrt(false);
        }
    }, [jobId, srtTexts, setIsSavingSrt]);

    const fetchJobData = useCallback(async (id: string): Promise<void> => {
        try {
            const res = await fetch(`/api/jobs/${id}`, {
                cache: 'no-store',
                headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' }
            });
            if (res.ok) {
                const data: JobData = await res.json();
                addSavedJobId(id);
                updateSavedJobMeta(id, jobMetaFromData(data));
                setJobData(data);

                const newDone = new Set<number>();
                if (data.video_stats) newDone.add(0);
                if ((data.pauses_count ?? 0) > 0) newDone.add(1);
                if (data.transcript_meta) newDone.add(2);
                if ((data.slots_count ?? 0) > 0) newDone.add(3);
                if ((data.images_count ?? 0) > 0) newDone.add(4);
                if ((data.persons_count ?? 0) > 0) newDone.add(5);
                if (data.gpt_records_broadcast || data.gpt_records_directors) newDone.add(6);
                if (data.final_mp4_path) newDone.add(7);
                setDoneSteps(newDone);

                let targetStep = 0;
                for (let i = 0; i <= 7; i++) {
                    if (!newDone.has(i)) {
                        targetStep = i;
                        break;
                    }
                }
                setCurrentStep(targetStep);

                // Restore progress if job is running and we have latest progress
                const latestProgress = data.latest_progress;
                if (data.status === 'running' && latestProgress) {
                    const progressStep = (latestProgress as { step?: string }).step;
                    if (progressStep) {
                        setProgressData(prev => ({
                            ...prev,
                            [progressStep]: {
                                msg: (latestProgress as { message?: string }).message ?? '',
                                percent: (latestProgress as { total?: number; current?: number }).total
                                    ? Math.round(((latestProgress as { current?: number }).current ?? 0) / (latestProgress as { total?: number }).total! * 100)
                                    : 100
                            }
                        }));
                    }
                }
            }
        } catch (err: unknown) {
            console.error("Failed to load job:", err);
        }
    }, [addSavedJobId, updateSavedJobMeta, setJobData, setDoneSteps, setCurrentStep]);

    useEffect(() => {
        if (savedJobIds.length === 0) return;

        const params = new URLSearchParams({ job_ids: savedJobIds.join(',') });
        const source = new EventSource(`/api/jobs/summary_stream?${params.toString()}`);

        const handleSummaries = (ev: MessageEvent) => {
            try {
                const summaries = JSON.parse(ev.data);
                if (!Array.isArray(summaries)) return;

                setSavedJobMeta(prev => {
                    const next = { ...prev };
                    summaries.forEach(summary => {
                        next[summary.job_id] = mergeSummaryMeta(prev[summary.job_id], summary);
                    });
                    writeSavedJobMeta(next);
                    return next;
                });
            } catch (err) {
                console.error("Summary stream parsing error", err);
            }
        };

        source.addEventListener('summaries', handleSummaries);

        source.onerror = () => {
            // EventSource reconnects automatically; keep this quiet unless parsing fails.
        };

        return () => {
            source.removeEventListener('summaries', handleSummaries);
            source.close();
        };
    }, [savedJobIds]);

    const handleUpdateSlotTiming = useCallback(async (slotId: number, start_s: number, end_s: number): Promise<void> => {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/jobs/${jobId}/slots`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ slots: [{ slot: slotId, start_s, end_s }] })
            });
            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.error || 'Failed to update slot timing');
            }
            // Optionally refresh job data to sync the UI with updated metadata
            fetchJobData(jobId);
        } catch (err) {
            console.error("Error updating slot timing:", (err as Error).message);
            alert("Error updating slot timing: " + (err as Error).message);
            // fetchJobData(jobId);
        }
    }, [jobId, fetchJobData]);

    // Load job from URL on mount
    useEffect(() => {
        if (jobId) {
            fetchJobData(jobId);
        }
    }, [jobId, fetchJobData]);

    const createJob = useCallback(async (): Promise<string | null> => {
        try {
            const res = await fetch('/api/jobs', { method: 'POST' });
            const data = await res.json();
            resetJobView();
            addSavedJobId(data.job_id);
            updateSavedJobMeta(data.job_id, {
                name: `Job ${String(data.job_id).slice(0, 8)}`,
                status: 'created',
                progressPercent: null,
                progressMessage: null
            });
            setJobId(data.job_id);
            window.history.pushState({}, '', `?job=${data.job_id}`);
            return data.job_id;
        } catch (err) {
            console.error("Failed to create job:", err);
            return null;
        }
    }, [addSavedJobId, resetJobView, updateSavedJobMeta]);

    const markStepDone = useCallback((step: number): void => {
        setDoneSteps(prev => new Set(prev).add(step));
    }, []);

    const markJobStarted = useCallback((step: string, message: string): void => {
        if (!jobId) return;
        const stepIndexes: Record<string, number> = {
            vad: 1,
            transcribe: 2,
            slots: 3,
            images: 4,
            gpt: 5,
            tts: 6
        };
        const startedStepIndex = stepIndexes[step];
        if (startedStepIndex !== undefined) {
            setDoneSteps(prev => {
                const next = new Set(prev);
                for (let i = startedStepIndex; i <= 7; i += 1) {
                    next.delete(i);
                }
                return next;
            });
            setCurrentStep(startedStepIndex);
        }
        updateSavedJobMeta(jobId, {
            status: 'running',
            progressPercent: 0,
            progressMessage: message
        });
        setJobData(prev => prev?.job_id === jobId
            ? {
                ...prev,
                status: 'running',
                latest_progress: {
                    step,
                    message,
                    current: 0,
                    total: 100
                }
            }
            : prev
        );
        setProgressData(prev => ({
            ...prev,
            [step]: {
                msg: message,
                percent: 0
            }
        }));
    }, [jobId, updateSavedJobMeta]);

    const handleRunVAD = useCallback(async (): Promise<void> => {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/jobs/${jobId}/vad`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(vadParams)
            });
            if (!res.ok) throw new Error("Failed to start VAD");
            markJobStarted('vad', 'Sprechpausen erkennen...');
        } catch (err) { alert("Error: " + (err as Error).message); setIsRunAllActive(false); }
    }, [jobId, vadParams, markJobStarted]);

    const handleRunTranscribe = useCallback(async (): Promise<void> => {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/jobs/${jobId}/transcribe`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(transcribeParams)
            });
            if (!res.ok) throw new Error("Failed to start transcription");
            markJobStarted('transcribe', 'Transkription starten...');
        } catch (err) { alert("Error: " + (err as Error).message); setIsRunAllActive(false); }
    }, [jobId, transcribeParams, markJobStarted]);

    const handleRunSlots = useCallback(async (): Promise<void> => {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/jobs/${jobId}/slots`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(slotsParams)
            });
            if (!res.ok) throw new Error("Failed to generate slots");
            markJobStarted('slots', 'AD-Slots generieren...');
        } catch (err) { alert("Error: " + (err as Error).message); setIsRunAllActive(false); }
    }, [jobId, slotsParams, markJobStarted]);

    const handleRunImages = useCallback(async (): Promise<void> => {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/jobs/${jobId}/images`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(imagesParams)
            });
            if (!res.ok) throw new Error("Failed to extract images");
            markJobStarted('images', 'Bilder extrahieren...');
        } catch (err) { alert("Error: " + (err as Error).message); setIsRunAllActive(false); }
    }, [jobId, imagesParams, markJobStarted]);

    const handleRunPersons = useCallback(async (): Promise<void> => {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/jobs/${jobId}/persons`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
            if (!res.ok) throw new Error("Failed to analyze persons");
            markJobStarted('persons', 'Personen analysieren...');
        } catch (err) { alert("Error: " + (err as Error).message); setIsRunAllActive(false); }
    }, [jobId, markJobStarted]);

    const handleRunGPT = useCallback(async (): Promise<void> => {
        if (!jobId) return;
        if (!gptParams) {
            setIsRunAllActive(false);
            return alert("Prompts fehlen. Bitte überprüfen Sie die Konfiguration.");
        }
        const selectedModelInfo = availableModels.find(m => m === gptParams.model) || (!gptParams.model ? availableModels[0] : null);
        // Track if model was implicitly selected (not explicitly set by user)
        const _modelWasImplicit = !gptParams.model && selectedModelInfo;
        const effectiveModel = gptParams.model || selectedModelInfo || "";

        let system_final = gptParams.system_prompt;
        if (gptParams.ad_rules) {
            system_final += "\n\n# Audiodeskription – Regeln\n" + gptParams.ad_rules;
        }
        if (gptParams.few_shots) {
            system_final += "\n\n# Few-Shots / Beispiele\n" + gptParams.few_shots;
        }
        const payload = {
            model: effectiveModel,
            temperature: gptParams.temperature,
            max_tokens: gptParams.max_tokens,
            detail: gptParams.detail,
            cut: gptParams.cut,
            syllables_per_second: gptParams.syllables_per_second || 6.0,
            system_prompt: system_final,
            user_prompt: gptParams.user_prompt || "Erstelle eine AD für diese Frames.",
        };
        try {
            if (!payload.model) throw new Error("Kein GPT-Modell ausgewählt. Bitte Konfiguration laden oder ein Modell auswählen.");
            const res = await fetch(`/api/jobs/${jobId}/gpt`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!res.ok) throw new Error((await res.json()).error || "Failed to start GPT generation");
            markJobStarted('gpt', 'Beschreibungen generieren...');
        } catch (err) { alert("Error: " + (err as Error).message); setIsRunAllActive(false); }
    }, [jobId, gptParams, availableModels, markJobStarted]);

    const handleRunTTS = useCallback(async (): Promise<void> => {
        if (!jobId) return;
        const payload = {
            api_key: ttsParams.apiKey,
            voice: ttsParams.voice,
            ducking_volume: parseFloat(ttsParams.duckingVolume)
        };
        try {
            const res = await fetch(`/api/jobs/${jobId}/tts`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!res.ok) throw new Error((await res.json()).error || "Failed to start TTS");
            markJobStarted('tts', 'Vertonung starten...');
        } catch (err) { alert("Error: " + (err as Error).message); setIsRunAllActive(false); }
    }, [jobId, ttsParams, markJobStarted]);

    const handleSSEEvent = useCallback((payload: { event: string; data: Record<string, unknown> }): void => {
        if (!jobId) return;
        
        const { event, data } = payload;

        if (event === 'ping' || event === 'connected') return;

        if (event === 'progress') {
            const step = String(data.step);
            const percent = progressPercent(data as ProgressInfo);
            updateSavedJobMeta(jobId, {
                status: 'running',
                progressPercent: percent,
                progressMessage: (data.message as string) || null
            });
            setProgressData(prev => ({
                ...prev,
                [step]: {
                    msg: data.message as string,
                    percent: percent ?? 100
                }
            }));
        } else if (event === 'error') {
            const step = String(data.step);
            updateSavedJobMeta(jobId, {
                status: 'error',
                progressPercent: null,
                progressMessage: (data.message as string) || null
            });
            alert(`Error in ${step}: ${data.message}`);
            setProgressData(prev => ({ ...prev, [step]: null }));
            fetchJobData(jobId);
        } else {
            // Refresh job data to get the latest state (links, stats, counts)
            fetchJobData(jobId);

            if (event === 'vad_done') {
                setDoneSteps(prev => new Set(prev).add(1));
                setCurrentStep(2);
                setProgressData(prev => ({ ...prev, vad: null }));
            } else if (event === 'transcribe_done') {
                setDoneSteps(prev => new Set(prev).add(2));
                setCurrentStep(3);
                setProgressData(prev => ({ ...prev, transcribe: null }));
            } else if (event === 'slots_done') {
                setDoneSteps(prev => new Set(prev).add(3));
                setCurrentStep(4);
                setProgressData(prev => ({ ...prev, slots: null }));
            } else if (event === 'images_done') {
                setDoneSteps(prev => new Set(prev).add(4));
                setCurrentStep(5);
                setProgressData(prev => ({ ...prev, images: null }));
            } else if (event === 'persons_done') {
                setDoneSteps(prev => new Set(prev).add(5));
                setCurrentStep(6);
                setProgressData(prev => ({ ...prev, persons: null }));
            } else if (event === 'gpt_done') {
                setDoneSteps(prev => new Set(prev).add(6));
                setCurrentStep(7);
                fetchJobData(jobId); // Need full update for outputs
                setProgressData(prev => ({ ...prev, gpt: null }));
                if ((Number(data.error_count) || 0) > 0) {
                    setIsRunAllActive(false);
                    alert(`${data.error_count} GPT-Slot(s) konnten nicht generiert werden. Bitte im Slot Manager prüfen oder GPT erneut starten.`);
                }
            } else if (event === 'tts_done') {
                setDoneSteps(prev => new Set(prev).add(7));
                setCurrentStep(8);
                fetchJobData(jobId);
                setProgressData(prev => ({ ...prev, tts: null }));
                setIsRunAllActive(false); // Finished all automatic steps
            }

            // Chain reactions if Run All is active
            if (isRunAllActive) {
                if (event === 'upload_done' || event === 'upload_success') {
                    // Start VAD automatically? We assume Run All is triggered AFTER upload, so VAD is the first target.
                } else if (event === 'vad_done') {
                    handleRunTranscribe();
                } else if (event === 'transcribe_done') {
                    handleRunSlots();
                } else if (event === 'slots_done') {
                    handleRunImages();
                } else if (event === 'images_done') {
                    handleRunPersons();
                } else if (event === 'persons_done') {
                    handleRunGPT();
                } else if (event === 'gpt_done' && !(data.error_count || 0)) {
                    handleRunTTS();
                }
            }
        }
    }, [
        jobId, fetchJobData, updateSavedJobMeta, setProgressData, setDoneSteps,
        setCurrentStep, isRunAllActive, handleRunTranscribe, handleRunSlots,
        handleRunImages, handleRunPersons, handleRunGPT, handleRunTTS
    ]);

    useEffect(() => {
        if (!jobId) return;

        const source = new EventSource(`/api/jobs/${jobId}/stream`);

        source.onopen = () => setSseConnected(true);
        source.onerror = () => setSseConnected(false);

        source.onmessage = (ev: MessageEvent) => {
            try {
                const payload = JSON.parse(ev.data);
                handleSSEEvent(payload);
            } catch (err) {
                console.error("SSE parsing error", err);
            }
        };

        return () => {
            source.close();
            setSseConnected(false);
        };
    }, [jobId, handleSSEEvent]);

    const runAllSteps = useCallback((): void => {
        if (!jobId) return alert("Bitte laden Sie zuerst ein Video hoch.");
        setIsRunAllActive(true);
        // Determine the next uncompleted step and start there
        if (!doneSteps.has(1)) handleRunVAD();
        else if (!doneSteps.has(2)) handleRunTranscribe();
        else if (!doneSteps.has(3)) handleRunSlots();
        else if (!doneSteps.has(4)) handleRunImages();
        else if (!doneSteps.has(5)) handleRunPersons();
        else if (!doneSteps.has(6)) handleRunGPT();
        else if (!doneSteps.has(7)) handleRunTTS();
        else setIsRunAllActive(false); // all done
    }, [doneSteps, handleRunGPT, handleRunPersons, handleRunImages, handleRunSlots, handleRunTTS, handleRunTranscribe, handleRunVAD, jobId]);

    const stopRunAll = useCallback((): void => {
        setIsRunAllActive(false);
    }, []);

    const handleUpdateGPTRecord = useCallback((recordId: string, updates: Partial<GPTRecord>): void => {
        setGptRecords(prevRecords =>
            prevRecords.map(record =>
                record.id === recordId ? { ...record, ...updates } : record
            )
        );
    }, []);

    const contextValue = useMemo((): JobContextValue => ({
        jobId,
        setJobId,
        savedJobIds,
        savedJobMeta,
        selectJob,
        removeSavedJobId,
        updateSavedJobMeta,
        jobData,
        sseConnected,
        gptRecords,
        setGptRecords,
        currentStep,
        setCurrentStep,
        doneSteps,
        markStepDone,
        progressData,
        setProgressData,
        focusedSlot,
        setFocusedSlot,
        createJob,
        fetchJobData,
        srtTexts,
        setSrtTexts,
        isSavingSrt,
        handleSaveSrtTexts,
        handleUpdateSlotTiming,
        isConfigModalOpen,
        setIsConfigModalOpen,
        gptParams,
        setGptParams,
        availableModels,
        setAvailableModels,
        vadParams,
        setVadParams,
        transcribeParams,
        setTranscribeParams,
        slotsParams,
        setSlotsParams,
        ttsParams,
        setTtsParams,
        imagesParams,
        setImagesParams,
        handleRunVAD,
        handleRunTranscribe,
        handleRunSlots,
        handleRunImages,
        handleRunPersons,
        handleRunGPT,
        handleUpdateGPTRecord,
        handleRunTTS,
        runAllSteps,
        isRunAllActive,
        stopRunAll,
        authState,
        login,
        logout,
        refreshAuthState
    }), [
        jobId, setJobId, savedJobIds, savedJobMeta, selectJob, removeSavedJobId, updateSavedJobMeta, jobData, sseConnected, gptRecords, setGptRecords, currentStep, setCurrentStep,
        doneSteps, markStepDone, progressData, setProgressData, focusedSlot, setFocusedSlot, createJob,
        fetchJobData, srtTexts, setSrtTexts, isSavingSrt, handleSaveSrtTexts, handleUpdateSlotTiming,
        isConfigModalOpen, setIsConfigModalOpen, gptParams, setGptParams, availableModels, setAvailableModels,
        vadParams, setVadParams, transcribeParams, setTranscribeParams, slotsParams, setSlotsParams,
        ttsParams, setTtsParams, imagesParams, setImagesParams, handleRunVAD, handleRunTranscribe,
        handleRunSlots, handleRunImages, handleRunPersons, handleRunGPT, handleUpdateGPTRecord, handleRunTTS, runAllSteps,
        isRunAllActive, stopRunAll, authState, login, logout, refreshAuthState
    ]);

    return (
        <JobContext.Provider value={contextValue}>
            {children}
        </JobContext.Provider>
    );
}

export function useJob(): JobContextValue {
    const context = useContext(JobContext);
    if (context === null) {
        throw new Error('useJob must be used within a JobProvider');
    }
    return context;
}
