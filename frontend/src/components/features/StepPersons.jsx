import React from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function StepPersons() {
    const { currentStep, jobData, handleRunPersons, progressData } = useJob();

    if (currentStep !== 5) return null;

    const personsCount = jobData?.persons_count || 0;
    const isRunning = progressData?.persons !== null && progressData?.persons !== undefined;
    const progressMsg = progressData?.persons?.msg || null;
    const progressPercent = progressData?.persons?.percent || null;

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-start justify-between gap-4 pb-4 border-b border-border-subtle">
                <div className="flex gap-4">
                    <div className="text-3xl leading-none">👤</div>
                    <div>
                        <h2 className="text-[1.4rem] font-bold mb-1">Personenanalyse</h2>
                        <p className="text-sm text-text-secondary">
                            Erkennt Personen in den extrahierten Frames mittels Gesichtsdetektion und OCR-basierter Namenserkennung (Bauchbinden).
                        </p>
                    </div>
                </div>
            </div>

            {/* Status section */}
            <div className="flex flex-col gap-3">
                {isRunning && (
                    <div className="flex items-center gap-3 p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                        <div className="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
                        <div className="flex-1">
                            <div className="text-sm font-medium text-amber-300">
                                {progressMsg || 'Personen werden analysiert...'}
                            </div>
                            {progressPercent !== null && (
                                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-bg-card border border-border-subtle">
                                    <div
                                        className="h-full bg-amber-400 transition-all"
                                        style={{ width: `${progressPercent}%` }}
                                    ></div>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* Results section */}
                {personsCount > 0 && !isRunning && (
                    <div className="flex flex-col gap-2 p-4 bg-green-500/10 border border-green-500/20 rounded-lg">
                        <div className="flex items-center gap-2">
                            <span className="material-icons-round text-green-500 text-lg">check_circle</span>
                            <span className="text-sm font-medium text-green-300">
                                {personsCount} {personsCount === 1 ? 'Person' : 'Personen'} erkannt
                            </span>
                        </div>
                    </div>
                )}

                {/* Action button */}
                {!isRunning && (
                    <button
                        className="flex items-center gap-2 self-start px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
                        onClick={handleRunPersons}
                        disabled={!jobData?.images_count}
                    >
                        <span className="material-icons-round text-lg">search</span>
                        Personen analysieren
                    </button>
                )}

                {!jobData?.images_count && !isRunning && (
                    <p className="text-xs text-text-muted">
                        Bitte führen Sie zuerst die Bilder-Extraktion durch.
                    </p>
                )}
            </div>

            {/* Info section */}
            <div className="flex flex-col gap-2 p-4 bg-bg-card border border-border-subtle rounded-lg">
                <h3 className="text-sm font-semibold">Was wird analysiert?</h3>
                <ul className="text-xs text-text-secondary space-y-1.5">
                    <li className="flex items-start gap-2">
                        <span className="material-icons-round text-[0.875rem] text-violet-400 shrink-0 mt-0.5">face</span>
                        <span>Gesichtserkennung mit OpenCV DNN (YuNet) für Personenidentifikation</span>
                    </li>
                    <li className="flex items-start gap-2">
                        <span className="material-icons-round text-[0.875rem] text-violet-400 shrink-0 mt-0.5">description</span>
                        <span>OCR-basierte Erkennung von Bauchbinden/Nameoverlays</span>
                    </li>
                    <li className="flex items-start gap-2">
                        <span className="material-icons-round text-[0.875rem] text-violet-400 shrink-0 mt-0.5">palette</span>
                        <span>Extraktion visueller Attribute (Kleidungsfarben)</span>
                    </li>
                    <li className="flex items-start gap-2">
                        <span className="material-icons-round text-[0.875rem] text-violet-400 shrink-0 mt-0.5">sync_alt</span>
                        <span>Personen-Tracking über mehrere Frames hinweg</span>
                    </li>
                </ul>
            </div>
        </div>
    );
}