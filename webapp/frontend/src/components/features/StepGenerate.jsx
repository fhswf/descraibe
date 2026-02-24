import React, { useState, useEffect } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepGenerate() {
    const { jobId, jobData, currentStep, progressData } = useJob();
    const [gptParams, setGptParams] = useState(null);

    useEffect(() => {
        const handler = (e) => setGptParams(e.detail);
        window.addEventListener('gpt-params-updated', handler);
        return () => window.removeEventListener('gpt-params-updated', handler);
    }, []);

    if (currentStep !== 6) return null;

    const handleRunGPT = async () => {
        if (!gptParams) return alert("Prompts missing. Please go back to step 6.");

        // Assemble system prompt exactly the way the backend auto-loader works
        let system_final = gptParams.system_prompt;
        if (gptParams.ad_rules) {
            system_final += "\n\n# Audiodeskription – Regeln\n" + gptParams.ad_rules;
        }
        if (gptParams.few_shots) {
            system_final += "\n\n# Few-Shots / Beispiele\n" + gptParams.few_shots;
        }

        const payload = {
            model: gptParams.model,
            temperature: gptParams.temperature,
            max_tokens: gptParams.max_tokens,
            cut: gptParams.cut,
            system_prompt: system_final,
            user_prompt: gptParams.user_prompt || "Erstelle eine AD für diese Frames.",
        };

        try {
            const res = await fetch(`/api/jobs/${jobId}/gpt`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!res.ok) {
                const body = await res.json();
                throw new Error(body.error || "Failed to start GPT generation");
            }
        } catch (err) {
            alert("Error: " + err.message);
        }
    };

    const progress = progressData?.gpt;

    return (
        <div className="step-content">
            <div className="step-header">
                <div className="step-icon">🤖</div>
                <div>
                    <h2>Audiodeskriptionen generieren</h2>
                    <p>GPT beschreibt jeden AD-Slot basierend auf Szenenbildern und deinen Prompts.</p>
                </div>
            </div>

            <div className="card" id="gpt-config-preview">
                <p className="card-title">Konfigurationsübersicht</p>
                {gptParams ? (
                    <div>
                        <p><strong>Modell:</strong> {gptParams.model}</p>
                        <p><strong>Cut:</strong> {gptParams.cut}</p>
                    </div>
                ) : <p>Gehe zurück zu Schritt 6 um die Config zu setzen.</p>}
            </div>

            <div className="btn-row">
                <button
                    className="btn btn-primary"
                    style={{ fontSize: '1rem', padding: '14px 28px' }}
                    onClick={handleRunGPT}
                    disabled={jobData?.status === 'running'}
                >
                    🚀 Beschreibungen generieren
                </button>
            </div>

            {progress && (
                <div className="card">
                    <p className="card-title">Fortschritt</p>
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
