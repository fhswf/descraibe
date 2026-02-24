import React, { useState } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepSlots() {
    const { jobId, jobData, currentStep } = useJob();

    const [params, setParams] = useState({
        min_slot_s: 1.0,
        pad_in_s: 0.0,
        pad_out_s: 0.0,
        filter_whisper: false
    });

    if (currentStep !== 3) return null;

    const handleRunSlots = async () => {
        try {
            const res = await fetch(`/api/jobs/${jobId}/slots`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params)
            });
            if (!res.ok) throw new Error("Failed to generate slots");
        } catch (err) {
            alert("Error: " + err.message);
        }
    };

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-start gap-4 pb-4 border-b border-border-subtle">
                <div className="text-3xl leading-none">🕐</div>
                <div>
                    <h2 className="text-[1.4rem] font-bold mb-1">AD-Slots generieren</h2>
                    <p className="text-sm text-text-secondary">Wandle Sprechpausen in Audio-Deskriptions-Slots um.</p>
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Parameter</p>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Min. Slot-Dauer (s)</label>
                        <input
                            type="number" min="0.1" step="0.1"
                            value={params.min_slot_s}
                            onChange={e => setParams({ ...params, min_slot_s: parseFloat(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Eingangs-Padding (s)</label>
                        <input
                            type="number" min="0" step="0.05"
                            value={params.pad_in_s}
                            onChange={e => setParams({ ...params, pad_in_s: parseFloat(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Ausgangs-Padding (s)</label>
                        <input
                            type="number" min="0" step="0.05"
                            value={params.pad_out_s}
                            onChange={e => setParams({ ...params, pad_out_s: parseFloat(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Whisper-Filter (Sprache überschneidend)</label>
                        <select
                            value={params.filter_whisper.toString()}
                            onChange={e => setParams({ ...params, filter_whisper: e.target.value === 'true' })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                        >
                            <option value="false">Nein</option>
                            <option value="true">Ja (Slots mit Sprache entfernen)</option>
                        </select>
                    </div>
                </div>
            </div>

            <div className="flex gap-2.5 items-center flex-wrap">
                <button
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-[10px] font-semibold text-[0.875rem] transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-gradient-to-br from-violet-500 to-[#7c3aed] text-white shadow-[0_4px_16px_rgba(139,92,246,0.3)] hover:not:disabled:shadow-[0_6px_24px_rgba(139,92,246,0.45)] hover:not:disabled:-translate-y-px"
                    onClick={handleRunSlots}
                    disabled={jobData?.status === 'running'}
                >
                    ▶ Slots generieren
                </button>
            </div>
        </div>
    );
}
