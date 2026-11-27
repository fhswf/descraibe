import { useMemo, useState } from 'react';
import type { DragEvent } from 'react';
import type { PersonData, PersonReview, PersonSimilarity } from '../../types';
import { PersonExample } from './FaceMergeDialog';

function similarityBetween(pairs: PersonSimilarity[], first: number, second: number) {
    return pairs.find(pair => (pair.person_a === first && pair.person_b === second)
        || (pair.person_a === second && pair.person_b === first));
}

function orderedPersons(persons: PersonData[], pairs: PersonSimilarity[]) {
    const remaining = new Map(persons.map(person => [person.person_id, person]));
    const ordered: PersonData[] = [];

    while (remaining.size) {
        if (ordered.length === 0) {
            const first = [...remaining.values()].sort((a, b) => b.appearances_count - a.appearances_count || a.person_id - b.person_id)[0];
            if (!first) break;
            ordered.push(first);
            remaining.delete(first.person_id);
            continue;
        }

        const previous = ordered[ordered.length - 1];
        if (!previous) break;
        const nearest = [...remaining.values()].sort((a, b) => {
            const aPair = similarityBetween(pairs, previous.person_id, a.person_id);
            const bPair = similarityBetween(pairs, previous.person_id, b.person_id);
            if (aPair && bPair) return aPair.distance - bPair.distance || a.person_id - b.person_id;
            if (aPair) return -1;
            if (bPair) return 1;
            return b.appearances_count - a.appearances_count || a.person_id - b.person_id;
        })[0];
        if (!nearest) break;
        ordered.push(nearest);
        remaining.delete(nearest.person_id);
    }
    return ordered;
}

export function PersonManagerDialog({ snapshot, jobId, disabled = false, onClose, onDetails, onMerge }: {
    snapshot: PersonReview;
    jobId: string;
    disabled?: boolean;
    onClose: () => void;
    onDetails: (_person: PersonData) => void;
    onMerge: (_source: number, _target: number) => Promise<void>;
}) {
    const [query, setQuery] = useState('');
    const [selectedSource, setSelectedSource] = useState<number | null>(null);
    const [dragSource, setDragSource] = useState<number | null>(null);
    const [pendingMerge, setPendingMerge] = useState<{ source: number; target: number } | null>(null);
    const [merging, setMerging] = useState(false);
    const [error, setError] = useState('');
    const pairs = snapshot.person_similarities || [];
    const suggestions = pairs.filter(pair => pair.suggested).slice(0, 4);
    const persons = useMemo(() => orderedPersons(snapshot.persons || [], pairs), [snapshot.persons, pairs]);
    const choices = persons.filter(person => `${person.person_id} ${person.name || ''} ${person.function || ''}`.toLowerCase().includes(query.toLowerCase()));
    const byId = new Map(persons.map(person => [person.person_id, person]));
    const pendingDistance = pendingMerge ? similarityBetween(pairs, pendingMerge.source, pendingMerge.target) : undefined;

    const startMerge = (source: number, target: number) => {
        if (source === target || disabled || merging) return;
        setSelectedSource(null);
        setPendingMerge({ source, target });
        setError('');
    };
    const dropOn = (event: DragEvent<HTMLElement>, target: number) => {
        event.preventDefault();
        const fromPayload = Number(event.dataTransfer.getData('text/plain'));
        const source = dragSource ?? (Number.isInteger(fromPayload) && fromPayload > 0 ? fromPayload : null);
        setDragSource(null);
        if (source !== null) startMerge(source, target);
    };
    const confirmMerge = async () => {
        if (!pendingMerge || merging) return;
        setMerging(true);
        setError('');
        try {
            await onMerge(pendingMerge.source, pendingMerge.target);
            setPendingMerge(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Zusammenführen fehlgeschlagen.');
        } finally {
            setMerging(false);
        }
    };

    return <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/65 backdrop-blur-sm p-3 sm:p-6" role="dialog" aria-modal="true" aria-label="Personen verwalten"
        onClick={onClose} onKeyDown={event => { if (event.key === 'Escape' && !merging) onClose(); }}>
        <section className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-border-subtle bg-bg-surface shadow-2xl" onClick={event => event.stopPropagation()}>
            <header className="flex items-start justify-between gap-4 border-b border-border-subtle px-5 py-4 sm:px-7">
                <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-[0.16em] text-violet-400">Identitäten</p>
                    <h2 className="text-xl font-semibold">Personen verwalten <span className="ml-1 text-sm font-normal text-text-muted">{persons.length}</span></h2>
                    <p className="mt-1 text-sm text-text-secondary">{pairs.length > 0
                        ? 'Ähnliche Personen stehen nebeneinander. Ziehe eine Karte auf eine andere oder wähle „Zusammenführen“.'
                        : persons.length > 1
                            ? 'Ziehe eine Karte auf eine andere oder wähle „Zusammenführen“. Für diesen Analysestand liegen keine Ähnlichkeitswerte vor.'
                            : 'Öffne die Details einer Person, um ihre Auftritte und Bilder zu verwalten.'}</p>
                </div>
                <button autoFocus onClick={onClose} aria-label="Personenverwaltung schließen" className="rounded-lg px-2 py-1 text-xl text-text-muted hover:bg-bg-card hover:text-text-primary">×</button>
            </header>

            <div className="flex flex-wrap items-center gap-3 border-b border-border-subtle px-5 py-3 sm:px-7">
                <label className="relative min-w-[220px] flex-1">
                    <span className="material-icons-round pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-base text-text-muted">search</span>
                    <input aria-label="Personen suchen" placeholder="Name oder ID suchen" value={query} onChange={event => setQuery(event.target.value)}
                        className="w-full rounded-xl border border-border-subtle bg-bg-card py-2 pl-10 pr-3 text-sm outline-none focus:border-violet-500" />
                </label>
                <p className="text-xs text-text-muted">d_cos = 1 − cos(θ); kleiner ist ähnlicher.</p>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-5 sm:px-7">
                {suggestions.length > 0 && <section className="mb-5 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.06] p-4" aria-label="Vorgeschlagene Zusammenführungen">
                    <div className="mb-3 flex items-center gap-2 text-sm font-medium"><span className="material-icons-round text-base text-emerald-400">auto_awesome</span>Ähnliche Personen gefunden</div>
                    <div className="flex flex-wrap gap-2">
                        {suggestions.map(pair => {
                            const first = byId.get(pair.person_a);
                            const second = byId.get(pair.person_b);
                            if (!first || !second) return null;
                            return <button key={`${pair.person_a}-${pair.person_b}`} disabled={disabled || merging}
                                onClick={() => startMerge(pair.person_a, pair.person_b)}
                                className="rounded-full border border-emerald-500/20 bg-bg-card px-3 py-1.5 text-xs transition hover:border-emerald-400/60 disabled:opacity-50">
                                {first.name || `Person ${first.person_id}`} + {second.name || `Person ${second.person_id}`} <span className="ml-1 text-emerald-300">· d_cos {pair.distance.toFixed(4)}</span>
                            </button>;
                        })}
                    </div>
                </section>}

                {selectedSource !== null && <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-violet-500/30 bg-violet-500/10 px-4 py-3 text-sm" role="status">
                    <span>Wähle die Zielperson für <strong>{byId.get(selectedSource)?.name || `Person ${selectedSource}`}</strong>.</span>
                    <button onClick={() => setSelectedSource(null)} className="text-xs underline">Abbrechen</button>
                </div>}

                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    {choices.map(person => {
                        const pair = pairs.filter(item => item.person_a === person.person_id || item.person_b === person.person_id)
                            .sort((a, b) => a.distance - b.distance)[0];
                        const nearbyId = pair ? (pair.person_a === person.person_id ? pair.person_b : pair.person_a) : null;
                        const nearby = nearbyId === null ? undefined : byId.get(nearbyId);
                        const isMergeTarget = selectedSource !== null && selectedSource !== person.person_id;
                        const selectedPair = selectedSource !== null && isMergeTarget
                            ? similarityBetween(pairs, selectedSource, person.person_id) : undefined;
                        const selectedPerson = selectedSource === null ? undefined : byId.get(selectedSource);
                        return <article key={person.person_id} draggable={!disabled && !merging}
                            onDragStart={event => { setDragSource(person.person_id); event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', String(person.person_id)); }}
                            onDragEnd={() => setDragSource(null)} onDragOver={event => { if (dragSource !== null && dragSource !== person.person_id) event.preventDefault(); }}
                            onDrop={event => dropOn(event, person.person_id)}
                            className={`group overflow-hidden rounded-2xl border bg-bg-card transition ${dragSource === person.person_id ? 'opacity-50' : ''} ${isMergeTarget ? 'border-violet-400/60 ring-1 ring-violet-400/20' : 'border-border-subtle hover:border-violet-500/40'}`}>
                            <div className="relative flex h-44 items-center justify-center overflow-hidden bg-black/20">
                                <PersonExample key={`${snapshot.analysis_id}:${person.representative_crop_id}`} person={person} jobId={jobId} analysisId={snapshot.analysis_id} />
                                {person.profile_crop_id != null && <span className="absolute left-3 top-3 rounded-full border border-white/10 bg-black/65 px-2 py-1 text-[10px] font-medium uppercase tracking-wide text-white">Profilbild</span>}
                                <span className="absolute bottom-3 right-3 rounded-full bg-black/65 px-2.5 py-1 text-xs text-white">ID {person.person_id}</span>
                            </div>
                            <div className="p-4">
                                <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                        <h3 className="truncate font-semibold">{person.name || `Person ${person.person_id}`}</h3>
                                        <p className="mt-0.5 truncate text-xs text-text-secondary">{person.function || 'Keine Funktion angegeben'}</p>
                                    </div>
                                    <span className="shrink-0 rounded-lg bg-bg-surface px-2 py-1 text-xs text-text-secondary">{person.appearances_count} Auftritte</span>
                                </div>
                                {isMergeTarget && selectedPerson ? <p className="mt-3 flex items-center gap-1.5 text-xs text-text-muted">
                                    <span className="material-icons-round text-sm text-violet-400">hub</span>
                                    d_cos zu {selectedPerson.name || `Person ${selectedPerson.person_id}`}: <span className="font-mono">{selectedPair ? selectedPair.distance.toFixed(4) : 'nicht verfügbar'}</span>
                                    {selectedPair?.suggested && <span className="ml-auto text-emerald-400">Vorschlag</span>}
                                </p> : nearby && <p className="mt-3 flex items-center gap-1.5 text-xs text-text-muted">
                                    <span className="material-icons-round text-sm text-violet-400">hub</span>
                                    Niedrigster d_cos zu {nearby.name || `Person ${nearby.person_id}`}: <span className="font-mono">{pair?.distance.toFixed(4)}</span>
                                    {pair?.suggested && <span className="ml-auto text-emerald-400">Vorschlag</span>}
                                </p>}
                                <div className="mt-4 flex gap-2">
                                    <button disabled={disabled || merging} onClick={() => onDetails(person)}
                                        className="flex-1 rounded-lg border border-border-subtle px-3 py-2 text-sm transition hover:border-violet-500/50 hover:bg-bg-surface disabled:opacity-50">
                                        Details
                                    </button>
                                    {selectedSource !== null && selectedSource !== person.person_id ?
                                        <button disabled={disabled || merging} onClick={() => startMerge(selectedSource, person.person_id)}
                                            className="flex-1 rounded-lg bg-violet-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-violet-500 disabled:opacity-50">Hier zusammenführen</button> :
                                        <button disabled={disabled || merging || persons.length < 2} onClick={() => setSelectedSource(current => current === person.person_id ? null : person.person_id)}
                                            className={`flex-1 rounded-lg px-3 py-2 text-sm transition disabled:opacity-50 ${selectedSource === person.person_id ? 'bg-violet-600 text-white' : 'border border-border-subtle hover:border-violet-500/50 hover:bg-bg-surface'}`}
                                            aria-label={`Person ${person.person_id} zum Zusammenführen auswählen`}>
                                            {selectedSource === person.person_id ? 'Person gewählt' : 'Zusammenführen'}
                                        </button>}
                                </div>
                            </div>
                        </article>;
                    })}
                </div>
                {choices.length === 0 && <p className="py-12 text-center text-sm text-text-muted">Keine Person passt zur Suche.</p>}
                {persons.length === 0 && <p className="py-12 text-center text-sm text-text-muted">Für dieses Video wurden keine Personen gefunden.</p>}
            </div>

            {pendingMerge && <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle bg-bg-card px-5 py-4 sm:px-7">
                <div><p className="text-sm">Alle Tracks von <strong>{byId.get(pendingMerge.source)?.name || `Person ${pendingMerge.source}`}</strong> werden <strong>{byId.get(pendingMerge.target)?.name || `Person ${pendingMerge.target}`}</strong> zugeordnet.</p>
                    <p className="mt-1 text-xs text-text-muted">Cosine-Abstand: <span className="font-mono">{pendingDistance ? pendingDistance.distance.toFixed(4) : 'nicht verfügbar'}</span></p></div>
                <div className="flex gap-2"><button disabled={merging} onClick={() => setPendingMerge(null)} className="rounded-lg px-3 py-2 text-sm">Abbrechen</button>
                    <button disabled={disabled || merging} onClick={() => void confirmMerge()} className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-500 disabled:opacity-50">{merging ? 'Führe zusammen …' : 'Zusammenführen bestätigen'}</button></div>
            </footer>}
            {error && <p role="alert" className="border-t border-red-500/20 px-5 py-3 text-sm text-red-400 sm:px-7">{error}</p>}
        </section>
    </div>;
}
