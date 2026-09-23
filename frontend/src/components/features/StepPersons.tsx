import { useEffect, useState } from 'react';
import { useJob } from '../../hooks/useJob';
import { FaceMergeDialog, PersonExample, PersonPicker } from './FaceMergeDialog';
import type { PersonData, PersonReview } from '../../types';
export type { PersonData } from '../../types';

function timestamp(seconds: number | undefined): string {
    if (seconds === undefined) return '–';
    return `${Math.floor(seconds / 60)}:${Math.floor(seconds % 60).toString().padStart(2, '0')}`;
}

function EditPersonDialog({ person, onSave, onClose }: {
    person: PersonData; onSave: (_updates: { name: string; function: string }) => Promise<void>; onClose: () => void;
}) {
    const [name, setName] = useState(person.name || '');
    const [personFunction, setPersonFunction] = useState(person.function || '');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const save = async () => {
        setSaving(true); setError('');
        try { await onSave({ name, function: personFunction }); onClose(); }
        catch (err) { setError(err instanceof Error ? err.message : 'Speichern fehlgeschlagen.'); }
        finally { setSaving(false); }
    };
    return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" role="dialog" aria-modal="true" aria-label="Person bearbeiten">
        <form onSubmit={e => { e.preventDefault(); void save(); }} className="bg-bg-surface border border-border-subtle rounded-xl shadow-2xl w-full max-w-md">
            <div className="p-4 border-b border-border-subtle flex justify-between"><h3 className="font-semibold">Person bearbeiten · ID {person.person_id}</h3><button type="button" disabled={saving} onClick={onClose} aria-label="Bearbeiten schließen">✕</button></div>
            <div className="p-4 space-y-4"><div className="grid grid-cols-1 sm:grid-cols-2 gap-3"><label className="block text-sm">Name<input autoFocus value={name} onChange={e => setName(e.target.value)} maxLength={10000}
                className="mt-1 w-full px-3 py-2 bg-bg-card border border-border-subtle rounded-lg" /></label>
                <label className="block text-sm">Funktion<input value={personFunction} onChange={e => setPersonFunction(e.target.value)} maxLength={10000}
                    className="mt-1 w-full px-3 py-2 bg-bg-card border border-border-subtle rounded-lg" /></label></div>
                {error && <p role="alert" className="text-red-400">{error}</p>}
            </div>
            <div className="p-4 border-t border-border-subtle flex justify-end gap-3"><button type="button" disabled={saving} onClick={onClose}>Abbrechen</button><button disabled={saving}
                className="px-4 py-2 bg-violet-600 text-white rounded-lg disabled:opacity-50">{saving ? 'Speichert …' : 'Speichern'}</button></div>
        </form>
    </div>;
}

function PersonsPanel({ jobId }: { jobId: string }) {
    const { jobData, handleRunPersons, progressData, fetchJobData } = useJob();
    const [snapshot, setSnapshot] = useState<PersonReview | null>(null);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [refresh, setRefresh] = useState(0);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [editing, setEditing] = useState<{ person: PersonData; version: string } | null>(null);
    const [managing, setManaging] = useState<{ person: PersonData | null; snapshot: PersonReview } | null>(null);
    const [merging, setMerging] = useState<{ source: PersonData; snapshot: PersonReview } | null>(null);
    const running = jobData?.status === 'running';
    useEffect(() => {
        if (running) return;
        const controller = new AbortController();
        fetch(`/api/jobs/${jobId}/persons`, { signal: controller.signal, cache: 'no-store' })
            .then(async res => {
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || data.detail || 'Personen konnten nicht geladen werden.');
                setSnapshot({ tracks: [], unassigned_tracks: [], version: '', analysis_id: '', revision: 0, review_available: false, ...data });
                setError('');
            }).catch(err => { if (!controller.signal.aborted) setError(String(err.message)); })
            .finally(() => { if (!controller.signal.aborted) setLoading(false); });
        return () => controller.abort();
    }, [jobId, jobData?.persons_version, jobData?.persons_count, running, refresh]);

    const accept = (result: PersonReview) => {
        setSnapshot(result); setError(''); setNotice(result.warning || 'Änderungen gespeichert.');
        void fetchJobData(jobId, true);
    };
    const mutate = async (path: string, method: string, body: Record<string, unknown>) => {
        const res = await fetch(`/api/jobs/${jobId}/${path}`, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || data.detail || 'Änderung konnte nicht gespeichert werden.');
        if (data.persons) accept(data);
        else { setRefresh(n => n + 1); void fetchJobData(jobId, true); }
    };
    const remove = async (person: PersonData) => {
        if (!snapshot || !window.confirm(`Person ${person.person_id} löschen? Ihre Tracks bleiben erhalten und werden nicht zugeordnet.`)) return;
        setBusy(true); setError('');
        try { await mutate(`persons/${person.person_id}`, 'DELETE', { version: snapshot.version }); }
        catch (err) { setError(err instanceof Error ? err.message : 'Löschen fehlgeschlagen.'); }
        finally { setBusy(false); }
    };
    const merge = async (target: number | 'new' | null) => {
        if (!merging || typeof target !== 'number') return;
        const source = merging.source;
        if (!window.confirm(`Alle Tracks von Person ${source.person_id} zu Person ${target} verschieben und Person ${source.person_id} zusammenführen?`)) return;
        setBusy(true); setError('');
        try { await mutate('persons/merge', 'POST', { version: merging.snapshot.version, source_person_id: source.person_id, target_person_id: target }); setMerging(null); }
        catch (err) { setError(err instanceof Error ? err.message : 'Zusammenführen fehlgeschlagen.'); setMerging(null); }
        finally { setBusy(false); }
    };
    const persons = snapshot?.persons || [];
    const filtered = persons;
    const disabled = running || busy || Boolean(error);
    return <div className="flex flex-col gap-5" data-review-size="persons">
        <div className="flex gap-4 pb-4 border-b border-border-subtle"><div className="text-3xl">👤</div><div><h2 className="text-[1.4rem] font-bold mb-1">Personen &amp; Cluster</h2>
            <p className="text-sm text-text-secondary">Personen und ihre Auftritte im Video. Track-Zuordnungen können bei Bedarf manuell korrigiert werden.</p></div></div>
        {(snapshot?.identities_stale || jobData?.person_stages?.identities_stale) && <p role="status" className="p-3 border border-amber-500 rounded-lg">Veraltet: Gesichtsbereinigung wurde geändert. Angezeigt wird der bisherige Personenstand. Schritt 2 erneut ausführen, um neu zu clustern.</p>}
        {jobData?.person_stages?.legacy && <p className="text-sm text-text-muted">Alter Analysejob: Personen und Korrekturen bleiben nutzbar. Für die neue Gesichtsbereinigung zuerst Tracking &amp; Gesichter ausführen.</p>}
        {running && <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg"><p className="text-sm">{progressData.identities?.msg || 'Verarbeitung läuft …'}</p>
            {progressData.identities && <progress aria-label="Personenanalyse Fortschritt" max={100} value={progressData.identities.percent} className="w-full" />}</div>}
        {error && <div role="alert" className="p-3 text-red-400 border border-red-500/30 rounded-lg">{error} <button onClick={() => { setLoading(true); setRefresh(n => n + 1); }} className="underline">Neu laden</button></div>}
        {(notice || snapshot?.warning) && <p role="status" className="text-sm text-text-secondary">{notice || snapshot?.warning}</p>}
        {loading && !running && <p className="text-sm text-text-muted">Lade Personendaten …</p>}
        {snapshot && !running && <>
            <div className="flex items-center justify-between flex-wrap gap-3"><span className="text-sm font-medium">{persons.length} Personen · {snapshot.tracks.length} Tracks</span>
                {snapshot.review_available && <button onClick={() => setManaging({ person: null, snapshot })} disabled={disabled}
                    className="px-3 py-2 bg-bg-card border border-border-subtle rounded-lg text-sm disabled:opacity-50">Nicht zugeordnete Tracks ({snapshot.unassigned_tracks.length})</button>}</div>
            <p className="text-sm font-medium">Zugeordnete Personen ({persons.length})</p>
            <div className="flex flex-col gap-2 max-h-[60vh] overflow-y-auto pr-1">
                {[...filtered].sort((a, b) => b.appearances_count - a.appearances_count).map(person => <article key={person.person_id} aria-label={`Person ${person.person_id}`}
                    className="flex flex-col gap-2 p-3 bg-bg-card border border-border-subtle rounded-lg">
                    <div className="flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-3">
                        <PersonExample compact key={`${snapshot.analysis_id}:${person.representative_crop_id}`} person={person} jobId={jobId} analysisId={snapshot.analysis_id} />
                        <div><div className="font-medium text-sm">{person.name || `Person ${person.person_id}`}</div>{person.function && <div className="text-xs text-text-secondary">{person.function}</div>}<div className="text-xs text-text-muted">Person {person.person_id}</div></div></div>
                        <div className="flex items-center flex-wrap gap-1"><div className="text-xs text-text-muted mr-2 text-right"><div>{person.appearances_count} Auftritte</div>
                            <div>{timestamp(person.first_seen_ts)}–{timestamp(person.last_seen_ts)}</div></div>
                            <button disabled={disabled} onClick={() => setEditing({ person, version: snapshot.version })} title="Bearbeiten" aria-label={`Person ${person.person_id} bearbeiten`} className="p-1.5 rounded-lg hover:bg-bg-surface"><span className="material-icons-round text-sm">edit</span></button>
                            <button disabled={disabled || !snapshot.review_available} onClick={() => setManaging({ person, snapshot })} title="Tracks verwalten" aria-label={`Tracks von Person ${person.person_id} verwalten`} className="p-1.5 rounded-lg hover:bg-bg-surface"><span className="material-icons-round text-sm">view_list</span></button>
                            <button disabled={disabled || persons.length < 2} onClick={() => setMerging({ source: person, snapshot })} title="Person zusammenführen" aria-label={`Person ${person.person_id} zusammenführen`} className="p-1.5 rounded-lg hover:bg-bg-surface"><span className="material-icons-round text-sm">call_merge</span></button>
                            <button disabled={disabled} onClick={() => void remove(person)} title="Person löschen" aria-label={`Person ${person.person_id} löschen`} className="p-1.5 rounded-lg hover:bg-bg-surface"><span className="material-icons-round text-sm">delete</span></button>
                        </div>
                    </div>
                </article>)}
                {!filtered.length && <p className="p-4 text-sm text-text-muted">Keine zugeordneten Personen. Nicht zugeordnete Tracks sind separat erreichbar.</p>}
            </div>
            {!snapshot.review_available && persons.length > 0 && <p className="text-sm text-text-muted">Dieser ältere Job enthält keine Track-Artefakte. Name und Funktion bleiben bearbeitbar.</p>}
        </>}
        {!running && <button disabled={!jobData?.video_path || busy || !jobData?.person_stages?.tracking_ready} onClick={handleRunPersons} className="w-fit flex items-center gap-2 px-4 py-2 bg-violet-600 text-white rounded-lg disabled:opacity-50"><span className="material-icons-round">search</span>Personen &amp; Cluster ausführen</button>}
        <div className="p-4 bg-bg-card border border-border-subtle rounded-lg text-xs text-text-secondary">Ein Auftritt entspricht dem Zeitintervall eines Tracks. Die automatische Zuordnung ist sofort nutzbar; manuelle Korrekturen sind optional.</div>
        {editing && <EditPersonDialog person={editing.person} onClose={() => setEditing(null)} onSave={updates => mutate(`persons/${editing.person.person_id}`, 'POST', { ...updates, version: editing.version })} />}
        {managing && <FaceMergeDialog person={managing.person} snapshot={managing.snapshot} jobId={jobId} onClose={() => setManaging(null)} onSaved={accept} />}
        {merging && !busy && <PersonPicker persons={merging.snapshot.persons.filter(p => p.person_id !== merging.source.person_id)} jobId={jobId} analysisId={merging.snapshot.analysis_id}
            title={`Person ${merging.source.person_id} zusammenführen mit …`} allowSpecial={false} onChoose={target => void merge(target)} onClose={() => setMerging(null)} />}
    </div>;
}

export function StepPersons() {
    const { currentStep, jobData } = useJob();
    if (currentStep !== 6) return null;
    if (!jobData?.job_id) return <p className="text-text-muted">Bitte zuerst ein Video hochladen.</p>;
    return <PersonsPanel key={jobData.job_id} jobId={jobData.job_id} />;
}
