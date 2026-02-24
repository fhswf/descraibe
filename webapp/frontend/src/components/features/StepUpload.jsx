import React, { useRef, useState } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepUpload() {
    const { jobId, createJob, fetchJobData, currentStep } = useJob();
    const fileInputRef = useRef(null);
    const [uploading, setUploading] = useState(false);
    const [progress, setProgress] = useState(0);

    if (currentStep !== 0) return null;

    const handleUpload = async (file) => {
        setUploading(true);
        setProgress(0);

        // Create job if none exists
        let activeJobId = jobId;
        if (!activeJobId) {
            activeJobId = await createJob();
        }

        const CHUNK_SIZE = 5 * 1024 * 1024;
        const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

        for (let i = 0; i < totalChunks; i++) {
            const start = i * CHUNK_SIZE;
            const end = Math.min(file.size, start + CHUNK_SIZE);
            const chunk = file.slice(start, end);

            const formData = new FormData();
            formData.append('filename', file.name);
            formData.append('chunkIndex', i);
            formData.append('totalChunks', totalChunks);
            formData.append('chunk', chunk);

            try {
                const res = await fetch(`/api/jobs/${activeJobId}/video`, {
                    method: 'POST',
                    body: formData
                });

                if (!res.ok) throw new Error("Upload failed");

                const data = await res.json();
                setProgress(Math.round(((i + 1) / totalChunks) * 100));

                if (data.complete) {
                    await fetchJobData(activeJobId);
                }
            } catch (err) {
                console.error(err);
                alert("Upload error: " + err.message);
                break;
            }
        }

        setUploading(false);
    };

    return (
        <div className="step-content">
            <div className="step-header">
                <div className="step-icon">📁</div>
                <div>
                    <h2>Video hochladen</h2>
                    <p>Wähle eine MP4-Datei zum Starten der Pipeline.</p>
                </div>
            </div>

            <div className="card">
                <div
                    className="drop-zone"
                    onClick={() => fileInputRef.current?.click()}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                        e.preventDefault();
                        if (e.dataTransfer.files?.[0]) handleUpload(e.dataTransfer.files[0]);
                    }}
                >
                    <input
                        type="file"
                        ref={fileInputRef}
                        accept="video/mp4,video/*"
                        style={{ display: 'none' }}
                        onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
                    />
                    <div className="drop-icon">🎞️</div>
                    <p className="drop-title">MP4 per Drag & Drop hier ablegen</p>
                    <p className="drop-sub">oder klicken zum Auswählen</p>
                </div>

                {uploading && (
                    <div className="upload-progress" style={{ marginTop: '16px' }}>
                        <div className="progress-wrap">
                            <div className="progress-bar-bg">
                                <div className="progress-bar-fill" style={{ width: `${progress}%` }}></div>
                            </div>
                            <span className="progress-msg">Uploading… {progress}%</span>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
