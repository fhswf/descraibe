import React, { useState } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepTranscribe() {
    const { jobId, jobData, currentStep } = useJob();

    const [params, setParams] = useState({
        model_size: "small",
        language: "de",
        use_fw_vad: true
    });

    if (currentStep !== 2) return null;

    const handleRunTranscribe = async () => {
        try {
            const res = await fetch(`/api/jobs/${jobId}/transcribe`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params)
            });
            if (!res.ok) throw new Error("Failed to start transcription");
        } catch (err) {
            alert("Error: " + err.message);
        }
    };

    const handleUploadSrt = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('srt', file);

        try {
            const res = await fetch(`/api/jobs/${jobId}/srt`, {
                method: 'POST',
                body: formData
            });
            if (!res.ok) throw new Error("Upload failed");
            // App will pick up the update via SSE fetchJobData
        } catch (err) {
            alert("SRT Upload error: " + err.message);
        }
    };

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-start gap-4 pb-4 border-b border-border-subtle">
                <div className="text-3xl leading-none">📝</div>
                <div>
                    <h2 className="text-[1.4rem] font-bold mb-1">Transkription</h2>
                    <p className="text-sm text-text-secondary">Faster-Whisper transkribiert die Sprache im Video.</p>
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Modell & Optionen</p>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Whisper Modell</label>
                        <select
                            value={params.model_size}
                            onChange={e => setParams({ ...params, model_size: e.target.value })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                        >
                            <option value="large-v3">large-v3 (beste Qualität)</option>
                            <option value="medium">medium</option>
                            <option value="small">small (schnell)</option>
                        </select>
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Sprache</label>
                        <select
                            value={params.language}
                            onChange={e => setParams({ ...params, language: e.target.value })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                        >
                            <option value="de">Deutsch</option>
                            <option value="en">Englisch</option>
                        </select>
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Faster-Whisper VAD</label>
                        <select
                            value={params.use_fw_vad.toString()}
                            onChange={e => setParams({ ...params, use_fw_vad: e.target.value === 'true' })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                        >
                            <option value="true">Ja</option>
                            <option value="false">Nein</option>
                        </select>
                    </div>
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Oder: Vorhandenes Transkript hochladen</p>
                <div className="flex gap-2.5 items-center flex-wrap">
                    <label className="inline-flex items-center gap-2 px-5 py-2.5 rounded-[10px] font-semibold text-[0.875rem] transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-bg-card text-text-primary border border-border-subtle hover:not:disabled:border-violet-500 hover:not:disabled:text-violet-500" style={{ cursor: 'pointer' }}>
                        📄 SRT hochladen
                        <input
                            type="file"
                            accept=".srt,.csv,.json"
                            style={{ display: 'none' }}
                            onChange={handleUploadSrt}
                        />
                    </label>
                </div>
            </div>

            <div className="flex gap-2.5 items-center flex-wrap">
                <button
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-[10px] font-semibold text-[0.875rem] transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-gradient-to-br from-violet-500 to-[#7c3aed] text-white shadow-[0_4px_16px_rgba(139,92,246,0.3)] hover:not:disabled:shadow-[0_6px_24px_rgba(139,92,246,0.45)] hover:not:disabled:-translate-y-px"
                    onClick={handleRunTranscribe}
                    disabled={jobData?.status === 'running'}
                >
                    ▶ Transkription starten
                </button>
            </div>
        </div>
    );
}
