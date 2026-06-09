import React from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepVAD() {
    const { currentStep } = useJob();

    if (currentStep !== 1) return null;

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-start justify-between gap-4 pb-4 border-b border-border-subtle">
                <div className="flex gap-4">
                    <div className="text-3xl leading-none">🔇</div>
                    <div>
                        <h2 className="text-[1.4rem] font-bold mb-1">Sprechpausen (VAD)</h2>
                        <p className="text-sm text-text-secondary">Erkenne Sprach- und Stimmphasen im Audio.</p>
                    </div>
                </div>
            </div>
        </div>
    );
}
