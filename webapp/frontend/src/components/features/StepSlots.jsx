import React, { useState } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepSlots() {
    const { jobId, jobData, currentStep, progressData } = useJob();

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

    const progress = progressData?.slots;

    return (
        <div className="step-content">
            <div className="step-header">
                <div className="step-icon">🕐</div>
                <div>
                    <h2>AD-Slots generieren</h2>
                    <p>Wandle Sprechpausen in Audio-Deskriptions-Slots um.</p>
                </div>
            </div>

            <div className="card">
                <p className="card-title">Parameter</p>
                <div className="form-grid">
                    <div className="form-group">
                        <label>Min. Slot-Dauer (s)</label>
                        <input
                            type="number" min="0.1" step="0.1"
                            value={params.min_slot_s}
                            onChange={e => setParams({ ...params, min_slot_s: parseFloat(e.target.value) })}
                        />
                    </div>
                    <div className="form-group">
                        <label>Eingangs-Padding (s)</label>
                        <input
                            type="number" min="0" step="0.05"
                            value={params.pad_in_s}
                            onChange={e => setParams({ ...params, pad_in_s: parseFloat(e.target.value) })}
                        />
                    </div>
                    <div className="form-group">
                        <label>Ausgangs-Padding (s)</label>
                        <input
                            type="number" min="0" step="0.05"
                            value={params.pad_out_s}
                            onChange={e => setParams({ ...params, pad_out_s: parseFloat(e.target.value) })}
                        />
                    </div>
                    <div className="form-group">
                        <label>Whisper-Filter (Sprache überschneidend)</label>
                        <select
                            value={params.filter_whisper.toString()}
                            onChange={e => setParams({ ...params, filter_whisper: e.target.value === 'true' })}
                        >
                            <option value="false">Nein</option>
                            <option value="true">Ja (Slots mit Sprache entfernen)</option>
                        </select>
                    </div>
                </div>
            </div>

            <div className="btn-row">
                <button
                    className="btn btn-primary"
                    onClick={handleRunSlots}
                    disabled={jobData?.status === 'running'}
                >
                    ▶ Slots generieren
                </button>
            </div>

            {progress && (
                <div className="card">
                    <div className="progress-wrap">
                        <div className="progress-bar-bg">
                            <div className="progress-bar-fill" style={{ width: `${progress.percent}%` }}></div>
                        </div>
                        <span className="progress-msg">{progress.msg}</span>
                    </div>
                </div>
            )}
        </div>
    );
}
