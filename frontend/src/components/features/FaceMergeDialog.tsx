import { useEffect, useState } from 'react';
import { ReviewImageSizeControl } from './ReviewImageSizeControl';
import { CropImage, CropDetailDialog } from './CropDetailDialog';
import type { PersonCrop, PersonData, PersonReview, PersonTrack, TrackChange } from '../../types';
export type { PersonData } from '../../types';

function cropUrl(jobId: string, cropId: number, analysisId: string): string {
    return `/api/jobs/${jobId}/person-crops/${cropId}?analysis_id=${encodeURIComponent(analysisId)}`;
}

export function PersonExample({ person, jobId, analysisId, compact = false }: { compact?: boolean; person: PersonData; jobId: string; analysisId: string }) {
    const [failed, setFailed] = useState(false);
    return person.representative_crop_id != null && !failed ? (
        <img src={cropUrl(jobId, person.representative_crop_id, analysisId)} alt={`Beispiel ${person.name || `Person ${person.person_id}`}`}
            style={{ height: compact ? '80px' : 'var(--review-image-height, 180px)', width: compact ? '64px' : 'auto', maxWidth: '100%' }} className="object-contain rounded-lg bg-bg-card" loading="lazy" onError={() => setFailed(true)} />
    ) : <span style={{ height: compact ? '80px' : 'var(--review-image-height, 180px)', width: compact ? '64px' : 'var(--review-card-width, 160px)' }} className="max-w-full flex items-center justify-center text-text-muted" aria-label="Kein Beispielbild">👤</span>;
}

export function PersonPicker({ persons, jobId, analysisId, title, onChoose, onClose, allowSpecial = true }: {
    persons: PersonData[]; jobId: string; analysisId: string; title: string;
    onChoose: (_target: number | 'new' | null) => void; onClose: () => void; allowSpecial?: boolean;
}) {
    const [query, setQuery] = useState('');
    const choices = persons.filter(p => `${p.person_id} ${p.name || ''}`.toLowerCase().includes(query.toLowerCase()));
    return <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-label={title}
        onClick={e => { e.stopPropagation(); onClose(); }} onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } }}>
        <div className="bg-bg-surface border border-border-subtle rounded-xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="p-4 border-b border-border-subtle flex items-center justify-between">
                <h3 className="font-semibold">{title}</h3><button autoFocus onClick={onClose} aria-label="Personenauswahl schließen">✕</button>
            </div>
            <div className="px-4 pt-3"><ReviewImageSizeControl stage="persons" /></div>
            <div className="p-4"><input aria-label="Person suchen" placeholder="Name oder Personen-ID suchen" value={query} onChange={e => setQuery(e.target.value)}
                className="w-full px-3 py-2 bg-bg-card border border-border-subtle rounded-lg" /></div>
            <div className="grid gap-3 p-4 pt-0 overflow-y-auto" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, var(--review-card-width, 160px)), 1fr))' }}>
                {choices.map(p => <button key={p.person_id} onClick={() => onChoose(p.person_id)}
                    className="flex flex-col items-center gap-2 p-3 bg-bg-card border border-border-subtle rounded-lg hover:border-violet-500"
                    aria-label={`${p.name || `Person ${p.person_id}`} (ID ${p.person_id}) auswählen`}>
                    <PersonExample key={`${analysisId}:${p.representative_crop_id}`} person={p} jobId={jobId} analysisId={analysisId} />
                    <span className="text-sm font-medium">{p.name || `Person ${p.person_id}`}</span><span className="text-xs text-text-muted">ID {p.person_id}</span>
                </button>)}
                {choices.length === 0 && <p className="col-span-full text-text-muted text-sm">Keine passende Person.</p>}
            </div>
            <div className="p-4 border-t border-border-subtle flex flex-wrap justify-end gap-3">
                {allowSpecial && <><button onClick={() => onChoose(null)} className="px-3 py-2 border border-border-subtle rounded-lg">Nicht zugeordnet</button>
                    <button onClick={() => onChoose('new')} className="px-3 py-2 bg-violet-600 text-white rounded-lg">+ Neue Person</button></>}
                <button onClick={onClose} className="px-3 py-2 rounded-lg">Abbrechen</button>
            </div>
        </div>
    </div>;
}

export function TrackRow({ track, change, jobId, analysisId, onChoose, onUndo, onEnlarge, disabled, persons, version, exclusions, onExclude, initialCrops, allowExclusions = false, showAssignments = true, onSplit, splitFrames = [], onProfile, profileCropId, profileDisabled = false }: {
    track: PersonTrack; change?: TrackChange; jobId: string; analysisId: string; disabled: boolean; persons: PersonData[];
    onChoose: () => void; onUndo: () => void; onEnlarge: (_crop: PersonCrop) => void;
    version: string; exclusions: Record<number, boolean>; onExclude: (_faceId: number, _excluded: boolean) => void;
    onSplit?: (_frame: number) => void; splitFrames?: number[];
    onProfile?: (_cropId: number) => void; profileCropId?: number | null; profileDisabled?: boolean;
    initialCrops?: PersonCrop[]; allowExclusions?: boolean; showAssignments?: boolean;
}) {
    const [loadedCrops, setCrops] = useState<PersonCrop[]>([]);
    const crops = initialCrops ?? loadedCrops;
    const [visibleCount, setVisibleCount] = useState(12);
    const visibleCrops = allowExclusions ? crops.slice(0, visibleCount) : crops;
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(!initialCrops);
    useEffect(() => {
        if (initialCrops) return;
        const controller = new AbortController();
        fetch(`/api/jobs/${jobId}/tracks/${track.track_id}/crops`, { signal: controller.signal })
            .then(async res => {
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || data.detail || 'Crops konnten nicht geladen werden.');
                if (data.analysis_id !== analysisId) throw new Error('Der Analyselauf hat sich geändert. Bitte neu laden.');
                if (data.version !== version) throw new Error('Der Review-Stand wurde geändert. Bitte neu laden.');
                setCrops(data.crops);
            }).catch(err => { if (!controller.signal.aborted) setError(String(err.message)); })
            .finally(() => { if (!controller.signal.aborted) setLoading(false); });
        return () => controller.abort();
    }, [jobId, track.track_id, analysisId, version, initialCrops]);
    const target = change?.action === 'create_person' ? 'Neue Person' : change?.action === 'unassign' ? 'Nicht zugeordnet'
        : change?.action === 'assign' ? `${persons.find(p => p.person_id === change.person_id)?.name || `Person ${change.person_id}`} (ID ${change.person_id})` : '';
    return <section className={`p-3 border rounded-lg ${change ? 'border-violet-500 bg-violet-500/10' : 'border-border-subtle bg-bg-card'}`} aria-label={`Track ${track.track_id}`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
            <div><h4 className="font-medium">Track {track.track_id}{track.is_split && ` · Segment von Track ${track.source_track_id}`}</h4><p className="text-xs text-text-muted">{track.start_s.toFixed(2)}–{track.end_s.toFixed(2)} s · {track.review_observation_count} {track.review_mode === 'facemoe' ? 'FaceMoE-Vorschauen' : track.review_mode === 'retinaface' ? 'Face-Beobachtungen' : track.review_mode === 'fallback' ? 'Fallback-Crops' : 'Legacy-Beobachtungen'} · Szene {track.scene_id}</p></div>
            {showAssignments && <div className="flex gap-3 text-sm">
                <button disabled={disabled} onClick={onChoose} className="px-3 py-1.5 bg-violet-600 text-white rounded-lg disabled:opacity-50">Track zuweisen</button></div>}
        </div>
        {change && <div className="mt-3 text-sm text-violet-400 flex justify-between gap-2"><span>Vorgemerkt: Track {track.track_id} → {target}</span><button disabled={disabled} onClick={onUndo} className="underline">Zurücknehmen</button></div>}
        <div className="mt-3">
            {track.review_mode === 'fallback' && <p className="text-xs text-text-muted mb-2">Kein brauchbares Gesicht. Zeitlich verteilte Personencrops zur Track-Kontrolle.</p>}
            {track.review_mode === 'legacy_unverified' && <p className="text-xs text-amber-600 mb-2">Altdaten: Qualität und Alignment bestanden; FaceMoE-Erfolg wurde damals nicht protokolliert.</p>}
            {loading && <p className="text-sm text-text-muted">Lade Vorschauen …</p>}{error && <p role="alert" className="text-red-400">{error}</p>}
            <div className="grid gap-3 items-start" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, var(--review-card-width, 160px)), 1fr))' }}>{visibleCrops.map(crop => {
                const staged = crop.face_id !== null && Object.prototype.hasOwnProperty.call(exclusions, crop.face_id);
                const excluded = crop.face_id !== null && (exclusions[crop.face_id] ?? crop.excluded);
                return <div key={crop.crop_id} className={`border rounded-lg overflow-hidden ${staged ? 'border-violet-500' : 'border-border-subtle'}`}>
                    <button onClick={() => onEnlarge(crop)} className="block w-full text-left" aria-label={`Crop vergrößern: Track ${track.track_id}, Frame ${crop.frame_number}`}>
                        <div className={excluded ? 'opacity-40' : ''} style={{ maxWidth: `calc(var(--review-image-height, 180px) * ${crop.width / Math.max(1, crop.height)})`, margin: 'auto' }}><CropImage crop={crop} jobId={jobId} analysisId={analysisId} /></div>
                        <span className="block p-1 text-xs text-text-muted">Frame {crop.frame_number} · {crop.timestamp_s.toFixed(2)} s</span>
                    </button>
                    <p className="px-2 text-xs">{excluded ? '✕ manuell ausgeschlossen' : crop.evidence_status === 'fallback' ? 'Fallback · keine Face-Evidenz' : crop.evidence_status === 'legacy_unverified' ? 'FaceMoE-Erfolg unbestätigt' : '✓ gültig'}{staged && ' · vorgemerkt'}</p>
                    {allowExclusions && crop.face_id !== null && <button disabled={disabled} onClick={() => onExclude(crop.face_id!, !excluded)} className="p-2 text-xs underline disabled:opacity-50"
                        aria-label={`Face ${crop.face_id} ${excluded ? 'wiederherstellen' : 'ausschließen'}`}>{excluded ? 'Ausschluss aufheben' : 'Beobachtung ausschließen'}</button>}
                    {onProfile && !excluded && <button disabled={disabled || profileDisabled || profileCropId === crop.crop_id} onClick={() => onProfile(crop.crop_id)} className="block p-2 text-xs underline disabled:opacity-50">{profileCropId === crop.crop_id ? 'Aktuelles Profilbild' : 'Als Profilbild verwenden'}</button>}
                    {onSplit && splitFrames.includes(crop.frame_number) && <button disabled={disabled} className="block p-2 text-xs underline" onClick={() => onSplit(crop.frame_number)}>Vor Frame {crop.frame_number} teilen</button>}
                </div>;
            })}</div>
            {allowExclusions && visibleCrops.length < crops.length && <button type="button" onClick={() => setVisibleCount(count => count + 12)}
                className="mt-3 px-3 py-2 border border-border-subtle rounded-lg text-sm">Weitere Bilder anzeigen ({visibleCrops.length} / {crops.length})</button>}
            {!loading && !error && crops.length === 0 && <p className="text-sm text-text-muted">Keine gespeicherten Crops für diesen Track.</p>}
        </div>
    </section>;
}

export function FaceMergeDialog({ person, snapshot, jobId, onClose, onSaved }: {
    person: PersonData | null; snapshot: PersonReview; jobId: string; onClose: () => void; onSaved: (_result: PersonReview) => void;
}) {
    // Pin the original version while changes are staged, including across SSE refreshes.
    const [baseline, setBaseline] = useState(snapshot);
    const [notice, setNotice] = useState('');
    const [pending, setPending] = useState<Record<number, TrackChange>>({});
    const [exclusions, setExclusions] = useState<Record<number, boolean>>({});
    const [pickerTrack, setPickerTrack] = useState<number | null>(null);
    const [enlarged, setEnlarged] = useState<PersonCrop | null>(null);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const tracks = baseline.tracks.filter(t => t.person_id === (person?.person_id ?? null));
    const changes = Object.values(pending);
    const faceExclusions = Object.entries(exclusions).map(([faceId, excluded]) => ({ face_id: Number(faceId), excluded }));
    const hasChanges = changes.length + faceExclusions.length > 0;
    const currentPerson = baseline.persons.find(p => p.person_id === person?.person_id);
    const saveProfile = async (cropId: number | null) => {
        if (!person || hasChanges || saving) return;
        setSaving(true); setError(''); setNotice('');
        try {
            const res = await fetch(`/api/jobs/${jobId}/persons/${person.person_id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ version: baseline.version, profile_crop_id: cropId }) });
            const result = await res.json();
            if (!res.ok) throw new Error(result.error || result.detail || 'Profilbild konnte nicht gespeichert werden.');
            setBaseline(result); onSaved(result); setNotice('Profilbild gespeichert.');
        } catch (err) { setError(err instanceof Error ? err.message : 'Speichern fehlgeschlagen.'); }
        finally { setSaving(false); }
    };
    const close = () => { if (!saving && (!hasChanges || window.confirm('Vorgemerkte Review-Änderungen verwerfen?'))) onClose(); };
    const save = async () => {
        setSaving(true); setError('');
        try {
            const res = await fetch(`/api/jobs/${jobId}/track-assignments`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version: baseline.version, changes, face_exclusions: faceExclusions }) });
            const result = await res.json();
            if (!res.ok) throw new Error(result.error || result.detail || 'Speichern fehlgeschlagen.');
            onSaved(result); onClose();
        } catch (err) { setError(err instanceof Error ? err.message : 'Speichern fehlgeschlagen.'); }
        finally { setSaving(false); }
    };
    return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" role="dialog" aria-modal="true" aria-label="Tracks verwalten"
        onClick={close} onKeyDown={e => { if (e.key === 'Escape' && pickerTrack === null && !enlarged) close(); }}>
        <div className="bg-bg-surface border border-border-subtle rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="p-4 border-b border-border-subtle flex items-center justify-between gap-4">
                <div><h3 className="text-lg font-semibold">{person ? `${person.name || `Person ${person.person_id}`} · ID ${person.person_id}` : 'Nicht zugeordnete Tracks'}</h3>
                    <p className="text-sm text-text-muted">{tracks.length} Tracks · Änderungen betreffen immer den gesamten Track. Gesichtsbereinigung ist in Schritt 1 möglich.</p></div>
                <button autoFocus disabled={saving} onClick={close} aria-label="Track-Verwaltung schließen">✕</button>
            </div>
            <div className="px-4 py-3"><ReviewImageSizeControl stage="persons" /></div>
            <div className="p-4 overflow-y-auto flex-1 space-y-3">
                {tracks.map(track => <TrackRow key={track.track_id} track={track} change={pending[track.track_id]} jobId={jobId} analysisId={baseline.analysis_id}
                    onProfile={person ? cropId => void saveProfile(cropId) : undefined} profileCropId={currentPerson?.representative_crop_id} profileDisabled={hasChanges}
                    persons={baseline.persons} disabled={saving} onChoose={() => setPickerTrack(track.track_id)} onEnlarge={setEnlarged}
                    version={baseline.version} exclusions={exclusions} onExclude={(fid, excluded) => setExclusions(prev => {
                        const next = { ...prev };
                        if (excluded === (baseline.excluded_face_observations || []).includes(fid)) delete next[fid];
                        else next[fid] = excluded;
                        return next;
                    })}
                    onUndo={() => setPending(prev => { const next = { ...prev }; delete next[track.track_id]; return next; })} />)}
                {tracks.length === 0 && <p className="text-text-muted">Keine Tracks vorhanden.</p>}
            </div>
            <div className="p-4 border-t border-border-subtle bg-bg-card">
                {error && <p role="alert" className="text-red-400 mb-3">{error}</p>}
                {notice && <p role="status" className="mb-2 text-sm">{notice}</p>}
                {person && hasChanges && <p className="mb-2 text-sm">Vor der Profilbildwahl bitte Trackänderungen speichern oder zurücknehmen.</p>}
                {currentPerson?.profile_crop_id != null && <button disabled={saving || hasChanges} onClick={() => void saveProfile(null)} className="mb-3 text-sm underline">Automatische Bildwahl verwenden</button>}
                <div className="flex flex-wrap items-center justify-between gap-3"><div className="text-sm text-text-muted"><span>{changes.length} Trackänderungen vorgemerkt</span></div>
                    <div className="flex gap-3"><button disabled={saving} onClick={close}>Abbrechen</button><button onClick={save} disabled={saving || !hasChanges}
                        className="px-4 py-2 bg-violet-600 text-white rounded-lg disabled:opacity-50">{saving ? 'Speichert …' : 'Alle Änderungen speichern'}</button></div>
                </div>
            </div>
        </div>
        {pickerTrack !== null && <PersonPicker persons={baseline.persons} jobId={jobId} analysisId={baseline.analysis_id} title={`Track ${pickerTrack} zuweisen`} onClose={() => setPickerTrack(null)} onChoose={target => {
            const tid = pickerTrack;
            const original = baseline.tracks.find(t => t.track_id === tid)?.person_id;
            setPending(prev => {
                const next = { ...prev };
                if (target === original) delete next[tid];
                else next[tid] = target === 'new' ? { track_id: tid, action: 'create_person' } : target === null ? { track_id: tid, action: 'unassign' } : { track_id: tid, action: 'assign', person_id: target };
                return next;
            }); setPickerTrack(null);
        }} />}
        {enlarged && <CropDetailDialog crop={enlarged} jobId={jobId} analysisId={baseline.analysis_id} onClose={() => setEnlarged(null)} />}
    </div>;
}
