import React from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepTranscribe() {
    const { jobId, currentStep } = useJob();

    if (currentStep !== 2) return null;

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
            <div className="flex items-start justify-between gap-4 pb-4 border-b border-border-subtle">
                <div className="flex gap-4">
                    <div className="text-3xl leading-none">📝</div>
                    <div>
                        <h2 className="text-[1.4rem] font-bold mb-1">Transkription</h2>
                        <p className="text-sm text-text-secondary">Erstelle ein genaues Transkript der Sprachphasen mit Whisper.</p>
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
        </div>
    );
}
