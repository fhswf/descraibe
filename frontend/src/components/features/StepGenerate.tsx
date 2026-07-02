import React from 'react';
import { useJob } from '../../hooks/useJob';

export function StepGenerate(): React.ReactElement | null {
    const { currentStep, gptParams } = useJob();

    if (currentStep !== 5) return null;

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-start justify-between gap-4 pb-4 border-b border-border-subtle">
                <div className="flex gap-4">
                    <div className="text-3xl leading-none">🤖</div>
                    <div>
                        <h2 className="text-[1.4rem] font-bold mb-1">Audiodeskriptionen generieren</h2>
                        <p className="text-sm text-text-secondary">GPT beschreibt jeden AD-Slot basierend auf Szenenbildern und deinen Prompts.</p>
                    </div>
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md" id="gpt-config-preview">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Konfigurationsübersicht</p>
                {gptParams ? (
                    <div className="text-sm">
                        <p><strong>Modell:</strong> {gptParams.model}</p>
                        <p><strong>Cut:</strong> {gptParams.cut}</p>
                    </div>
                ) : <p className="text-sm text-text-secondary">Gehe in die Konfiguration (Zahnrad) um Modell und Prompts zu setzen.</p>}
            </div>
        </div>
    );
}
