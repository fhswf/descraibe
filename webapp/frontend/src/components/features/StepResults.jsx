import React from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepResults() {
    const { jobId, jobData, currentStep } = useJob();

    if (currentStep !== 7) return null;

    const paths = jobData?.output_paths || {};

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-start gap-4 pb-4 border-b border-border-subtle">
                <div className="text-3xl leading-none">📥</div>
                <div>
                    <h2 className="text-[1.4rem] font-bold mb-1">Ergebnisse & Download</h2>
                    <p className="text-sm text-text-secondary">Lade alle erzeugten Audiodeskriptions-Dateien herunter.</p>
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Ausgabedateien</p>
                <div className="flex flex-col gap-2">
                    {Object.entries(paths).map(([key, filename]) => (
                        <a
                            key={key}
                            href={`/api/jobs/${jobId}/downloads/${key}`}
                            target="_blank"
                            rel="noreferrer"
                            className="flex items-center gap-3 px-4 py-3 bg-white/5 border border-border-subtle rounded-md no-underline text-text-primary transition-all hover:border-violet-500 hover:bg-violet-500/5 hover:text-violet-500"
                        >
                            <span className="text-[1.2rem]">📄</span>
                            <div className="flex-1">
                                <div className="text-[0.875rem] font-medium">{key}</div>
                                <div className="text-[0.75rem] text-text-muted">{filename}</div>
                            </div>
                        </a>
                    ))}
                    {Object.keys(paths).length === 0 && <p className="text-sm text-text-secondary">Noch keine Ausgabedateien vorhanden.</p>}
                </div>
            </div>
        </div>
    );
}
