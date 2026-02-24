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
        <div className="flex flex-col gap-5">
            <div className="flex items-start gap-4 pb-4 border-b border-border-subtle">
                <div className="text-3xl leading-none">📁</div>
                <div>
                    <h2 className="text-[1.4rem] font-bold mb-1">Video hochladen</h2>
                    <p className="text-sm text-text-secondary">Wähle eine MP4-Datei zum Starten der Pipeline.</p>
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                <div
                    className="border-2 border-dashed border-border-subtle rounded-2xl p-12 text-center cursor-pointer transition-all relative hover:border-violet-500 hover:bg-violet-500/5 group"
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
                    <div className="text-[3rem] mb-3">🎞️</div>
                    <p className="text-[1.1rem] font-semibold mb-1">MP4 per Drag & Drop hier ablegen</p>
                    <p className="text-sm text-text-secondary">oder klicken zum Auswählen</p>
                </div>

                {uploading && (
                    <div className="mt-4">
                        <div className="flex flex-col gap-2">
                            <div className="h-1.5 bg-border-subtle rounded-full overflow-hidden">
                                <div className="h-full bg-gradient-to-r from-violet-500 to-teal-500 rounded-full transition-all duration-400 relative overflow-hidden" style={{ width: `${progress}%` }}>
                                    <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/25 to-transparent animate-[shimmer_1.4s_infinite]"></div>
                                </div>
                            </div>
                            <span className="text-xs text-text-secondary">Uploading… {progress}%</span>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
