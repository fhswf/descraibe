import React, { useState, useEffect } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

function formatTimestamp(seconds) {
    if (!seconds && seconds !== 0) return '-';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function ColorBadge({ color, label }) {
    if (!color) return null;
    const colorMap = {
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

function PersonCard({ person }) {
    const attributes = person.attributes ? (typeof person.attributes === 'string' ? JSON.parse(person.attributes) : person.attributes) : {};
    
    return (
        <div className="flex flex-col gap-2 p-3 bg-bg-card border border-border-subtle rounded-lg">
            <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                    <span className="text-lg">👤</span>
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
                <div className="text-xs text-text-muted text-right">
                    <div>{person.appearances_count} Auftritt{person.appearances_count !== 1 ? 'e' : ''}</div>
                    <div>{formatTimestamp(person.first_seen_ts)} - {formatTimestamp(person.last_seen_ts)}</div>
                </div>
            </div>
            
            {(attributes.top_color || attributes.bottom_color || attributes.dominant_color) && (
                <div className="flex flex-wrap gap-1.5">
                    <ColorBadge color={attributes.top_color} label="Oben" />
                    <ColorBadge color={attributes.bottom_color} label="Unten" />
                    <ColorBadge color={attributes.dominant_color} label="Hauptfarbe" />
                </div>
            )}
            
            {person.description && (
                <div className="text-xs text-text-secondary pt-1 border-t border-border-subtle">
                    {person.description}
                </div>
            )}
        </div>
    );
}

export function StepPersons() {
    const { currentStep, jobData, handleRunPersons, progressData, apiFetch } = useJob();
    const [persons, setPersons] = useState([]);
    const [loading, setLoading] = useState(false);

    if (currentStep !== 5) return null;

    const personsCount = jobData?.persons_count || 0;
    const isRunning = progressData?.persons !== null && progressData?.persons !== undefined;
    const progressMsg = progressData?.persons?.msg || null;
    const progressPercent = progressData?.persons?.percent || null;

    // Load persons data when not running
    useEffect(() => {
        if (!isRunning && jobData?.id) {
            setLoading(true);
            apiFetch(`/api/jobs/${jobData.id}/persons`)
                .then(data => setPersons(data.persons || []))
                .catch(() => setPersons([]))
                .finally(() => setLoading(false));
        }
    }, [isRunning, jobData?.id]);

    return (
        <div className="flex flex-col gap-5">
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
                        
                        {/* Person cards */}
                        <div className="flex flex-col gap-2">
                            {persons.map(person => (
                                <PersonCard key={person.person_id} person={person} />
                            ))}
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

                {/* Action button */}
                {!isRunning && (
                    <button
                        className="flex items-center gap-2 self-start px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
                        onClick={handleRunPersons}
                        disabled={!jobData?.images_count}
                    >
                        <span className="material-icons-round text-lg">search</span>
                        Personen analysieren
                    </button>
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