import React from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepImages() {
    const { currentStep } = useJob();

    if (currentStep !== 4) return null;

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-start justify-between gap-4 pb-4 border-b border-border-subtle">
                <div className="flex gap-4">
                    <div className="text-3xl leading-none">🖼️</div>
                    <div>
                        <h2 className="text-[1.4rem] font-bold mb-1">Bilder extrahieren</h2>
                        <p className="text-sm text-text-secondary">SceneDetect identifiziert Szenen und extrahiert repräsentative Frames für jeden AD-Slot.</p>
                    </div>
                </div>
            </div>
        </div>
    );
}
