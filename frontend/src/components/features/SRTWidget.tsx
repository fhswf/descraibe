import { useJob } from '../../hooks/useJob.jsx';
import { GPTRecord } from '../../types/index.js';

export function SRTWidget() {
    const { jobData, setFocusedSlot, srtTexts, setSrtTexts } = useJob();

    const maxDuration = jobData?.gpt_records?.length && jobData.gpt_records.length > 0
        ? Math.max(...jobData.gpt_records.map((rec: GPTRecord) => rec.end_s || 0))
        : 0;

    const formatTime = (seconds: number): string => {
        if (!seconds || Number.isNaN(seconds)) seconds = 0;
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        const mm = m.toString().padStart(2, '0');
        const ss = s.toFixed(2).padStart(5, '0');

        if (maxDuration < 3600) {
            return `${mm}:${ss}`;
        }

        const hh = h.toString().padStart(2, '0');
        return `${hh}:${mm}:${ss}`;
    };

    if (!jobData?.gpt_records || jobData.gpt_records.length === 0) {
        return null;
    }

    const handleChange = (slotId: number, newText: string): void => {
        setSrtTexts(prev => ({ ...prev, [slotId]: newText }));
    };

    const statusFor = (rec: GPTRecord): { label: string; className: string } => {
        if (rec.skipped) return { label: 'SKIP', className: 'bg-yellow-500/10 text-yellow-500' };
        if (!rec.ok) return { label: 'ERROR', className: 'bg-red-500/10 text-red-400' };
        return { label: 'READY', className: 'bg-green-500/10 text-green-500' };
    };

    const noteFor = (rec: GPTRecord): string => {
        if (rec.error?.message) return rec.error.message;
        return rec.reason || '';
    };

    const syllableInfo = (rec: GPTRecord): string => {
        if (!rec.syllable_limit) return '';
        const original = rec.syllables_original && rec.syllables_original > 0 ? `${rec.syllables_original}` : '?';
        const final = rec.syllables_final && rec.syllables_final > 0 ? `${rec.syllables_final}` : '?';
        return `${original} → ${final} / ${rec.syllable_limit}`;
    };

    return (
        <div className="flex flex-col h-full bg-bg-surface overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 bg-bg-card border-b border-border-subtle shrink-0">
                <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted">Slot Manager (SRT Ansicht)</span>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {jobData.gpt_records.map((rec: GPTRecord, idx: number) => {
                    const status = statusFor(rec);
                    const note = noteFor(rec);
                    const hasOriginal = Boolean(rec.original_text && rec.original_text !== rec.text);
                    const syllables = syllableInfo(rec);
                    const slotNum = rec.slot_id ?? rec.slot ?? idx + 1;
                    return (
                        <div key={idx} className="group border border-border-subtle rounded-xl bg-bg-card shadow-sm hover:border-violet-500/50 transition-colors overflow-hidden">
                            <div className="flex items-center justify-between px-4 py-2 bg-white/5 border-b border-border-subtle/50">
                                <div className="flex items-center gap-2">
                                    <span className="text-[10px] font-bold text-violet-500">Slot {slotNum}</span>
                                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${status.className}`}>{status.label}</span>
                                </div>
                                <div className="text-[10px] font-mono text-text-secondary">
                                    {formatTime(rec.start_s ?? 0)} → {formatTime(rec.end_s ?? 0)} <span className="text-violet-500">({(rec.duration_s ?? 0).toFixed(2)}s)</span>
                                </div>
                            </div>
                            {note && !rec.ok && (
                                <div className="px-4 pt-3 text-xs text-red-300">
                                    GPT-Fehler: {note}
                                </div>
                            )}
                            {hasOriginal && (
                                <div className="px-4 pt-3 flex items-center justify-between gap-3 text-[10px] font-bold uppercase tracking-widest text-text-muted">
                                    <span>Gekürzte Fassung</span>
                                    {syllables && <span className="font-mono text-violet-400 normal-case tracking-normal">Silben {syllables}</span>}
                                </div>
                            )}
                            <textarea
                                className="w-full p-4 text-sm bg-transparent border-0 outline-none focus:ring-0 resize-y font-sans leading-relaxed text-text-primary min-h-[60px]"
                                rows={3}
                                value={srtTexts[slotNum] !== undefined ? srtTexts[slotNum] : (rec.text || '')}
                                placeholder={!rec.ok ? 'Beschreibung manuell ergänzen oder GPT erneut starten.' : ''}
                                onFocus={() => setFocusedSlot(slotNum)}
                                onChange={(e) => handleChange(slotNum, e.target.value)}
                            />
                            {hasOriginal && (
                                <details open className="border-t border-border-subtle/50 bg-white/[0.03]">
                                    <summary className="cursor-pointer px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-text-muted hover:text-text-secondary">
                                        Original / Director&apos;s Cut
                                    </summary>
                                    <div className="px-4 pb-4 text-sm leading-relaxed text-text-secondary whitespace-pre-wrap">
                                        {rec.original_text}
                                    </div>
                                </details>
                            )}
                            <div className="px-4 py-2 flex justify-end gap-2 border-t border-border-subtle/50 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button className="p-1 text-text-muted hover:text-violet-500 transition-colors" title="Kopieren">
                                    <span className="material-icons-round text-sm">content_copy</span>
                                </button>
                                <button className="p-1 text-text-muted hover:text-red-500 transition-colors" title="Löschen">
                                    <span className="material-icons-round text-sm">delete</span>
                                </button>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
