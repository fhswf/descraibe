import React, { useState } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

const AUDIO_EXTS = ['.mp3', '.wav', '.ogg', '.m4a', '.aac'];
const VIDEO_EXTS = ['.mp4', '.webm', '.mkv', '.mov'];

function isAudio(filename) {
    if (!filename) return false;
    return AUDIO_EXTS.some(ext => filename.toLowerCase().endsWith(ext));
}

function isVideo(filename) {
    if (!filename) return false;
    return VIDEO_EXTS.some(ext => filename.toLowerCase().endsWith(ext));
}

function FileRow({ jobId, fileKey, filename }) {
    const [expanded, setExpanded] = useState(false);
    const url = `/api/jobs/${jobId}/downloads/${fileKey}`;
    const audio = isAudio(filename);
    const video = isVideo(filename);
    const playable = audio || video;

    return (
        <div className="flex flex-col gap-2 bg-white/5 border border-border-subtle rounded-xl overflow-hidden transition-all hover:border-violet-500/50">
            <div className="flex items-center gap-3 px-4 py-3">
                <span className="text-[1.2rem]">
                    {video ? '🎬' : audio ? '🎵' : '📄'}
                </span>
                <div className="flex-1 min-w-0">
                    <div className="text-[0.875rem] font-medium truncate">{fileKey}</div>
                    <div className="text-[0.75rem] text-text-muted truncate">{filename}</div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                    {playable && (
                        <button
                            onClick={() => setExpanded(e => !e)}
                            className={`w-8 h-8 flex items-center justify-center rounded-full transition-all hover:scale-105 ${expanded ? 'bg-violet-600 text-white' : 'bg-white/10 text-text-secondary hover:bg-violet-600/30 hover:text-violet-400'}`}
                            title={expanded ? 'Player schließen' : audio ? 'Audio abspielen' : 'Video abspielen'}
                        >
                            <span className="material-icons-round text-[1.1rem]">
                                {expanded ? 'close' : 'play_arrow'}
                            </span>
                        </button>
                    )}
                    <a
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                        className="w-8 h-8 flex items-center justify-center rounded-full bg-white/10 text-text-secondary hover:bg-violet-600/30 hover:text-violet-400 transition-all hover:scale-105"
                        title="Herunterladen"
                        download={filename}
                    >
                        <span className="material-icons-round text-[1.1rem]">download</span>
                    </a>
                </div>
            </div>

            {expanded && audio && (
                <div className="px-4 pb-4">
                    {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                    <audio
                        controls
                        autoPlay
                        className="w-full rounded-lg"
                        src={url}
                        key={url}
                    />
                </div>
            )}

            {expanded && video && (
                <div className="px-4 pb-4">
                    {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                    <video
                        controls
                        autoPlay
                        className="w-full rounded-lg max-h-[400px] bg-black"
                        src={url}
                        key={url}
                    />
                </div>
            )}
        </div>
    );
}

export function StepResults() {
    const { jobId, currentStep } = useJob();
    const { jobData } = useJob();

    if (currentStep !== 7) return null;

    const paths = jobData?.output_paths || {};

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-start gap-4 pb-4 border-b border-border-subtle">
                <div className="text-3xl leading-none">📥</div>
                <div>
                    <h2 className="text-[1.4rem] font-bold mb-1">Ergebnisse &amp; Download</h2>
                    <p className="text-sm text-text-secondary">Lade alle erzeugten Audiodeskriptions-Dateien herunter oder spiele sie direkt ab.</p>
                </div>
            </div>

            <div className="bg-bg-card border border-border-subtle rounded-2xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Ausgabedateien</p>
                <div className="flex flex-col gap-2">
                    {Object.entries(paths).map(([key, filename]) => (
                        <FileRow key={key} jobId={jobId} fileKey={key} filename={filename} />
                    ))}
                    {Object.keys(paths).length === 0 && (
                        <p className="text-sm text-text-secondary">Noch keine Ausgabedateien vorhanden.</p>
                    )}
                </div>
            </div>
        </div>
    );
}
