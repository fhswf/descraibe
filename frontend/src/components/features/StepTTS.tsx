import React from 'react';
import { useJob } from '../../hooks/useJob';

export function StepTTS(): React.ReactElement | null {
    const { currentStep, ttsParams } = useJob();

    if (currentStep !== 6) return null;

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-start justify-between gap-4 pb-4 border-b border-border-subtle">
                <div className="flex gap-4">
                    <div className="text-3xl leading-none">🎙️</div>
                    <div>
                        <h2 className="text-[1.4rem] font-bold mb-1">Vertonung (TTS)</h2>
                        <p className="text-sm text-text-secondary">Generiere Audio-Sprachspuren aus den Text-Deskriptionen und mische sie ab.</p>
                    </div>
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-2">TTS Konfiguration</p>
                {!ttsParams.apiKey ? (
                    <p className="text-sm text-red-400 mb-0">OpenAI API Key fehlt! Bitte in der Konfiguration eintragen.</p>
                ) : (
                    <div className="text-sm text-text-muted">
                        Bereit. (Voice: {ttsParams.voice}, Ducking: {ttsParams.duckingVolume})
                    </div>
                )}
            </div>
        </div>
    );
}
