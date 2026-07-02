import { useState, useMemo, useEffect, useCallback, memo } from 'react';

export interface PersonData {
    person_id: number;
    name?: string;
    attributes?: string | Record<string, string>;
    appearances_count?: number;
    description?: string;
    representative_crop?: string;
    representative_image?: string;
    first_seen_ts?: number;
    last_seen_ts?: number;
    face_ids?: string | string[];
    [key: string]: unknown;
}

interface FaceMergeDialogProps {
    person: PersonData;
    jobId: string;
    onClose: () => void;
    onRefresh: () => void;
}

interface SimilarFace {
    face: {
        face_id: string;
    };
    similarity: number;
}

interface UnassignedFace {
    face_id: string;
}

interface FaceThumbnailProps {
    faceId: string;
    jobId: string;
    isOwn?: boolean;
    similarity?: number;
    selectable?: boolean;
    selected?: boolean;
    onToggle?: (_: string) => void;
    similarityColor?: string;
}

export function FaceMergeDialog({ person, jobId, onClose, onRefresh }: FaceMergeDialogProps) {
    const [similarFaces, setSimilarFaces] = useState<SimilarFace[]>([]);
    const [unassignedFaces, setUnassignedFaces] = useState<UnassignedFace[]>([]);
    const [selectedForMerge, setSelectedForMerge] = useState<Set<string>>(new Set());
    const [selectedForSplit, setSelectedForSplit] = useState<Set<string>>(new Set());
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [threshold, setThreshold] = useState(0.6);

    const faceIds = useMemo((): string[] => {
        if (!person.face_ids) return [];
        if (typeof person.face_ids === "string") {
            try { return JSON.parse(person.face_ids); } catch { return []; }
        }
        return person.face_ids || [];
    }, [person.face_ids]);

    useEffect(() => {
        async function fetchSimilarFaces(): Promise<void> {
            setLoading(true);
            try {
                const res = await fetch(`/api/jobs/${jobId}/persons/${person.person_id}/similar-faces?threshold=${threshold}`);
                const data = await res.json();
                setSimilarFaces(data.similar_faces || []);
                setUnassignedFaces(data.unassigned_faces || []);
            } catch (err) {
                console.error("Failed to fetch similar faces:", err);
            } finally {
                setLoading(false);
            }
        }
        fetchSimilarFaces();
    }, [jobId, person.person_id, threshold]);

    const toggleMergeSelection = useCallback((faceId: string): void => {
        setSelectedForMerge(prev => {
            const newSet = new Set(prev);
            if (newSet.has(faceId)) { newSet.delete(faceId); } else { newSet.add(faceId); }
            return newSet;
        });
    }, []);

    const toggleSplitSelection = useCallback((faceId: string): void => {
        setSelectedForSplit(prev => {
            const newSet = new Set(prev);
            if (newSet.has(faceId)) { newSet.delete(faceId); } else { newSet.add(faceId); }
            return newSet;
        });
    }, []);

    const handleSave = async (): Promise<void> => {
        if (selectedForMerge.size === 0 && selectedForSplit.size === 0) return;
        setSaving(true);
        try {
            // 1. Perform merge if selected
            if (selectedForMerge.size > 0) {
                const res = await fetch(`/api/jobs/${jobId}/faces/merge`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        action: "merge_to_person",
                        face_ids: Array.from(selectedForMerge),
                        target_person_id: person.person_id
                    })
                });
                if (!res.ok) throw new Error("Merge failed");
            }
            // 2. Perform split if selected
            if (selectedForSplit.size > 0) {
                const res = await fetch(`/api/jobs/${jobId}/faces/merge`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        action: "split_from_person",
                        face_ids: Array.from(selectedForSplit),
                        source_person_id: person.person_id
                    })
                });
                if (!res.ok) throw new Error("Split failed");
            }
            onRefresh();
            onClose();
        } catch (err) {
            console.error("Failed to update face assignments:", err);
        } finally {
            setSaving(false);
        }
    };

    const similarityColor = (sim: number): string => sim >= 0.8 ? "text-green-500" : sim >= 0.7 ? "text-yellow-500" : "text-orange-500";

    const hasChanges = selectedForMerge.size > 0 || selectedForSplit.size > 0;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
            <div className="bg-bg-surface border border-border-subtle rounded-xl shadow-2xl w-full max-w-4xl mx-4 max-h-[90vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
                <div className="flex items-center justify-between p-4 border-b border-border-subtle shrink-0">
                    <div>
                        <h3 className="text-lg font-semibold">Gesichter verwalten: {person.name || `Person ${person.person_id}`}</h3>
                        <p className="text-sm text-text-muted">Zuweisen von ähnlichen Gesichtern oder Entfernen von eigenen Gesichtern</p>
                    </div>
                    <button onClick={onClose} className="p-1 hover:bg-bg-card rounded-lg transition-colors"><span className="material-icons-round text-text-muted">close</span></button>
                </div>
                <div className="p-4 border-b border-border-subtle shrink-0">
                    <div className="flex items-center gap-4">
                        <label className="text-sm text-text-secondary">Ähnlichkeits-Schwellwert:</label>
                        <input type="range" min="0.3" max="0.9" step="0.05" value={threshold} onChange={e => setThreshold(parseFloat(e.target.value))} className="flex-1 max-w-xs" />
                        <span className="text-sm font-medium min-w-[3rem]">{threshold.toFixed(2)}</span>
                    </div>
                </div>
                <div className="flex-1 overflow-y-auto p-4">
                    {loading ? (
                        <div className="flex items-center justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-violet-600"></div></div>
                    ) : (
                        <div className="space-y-6">
                            <div>
                                <h4 className="text-sm font-medium text-text-secondary mb-3">Eigene Gesichter ({faceIds.length})</h4>
                                <p className="text-xs text-text-muted mb-2">Auswählen zum Entfernen (rot markiert)</p>
                                <div className="flex flex-wrap gap-3">
                                    {faceIds.map(fid => (
                                        <FaceThumbnail 
                                            key={fid} 
                                            faceId={fid} 
                                            jobId={jobId} 
                                            isOwn={true} 
                                            selectable={true}
                                            selected={selectedForSplit.has(fid)}
                                            onToggle={toggleSplitSelection}
                                        />
                                    ))}
                                    {faceIds.length === 0 && <p className="text-sm text-text-muted">Keine Gesichter gefunden</p>}
                                </div>
                            </div>
                            {similarFaces.length > 0 && (
                                <div>
                                    <h4 className="text-sm font-medium text-text-secondary mb-3">Ähnliche Gesichter ({similarFaces.length})</h4>
                                    <p className="text-xs text-text-muted mb-2">Auswählen zum Hinzufügen (violett markiert)</p>
                                    <div className="flex flex-wrap gap-3">
                                        {similarFaces.map(({ face, similarity }) => (
                                            <FaceThumbnail key={face.face_id} faceId={face.face_id} jobId={jobId} similarity={similarity} selectable={true}
                                                selected={selectedForMerge.has(face.face_id)} onToggle={toggleMergeSelection}
                                                similarityColor={similarityColor(similarity)} />
                                        ))}
                                    </div>
                                </div>
                            )}
                            {unassignedFaces.length > 0 && (
                                <div>
                                    <h4 className="text-sm font-medium text-text-secondary mb-3">Unzugewiesene Gesichter ({unassignedFaces.length})</h4>
                                    <p className="text-xs text-text-muted mb-2">Auswählen zum Hinzufügen (violett markiert)</p>
                                    <div className="flex flex-wrap gap-3">
                                        {unassignedFaces.map(face => (
                                            <FaceThumbnail key={face.face_id} faceId={face.face_id} jobId={jobId} selectable={true}
                                                selected={selectedForMerge.has(face.face_id)} onToggle={toggleMergeSelection} />
                                        ))}
                                    </div>
                                </div>
                            )}
                            {similarFaces.length === 0 && unassignedFaces.length === 0 && (
                                <p className="text-center text-text-muted py-8">Keine ähnlichen oder unzugewiesenen Gesichter gefunden</p>
                            )}
                        </div>
                    )}
                </div>
                <div className="flex items-center justify-between p-4 border-t border-border-subtle shrink-0 bg-bg-card">
                    <div className="text-sm text-text-muted flex gap-2">
                        {selectedForMerge.size > 0 && <span className="text-violet-400">{selectedForMerge.size} hinzufügen</span>}
                        {selectedForMerge.size > 0 && selectedForSplit.size > 0 && <span>•</span>}
                        {selectedForSplit.size > 0 && <span className="text-red-400">{selectedForSplit.size} entfernen</span>}
                        {!hasChanges && <span>Keine Änderungen ausgewählt</span>}
                    </div>
                    <div className="flex gap-3">
                        <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-text-secondary hover:bg-bg-card rounded-lg transition-colors">Abbrechen</button>
                        <button onClick={handleSave} disabled={!hasChanges || saving}
                            className="px-4 py-2 text-sm font-medium bg-violet-600 hover:bg-violet-500 disabled:bg-violet-600/50 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-colors duration-200">
                            {saving ? <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent animate-spin"></div> : <><span className="material-icons-round text-sm">save</span>Speichern</>}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

export const FaceThumbnail = memo(function FaceThumbnail({ faceId, jobId, isOwn, similarity, selectable, selected, onToggle, similarityColor }: FaceThumbnailProps) {
    const [imgError, setImgError] = useState(false);
    const imageUrl = `/api/jobs/${jobId}/faces/${faceId}`;

    let borderClass = "border-border-subtle";
    if (isOwn) {
        borderClass = selected ? "border-red-500 ring-2 ring-red-500/30" : "border-green-500/50";
    } else if (selected) {
        borderClass = "border-violet-600 ring-2 ring-violet-600/30";
    } else if (selectable) {
        borderClass = "hover:border-violet-500/50";
    }

    const handleClick = (): void => {
        if (selectable && onToggle) {
            onToggle(faceId);
        }
    };

    return (
        <div className={`relative group ${selectable ? "cursor-pointer" : ""}`} onClick={handleClick}>
            <div className={`relative w-20 h-20 rounded-lg overflow-hidden border-2 transition-all ${borderClass}`}>
                {!imgError ? (
                    <img src={imageUrl} alt={`Face ${faceId}`} className="w-full h-full object-cover" onError={() => setImgError(true)} />
                ) : (
                    <div className="w-full h-full flex items-center justify-center bg-bg-card text-text-muted"><span className="text-2xl">👤</span></div>
                )}
                {selectable && (
                    <div className={`absolute top-1 right-1 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all ${
                        selected 
                            ? (isOwn ? "bg-red-500 border-red-500" : "bg-violet-600 border-violet-600") 
                            : "bg-bg-surface/80 border-border-subtle group-hover:border-violet-500/50"
                    }`}>
                        {selected && <span className="material-icons-round text-white text-sm">{isOwn ? "remove" : "check"}</span>}
                    </div>
                )}
            </div>
            {similarity !== undefined && <div className={`text-xs text-center mt-1 font-medium ${similarityColor || ""}`}>{(similarity * 100).toFixed(0)}%</div>}
            <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 bg-bg-card px-1.5 py-0.5 rounded text-[10px] text-text-muted opacity-0 group-hover:opacity-100 transition-opacity">#{faceId}</div>
        </div>
    );
});
