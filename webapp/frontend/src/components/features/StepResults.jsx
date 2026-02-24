import React from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepResults() {
    const { jobId, jobData, currentStep } = useJob();

    if (currentStep !== 7) return null;

    const paths = jobData?.output_paths || {};

    return (
        <div className="step-content">
            <div className="step-header">
                <div className="step-icon">📥</div>
                <div>
                    <h2>Ergebnisse & Download</h2>
                    <p>Lade alle erzeugten Audiodeskriptions-Dateien herunter.</p>
                </div>
            </div>

            <div className="card">
                <p className="card-title">Ausgabedateien</p>
                <div className="download-list">
                    {Object.entries(paths).map(([key, filename]) => (
                        <a
                            key={key}
                            href={`/api/jobs/${jobId}/downloads/${key}`}
                            target="_blank"
                            rel="noreferrer"
                            className="download-link"
                            style={{ display: 'block', margin: '8px 0', textDecoration: 'none', color: '#3b82f6' }}
                        >
                            📄 {key} ({filename})
                        </a>
                    ))}
                    {Object.keys(paths).length === 0 && <p>Noch keine Ausgabedateien vorhanden.</p>}
                </div>
            </div>
        </div>
    );
}
