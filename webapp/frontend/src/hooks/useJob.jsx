/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';

const JobContext = createContext();
const SAVED_JOBS_STORAGE_KEY = 'descrAIbe.savedJobIds';
const SAVED_JOB_META_STORAGE_KEY = 'descrAIbe.savedJobMeta';

function readSavedJobIds() {
    try {
        const raw = window.localStorage.getItem(SAVED_JOBS_STORAGE_KEY);
        const parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed.filter(id => typeof id === 'string' && id.trim()) : [];
    } catch (err) {
        console.warn("Could not read saved jobs from localStorage:", err);
        return [];
    }
}

function writeSavedJobIds(jobIds) {
    try {
        window.localStorage.setItem(SAVED_JOBS_STORAGE_KEY, JSON.stringify(jobIds));
    } catch (err) {
        console.warn("Could not write saved jobs to localStorage:", err);
    }
}

function readSavedJobMeta() {
    try {
        const raw = window.localStorage.getItem(SAVED_JOB_META_STORAGE_KEY);
        const parsed = raw ? JSON.parse(raw) : {};
        return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
    } catch (err) {
        console.warn("Could not read saved job metadata from localStorage:", err);
        return {};
    }
}

function writeSavedJobMeta(meta) {
    try {
        window.localStorage.setItem(SAVED_JOB_META_STORAGE_KEY, JSON.stringify(meta));
    } catch (err) {
        console.warn("Could not write saved job metadata to localStorage:", err);
    }
}

function basename(path) {
    if (!path) return '';
    return String(path).split(/[\\/]/).filter(Boolean).pop() || '';
}

function progressPercent(progress) {
    if (!progress?.total) return null;
    return Math.max(0, Math.min(100, Math.round((progress.current / progress.total) * 100)));
}

function jobMetaFromData(data) {
    const percent = data.status === 'running' ? progressPercent(data.latest_progress) : null;
    return {
        name: data.original_video_filename || basename(data.video_path) || `Job ${String(data.job_id || '').slice(0, 8)}`,
        status: data.status || null,
        progressPercent: percent,
        progressMessage: data.latest_progress?.message || null,
        updatedAt: new Date().toISOString()
    };
}

function mergeSummaryMeta(existing, summary) {
    const incoming = jobMetaFromData(summary);
    if (existing?.status === 'uploading' && !summary.video_path && summary.status !== 'error') {
        return {
            ...existing,
            updatedAt: new Date().toISOString()
        };
    }
    return incoming;
}

export function JobProvider({ children }) {
    const [jobId, setJobId] = useState(() => {
        const params = new URLSearchParams(window.location.search);
        return params.get('job') || null;
    });
    const [savedJobIds, setSavedJobIds] = useState(readSavedJobIds);
    const [savedJobMeta, setSavedJobMeta] = useState(readSavedJobMeta);
    const [jobData, setJobData] = useState(null);
    const [sseConnected, setSseConnected] = useState(false);
    const [gptRecords, setGptRecords] = useState([]);
    const [currentStep, setCurrentStep] = useState(0);
    const [doneSteps, setDoneSteps] = useState(new Set());
    const [progressData, setProgressData] = useState({}); // { step: { msg, percent } }
    const [focusedSlot, setFocusedSlot] = useState(null);
    const [srtTexts, setSrtTexts] = useState({});
    const [isSavingSrt, setIsSavingSrt] = useState(false);
    const [isRunAllActive, setIsRunAllActive] = useState(false);
    
    // Global Config Modal State
    const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
    const [availableModels, setAvailableModels] = useState([]);
    const [gptParams, setGptParams] = useState({
        system_prompt: "",
        user_prompt: "",
        ad_rules: "",
        few_shots: "",
        model: "gpt-4o",
        temperature: 0.2,
        max_tokens: 1024,
        detail: "low",
        cut: "broadcast",
        syllables_per_second: 6.0
    });

    const [vadParams, setVadParams] = useState({
        threshold: 0.5,
        min_speech_duration_ms: 1500,
        min_silence_duration_ms: 400,
        min_pause_duration_s: 0.3
    });

    const [transcribeParams, setTranscribeParams] = useState({
        model_size: "small",
        language: "de",
        use_fw_vad: true
    });

    const [slotsParams, setSlotsParams] = useState({
        min_slot_s: 1.0,
        pad_in_s: 0.0,
        pad_out_s: 0.0,
        filter_whisper: false
    });

    const [ttsParams, setTtsParams] = useState({
        apiKey: '',
        voice: 'alloy',
        duckingVolume: '0.4'
    });

    const [imagesParams, setImagesParams] = useState({
        threshold: 24,
        blur_threshold: 80,
        min_scene_length: 20,
        short_scene_s: 3.0
    });

    const addSavedJobId = useCallback((id) => {
        if (!id) return;
        setSavedJobIds(prev => {
            const next = prev.includes(id) ? prev : [id, ...prev];
            writeSavedJobIds(next);
            return next;
        });
    }, []);

    const updateSavedJobMeta = useCallback((id, updates) => {
        if (!id) return;
        setSavedJobMeta(prev => {
            const next = {
                ...prev,
                [id]: {
                    ...(prev[id] || {}),
                    ...updates,
                    updatedAt: new Date().toISOString()
                }
            };
            writeSavedJobMeta(next);
            return next;
        });
    }, []);

    const removeSavedJobId = useCallback((id) => {
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

    const selectJob = useCallback((id) => {
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
                        newP.model = firstModel.model;
                        newP.temperature = firstModel.temperature !== undefined ? firstModel.temperature : 0.2;
                        newP.max_tokens = firstModel.max_tokens !== undefined ? firstModel.max_tokens : 1024;
                        newP.detail = firstModel.detail !== undefined ? firstModel.detail : "low";
                    }
                    return newP;
                });
            })
            .catch(console.error);
    }, []);

    useEffect(() => {
        if (jobData?.gpt_records) {
            const initialTexts = {};
            jobData.gpt_records.forEach(rec => {
                initialTexts[rec.slot] = rec.text || '';
            });
            setSrtTexts(initialTexts);
        }
    }, [jobData?.gpt_records]);

    const handleSaveSrtTexts = useCallback(async () => {
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
            alert("Änderungen erfolgreich gespeichert! Die Ausgabedateien wurden aktualisiert.");
        } catch (err) {
            alert("Error: " + err.message);
        } finally {
            setIsSavingSrt(false);
        }
    }, [jobId, srtTexts, setIsSavingSrt]);

    const fetchJobData = useCallback(async (id) => {
        try {
            const res = await fetch(`/api/jobs/${id}`, {
                cache: 'no-store',
                headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' }
            });
            if (res.ok) {
                const data = await res.json();
                addSavedJobId(id);
                updateSavedJobMeta(id, jobMetaFromData(data));
                setJobData(data);

                const newDone = new Set();
                if (data.video_stats) newDone.add(0);
                if (data.pauses_count > 0) newDone.add(1);
                if (data.transcript_meta) newDone.add(2);
                if (data.slots_count > 0) newDone.add(3);
                if (data.images_count > 0) newDone.add(4);
                if (data.gpt_records_broadcast || data.gpt_records_directors) newDone.add(5);
                if (data.final_mp4_path) newDone.add(6);
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
                if (data.status === 'running' && data.latest_progress) {
                    setProgressData(prev => ({
                        ...prev,
                        [data.latest_progress.step]: {
                            msg: data.latest_progress.message,
                            percent: data.latest_progress.total
                                ? Math.round((data.latest_progress.current / data.latest_progress.total) * 100)
                                : 100
                        }
                    }));
                }
            }
        } catch (err) {
            console.error("Failed to load job:", err);
        }
    }, [addSavedJobId, updateSavedJobMeta, setJobData, setDoneSteps, setCurrentStep]);

    useEffect(() => {
        if (savedJobIds.length === 0) return;

        const params = new URLSearchParams({ job_ids: savedJobIds.join(',') });
        const source = new EventSource(`/api/jobs/summary_stream?${params.toString()}`);

        const handleSummaries = (ev) => {
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

    const handleUpdateSlotTiming = useCallback(async (slotId, start_s, end_s) => {
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
            console.error("Error updating slot timing:", err.message);
            alert("Error updating slot timing: " + err.message);
            // fetchJobData(jobId);
        }
    }, [jobId, fetchJobData]);

    // Load job from URL on mount
    useEffect(() => {
        if (jobId) {
            fetchJobData(jobId);
        }
    }, [jobId, fetchJobData]);

    const createJob = useCallback(async () => {
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
        }
    }, [addSavedJobId, resetJobView, updateSavedJobMeta]);

    const markStepDone = useCallback((step) => {
        setDoneSteps(prev => new Set(prev).add(step));
    }, []);

    const markJobStarted = useCallback((step, message) => {
        if (!jobId) return;
        const stepIndexes = {
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

    const handleRunVAD = useCallback(async () => {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/jobs/${jobId}/vad`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(vadParams)
            });
            if (!res.ok) throw new Error("Failed to start VAD");
            markJobStarted('vad', 'Sprechpausen erkennen...');
        } catch (err) { alert("Error: " + err.message); setIsRunAllActive(false); }
    }, [jobId, vadParams, markJobStarted]);

    const handleRunTranscribe = useCallback(async () => {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/jobs/${jobId}/transcribe`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(transcribeParams)
            });
            if (!res.ok) throw new Error("Failed to start transcription");
            markJobStarted('transcribe', 'Transkription starten...');
        } catch (err) { alert("Error: " + err.message); setIsRunAllActive(false); }
    }, [jobId, transcribeParams, markJobStarted]);

    const handleRunSlots = useCallback(async () => {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/jobs/${jobId}/slots`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(slotsParams)
            });
            if (!res.ok) throw new Error("Failed to generate slots");
            markJobStarted('slots', 'AD-Slots generieren...');
        } catch (err) { alert("Error: " + err.message); setIsRunAllActive(false); }
    }, [jobId, slotsParams, markJobStarted]);

    const handleRunImages = useCallback(async () => {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/jobs/${jobId}/images`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(imagesParams)
            });
            if (!res.ok) throw new Error("Failed to extract images");
            markJobStarted('images', 'Bilder extrahieren...');
        } catch (err) { alert("Error: " + err.message); setIsRunAllActive(false); }
    }, [jobId, imagesParams, markJobStarted]);

    const handleRunGPT = useCallback(async () => {
        if (!jobId) return;
        if (!gptParams) {
            setIsRunAllActive(false);
            return alert("Prompts fehlen. Bitte überprüfen Sie die Konfiguration.");
        }
        let system_final = gptParams.system_prompt;
        if (gptParams.ad_rules) {
            system_final += "\n\n# Audiodeskription – Regeln\n" + gptParams.ad_rules;
        }
        if (gptParams.few_shots) {
            system_final += "\n\n# Few-Shots / Beispiele\n" + gptParams.few_shots;
        }
        const payload = {
            model: gptParams.model,
            temperature: gptParams.temperature,
            max_tokens: gptParams.max_tokens,
            cut: gptParams.cut,
            syllables_per_second: gptParams.syllables_per_second || 6.0,
            system_prompt: system_final,
            user_prompt: gptParams.user_prompt || "Erstelle eine AD für diese Frames.",
        };
        try {
            const res = await fetch(`/api/jobs/${jobId}/gpt`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!res.ok) throw new Error((await res.json()).error || "Failed to start GPT generation");
            markJobStarted('gpt', 'Beschreibungen generieren...');
        } catch (err) { alert("Error: " + err.message); setIsRunAllActive(false); }
    }, [jobId, gptParams, markJobStarted]);

    const handleRunTTS = useCallback(async () => {
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
        } catch (err) { alert("Error: " + err.message); setIsRunAllActive(false); }
    }, [jobId, ttsParams, markJobStarted]);

    const handleSSEEvent = useCallback((payload) => {
        const { event, data } = payload;

        if (event === 'ping' || event === 'connected') return;

        if (event === 'progress') {
            const percent = progressPercent(data);
            updateSavedJobMeta(jobId, {
                status: 'running',
                progressPercent: percent,
                progressMessage: data.message || null
            });
            setProgressData(prev => ({
                ...prev,
                [data.step]: {
                    msg: data.message,
                    percent: percent ?? 100
                }
            }));
        } else if (event === 'error') {
            updateSavedJobMeta(jobId, {
                status: 'error',
                progressPercent: null,
                progressMessage: data.message || null
            });
            alert(`Error in ${data.step}: ${data.message}`);
            setProgressData(prev => ({ ...prev, [data.step]: null }));
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
            } else if (event === 'gpt_done') {
                setDoneSteps(prev => new Set(prev).add(5));
                setCurrentStep(6);
                fetchJobData(jobId); // Need full update for outputs
                setProgressData(prev => ({ ...prev, gpt: null }));
            } else if (event === 'tts_done') {
                setDoneSteps(prev => new Set(prev).add(6));
                setCurrentStep(7);
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
                    handleRunGPT();
                } else if (event === 'gpt_done') {
                    handleRunTTS();
                }
            }
        }
    }, [
        jobId, fetchJobData, updateSavedJobMeta, setProgressData, setDoneSteps,
        setCurrentStep, isRunAllActive, handleRunTranscribe, handleRunSlots,
        handleRunImages, handleRunGPT, handleRunTTS
    ]);

    useEffect(() => {
        if (!jobId) return;

        const source = new EventSource(`/api/jobs/${jobId}/stream`);

        source.onopen = () => setSseConnected(true);
        source.onerror = () => setSseConnected(false);

        source.onmessage = (ev) => {
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

    const runAllSteps = useCallback(() => {
        if (!jobId) return alert("Bitte laden Sie zuerst ein Video hoch.");
        setIsRunAllActive(true);
        // Determine the next uncompleted step and start there
        if (!doneSteps.has(1)) handleRunVAD();
        else if (!doneSteps.has(2)) handleRunTranscribe();
        else if (!doneSteps.has(3)) handleRunSlots();
        else if (!doneSteps.has(4)) handleRunImages();
        else if (!doneSteps.has(5)) handleRunGPT();
        else if (!doneSteps.has(6)) handleRunTTS();
        else setIsRunAllActive(false); // all done
    }, [doneSteps, handleRunGPT, handleRunImages, handleRunSlots, handleRunTTS, handleRunTranscribe, handleRunVAD, jobId]);

    const stopRunAll = useCallback(() => {
        setIsRunAllActive(false);
    }, []);

    const handleUpdateGPTRecord = useCallback((recordId, updates) => {
        setGptRecords(prevRecords =>
            prevRecords.map(record =>
                record.id === recordId ? { ...record, ...updates } : record
            )
        );
    }, []);

    const contextValue = useMemo(() => ({
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
        handleRunGPT,
        handleUpdateGPTRecord,
        handleRunTTS,
        runAllSteps,
        isRunAllActive,
        stopRunAll
    }), [
        jobId, setJobId, savedJobIds, savedJobMeta, selectJob, removeSavedJobId, updateSavedJobMeta, jobData, sseConnected, gptRecords, setGptRecords, currentStep, setCurrentStep,
        doneSteps, markStepDone, progressData, setProgressData, focusedSlot, setFocusedSlot, createJob,
        fetchJobData, srtTexts, setSrtTexts, isSavingSrt, handleSaveSrtTexts, handleUpdateSlotTiming,
        isConfigModalOpen, setIsConfigModalOpen, gptParams, setGptParams, availableModels, setAvailableModels,
        vadParams, setVadParams, transcribeParams, setTranscribeParams, slotsParams, setSlotsParams,
        ttsParams, setTtsParams, imagesParams, setImagesParams, handleRunVAD, handleRunTranscribe,
        handleRunSlots, handleRunImages, handleRunGPT, handleUpdateGPTRecord, handleRunTTS, runAllSteps,
        isRunAllActive, stopRunAll
    ]);

    return (
        <JobContext.Provider value={contextValue}>
            {children}
        </JobContext.Provider>
    );
}

export function useJob() {
    return useContext(JobContext);
}
