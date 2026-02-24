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
        <div className="step-content">
            <div className="step-header">
                <div className="step-icon">🖼️</div>
                <div>
                    <h2>Bilder extrahieren</h2>
                    <p>SceneDetect identifiziert Szenen und extrahiert repräsentative Frames für jeden AD-Slot.</p>
                </div>
            </div>

            <div className="card">
                <p className="card-title">Parameter</p>
                <div className="form-grid">
                    <div className="form-group">
                        <label>Scene-Threshold: {params.threshold}</label>
                        <input
                            type="range" min="10" max="50" step="1"
                            value={params.threshold}
                            onChange={e => setParams({ ...params, threshold: parseInt(e.target.value) })}
                        />
                    </div>
                    <div className="form-group">
                        <label>Blur-Threshold: {params.blur_threshold}</label>
                        <input
                            type="range" min="20" max="200" step="5"
                            value={params.blur_threshold}
                            onChange={e => setParams({ ...params, blur_threshold: parseInt(e.target.value) })}
                        />
                    </div>
                    <div className="form-group">
                        <label>Min. Szenenlänge (Frames)</label>
                        <input
                            type="number" min="5"
                            value={params.min_scene_length}
                            onChange={e => setParams({ ...params, min_scene_length: parseInt(e.target.value) })}
                        />
                    </div>
                    <div className="form-group">
                        <label>Kurzszenen-Grenze (s)</label>
                        <input
                            type="number" min="0.5" step="0.5"
                            value={params.short_scene_s}
                            onChange={e => setParams({ ...params, short_scene_s: parseFloat(e.target.value) })}
                        />
                    </div>
                </div>
            </div>

            <div className="btn-row">
                <button
                    className="btn btn-primary"
                    onClick={handleRunImages}
                    disabled={jobData?.status === 'running'}
                >
                    ▶ Bilder extrahieren
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
