import React, { useState, useEffect } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepPrompts() {
    const { currentStep, setCurrentStep, markStepDone } = useJob();

    const [params, setParams] = useState({
        system_prompt: "",
        user_prompt: "",
        ad_rules: "",
        few_shots: "",
        model: "gpt-4o",
        temperature: 0.2,
        max_tokens: 1024,
        detail: "low",
        cut: "broadcast"
    });

    useEffect(() => {
        // Fetch default prompts from server on mount
        fetch('/api/system_info')
            .then(res => res.json())
            .then(data => {
                if (data.default_prompts) {
                    setParams(p => ({
                        ...p,
                        system_prompt: data.default_prompts.system_instruction || p.system_prompt,
                        user_prompt: data.default_prompts.user_instruction || p.user_prompt,
                        ad_rules: data.default_prompts.ad_rules || p.ad_rules,
                        few_shots: data.default_prompts.few_shots || p.few_shots
                    }));
                }
            })
            .catch(console.error);
    }, []);

    if (currentStep !== 5) return null;

    const handleNext = () => {
        // Just navigate to the next step, there is no backend action yet
        // The generation happens in step 6
        // We save the prompts state simply by keeping the component alive or storing it in job context?
        // Actually, we need to pass these params to StepGenerate. 
        // To make it easy, we will dispatch an event or store it in context. Let's add it to a window object for now or lift state.
        // For React structure, passing via Context is best. Let's add a setGptParams to Context later, or just keep it simple.

        // Quick hack: dispatch custom event with params so StepGenerate can pick them up 
        // (A better way is adding `gptParams` to `JobContext`)
        window.dispatchEvent(new CustomEvent('gpt-params-updated', { detail: params }));
        markStepDone(5);
        setCurrentStep(6);
    };

    return (
        <div className="step-content">
            <div className="step-header">
                <div className="step-icon">⚙️</div>
                <div>
                    <h2>Prompts & GPT-Konfiguration</h2>
                    <p>Definiere System-Instruktion, User-Instruktion, AD-Regeln und Modell-Parameter.</p>
                </div>
            </div>

            <div className="card">
                <p className="card-title">System-Instruktion (Rolle & Grundregeln)</p>
                <div className="form-group">
                    <textarea
                        rows="4"
                        placeholder="Du bist ein professioneller Audiodeskriptions-Autor…"
                        value={params.system_prompt}
                        onChange={e => setParams({ ...params, system_prompt: e.target.value })}
                    />
                </div>
            </div>

            <div className="card">
                <p className="card-title">User-Instruktion (Aufgabe & Format)</p>
                <div className="form-group">
                    <textarea
                        rows="3"
                        placeholder="Erstelle eine präzise Audiodeskription für die folgenden Szenenbilder…"
                        value={params.user_prompt}
                        onChange={e => setParams({ ...params, user_prompt: e.target.value })}
                    />
                </div>
            </div>

            <div className="card">
                <p className="card-title">AD-Regeln</p>
                <div className="form-group">
                    <textarea
                        rows="4"
                        placeholder="1. Beschreibe Handlungen im Präsens…"
                        value={params.ad_rules}
                        onChange={e => setParams({ ...params, ad_rules: e.target.value })}
                    />
                </div>
            </div>

            <div className="card">
                <p className="card-title">Few-Shots (optional)</p>
                <div className="form-group">
                    <textarea
                        rows="3"
                        placeholder="Beispiel 1: …"
                        value={params.few_shots}
                        onChange={e => setParams({ ...params, few_shots: e.target.value })}
                    />
                </div>
            </div>

            <div className="card">
                <p className="card-title">GPT-Modell & Parameter</p>
                <div className="form-grid">
                    <div className="form-group">
                        <label>Modell</label>
                        <select value={params.model} onChange={e => setParams({ ...params, model: e.target.value })}>
                            <option value="gpt-4o">gpt-4o</option>
                            <option value="gpt-4o-mini">gpt-4o-mini</option>
                        </select>
                    </div>
                    <div className="form-group">
                        <label>Temperature: {params.temperature}</label>
                        <input
                            type="range" min="0" max="1.5" step="0.05"
                            value={params.temperature}
                            onChange={e => setParams({ ...params, temperature: parseFloat(e.target.value) })}
                        />
                    </div>
                    <div className="form-group">
                        <label>Max. Tokens</label>
                        <input
                            type="number" min="64" step="64"
                            value={params.max_tokens}
                            onChange={e => setParams({ ...params, max_tokens: parseInt(e.target.value) })}
                        />
                    </div>
                    <div className="form-group">
                        <label>Cut-Typ</label>
                        <select value={params.cut} onChange={e => setParams({ ...params, cut: e.target.value })}>
                            <option value="broadcast">Broadcast (Silbenlimit)</option>
                            <option value="directors">Director's Cut (ausführlich)</option>
                        </select>
                    </div>
                </div>
            </div>

            <div className="btn-row">
                <button className="btn btn-primary" onClick={handleNext}>
                    Weiter → Generierung →
                </button>
            </div>
        </div>
    );
}
