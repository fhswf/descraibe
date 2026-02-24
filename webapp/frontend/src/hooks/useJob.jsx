import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const JobContext = createContext();

export function JobProvider({ children }) {
    const [jobId, setJobId] = useState(null);
    const [jobData, setJobData] = useState(null);
    const [sseConnected, setSseConnected] = useState(false);
    const [gptRecords, setGptRecords] = useState([]);
    const [currentStep, setCurrentStep] = useState(0);
    const [doneSteps, setDoneSteps] = useState(new Set());
    const [progressData, setProgressData] = useState({}); // { step: { msg, percent } }
    const [focusedSlot, setFocusedSlot] = useState(null);

    // Load job from URL on mount
    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const id = params.get('job');
        if (id) {
            setJobId(id);
            fetchJobData(id);
        }
    }, []);

    const fetchJobData = async (id) => {
        try {
            const res = await fetch(`/api/jobs/${id}`);
            if (res.ok) {
                const data = await res.json();
                setJobData(data);

                const newDone = new Set();
                if (data.video_stats) newDone.add(0);
                if (data.pauses_count > 0) newDone.add(1);
                if (data.transcript_meta) newDone.add(2);
                if (data.slots_count > 0) newDone.add(3);
                if (data.images_count > 0) newDone.add(4);
                if (data.quality_report) newDone.add(5);
                // Note: step 6 is GPT generation, step 7 is results
                setDoneSteps(newDone);

                let targetStep = 0;
                for (let i = 0; i <= 7; i++) {
                    if (!newDone.has(i)) {
                        targetStep = i;
                        break;
                    }
                }
                setCurrentStep(targetStep);
            }
        } catch (err) {
            console.error("Failed to load job:", err);
        }
    };

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
    }, [jobId]);

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
        } else {
            // Refresh job data to get the latest state (links, stats, counts)
            fetchJobData(jobId);

            if (event === 'vad_done') {
                setDoneSteps(prev => new Set(prev).add(1));
                setCurrentStep(2);
            } else if (event === 'transcribe_done') {
                setDoneSteps(prev => new Set(prev).add(2));
                setCurrentStep(3);
            } else if (event === 'slots_done') {
                setDoneSteps(prev => new Set(prev).add(3));
                setCurrentStep(4);
            } else if (event === 'images_done') {
                setDoneSteps(prev => new Set(prev).add(4));
                setCurrentStep(5);
            } else if (event === 'gpt_done') {
                setDoneSteps(prev => new Set(prev).add(6));
                setCurrentStep(7);
                fetchJobData(jobId); // Need full update for outputs
            }
        }
    }, [jobId]);

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
            focusedSlot,
            setFocusedSlot,
            createJob,
            fetchJobData
        }}>
            {children}
        </JobContext.Provider>
    );
}

export function useJob() {
    return useContext(JobContext);
}
