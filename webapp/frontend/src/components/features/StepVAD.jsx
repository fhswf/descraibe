import React, { useState } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepVAD() {
    const { jobId, jobData, currentStep, progressData, fetchJobData } = useJob();

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

    const progress = progressData?.vad;

    return (
        <div className="step-content">
            <div className="step-header">
                <div className="step-icon">🔇</div>
                <div>
                    <h2>Sprechpausen erkennen</h2>
                    <p>Silero VAD erkennt Sprach- und Pausensegmente im Video.</p>
                </div>
            </div>

            <div className="card">
                <p className="card-title">Parameter</p>
                <div className="form-grid">
                    <div className="form-group">
                        <label>VAD-Schwellwert: {params.threshold}</label>
                        <input
                            type="range" min="0.1" max="0.9" step="0.05"
                            value={params.threshold}
                            onChange={e => setParams({ ...params, threshold: parseFloat(e.target.value) })}
                        />
                    </div>
                    <div className="form-group">
                        <label>Min. Sprachdauer (ms)</label>
                        <input
                            type="number" min="100" step="100"
                            value={params.min_speech_duration_ms}
                            onChange={e => setParams({ ...params, min_speech_duration_ms: parseInt(e.target.value) })}
                        />
                    </div>
                    <div className="form-group">
                        <label>Min. Stille (ms)</label>
                        <input
                            type="number" min="50" step="50"
                            value={params.min_silence_duration_ms}
                            onChange={e => setParams({ ...params, min_silence_duration_ms: parseInt(e.target.value) })}
                        />
                    </div>
                    <div className="form-group">
                        <label>Min. Pausen-Dauer (s)</label>
                        <input
                            type="number" min="0.1" step="0.1"
                            value={params.min_pause_duration_s}
                            onChange={e => setParams({ ...params, min_pause_duration_s: parseFloat(e.target.value) })}
                        />
                    </div>
                </div>
            </div>

            <div className="btn-row">
                <button
                    className="btn btn-primary"
                    onClick={handleRunVAD}
                    disabled={jobData?.status === 'running'}
                >
                    ▶ Pausen erkennen
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
