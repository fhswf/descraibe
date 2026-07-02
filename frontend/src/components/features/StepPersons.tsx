import React, { useState, useEffect, useRef } from 'react';
import { useJob } from '../../hooks/useJob.jsx';
import { FaceMergeDialog, PersonData } from './FaceMergeDialog.jsx';

// Extended person type from API response (re-exported from FaceMergeDialog)
// Re-export for convenience
export type { PersonData };

interface MergeSuggestion {
    person_a: { person_id: number; name?: string };
    person_b: { person_id: number; name?: string };
    similarity: number;
}

interface MergePersonsDialogProps {
    persons: PersonData[];
    jobId: string | undefined;
    onMerge: (_sourceId: number, _targetId: number) => Promise<void>;
    onClose: () => void;
    initialSourceId: number | null;
}

interface ColorBadgeProps {
    color?: string;
    label?: string;
}

interface EditPersonDialogProps {
    person: PersonData;
    onSave: (_personId: number, _data: { name: string; description: string }) => Promise<void>;
    onClose: () => void;
}

interface PersonCardProps {
    person: PersonData;
    onEdit: (_person: PersonData) => void;
    onMergeFaces?: (_person: PersonData) => void;
    onMergeInto?: (_personId: number) => void;
    onDelete?: (_personId: number) => void;
    jobId: string | undefined;
}

function formatTimestamp(seconds: number | undefined): string {
    if (!seconds && seconds !== 0) return '-';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function MergePersonsDialog({ persons, jobId, onMerge, onClose, initialSourceId }: MergePersonsDialogProps) {
    const [sourceId, setSourceId] = useState<number | null>(initialSourceId || null);
    const [targetId, setTargetId] = useState<number | null>(null);
    const [saving, setSaving] = useState(false);
    const [suggestions, setSuggestions] = useState<MergeSuggestion[]>([]);
    const [loadingSuggestions, setLoadingSuggestions] = useState(false);

    useEffect(() => {
        if (!jobId) return;
        setLoadingSuggestions(true);
        fetch(`/api/jobs/${jobId}/persons/merge-suggestions`)
            .then(res => res.json())
            .then(data => setSuggestions(data.suggestions || []))
            .catch(err => console.error('Failed to load merge suggestions:', err))
            .finally(() => setLoadingSuggestions(false));
    }, [jobId]);

    const handleMerge = async (srcId?: number, tgtId?: number): Promise<void> => {
        const sId = srcId !== undefined ? srcId : sourceId;
        const tId = tgtId !== undefined ? tgtId : targetId;
        if (!sId || !tId || sId === tId) return;
        setSaving(true);
        try {
            await onMerge(sId, tId);
            onClose();
        } catch (err) {
            console.error('Failed to merge persons:', err);
        } finally {
            setSaving(false);
        }
    };

    const selectedSource = persons.find(p => p.person_id === sourceId);
    const selectedTarget = persons.find(p => p.person_id === targetId);

    return (
        <div 
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
            onClick={onClose}
        >
            <div 
                className="bg-bg-surface border border-border-subtle rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[90vh] overflow-hidden flex flex-col"
                onClick={e => e.stopPropagation()}
            >
                <div className="flex items-center justify-between p-4 border-b border-border-subtle shrink-0">
                    <h3 className="text-lg font-semibold">Personen zusammenführen</h3>
                    <button 
                        onClick={onClose}
                        className="p-1 hover:bg-bg-card rounded-lg transition-colors"
                    >
                        <span className="material-icons-round text-text-muted">close</span>
                    </button>
                </div>
                
                <div className="p-4 space-y-4 overflow-y-auto flex-1">
                    {loadingSuggestions ? (
                        <div className="flex items-center gap-2 text-xs text-text-muted py-2 bg-violet-950/10 border border-violet-500/10 rounded-lg justify-center">
                            <div className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
                            Lade Vorschläge...
                        </div>
                    ) : suggestions.length > 0 ? (
                        <div className="space-y-2">
                            <h4 className="text-xs font-semibold text-violet-400 uppercase tracking-wider">Vorschläge zum Zusammenführen</h4>
                            <div className="space-y-2 max-h-[200px] overflow-y-auto pr-1">
                                {suggestions.map(({ person_a, person_b, similarity }) => (
                                    <div key={`${person_a.person_id}-${person_b.person_id}`} className="flex items-center justify-between p-2.5 bg-violet-950/20 border border-violet-500/20 rounded-lg">
                                        <div className="text-xs">
                                            <span className="font-medium text-text-primary">{person_a.name || `Person ${person_a.person_id}`}</span> 
                                            {' '}und{' '}
                                            <span className="font-medium text-text-primary">{person_b.name || `Person ${person_b.person_id}`}</span>
                                            <div className="text-text-muted mt-0.5">Übereinstimmung: {(similarity * 100).toFixed(0)}%</div>
                                        </div>
                                        <button
                                            onClick={() => handleMerge(person_a.person_id, person_b.person_id)}
                                            disabled={saving}
                                            className="px-2.5 py-1 text-xs font-medium bg-violet-600 hover:bg-violet-500 text-white rounded transition-colors"
                                        >
                                            Zusammenführen
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ) : null}

                    <p className="text-sm text-text-secondary">
                        Wähle zwei Personen aus, die zusammengeführt werden sollen. 
                        Die zweite Person wird zur ersten hinzugefügt und dann gelöscht.
                    </p>
                    
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-medium text-text-secondary mb-1.5">
                                Person die entfernt wird
                            </label>
                            <select
                                value={sourceId || ''}
                                onChange={e => setSourceId(e.target.value ? parseInt(e.target.value) : null)}
                                className="w-full px-3 py-2 bg-bg-card border border-border-subtle rounded-lg text-sm
                                           focus:outline-none focus:ring-2 focus:ring-violet-500"
                            >
                                <option value="">-- Auswählen --</option>
                                {persons
                                    .sort((a, b) => (b.appearances_count || 1) - (a.appearances_count || 1))
                                    .map(p => (
                                        <option key={p.person_id} value={p.person_id}>
                                            {p.name || `Person ${p.person_id}`} ({p.appearances_count}x)
                                        </option>
                                    ))}
                            </select>
                            {selectedSource && (
                                <div className="mt-2 text-xs text-text-muted">
                                    {selectedSource.appearances_count} Auftritte
                                </div>
                            )}
                        </div>
                        
                        <div>
                            <label className="block text-sm font-medium text-text-secondary mb-1.5">
                                Person die bleibt
                            </label>
                            <select
                                value={targetId || ''}
                                onChange={e => setTargetId(e.target.value ? parseInt(e.target.value) : null)}
                                className="w-full px-3 py-2 bg-bg-card border border-border-subtle rounded-lg text-sm
                                           focus:outline-none focus:ring-2 focus:ring-violet-500"
                            >
                                <option value="">-- Auswählen --</option>
                                {persons
                                    .filter(p => p.person_id !== sourceId)
                                    .sort((a, b) => (b.appearances_count || 1) - (a.appearances_count || 1))
                                    .map(p => (
                                        <option key={p.person_id} value={p.person_id}>
                                            {p.name || `Person ${p.person_id}`} ({p.appearances_count}x)
                                        </option>
                                    ))}
                            </select>
                            {selectedTarget && (
                                <div className="mt-2 text-xs text-text-muted">
                                    {selectedTarget.appearances_count} Auftritte
                                </div>
                            )}
                        </div>
                    </div>

                    {sourceId && targetId && sourceId !== targetId && (
                         <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                             <p className="text-sm text-amber-300">
                                 <strong>Achtung:</strong> Person {sourceId} wird mit Person {targetId}
                                 zusammengeführt. Alle Auftritte von Person {sourceId} werden zu Person {targetId}
                                 hinzugefügt. Diese Aktion kann nicht rückgängig gemacht werden.
                             </p>
                         </div>
                     )}
                </div>

                <div className="flex justify-end gap-2 p-4 border-t border-border-subtle shrink-0">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary
                                   hover:bg-bg-card rounded-lg transition-colors"
                        disabled={saving}
                    >
                        Abbrechen
                    </button>
                    <button
                        onClick={() => handleMerge()}
                        disabled={!sourceId || !targetId || sourceId === targetId || saving}
                        className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-500
                                   disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
                    >
                        {saving ? (
                            <>
                                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                                Zusammenführen...
                            </>
                        ) : (
                            <>
                                <span className="material-icons-round text-sm">merge</span>
                                Zusammenführen
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
}

function ColorBadge({ color, label }: ColorBadgeProps) {
    if (!color) return null;
    const colorMap: Record<string, string> = {
        'rot': 'bg-red-600', 'blau': 'bg-blue-600', 'grün': 'bg-green-600',
        'gelb': 'bg-yellow-500', 'schwarz': 'bg-gray-900', 'weiß': 'bg-white',
        'braun': 'bg-amber-800', 'grau': 'bg-gray-500', 'orange': 'bg-orange-500',
        'violett': 'bg-purple-600', 'rosa': 'bg-pink-400', 'dunkelblau': 'bg-blue-900',
        'dunkelbraun': 'bg-amber-950', 'hellgrau': 'bg-gray-300', 'dunkelgrau': 'bg-gray-700',
        'türkis': 'bg-teal-500', 'olivgrün': 'bg-green-900', 'navy': 'bg-blue-950',
    };
    const bgClass = colorMap[color] || 'bg-gray-400';
    return (
        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs text-white ${bgClass}`}>
            {label && <span className="opacity-75">{label}:</span>}
            {color}
        </span>
    );
}

function EditPersonDialog({ person, onSave, onClose }: EditPersonDialogProps) {
    const [name, setName] = useState(person.name || '');
    const [description, setDescription] = useState(person.description || '');
    const [saving, setSaving] = useState(false);

    const handleSave = async (): Promise<void> => {
        setSaving(true);
        try {
            await onSave(person.person_id, { name, description });
            onClose();
        } catch (err) {
            console.error('Failed to save person:', err);
        } finally {
            setSaving(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent): void => {
        if (e.key === 'Escape') onClose();
        if (e.key === 'Enter' && e.ctrlKey) handleSave();
    };

    const attributes = person.attributes ? (typeof person.attributes === 'string' ? JSON.parse(person.attributes) : person.attributes) : {} as Record<string, string>;

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
            onClick={onClose}
            onKeyDown={handleKeyDown}
        >
            <div
                className="bg-bg-surface border border-border-subtle rounded-xl shadow-2xl w-full max-w-md mx-4"
                onClick={e => e.stopPropagation()}
            >
                <div className="flex items-center justify-between p-4 border-b border-border-subtle">
                    <h3 className="text-lg font-semibold">Person bearbeiten</h3>
                    <button
                        onClick={onClose}
                        className="p-1 hover:bg-bg-card rounded-lg transition-colors"
                    >
                        <span className="material-icons-round text-text-muted">close</span>
                    </button>
                </div>

                <div className="p-4 space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-text-secondary mb-1.5">
                            Name
                        </label>
                        <input
                            type="text"
                            value={name}
                            onChange={e => setName(e.target.value)}
                            placeholder="z.B. Moderator, Interviewpartner..."
                            className="w-full px-3 py-2 bg-bg-card border border-border-subtle rounded-lg text-sm
                                       focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent
                                       placeholder:text-text-muted"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-text-secondary mb-1.5">
                            Beschreibung
                        </label>
                        <textarea
                            value={description}
                            onChange={e => setDescription(e.target.value)}
                            placeholder="Zusätzliche Informationen..."
                            rows={3}
                            className="w-full px-3 py-2 bg-bg-card border border-border-subtle rounded-lg text-sm
                                       focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent
                                       placeholder:text-text-muted resize-none"
                        />
                    </div>

                    <div className="flex flex-wrap gap-1.5">
                        <ColorBadge color={attributes?.top_color} label="Oben" />
                        <ColorBadge color={attributes?.bottom_color} label="Unten" />
                        <ColorBadge color={attributes?.dominant_color} label="Hauptfarbe" />
                    </div>

                    <div className="text-xs text-text-muted">
                        {person.appearances_count} Auftritt{person.appearances_count !== 1 ? 'e' : ''} • {' '}
                        {formatTimestamp(person.first_seen_ts)} - {formatTimestamp(person.last_seen_ts)}
                    </div>
                </div>

                <div className="flex justify-end gap-2 p-4 border-t border-border-subtle">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary
                                   hover:bg-bg-card rounded-lg transition-colors"
                        disabled={saving}
                    >
                        Abbrechen
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={saving}
                        className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500
                                   disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
                    >
                        {saving ? (
                            <>
                                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                                Speichern...
                            </>
                        ) : (
                            <>
                                <span className="material-icons-round text-sm">save</span>
                                Speichern
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
}

function PersonCard({ person, onEdit, onMergeFaces, onMergeInto, onDelete, jobId }: PersonCardProps) {
    const [imgError, setImgError] = useState(false);
    // Use face crop if available, otherwise fall back to full frame
    const faceCrop = person.representative_crop;
    const imageName = person.representative_image ? person.representative_image.split('/').pop() : null;
    // Face crop URL: /api/jobs/{jobId}/faces/{faceId}
    const faceId = faceCrop ? parseInt(faceCrop.match(/face_(\d+)/)?.[1] || '') : null;
    const faceImageUrl = faceId && jobId ? `/api/jobs/${jobId}/faces/${faceId}` : null;
    const frameImageUrl = imageName && jobId ? `/api/jobs/${jobId}/images/${imageName}` : null;

    const attributes = person.attributes ? (typeof person.attributes === 'string' ? JSON.parse(person.attributes) : person.attributes) : {};

    return (
        <div className="flex flex-col gap-2 p-3 bg-bg-card border border-border-subtle rounded-lg">
            <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                    {faceImageUrl && !imgError ? (
                        <img
                            src={faceImageUrl}
                            alt={`Person ${person.person_id}`}
                            className="w-12 h-12 rounded-full object-cover ring-2 ring-primary/30"
                            onError={() => setImgError(true)}
                        />
                    ) : frameImageUrl && !imgError ? (
                        <img
                            src={frameImageUrl}
                            alt={`Person ${person.person_id}`}
                            className="w-12 h-12 rounded-lg object-cover ring-1 ring-border-subtle"
                            onError={() => setImgError(true)}
                        />
                    ) : (
                        <span className="text-lg">👤</span>
                    )}
                    <div>
                        <div className="font-medium text-sm">
                            {person.name || `Person ${person.person_id}`}
                        </div>
                        {person.name && (
                            <div className="text-xs text-text-muted">
                                Person {person.person_id}
                            </div>
                        )}
                    </div>
                </div>
                <div className="flex items-center gap-1">
                    <div className="text-xs text-text-muted text-right mr-2">
                        <div>{person.appearances_count} Auftritt{person.appearances_count !== 1 ? 'e' : ''}</div>
                        <div>{formatTimestamp(person.first_seen_ts)} - {formatTimestamp(person.last_seen_ts)}</div>
                    </div>
                    <button
                        onClick={() => onEdit(person)}
                        className="p-1.5 hover:bg-bg-card rounded-lg transition-colors"
                        title="Bearbeiten"
                    >
                        <span className="material-icons-round text-sm text-text-muted hover:text-text-primary">edit</span>
                    </button>
                    {onMergeFaces && (
                        <button
                            onClick={() => onMergeFaces(person)}
                            className="p-1.5 hover:bg-bg-card rounded-lg transition-colors"
                            title="Gesichter verwalten"
                        >
                            <span className="material-icons-round text-sm text-text-muted hover:text-text-primary">face</span>
                        </button>
                    )}
                    {onMergeInto && (
                        <button
                            onClick={() => onMergeInto(person.person_id)}
                            className="p-1.5 hover:bg-bg-card rounded-lg transition-colors"
                            title="In eine andere Person zusammenführen"
                        >
                            <span className="material-icons-round text-sm text-text-muted hover:text-text-primary">call_merge</span>
                        </button>
                    )}
                    {onDelete && (
                        <button
                            onClick={() => onDelete(person.person_id)}
                            className="p-1.5 hover:bg-bg-card rounded-lg transition-colors"
                            title="Person löschen"
                        >
                            <span className="material-icons-round text-sm text-text-muted hover:text-red-500">delete</span>
                        </button>
                    )}
                </div>
            </div>

            {(attributes as Record<string, string>).top_color || (attributes as Record<string, string>).bottom_color || (attributes as Record<string, string>).dominant_color ? (
                <div className="flex flex-wrap gap-1.5">
                    <ColorBadge color={(attributes as Record<string, string>).top_color} label="Oben" />
                    <ColorBadge color={(attributes as Record<string, string>).bottom_color} label="Unten" />
                    <ColorBadge color={(attributes as Record<string, string>).dominant_color} label="Hauptfarbe" />
                </div>
            ) : null}

            {person.description && (
                <div className="text-xs text-text-secondary pt-1 border-t border-border-subtle">
                    {person.description}
                </div>
            )}
        </div>
    );
}

export function StepPersons() {
    const { currentStep, jobData, handleRunPersons, progressData } = useJob();
    const [persons, setPersons] = useState<PersonData[]>([]);
    const [loading, setLoading] = useState(false);
    const [editingPerson, setEditingPerson] = useState<PersonData | null>(null);
    const [mergingPersons, setMergingPersons] = useState(false);
    const [mergeInitialSourceId, setMergeInitialSourceId] = useState<number | null>(null);
    const [mergingFacesPerson, setMergingFacesPerson] = useState<PersonData | null>(null);
    const [filter, setFilter] = useState<'main' | 'all' | 'statists'>('main');
    const jobDataRef = useRef(jobData);
    jobDataRef.current = jobData;

    useEffect(() => {
        if (currentStep !== 5) return;
        setLoading(true);
        const jobId = jobDataRef.current?.job_id;
        if (jobId) {
            fetch(`/api/jobs/${jobId}/persons`)
                .then(res => res.json())
                .then(data => setPersons(data.persons || []))
                .finally(() => setLoading(false));
        } else {
            setLoading(false);
        }
    }, [currentStep, jobData?.persons_count]);

    if (currentStep !== 5) return null;

    const isRunning = jobData?.status === 'running';
    const progressMsg = progressData.persons?.msg;
    const progressPercent = progressData.persons?.percent ?? null;

    const personsCount = persons.length;
    const mainCastCount = persons.filter(p => (p.appearances_count || 1) >= 5).length;
    const statistsCount = persons.filter(p => (p.appearances_count || 1) < 3).length;

    const filteredPersons = persons.filter(p => {
        const appearances = p.appearances_count || 1;
        if (filter === 'main') return appearances >= 5;
        if (filter === 'statists') return appearances < 3;
        return true;
    });

    const handleMergeFacesRefresh = (): void => {
        // Refresh persons from API
        const jobId = jobDataRef.current?.job_id;
        if (jobId) {
            fetch(`/api/jobs/${jobId}/persons`)
                .then(res => res.json())
                .then(data => setPersons(data.persons || []));
        }
    };

    const handleSavePerson = async (personId: number, updates: { name: string; description: string }): Promise<void> => {
        try {
            const res = await fetch(`/api/jobs/${jobData?.job_id}/persons/${personId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });
            if (!res.ok) {
                throw new Error("Save failed");
            }
            setPersons(prev => prev.map(p =>
                p.person_id === personId
                    ? { ...p, ...updates }
                    : p
            ));
        } catch (err) {
            console.error('Failed to save person details:', err);
            setPersons(prev => prev.map(p =>
                p.person_id === personId
                    ? { ...p, ...updates }
                    : p
            ));
        }
    };

    const handleMergePersons = async (sourceId: number, targetId: number): Promise<void> => {
        const source = persons.find(p => p.person_id === sourceId);
        const target = persons.find(p => p.person_id === targetId);

        if (!source || !target) return;

        try {
            const res = await fetch(`/api/jobs/${jobData?.job_id}/persons/merge`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_person_id: sourceId, target_person_id: targetId })
            });
            if (!res.ok) {
                throw new Error("Merge failed");
            }
            handleMergeFacesRefresh();
        } catch (err) {
            console.error('Failed to merge persons:', err);
            const mergedPerson: PersonData = {
                ...target,
                person_id: targetId,
                appearances_count: (target.appearances_count || 1) + (source.appearances_count || 1),
                first_seen_ts: Math.min(target.first_seen_ts || Infinity, source.first_seen_ts || Infinity),
                last_seen_ts: Math.max(target.last_seen_ts || 0, source.last_seen_ts || 0),
                name: target.name || source.name || undefined,
                description: target.description || source.description || '',
                attributes: { ...(source.attributes as Record<string, string> || {}), ...(target.attributes as Record<string, string> || {}) },
            };
            setPersons(prev => [
                ...prev.filter(p => p.person_id !== sourceId),
                ...prev.filter(p => p.person_id === targetId).map(() => mergedPerson)
            ]);
        }
    };

    const handleDeletePerson = async (personId: number): Promise<void> => {
        if (!window.confirm("Möchtest du diese Person wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.")) return;
        try {
            const res = await fetch(`/api/jobs/${jobData?.job_id}/persons/${personId}`, {
                method: 'DELETE'
            });
            if (!res.ok) {
                throw new Error("Delete failed");
            }
            setPersons(prev => prev.filter(p => p.person_id !== personId));
        } catch (err) {
            console.error('Failed to delete person:', err);
            setPersons(prev => prev.filter(p => p.person_id !== personId));
        }
    };

    return (
        <div className="flex flex-col gap-5">
            {editingPerson && (
                <EditPersonDialog
                    person={editingPerson}
                    onSave={handleSavePerson}
                    onClose={() => setEditingPerson(null)}
                />
            )}

            {mergingPersons && (
                <MergePersonsDialog
                    persons={persons}
                    jobId={jobData?.job_id}
                    initialSourceId={mergeInitialSourceId}
                    onMerge={handleMergePersons}
                    onClose={() => {
                        setMergingPersons(false);
                        setMergeInitialSourceId(null);
                    }}
                />
            )}

            {mergingFacesPerson && (
                <FaceMergeDialog
                    person={mergingFacesPerson}
                    jobId={jobData?.job_id || ''}
                    onClose={() => setMergingFacesPerson(null)}
                    onRefresh={handleMergeFacesRefresh}
                />
            )}

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
                {personsCount > 0 && !isRunning && !loading && (
                    <div className="flex flex-col gap-3">
                        <div className="flex items-center gap-2">
                            <span className="material-icons-round text-green-500 text-lg">check_circle</span>
                            <span className="text-sm font-medium text-green-300">
                                {personsCount} {personsCount === 1 ? 'Person' : 'Personen'} erkannt
                            </span>
                        </div>
                        
                        {/* Filter tabs */}
                        <div className="flex gap-1 p-1 bg-bg-card rounded-lg w-fit">
                            <button
                                onClick={() => setFilter('main')}
                                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                                    filter === 'main' 
                                        ? 'bg-violet-600 text-white' 
                                        : 'text-text-secondary hover:text-text-primary'
                                }`}
                            >
                                Hauptbesetzung ({mainCastCount})
                            </button>
                            <button
                                onClick={() => setFilter('all')}
                                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                                    filter === 'all' 
                                        ? 'bg-violet-600 text-white' 
                                        : 'text-text-secondary hover:text-text-primary'
                                }`}
                            >
                                Alle ({personsCount})
                            </button>
                            <button
                                onClick={() => setFilter('statists')}
                                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                                    filter === 'statists' 
                                        ? 'bg-violet-600 text-white' 
                                        : 'text-text-secondary hover:text-text-primary'
                                }`}
                            >
                                Statisten ({statistsCount})
                            </button>
                        </div>
                        
                        {/* Person cards */}
                        <div className="flex flex-col gap-2 max-h-[60vh] overflow-y-auto pr-1">
                            {filteredPersons.length === 0 ? (
                                <div className="text-sm text-text-muted p-4 text-center">
                                    Keine Personen in dieser Kategorie.
                                </div>
                            ) : (
                                filteredPersons
                                    .sort((a, b) => (b.appearances_count || 1) - (a.appearances_count || 1))
                                    .map(person => (
                                        <PersonCard 
                                            key={person.person_id} 
                                            person={person} 
                                            onEdit={setEditingPerson}
                                            onMergeFaces={setMergingFacesPerson}
                                            onMergeInto={(pid) => {
                                                setMergeInitialSourceId(pid);
                                                setMergingPersons(true);
                                            }}
                                            onDelete={handleDeletePerson}
                                            jobId={jobData?.job_id}
                                        />
                                    ))
                            )}
                        </div>
                    </div>
                )}

                {personsCount === 0 && !isRunning && !loading && (
                    <div className="flex items-center gap-2 p-3 bg-bg-card border border-border-subtle rounded-lg">
                        <span className="material-icons-round text-text-muted text-lg">info</span>
                        <span className="text-sm text-text-secondary">
                            Keine Personen in den extrahierten Frames gefunden.
                        </span>
                    </div>
                )}

                {loading && !isRunning && (
                    <div className="flex items-center gap-2 p-3 text-sm text-text-muted">
                        <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
                        Lade Personendaten...
                    </div>
                )}

                {/* Action buttons */}
                {!isRunning && (
                    <div className="flex gap-2">
                        <button
                            className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
                            onClick={handleRunPersons}
                            disabled={!jobData?.images_count}
                        >
                            <span className="material-icons-round text-lg">search</span>
                            Personen analysieren
                        </button>
                        
                        {personsCount > 0 && (
                            <button
                                className="flex items-center gap-2 px-4 py-2 bg-bg-card hover:bg-bg-surface border border-border-subtle text-text-secondary hover:text-text-primary text-sm font-medium rounded-lg transition-colors"
                                onClick={() => setMergingPersons(true)}
                            >
                                <span className="material-icons-round text-lg">merge</span>
                                Zusammenführen
                            </button>
                        )}
                    </div>
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
