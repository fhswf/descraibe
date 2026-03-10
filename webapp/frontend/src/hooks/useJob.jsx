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
                if (data.gpt_records_broadcast || data.gpt_records_directors) newDone.add(6);
                if (data.final_mp4_path) newDone.add(7);
                setDoneSteps(newDone);

                let targetStep = 0;
                for (let i = 0; i <= 8; i++) {
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
                setDoneSteps(prev => new Set(prev).add(6));
                setCurrentStep(7);
                fetchJobData(jobId); // Need full update for outputs
                setProgressData(prev => ({ ...prev, gpt: null }));
            } else if (event === 'tts_done') {
                setDoneSteps(prev => new Set(prev).add(7));
                setCurrentStep(8);
                fetchJobData(jobId);
                setProgressData(prev => ({ ...prev, tts: null }));
            }
        }
    }, [jobId, fetchJobData, setProgressData, setDoneSteps, setCurrentStep]);

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

    return (
        <JobContext.Provider value={{
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
            handleUpdateSlotTiming
        }}>
            {children}
        </JobContext.Provider>
    );
}

export function useJob() {
    return useContext(JobContext);
}
