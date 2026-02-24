import React, { useState } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepImages() {
    const { jobId, jobData, currentStep, progressData } = useJob();

    const [params, setParams] = useState({
        threshold: 24,
        blur_threshold: 80,
        min_scene_length: 20,
        short_scene_s: 3.0
    });

    if (currentStep !== 4) return null;

    const handleRunImages = async () => {
        try {
            const res = await fetch(`/api/jobs/${jobId}/images`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params)
            });
            if (!res.ok) throw new Error("Failed to extract images");
        } catch (err) {
            alert("Error: " + err.message);
        }
    };

    const progress = progressData?.images;

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-start gap-4 pb-4 border-b border-border-subtle">
                <div className="text-3xl leading-none">🖼️</div>
                <div>
                    <h2 className="text-[1.4rem] font-bold mb-1">Bilder extrahieren</h2>
                    <p className="text-sm text-text-secondary">SceneDetect identifiziert Szenen und extrahiert repräsentative Frames für jeden AD-Slot.</p>
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Parameter</p>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Scene-Threshold: {params.threshold}</label>
                        <input
                            type="range" min="10" max="50" step="1"
                            value={params.threshold}
                            onChange={e => setParams({ ...params, threshold: parseInt(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15 accent-violet-500 pr-0 pl-0 py-0"
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Blur-Threshold: {params.blur_threshold}</label>
                        <input
                            type="range" min="20" max="200" step="5"
                            value={params.blur_threshold}
                            onChange={e => setParams({ ...params, blur_threshold: parseInt(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15 accent-violet-500 pr-0 pl-0 py-0"
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Min. Szenenlänge (Frames)</label>
                        <input
                            type="number" min="5"
                            value={params.min_scene_length}
                            onChange={e => setParams({ ...params, min_scene_length: parseInt(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Kurzszenen-Grenze (s)</label>
                        <input
                            type="number" min="0.5" step="0.5"
                            value={params.short_scene_s}
                            onChange={e => setParams({ ...params, short_scene_s: parseFloat(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                        />
                    </div>
                </div>
            </div>

            <div className="flex gap-2.5 items-center flex-wrap">
                <button
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-[10px] font-semibold text-[0.875rem] transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-gradient-to-br from-violet-500 to-[#7c3aed] text-white shadow-[0_4px_16px_rgba(139,92,246,0.3)] hover:not:disabled:shadow-[0_6px_24px_rgba(139,92,246,0.45)] hover:not:disabled:-translate-y-px"
                    onClick={handleRunImages}
                    disabled={jobData?.status === 'running'}
                >
                    ▶ Bilder extrahieren
                </button>
            </div>

            {progress && (
                <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                    <div className="flex flex-col gap-2">
                        <div className="h-1.5 bg-border-subtle rounded-full overflow-hidden">
                            <div className="h-full bg-gradient-to-r from-violet-500 to-teal-500 rounded-full transition-all duration-400 relative overflow-hidden" style={{ width: `${progress.percent}%` }}>
                                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/25 to-transparent animate-[shimmer_1.4s_infinite]"></div>
                            </div>
                        </div>
                        <span className="text-xs text-text-secondary">{progress.msg}</span>
                    </div>
                </div>
            )}
        </div>
    );
}
