import React, { useState, useEffect } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepGenerate() {
    const { jobId, jobData, currentStep } = useJob();
    const [gptParams, setGptParams] = useState(null);

    useEffect(() => {
                if (window._gptParams) setGptParams(window._gptParams);
        const handler = (e) => setGptParams(e.detail);
        window.addEventListener('gpt-params-updated', handler);
        return () => window.removeEventListener('gpt-params-updated', handler);
    }, []);

    if (currentStep !== 6) return null;

    const handleRunGPT = async () => {
        if (!gptParams) return alert("Prompts fehlen. Bitte zurück zu Schritt 5 gehen.");

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

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-start gap-4 pb-4 border-b border-border-subtle">
                <div className="text-3xl leading-none">🤖</div>
                <div>
                    <h2 className="text-[1.4rem] font-bold mb-1">Audiodeskriptionen generieren</h2>
                    <p className="text-sm text-text-secondary">GPT beschreibt jeden AD-Slot basierend auf Szenenbildern und deinen Prompts.</p>
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md" id="gpt-config-preview">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Konfigurationsübersicht</p>
                {gptParams ? (
                    <div className="text-sm">
                        <p><strong>Modell:</strong> {gptParams.model}</p>
                        <p><strong>Cut:</strong> {gptParams.cut}</p>
                    </div>
                ) : <p className="text-sm text-text-secondary">Gehe zurück zu Schritt 5 um die Konfiguration zu setzen.</p>}
            </div>

            <div className="flex gap-2.5 items-center flex-wrap">
                <button
                    className="inline-flex items-center gap-2 px-7 py-3.5 rounded-[10px] font-semibold text-[1rem] transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-gradient-to-br from-violet-500 to-[#7c3aed] text-white shadow-[0_4px_16px_rgba(139,92,246,0.3)] hover:not:disabled:shadow-[0_6px_24px_rgba(139,92,246,0.45)] hover:not:disabled:-translate-y-px"
                    onClick={handleRunGPT}
                    disabled={jobData?.status === 'running'}
                >
                    🚀 Beschreibungen generieren
                </button>
            </div>
        </div>
    );
}
