import React, { useState } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepTranscribe() {
    const { jobId, jobData, currentStep, progressData } = useJob();

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

    const progress = progressData?.transcribe;

    return (
        <div className="step-content">
            <div className="step-header">
                <div className="step-icon">📝</div>
                <div>
                    <h2>Transkription</h2>
                    <p>Faster-Whisper transkribiert die Sprache im Video.</p>
                </div>
            </div>

            <div className="card">
                <p className="card-title">Modell & Optionen</p>
                <div className="form-grid">
                    <div className="form-group">
                        <label>Whisper Modell</label>
                        <select
                            value={params.model_size}
                            onChange={e => setParams({ ...params, model_size: e.target.value })}
                        >
                            <option value="large-v3">large-v3 (beste Qualität)</option>
                            <option value="medium">medium</option>
                            <option value="small">small (schnell)</option>
                        </select>
                    </div>
                    <div className="form-group">
                        <label>Sprache</label>
                        <select
                            value={params.language}
                            onChange={e => setParams({ ...params, language: e.target.value })}
                        >
                            <option value="de">Deutsch</option>
                            <option value="en">Englisch</option>
                        </select>
                    </div>
                    <div className="form-group">
                        <label>Faster-Whisper VAD</label>
                        <select
                            value={params.use_fw_vad.toString()}
                            onChange={e => setParams({ ...params, use_fw_vad: e.target.value === 'true' })}
                        >
                            <option value="true">Ja</option>
                            <option value="false">Nein</option>
                        </select>
                    </div>
                </div>
            </div>

            <div className="card">
                <p className="card-title">Oder: Vorhandenes Transkript hochladen</p>
                <div className="btn-row">
                    <label className="btn btn-secondary" style={{ cursor: 'pointer' }}>
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

            <div className="btn-row">
                <button
                    className="btn btn-primary"
                    onClick={handleRunTranscribe}
                    disabled={jobData?.status === 'running'}
                >
                    ▶ Transkription starten
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
