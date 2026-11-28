import { useEffect, useState } from 'react';
import { useJob } from '../../hooks/useJob.jsx';
import type { ProgressEntry } from '../../types';

type StepName = keyof typeof stepLabels;

const stepLabels = {
    upload: 'Video hochladen',
    vad: 'Sprechpausen erkennen',
    transcribe: 'Transkription',
    slots: 'AD-Slots generieren',
    images: 'Bilder extrahieren',
    gpt: 'Beschreibungen generieren',
    tracking: 'Personen tracken',
    identities: 'Personen zuordnen',
    attributes: 'Personenattribute'
} as const;

const phaseLabels: Record<string, string> = {
    models: 'Modelle laden', scenes: 'Szenen verarbeiten', decode: 'Videoframes lesen',
    embeddings: 'Gesichter erkennen', distance_matrix: 'Track-Ähnlichkeiten',
    cluster_merges: 'Personen gruppieren', clustering: 'Clustering',
    fallback: 'Fallback-Bilder', selection: 'Bilder auswählen', person_attributes: 'Personen auswerten',
    merge: 'Ergebnisse zusammenführen', publishing: 'Ergebnisse speichern', complete: 'Abgeschlossen',
    cancelling: 'Abbrechen', cancelled: 'Abgebrochen'
};

export function GlobalProgress() {
    const { jobId, progressData, setProgressData } = useJob();
    const [cancelPending, setCancelPending] = useState(false);
    const [cancelError, setCancelError] = useState('');
    const [hiddenStep, setHiddenStep] = useState<string | null>(null);

    const entries = Object.entries(progressData ?? {}).filter(([, data]) => data !== null) as [string, ProgressEntry][];
    const activeEntries = entries.filter(([, data]) => data.status !== 'cancelled');
    const selectedEntry = activeEntries[0] ?? entries[entries.length - 1];
    const stepName = selectedEntry?.[0];
    const progress = selectedEntry?.[1];

    useEffect(() => {
        if (!stepName || progress?.status !== 'cancelled') return;
        const timeout = window.setTimeout(() => {
            setProgressData(prev => prev[stepName]?.status === 'cancelled'
                ? { ...prev, [stepName]: null }
                : prev);
        }, 5000);
        return () => window.clearTimeout(timeout);
    }, [stepName, progress?.status, setProgressData]);

    useEffect(() => {
        if (!progress || (hiddenStep && hiddenStep !== stepName)) setHiddenStep(null);
    }, [progress, hiddenStep, stepName]);

    const isComplete = Boolean(progress && progress.status !== 'cancelled' && progress.status !== 'cancelling'
        && progress.phase === 'complete');
    useEffect(() => {
        if (!stepName || !progress || !isComplete) return;
        const timeout = window.setTimeout(() => {
            setProgressData(prev => {
                const current = prev[stepName];
                if (!current || current.run_id !== progress.run_id) return prev;
                return current.phase === 'complete' ? { ...prev, [stepName]: null } : prev;
            });
        }, 1500);
        return () => window.clearTimeout(timeout);
    }, [stepName, progress, isComplete, setProgressData]);

    if (!stepName || !progress || hiddenStep === stepName) return null;

    const label = stepLabels[stepName as StepName] ?? 'Fortschritt';
    const workers = progress.workers;
    const task = progress.current_task;
    const taskSummary = task?.person_id !== undefined
        ? `Person ${task.person_id}`
        : task?.frame_number !== undefined
            ? `${task.id?.startsWith('scene-') ? `Szene ${task.id.slice(6)} · ` : ''}Frame ${task.frame_number}`
            : task?.id ?? '';
    const phaseSummary = [
        progress.phase ? phaseLabels[progress.phase] ?? progress.phase : '',
        taskSummary
    ].filter(Boolean).join(' · ');
    const completed = progress.completed ?? progress.current;
    const throughput = completed != null && progress.elapsed_seconds != null && progress.elapsed_seconds > 0
        ? completed / progress.elapsed_seconds
        : null;
    const throughputUnit = progress.unit === 'tracking_frames' ? 'Frames/s'
        : progress.unit === 'faces' ? 'Gesichter/s'
            : progress.unit === 'people' ? 'Personen/s'
                : progress.unit === 'scenes' ? 'Szenen/s'
                    : '/s';
    const pipeline = progress.pipeline;
    const cpuText = pipeline?.cpu_utilization_latest_pct != null
        ? `CPU (Server) ${pipeline.cpu_utilization_latest_pct.toFixed(0)}%`
        : pipeline?.cpu_utilization_status === 'sampling' ? 'CPU wird gemessen …'
            : pipeline?.cpu_utilization_status ? 'CPU nicht verfügbar' : '';
    const gpuText = pipeline?.gpu_utilization_latest_pct != null
        ? `GPU ${pipeline.gpu_utilization_latest_pct.toFixed(0)}%`
        : pipeline?.gpu_utilization_status === 'sampling' ? 'GPU wird gemessen …'
            : pipeline?.gpu_utilization_status === 'model_on_cpu' ? 'GPU nicht verwendet'
                : pipeline?.gpu_utilization_status ? 'GPU nicht verfügbar' : '';
    const statistics = [
        workers ? `${workers.running ?? 0}${workers.limit ? `/${workers.limit}` : ''} parallele Aufgaben · ${workers.queued ?? 0} wartend` : '',
        throughput != null ? `${new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1 }).format(throughput)} ${throughputUnit}` : '',
        cpuText,
        gpuText
    ].filter(Boolean);
    const canCancel = Boolean(jobId && ['tracking', 'identities', 'attributes'].includes(stepName)
        && progress.status !== 'cancelling' && progress.status !== 'cancelled'
        && progress.phase !== 'publishing' && progress.phase !== 'complete');

    const cancel = async () => {
        if (!jobId || !canCancel || cancelPending) return;
        setCancelPending(true);
        setCancelError('');
        try {
            const response = await fetch(`/api/jobs/${jobId}/person-analysis/cancel`, {
                method: 'POST',
                cache: 'no-store'
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Der Prozessschritt konnte nicht abgebrochen werden.');
            setProgressData(prev => {
                const current = prev[stepName];
                if (!current) return prev;
                const status = data.status === 'cancelled' ? 'cancelled' : 'cancelling';
                return {
                    ...prev,
                    [stepName]: {
                        ...current,
                        status,
                        msg: status === 'cancelled' ? 'Personenschritt abgebrochen.' : 'Abbrechen wird ausgeführt …'
                    }
                };
            });
        } catch (err) {
            setCancelError(err instanceof Error ? err.message : 'Der Prozessschritt konnte nicht abgebrochen werden.');
        } finally {
            setCancelPending(false);
        }
    };

    return (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 w-full max-w-2xl z-50 animate-in fade-in slide-in-from-bottom-4 duration-300">
            <div className="bg-bg-card border border-violet-500/30 shadow-[0_8px_32px_rgba(139,92,246,0.25)] rounded-2xl p-5 backdrop-blur-md">
                <div className="flex justify-between items-center mb-3.5">
                    <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider">{label}</p>
                    <div className="flex items-center gap-3">
                        <span className="text-xs font-mono font-bold text-violet-400">{progress.percent}%</span>
                        {canCancel && <button
                            type="button"
                            onClick={() => void cancel()}
                            disabled={cancelPending}
                            className="px-2.5 py-1 text-xs font-semibold rounded-md border border-red-500/50 text-red-400 hover:bg-red-500/10 disabled:opacity-50"
                        >{cancelPending ? 'Wird abgebrochen …' : 'Abbrechen'}</button>}
                        <button type="button" onClick={() => setHiddenStep(stepName)} aria-label="Fortschritt ausblenden"
                            className="px-1.5 py-1 text-sm text-text-muted hover:text-text-primary">✕</button>
                    </div>
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
                    {phaseSummary && <span className="text-[11px] text-text-muted truncate">{phaseSummary}</span>}
                    {statistics.length > 0 && <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-text-muted" aria-label="Aufgabenstatistik">
                        {statistics.map((stat, index) => <span key={`${index}-${stat}`}>{stat}</span>)}
                    </div>}
                    {progress.status === 'cancelling' && <span role="status" className="text-[11px] text-text-muted">Abbruch läuft; aktive Arbeit wird am nächsten sicheren Punkt beendet.</span>}
                    {progress.status === 'cancelled' && <span role="status" className="text-[11px] text-text-muted">Abgebrochen. Vorherige Ergebnisse bleiben erhalten.</span>}
                    {cancelError && <span role="alert" className="text-[11px] text-red-400">{cancelError}</span>}
                </div>
            </div>
        </div>
    );
}
