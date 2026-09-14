import { ReviewImageSizeControl } from './ReviewImageSizeControl';
import { useEffect, useState } from 'react';
import { useJob } from '../../hooks/useJob';
import { STEP } from '../../workflow';
import type { FaceReview, PersonCrop, TrackingChange } from '../../types';
import { TrackRow } from './FaceMergeDialog';
import { CropDetailDialog } from './CropDetailDialog';

function TrackingPanel({ jobId }: { jobId: string }) {
    const { jobData, progressData, handleRunTracking, fetchJobData } = useJob();
    const [snapshot, setSnapshot] = useState<FaceReview | null>(null);
    const [pending, setPending] = useState<Record<number, boolean>>({});
    const [splits, setSplits] = useState<Record<number, TrackingChange>>({});
    const [open, setOpen] = useState(false);
    const [error, setError] = useState('');
    const [saving, setSaving] = useState(false);
    const [fallbacks, setFallbacks] = useState(false);
    const [enlarged, setEnlarged] = useState<PersonCrop | null>(null);
    const [refresh, setRefresh] = useState(0);
    const dirty = Object.keys(pending).length + Object.keys(splits).length > 0;
    const running = jobData?.status === 'running';
    useEffect(() => {
        if (running || dirty) return;
        const controller = new AbortController();
        fetch(`/api/jobs/${jobId}/person-analysis/tracking`, { signal: controller.signal, cache: 'no-store' })
            .then(async res => { const data = await res.json(); if (!res.ok) throw new Error(data.error || 'Tracking-Daten nicht verfügbar.'); setSnapshot(data); setError(''); })
            .catch(err => { if (!controller.signal.aborted) setError(err.message); });
        return () => controller.abort();
    }, [jobId, jobData?.person_stages?.face_review_version, jobData?.person_stages?.tracking_run, running, dirty, refresh]);
    useEffect(() => {
        if (!open) return;
        const previous = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        return () => { document.body.style.overflow = previous; };
    }, [open]);
    const save = async () => {
        if (!snapshot) return;
        setSaving(true); setError('');
        try {
            const res = await fetch(`/api/jobs/${jobId}/person-analysis/face-review`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ version: snapshot.version, face_exclusions: Object.entries(pending).map(([id, excluded]) => ({ face_id: Number(id), excluded })), track_changes: Object.values(splits) }) });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Speichern fehlgeschlagen.');
            setSnapshot(data); setPending({}); setSplits({}); void fetchJobData(jobId, true);
        } catch (err) { setError(err instanceof Error ? err.message : 'Speichern fehlgeschlagen.'); }
        finally { setSaving(false); }
    };
    const discard = () => { setPending({}); setSplits({}); setRefresh(n => n + 1); };
    const close = () => { if (!saving && (!dirty || window.confirm('Vorgemerkte Review-Änderungen verwerfen?'))) { discard(); setOpen(false); } };
    const stale = snapshot?.identities_stale || jobData?.person_stages?.identities_stale;
    const summary = snapshot ? `${snapshot.tracks.length} Tracks · ${snapshot.tracks.reduce((n, t) => n + t.quality_face_count, 0)} Face-Beobachtungen` : '';
    return <div className="flex flex-col gap-5" data-review-size="tracking">
        <h2 className="text-[1.4rem] font-bold">Tracking &amp; Gesichter</h2>
        <p className="text-sm text-text-secondary">Die Review ist optional. Face-Ausschlüsse ändern keine Trackzeiten. Für einen dauerhaften Personenwechsel kann ein Track zeitlich geteilt werden.</p>
        {running && <p role="status">{progressData.tracking?.msg || 'Verarbeitung läuft …'}</p>}
        {!open && error && <p role="alert" className="text-amber-600">{error}</p>}
        {stale && !open && <p role="status" className="p-3 border border-amber-500 rounded-lg">Personen &amp; Cluster ist veraltet. Vorhandene Personen bleiben bis zum erneuten Ausführen von Schritt 2 unverändert.</p>}
        {snapshot && !running && <div className="p-4 border border-border-subtle rounded-lg flex flex-wrap justify-between items-center gap-4"><span>{summary}</span>
            <button onClick={() => setOpen(true)} className="px-4 py-2 bg-violet-600 text-white rounded-lg">Tracks prüfen</button></div>}
        <button disabled={running || saving || !jobData?.video_path} onClick={() => void handleRunTracking()} className="w-fit px-4 py-2 bg-violet-600 text-white rounded-lg disabled:opacity-50">Tracking &amp; Gesichter ausführen</button>
        {open && snapshot && <div role="dialog" aria-modal="true" aria-label="Tracking-Review" className="fixed inset-0 z-[60] bg-black/60 flex items-center justify-center p-2 sm:p-4"
            onKeyDown={e => { if (e.key === 'Escape' && !enlarged) close(); }}>
            <div className="w-[97vw] h-[94vh] bg-bg-surface rounded-xl border border-border-subtle shadow-2xl flex flex-col overflow-hidden">
                <div className="p-4 border-b border-border-subtle flex justify-between gap-4"><div><h3 className="text-xl font-semibold">Tracks prüfen</h3><p>{summary}</p></div>
                    <button autoFocus disabled={saving} onClick={close} aria-label="Tracking-Review schließen">Schließen ✕</button></div>
                <div className="px-4 py-3 flex flex-wrap items-center justify-between gap-2">
                    <ReviewImageSizeControl stage="tracking" />
                    <label><input type="checkbox" checked={fallbacks} onChange={e => setFallbacks(e.target.checked)} /> Tracks ohne brauchbares Gesicht anzeigen</label>
                    <span className="text-sm text-text-muted">Originaltracks: {snapshot.original_tracks_count} · Fallbacks: bis zu 5 pro Track</span>
                </div>
                {!snapshot.split_available && <p className="px-4 pb-3 text-amber-600">Dieser ältere Lauf enthält kein vollständiges Frame-Protokoll. Gesichtsbereinigung bleibt möglich; für präzise Track-Splits Tracking erneut ausführen.</p>}
                {stale && <p role="status" className="px-4 pb-3 text-amber-600">Personen &amp; Cluster ist veraltet. Angezeigt bleiben die bisherigen Personen bis zum erneuten Clustering.</p>}
                <div data-testid="tracking-review-scroll" className="flex-1 min-h-0 overflow-y-auto p-4 space-y-5">
                    {snapshot.tracks.filter(t => t.quality_face_count > 0 || fallbacks).map(track => {
                        const source = track.source_track_id ?? track.track_id;
                        const change = splits[source];
                        const option = change?.action === 'split' ? track.split_options?.find(o => o.before_frame === change.before_frame && track.track_id === change.track_id) : null;
                        return <div key={`${snapshot.version}:${track.track_id}`} className={change ? 'border-2 border-violet-500 rounded-lg' : ''}>
                            <TrackRow track={{ ...track, review_mode: track.quality_face_count ? 'retinaface' : 'fallback', review_observation_count: track.observations.length }}
                                jobId={jobId} analysisId={snapshot.analysis_id} version={snapshot.version} initialCrops={track.observations} disabled={saving || running}
                                persons={[]} onChoose={() => {}} onUndo={() => {}} onEnlarge={setEnlarged} exclusions={pending} allowExclusions showAssignments={false}
                                splitFrames={snapshot.split_available ? (track.split_options || []).map(o => o.before_frame) : []}
                                onSplit={frame => setSplits(prev => ({ ...prev, [source]: { action: 'split', track_id: track.track_id, before_frame: frame } }))}
                                onExclude={(fid, excluded) => setPending(prev => { const next = { ...prev }; if (excluded === snapshot.excluded_face_observations.includes(fid)) delete next[fid]; else next[fid] = excluded; return next; })} />
                            <div className="px-3 pb-3 text-sm flex flex-wrap gap-3 items-center">
                                {track.is_split && <button disabled={saving} className="underline" onClick={() => setSplits(prev => ({ ...prev, [source]: { action: 'undo_split', source_track_id: source } }))}>Alle Splits von Track {source} aufheben</button>}
                                {change && <><span className="text-violet-700">{change.action === 'undo_split' ? `Vorgemerkt: Originaltrack ${source} wiederherstellen; Face-Ausschlüsse bleiben erhalten.` : option ? `Vorgemerkt: Schnitt vor Frame ${change.before_frame} · links bis ${option.left_end_s.toFixed(3)} s, rechts ab ${option.right_start_s.toFixed(3)} s` : `Split für Originaltrack ${source} vorgemerkt`}</span>
                                    <button disabled={saving} className="underline" onClick={() => setSplits(prev => { const next = { ...prev }; delete next[source]; return next; })}>Split-Änderung zurücknehmen</button></>}
                            </div>
                        </div>;
                    })}
                    {snapshot.tracks.every(t => t.quality_face_count === 0) && !fallbacks && <p>Keine qualitativ verwendbaren Gesichter. Tracks bleiben über die Fallback-Ansicht kontrollierbar.</p>}
                </div>
                <div className="p-4 border-t border-border-subtle bg-bg-card">
                    {error && <p role="alert" className="text-red-500 mb-2">{error}</p>}
                    <div className="flex flex-wrap justify-between gap-3 items-center"><span>{Object.keys(pending).length} Face-Änderungen vorgemerkt · {Object.keys(splits).length} Split-Änderungen vorgemerkt</span>
                        <div className="flex gap-3"><button disabled={saving || !dirty} onClick={() => { if (window.confirm('Vorgemerkte Review-Änderungen verwerfen?')) discard(); }}>Verwerfen</button>
                            <button disabled={saving || running || !dirty} onClick={() => void save()} className="px-4 py-2 bg-violet-600 text-white rounded-lg disabled:opacity-50">{saving ? 'Speichert …' : 'Review-Änderungen speichern'}</button></div></div>
                </div>
            </div>
            {enlarged && <CropDetailDialog crop={{ ...enlarged, excluded: enlarged.face_id !== null ? pending[enlarged.face_id] ?? enlarged.excluded : false }} jobId={jobId} analysisId={snapshot.analysis_id} onClose={() => setEnlarged(null)} />}
        </div>}
    </div>;
}

export function StepTracking() {
    const { currentStep, jobData } = useJob();
    if (currentStep !== STEP.tracking) return null;
    return jobData?.job_id ? <TrackingPanel key={jobData.job_id} jobId={jobData.job_id} /> : <p>Bitte zuerst ein Video hochladen.</p>;
}
