import { useJob } from '../../hooks/useJob.jsx';

type StepName = keyof typeof stepLabels;

const stepLabels = {
    upload: 'Video hochladen',
    vad: 'Sprechpausen erkennen',
    transcribe: 'Transkription',
    slots: 'AD-Slots generieren',
    images: 'Bilder extrahieren',
    gpt: 'Beschreibungen generieren'
} as const;

export function GlobalProgress() {
    const { progressData } = useJob();

    const activeEntries = Object.entries(progressData ?? {}).filter(([, data]) => data !== null) as [StepName, { msg: string; percent: number }][];

    if (activeEntries.length === 0) return null;

    const [stepName, progress] = activeEntries[0] ?? ['gpt', { msg: '', percent: 0 }];

    const label = stepLabels[stepName] ?? 'Fortschritt';

    return (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 w-full max-w-md z-50 animate-in fade-in slide-in-from-bottom-4 duration-300">
            <div className="bg-bg-card border border-violet-500/30 shadow-[0_8px_32px_rgba(139,92,246,0.25)] rounded-2xl p-5 backdrop-blur-md">
                <div className="flex justify-between items-center mb-3.5">
                    <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider">{label}</p>
                    <span className="text-xs font-mono font-bold text-violet-400">{progress.percent}%</span>
                </div>
                <div className="flex flex-col gap-2">
                    <div className="h-1.5 bg-border-subtle rounded-full overflow-hidden">
                        <div
                            className="h-full bg-gradient-to-r from-violet-500 to-teal-500 rounded-full transition-all duration-400 relative overflow-hidden"
                            style={{ width: `${progress.percent}%` }}
                        >
                            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/25 to-transparent animate-[shimmer_1.4s_infinite]"></div>
                        </div>
                    </div>
                    <span className="text-xs text-text-secondary truncate">{progress.msg}</span>
                </div>
            </div>
        </div>
    );
}
