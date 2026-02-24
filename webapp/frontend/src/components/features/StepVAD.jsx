import React, { useState } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepVAD() {
    const { jobId, jobData, currentStep } = useJob();

    const [params, setParams] = useState({
        threshold: 0.5,
        min_speech_duration_ms: 1500,
        min_silence_duration_ms: 400,
        min_pause_duration_s: 0.3
    });

    if (currentStep !== 1) return null;

    const handleRunVAD = async () => {
        try {
            const res = await fetch(`/api/jobs/${jobId}/vad`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params)
            });
            if (!res.ok) throw new Error("Failed to start VAD");
        } catch (err) {
            alert("Error: " + err.message);
        }
    };

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-start gap-4 pb-4 border-b border-border-subtle">
                <div className="text-3xl leading-none">🔇</div>
                <div>
                    <h2 className="text-[1.4rem] font-bold mb-1">Sprechpausen erkennen</h2>
                    <p className="text-sm text-text-secondary">Silero VAD erkennt Sprach- und Pausensegmente im Video.</p>
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Parameter</p>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">VAD-Schwellwert: {params.threshold}</label>
                        <input
                            type="range" min="0.1" max="0.9" step="0.05"
                            value={params.threshold}
                            onChange={e => setParams({ ...params, threshold: parseFloat(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15 accent-violet-500 pr-0 pl-0 py-0"
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Min. Sprachdauer (ms)</label>
                        <input
                            type="number" min="100" step="100"
                            value={params.min_speech_duration_ms}
                            onChange={e => setParams({ ...params, min_speech_duration_ms: parseInt(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Min. Stille (ms)</label>
                        <input
                            type="number" min="50" step="50"
                            value={params.min_silence_duration_ms}
                            onChange={e => setParams({ ...params, min_silence_duration_ms: parseInt(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Min. Pausen-Dauer (s)</label>
                        <input
                            type="number" min="0.1" step="0.1"
                            value={params.min_pause_duration_s}
                            onChange={e => setParams({ ...params, min_pause_duration_s: parseFloat(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                        />
                    </div>
                </div>
            </div>

            <div className="flex gap-2.5 items-center flex-wrap">
                <button
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-[10px] font-semibold text-[0.875rem] transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-gradient-to-br from-violet-500 to-[#7c3aed] text-white shadow-[0_4px_16px_rgba(139,92,246,0.3)] hover:not:disabled:shadow-[0_6px_24px_rgba(139,92,246,0.45)] hover:not:disabled:-translate-y-px"
                    onClick={handleRunVAD}
                    disabled={jobData?.status === 'running'}
                >
                    ▶ Pausen erkennen
                </button>
            </div>
        </div>
    );
}
