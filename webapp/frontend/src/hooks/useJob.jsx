/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const JobContext = createContext();

export function JobProvider({ children }) {
    const [jobId, setJobId] = useState(() => {
        const params = new URLSearchParams(window.location.search);
        return params.get('job') || null;
    });
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
        cut: "broadcast"
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
            // Add a cache-busting timestamp to ensure we get fresh data
            const res = await fetch(`/api/jobs/${id}?t=${Date.now()}`, {
                headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' }
            });
            if (res.ok) {
                const data = await res.json();
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
    }, [setJobData, setDoneSteps, setCurrentStep]);

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



    const handleSSEEvent = useCallback((payload) => {
        const { event, data } = payload;

        if (event === 'ping' || event === 'connected') return;

        if (event === 'progress') {
            setProgressData(prev => ({
                ...prev,
                [data.step]: {
                    msg: data.message,
                    percent: data.total ? Math.round((data.current / data.total) * 100) : 100
                }
            }));
        } else if (event === 'error') {
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
    }, [jobId, fetchJobData, setProgressData, setDoneSteps, setCurrentStep, isRunAllActive]);

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



    const createJob = async () => {
        try {
            const res = await fetch('/api/jobs', { method: 'POST' });
            const data = await res.json();
            setJobId(data.job_id);
            window.history.pushState({}, '', `?job=${data.job_id}`);
            return data.job_id;
        } catch (err) {
            console.error("Failed to create job:", err);
        }
    };

    const markStepDone = (step) => {
        setDoneSteps(prev => new Set(prev).add(step));
    };

    const handleRunVAD = useCallback(async () => {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/jobs/${jobId}/vad`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(vadParams)
            });
            if (!res.ok) throw new Error("Failed to start VAD");
        } catch (err) { alert("Error: " + err.message); setIsRunAllActive(false); }
    }, [jobId, vadParams]);

    const handleRunTranscribe = useCallback(async () => {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/jobs/${jobId}/transcribe`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(transcribeParams)
            });
            if (!res.ok) throw new Error("Failed to start transcription");
        } catch (err) { alert("Error: " + err.message); setIsRunAllActive(false); }
    }, [jobId, transcribeParams]);

    const handleRunSlots = useCallback(async () => {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/jobs/${jobId}/slots`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(slotsParams)
            });
            if (!res.ok) throw new Error("Failed to generate slots");
        } catch (err) { alert("Error: " + err.message); setIsRunAllActive(false); }
    }, [jobId, slotsParams]);

    const handleRunImages = useCallback(async () => {
        if (!jobId) return;
        try {
            const res = await fetch(`/api/jobs/${jobId}/images`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(imagesParams)
            });
            if (!res.ok) throw new Error("Failed to extract images");
        } catch (err) { alert("Error: " + err.message); setIsRunAllActive(false); }
    }, [jobId, imagesParams]);

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
        } catch (err) { alert("Error: " + err.message); setIsRunAllActive(false); }
    }, [jobId, gptParams]);

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
        } catch (err) { alert("Error: " + err.message); setIsRunAllActive(false); }
    }, [jobId, ttsParams]);

    const runAllSteps = () => {
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
    };

    const stopRunAll = () => {
        setIsRunAllActive(false);
    };

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
        jobId, setJobId, jobData, sseConnected, gptRecords, setGptRecords, currentStep, setCurrentStep,
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
