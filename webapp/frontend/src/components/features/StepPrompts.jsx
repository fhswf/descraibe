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
        <div className="flex flex-col gap-5">
            <div className="flex items-start gap-4 pb-4 border-b border-border-subtle">
                <div className="text-3xl leading-none">⚙️</div>
                <div>
                    <h2 className="text-[1.4rem] font-bold mb-1">Prompts & GPT-Konfiguration</h2>
                    <p className="text-sm text-text-secondary">Definiere System-Instruktion, User-Instruktion, AD-Regeln und Modell-Parameter.</p>
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">System-Instruktion (Rolle & Grundregeln)</p>
                <div className="flex flex-col gap-1.5">
                    <textarea
                        rows="4"
                        placeholder="Du bist ein professioneller Audiodeskriptions-Autor…"
                        value={params.system_prompt}
                        onChange={e => setParams({ ...params, system_prompt: e.target.value })}
                        className="resize-y min-h-[100px] bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                    />
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">User-Instruktion (Aufgabe & Format)</p>
                <div className="flex flex-col gap-1.5">
                    <textarea
                        rows="3"
                        placeholder="Erstelle eine präzise Audiodeskription für die folgenden Szenenbilder…"
                        value={params.user_prompt}
                        onChange={e => setParams({ ...params, user_prompt: e.target.value })}
                        className="resize-y min-h-[100px] bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                    />
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">AD-Regeln</p>
                <div className="flex flex-col gap-1.5">
                    <textarea
                        rows="4"
                        placeholder="1. Beschreibe Handlungen im Präsens…"
                        value={params.ad_rules}
                        onChange={e => setParams({ ...params, ad_rules: e.target.value })}
                        className="resize-y min-h-[100px] bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                    />
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Few-Shots (optional)</p>
                <div className="flex flex-col gap-1.5">
                    <textarea
                        rows="3"
                        placeholder="Beispiel 1: …"
                        value={params.few_shots}
                        onChange={e => setParams({ ...params, few_shots: e.target.value })}
                        className="resize-y min-h-[100px] bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                    />
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">GPT-Modell & Parameter</p>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Modell</label>
                        <select value={params.model} onChange={e => setParams({ ...params, model: e.target.value })} className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15">
                            <option value="gpt-4o">gpt-4o</option>
                            <option value="gpt-4o-mini">gpt-4o-mini</option>
                        </select>
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Temperature: {params.temperature}</label>
                        <input
                            type="range" min="0" max="1.5" step="0.05"
                            value={params.temperature}
                            onChange={e => setParams({ ...params, temperature: parseFloat(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15 accent-violet-500 pr-0 pl-0 py-0"
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Max. Tokens</label>
                        <input
                            type="number" min="64" step="64"
                            value={params.max_tokens}
                            onChange={e => setParams({ ...params, max_tokens: parseInt(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15"
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Cut-Typ</label>
                        <select value={params.cut} onChange={e => setParams({ ...params, cut: e.target.value })} className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15">
                            <option value="broadcast">Broadcast (Silbenlimit)</option>
                            <option value="directors">Director's Cut (ausführlich)</option>
                        </select>
                    </div>
                </div>
            </div>

            <div className="flex gap-2.5 items-center flex-wrap">
                <button className="inline-flex items-center gap-2 px-5 py-2.5 rounded-[10px] font-semibold text-[0.875rem] transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-gradient-to-br from-violet-500 to-[#7c3aed] text-white shadow-[0_4px_16px_rgba(139,92,246,0.3)] hover:not:disabled:shadow-[0_6px_24px_rgba(139,92,246,0.45)] hover:not:disabled:-translate-y-px" onClick={handleNext}>
                    Weiter → Generierung →
                </button>
            </div>
        </div>
    );
}
