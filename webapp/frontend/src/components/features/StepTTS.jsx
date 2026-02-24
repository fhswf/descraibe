import React, { useState } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepTTS() {
    const { jobId, jobData, currentStep } = useJob();
    const [apiKey, setApiKey] = useState('');
    const [voice, setVoice] = useState('alloy');
    const [duckingVolume, setDuckingVolume] = useState('0.4');

    if (currentStep !== 7) return null;

    const handleRunTTS = async () => {
        const payload = {
            api_key: apiKey,
            voice,
            ducking_volume: parseFloat(duckingVolume)
        };

        try {
            const res = await fetch(`/api/jobs/${jobId}/tts`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!res.ok) {
                const body = await res.json();
                throw new Error(body.error || "Failed to start TTS");
            }
        } catch (err) {
            alert("Error: " + err.message);
        }
    };

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-start gap-4 pb-4 border-b border-border-subtle">
                <div className="text-3xl leading-none">🎙️</div>
                <div>
                    <h2 className="text-[1.4rem] font-bold mb-1">Vertonung (TTS & Export)</h2>
                    <p className="text-sm text-text-secondary">Generiert Sprache aus den Texten und mixt sie mit dem Originalvideo.</p>
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Einstellungen</p>
                <div className="flex flex-col gap-4">
                    <div className="flex flex-col gap-1.5">
                        <label className="text-sm font-medium text-text-primary">OpenAI API-Key (Optional wenn im Backend gesetzt)</label>
                        <input
                            type="password"
                            value={apiKey}
                            onChange={(e) => setApiKey(e.target.value)}
                            className="bg-bg-surface border border-border-subtle rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-violet-500"
                            placeholder="sk-..."
                        />
                    </div>

                    <div className="flex flex-col gap-1.5">
                        <label className="text-sm font-medium text-text-primary">Stimme</label>
                        <select
                            value={voice}
                            onChange={(e) => setVoice(e.target.value)}
                            className="bg-bg-surface border border-border-subtle rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-violet-500"
                        >
                            <option value="alloy">Alloy (Männlich, neutral)</option>
                            <option value="echo">Echo (Männlich, warm)</option>
                            <option value="fable">Fable (Männlich, erzählend)</option>
                            <option value="onyx">Onyx (Männlich, tief)</option>
                            <option value="nova">Nova (Weiblich, lebhaft)</option>
                            <option value="shimmer">Shimmer (Weiblich, ruhig)</option>
                        </select>
                    </div>

                    <div className="flex flex-col gap-1.5">
                        <label className="text-sm font-medium text-text-primary">Hintergrund-Lautstärke (0.0 - 1.0)</label>
                        <input
                            type="number"
                            step="0.1"
                            min="0"
                            max="1"
                            value={duckingVolume}
                            onChange={(e) => setDuckingVolume(e.target.value)}
                            className="bg-bg-surface border border-border-subtle rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-violet-500"
                        />
                        <p className="text-[0.75rem] text-text-muted">Die Originaltonspur wird während der gesamten Wiedergabe auf diesen Wert reduziert.</p>
                    </div>
                </div>
            </div>

            <button
                className="inline-flex justify-center items-center gap-2 px-7 py-3.5 rounded-[10px] font-semibold text-[1rem] transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-gradient-to-br from-violet-500 to-[#7c3aed] text-white shadow-[0_4px_16px_rgba(139,92,246,0.3)] hover:not:disabled:shadow-[0_6px_24px_rgba(139,92,246,0.45)] hover:not:disabled:-translate-y-px"
                onClick={handleRunTTS}
                disabled={jobData?.status === 'running'}
            >
                🎬 Audiodatei erstellen & Exportieren
            </button>
        </div>
    );
}
