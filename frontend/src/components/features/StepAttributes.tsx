import { useEffect, useState } from 'react';
import type { ChangeEvent } from 'react';
import { useJob } from '../../hooks/useJob';

interface AttributePerson {
    person_id: number; name: string; status: string; error: string | null;
    attributes: Record<string, string>;
    images: { crop_id: number; frame_number: number; track_id: number; timestamp_s: number }[];
}
interface AttributeReview {
    ready: boolean; stale: boolean; version?: string | null;
    error?: string; persons: AttributePerson[]; fields: string[]; labels: Record<string, string>;
}
const statuses: Record<string, string> = { ok: 'Extrahiert', no_eligible_images: 'Keine geeigneten Bilder (15-%-Mindesthöhe)', parse_error: 'JSON konnte nicht gelesen werden', generation_error: 'Extraktion fehlgeschlagen' };
const categoryOptions: Record<string, string[]> = {
    hair_length: ['glatze', 'sehr kurz', 'kurz', 'mittellang', 'lang', 'nicht erkennbar'],
    headwear: ['keine', 'Helm', 'Kappe', 'Hut', 'Mütze', 'andere', 'nicht erkennbar'],
    beard: ['ja', 'nein', 'nicht erkennbar'],
    glasses: ['ja', 'nein', 'Sonnenbrille', 'nicht erkennbar'],
    age_group: ['<=16', '17-30', '31-45', '46-60', '>60', 'nicht erkennbar'],
    body_build: ['schlank', 'normal', 'kräftig', 'nicht erkennbar'],
};

function AttributesPanel({ jobId }: { jobId: string }) {
    const { jobData, handleRunAttributes, progressData, fetchJobData } = useJob();
    const [snapshot, setSnapshot] = useState<AttributeReview | null>(null);
    const [pending, setPending] = useState<Record<string, { person_id: number; field: string; value: string }>>({});
    const [pendingNames, setPendingNames] = useState<Record<number, string>>({});
    const [personsVersion, setPersonsVersion] = useState('');
    const [error, setError] = useState('');
    const [saving, setSaving] = useState(false);
    const [refresh, setRefresh] = useState(0);
    const [open, setOpen] = useState(false);
    const [enlarged, setEnlarged] = useState<string | null>(null);
    const running = jobData?.status === 'running';
    const dirty = Object.keys(pending).length + Object.keys(pendingNames).length > 0;
    useEffect(() => {
        if (running || dirty || saving) return;
        const controller = new AbortController();
        Promise.all([
            fetch(`/api/jobs/${jobId}/person-analysis/attributes`, { signal: controller.signal, cache: 'no-store' }),
            fetch(`/api/jobs/${jobId}/persons`, { signal: controller.signal, cache: 'no-store' }),
        ]).then(async responses => {
            const [data, persons] = await Promise.all(responses.map(async response => {
                const value = await response.json();
                if (!response.ok || value.error) throw new Error(value.error || 'Daten nicht verfügbar.');
                return value;
            }));
            if (controller.signal.aborted) return;
            setSnapshot(data); setPersonsVersion(persons.version); setError('');
        }).catch(err => { if (!controller.signal.aborted) setError(err.message); });
        return () => controller.abort();
    }, [jobId, running, dirty, saving, refresh, jobData?.persons_version, jobData?.attribute_stage?.version, jobData?.attribute_stage?.stale]);


    useEffect(() => {
        if (!open) return;
        const previous = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        return () => { document.body.style.overflow = previous; };
    }, [open]);
    const close = () => {
        if (saving || (dirty && !window.confirm('Ungespeicherte Attributänderungen verwerfen?'))) return;
        setPending({}); setPendingNames({}); setOpen(false); setEnlarged(null);
        if (dirty) setRefresh(n => n + 1);
    };
    const stale = snapshot?.stale || jobData?.attribute_stage?.stale || Boolean(snapshot?.ready && jobData?.attribute_stage && (!jobData.attribute_stage.ready || snapshot.version !== jobData.attribute_stage.version) && dirty);
    const save = async () => {
        setSaving(true); setError('');
        try {
            let version = personsVersion;
            for (const [id, name] of Object.entries(pendingNames)) {
                const response = await fetch(`/api/jobs/${jobId}/persons/${id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version, name }) });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || data.detail || 'Name konnte nicht gespeichert werden.');
                version = data.version;
                setPersonsVersion(version);
                const savedName = data.persons.find((person: { person_id: number }) => person.person_id === Number(id)).name;
                setSnapshot(prev => prev && ({ ...prev, persons: prev.persons.map(person => person.person_id === Number(id) ? { ...person, name: savedName } : person) }));
                setPendingNames(prev => { const next = { ...prev }; delete next[Number(id)]; return next; });
            }
            if (Object.keys(pending).length) {
                const response = await fetch(`/api/jobs/${jobId}/person-analysis/attribute-review`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version: snapshot?.version, changes: Object.values(pending) }) });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Speichern fehlgeschlagen.');
                setSnapshot(data); setPending({});
            }
        } catch (err) { setError(err instanceof Error ? err.message : 'Speichern fehlgeschlagen.'); }
        finally { await fetchJobData(jobId, true); setSaving(false); }
    };
    const imageUrl = (id: number) => `/api/jobs/${jobId}/person-analysis/attributes/${snapshot?.version}/images/${id}`;
    const disabled = running || saving || Boolean(stale);
    return <div className="flex flex-col gap-5">
        <h2 className="text-[1.4rem] font-bold">Attribute</h2>
        <p className="text-sm text-text-secondary">Ausgewählte Personenbilder und automatisch erkannte Attribute. Korrekturen ersetzen die aktuell gespeicherten Werte.</p>
        {stale && <p role="status" className="p-3 border border-amber-500 rounded-lg">Veraltet: Personenstand geändert. Diese Attribute gehören zum bisherigen Lauf. Bitte Attribute nach aktuellem Clustering erneut ausführen.</p>}
        {running && <p role="status">{progressData.attributes?.msg || 'Verarbeitung läuft …'}</p>}
        {error && <p role="alert" className="text-red-400">{error}</p>}
        <button disabled={running || saving || dirty || !jobData?.person_stages?.identities_ready || jobData?.person_stages?.identities_stale} onClick={() => void handleRunAttributes()}
            className="w-fit px-4 py-2 bg-violet-600 text-white rounded-lg disabled:opacity-50">Attribute ausführen</button>
        {snapshot && !snapshot.ready && <p>Noch kein Attributlauf vorhanden.</p>}
        {jobData?.person_stages?.legacy && <p>Für Attribute dieses älteren Jobs bitte zuerst Tracking &amp; Gesichter und Personen &amp; Cluster ausführen. Vorhandene Ergebnisse bleiben verfügbar.</p>}
        {snapshot?.ready && snapshot.persons.length === 0 && <p>Keine zugeordneten Personen.</p>}
        {snapshot?.ready && <div className="p-4 border border-border-subtle rounded-lg flex flex-wrap justify-between items-center gap-3">
            <div><p className="font-medium">{snapshot.persons.length} Personen</p><p className="text-sm text-text-secondary">{stale ? 'Attributlauf veraltet' : 'Attributlauf vorhanden'} · {snapshot.persons.filter(person => person.status === 'ok').length} erfolgreich extrahiert</p></div>
            <button onClick={() => setOpen(true)} className="px-4 py-2 bg-violet-600 text-white rounded-lg">Attribute prüfen / bearbeiten</button>
        </div>}
        {open && snapshot && <div role="dialog" aria-modal="true" aria-label="Attribut-Review" className="fixed inset-0 z-[60] bg-black/60 flex items-center justify-center p-2 sm:p-4"
            onKeyDown={e => { if (e.key === 'Escape' && !enlarged) close(); }}>
            <div className="w-[97vw] h-[94vh] bg-bg-surface rounded-xl border border-border-subtle shadow-2xl flex flex-col overflow-hidden">
                <div className="p-4 border-b border-border-subtle flex justify-between items-center gap-4 shrink-0">
                    <div><h3 className="text-xl font-semibold">Attribute prüfen / bearbeiten</h3><p className="text-sm text-text-secondary">{snapshot.persons.length} Personen · Änderungen gemeinsam speichern</p></div>
                    <button autoFocus disabled={saving} onClick={() => close()} aria-label="Attribut-Review schließen">Schließen ✕</button>
                </div>
                <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-6">
                    {stale && <p role="status" className="text-amber-600">Veraltet: Personenstand geändert. Bitte Attribute nach aktuellem Clustering erneut ausführen.</p>}
                    {snapshot.persons.map(person => <section key={person.person_id} aria-label={`Attribute Person ${person.person_id}`} className="p-4 border border-border-subtle rounded-lg space-y-3">
                    <div>
                        <label htmlFor={`person-name-${person.person_id}`} className="block text-sm mb-1">Name</label>
                        <div className="flex items-center gap-3">
                            <input id={`person-name-${person.person_id}`} aria-label={`Name Person ${person.person_id}`} disabled={disabled} maxLength={10000}
                                value={pendingNames[person.person_id] ?? person.name ?? ''}
                                onChange={e => setPendingNames(prev => { const next = { ...prev }; if (e.target.value === person.name) delete next[person.person_id]; else next[person.person_id] = e.target.value; return next; })}
                                className="w-full max-w-md px-2 py-1.5 bg-bg-card border border-border-subtle rounded text-lg font-semibold" />
                            <span className="text-sm whitespace-nowrap">ID {person.person_id}</span>
                        </div>
                        <div className="flex flex-wrap gap-x-2 text-xs text-text-muted mt-1">
                            <span>Gespeichert: {person.name || '—'}</span>
                            <button disabled={disabled || !(person.person_id in pendingNames)} aria-label={`Eingabe verwerfen: Name Person ${person.person_id}`}
                                onClick={() => setPendingNames(prev => { const next = { ...prev }; delete next[person.person_id]; return next; })} className="underline">Eingabe verwerfen</button>
                            {person.person_id in pendingNames && <span className="text-violet-500">vorgemerkt</span>}
                        </div>
                        <p className="text-xs text-text-secondary mt-1">{statuses[person.status] || person.status}</p>
                    </div>
                    {person.error && <p className="text-sm text-red-400">{person.error}</p>}
                    <div className="flex flex-wrap gap-3">{person.images.map(image => <button key={image.crop_id} onClick={() => setEnlarged(imageUrl(image.crop_id))} aria-label={`Attributbild vergrößern: Track ${image.track_id}`}>
                        <img src={imageUrl(image.crop_id)} alt={`Track ${image.track_id}, Frame ${image.frame_number}`} loading="lazy" className="h-48 sm:h-56 max-w-full object-contain rounded-lg" />
                        <span className="text-xs">Track {image.track_id} · {image.timestamp_s.toFixed(2)} s</span>
                    </button>)}</div>
                    {person.images.length === 0 && <p className="text-sm text-text-secondary">Keine ausgewählten Qwen-Bilder vorhanden.</p>}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3">{snapshot.fields.map(field => {
                        const key = `${person.person_id}:${field}`;
                        const staged = pending[key];
                        const value = staged ? staged.value : person.attributes[field];
                        const options = categoryOptions[field];
                        const inputProps = {
                            id: `attribute-${key}`, 'aria-label': `${snapshot.labels[field]} Person ${person.person_id}`,
                            disabled, value: value || '',
                            onChange: (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setPending(prev => { const next = { ...prev }; if (e.target.value === person.attributes[field]) delete next[key]; else next[key] = { person_id: person.person_id, field, value: e.target.value }; return next; }),
                            className: 'w-full px-2 py-1.5 bg-bg-card border border-border-subtle rounded',
                        };
                        return <div key={field} className={`min-w-0 rounded ${staged ? 'bg-violet-500/10' : ''}`}>
                            <label htmlFor={inputProps.id} className="block text-sm mb-1">{snapshot.labels[field]}</label>
                            {options ? <select {...inputProps}>
                                <option value="">—</option>
                                {value && !options.includes(value) && <option value={value}>{value}</option>}
                                {options.map(option => <option key={option} value={option}>{option}</option>)}
                            </select> : <input {...inputProps} maxLength={1000} />}
                            <div className="flex flex-wrap gap-x-2 text-xs text-text-muted mt-1">
                                <span>Gespeichert: {person.attributes[field] || '—'}</span>
                                <button disabled={disabled || !staged} aria-label={`Eingabe verwerfen: ${snapshot.labels[field]} Person ${person.person_id}`} onClick={() => setPending(prev => { const next = { ...prev }; delete next[key]; return next; })} className="underline">Eingabe verwerfen</button>
                                {staged && <span className="text-violet-500">vorgemerkt</span>}
                            </div>
                        </div>;
                    })}</div></section>)}
                </div>
                <div className="p-4 border-t border-border-subtle bg-bg-card shrink-0">
                    {error && <p role="alert" className="text-red-400 mb-2">{error}</p>}
                    <div className="flex flex-wrap gap-3 items-center justify-between">
                        <div className="flex flex-wrap gap-3 items-center">
                            <span className="text-xs text-text-secondary" aria-live="polite">{Object.keys(pending).length} Attributänderungen · {Object.keys(pendingNames).length} Namensänderungen vorgemerkt</span>
                            <button disabled={saving || !dirty} onClick={() => { if (window.confirm('Ungespeicherte Attributänderungen verwerfen?')) { setPending({}); setPendingNames({}); setRefresh(n => n+1); } }} className="text-xs underline">Verwerfen / Neu laden</button>
                            <button disabled={disabled || !dirty} onClick={() => void save()} className="px-4 py-2 bg-violet-600 text-white rounded-lg disabled:opacity-50">{saving ? 'Wird gespeichert …' : 'Änderungen speichern'}</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>}
        {enlarged && <div role="dialog" aria-modal="true" aria-label="Attributbild" className="fixed inset-0 z-[90] bg-black/90 flex flex-col items-center justify-center p-4" onClick={() => setEnlarged(null)} onKeyDown={e => { if (e.key === 'Escape') setEnlarged(null); }}>
            <button autoFocus className="text-white mb-3" onClick={() => setEnlarged(null)}>Bild schließen</button><img src={enlarged} alt="Ausgewähltes Qwen-Bild" className="max-w-full max-h-[85vh] object-contain" />
        </div>}
    </div>;
}

export function StepAttributes() {
    const { currentStep, jobData } = useJob();
    if (currentStep !== 7) return null;
    return jobData?.job_id ? <AttributesPanel key={jobData.job_id} jobId={jobData.job_id} /> : <p>Bitte zuerst ein Video hochladen.</p>;
}
