import { useState } from 'react';
import type { PersonCrop } from '../../types';

function source(crop: PersonCrop, jobId: string, analysisId: string) {
    return `/api/jobs/${jobId}/person-crops/${crop.crop_id}?analysis_id=${encodeURIComponent(analysisId)}`;
}

export function CropImage({ crop, jobId, analysisId }: { crop: PersonCrop; jobId: string; analysisId: string }) {
    const [failed, setFailed] = useState(false);
    const box = crop.face_bbox;
    return <div className="relative w-full bg-bg-card" style={{ aspectRatio: `${Math.max(1, crop.width)} / ${Math.max(1, crop.height)}` }}>
        {failed ? <div className="absolute inset-0 flex items-center justify-center text-xs text-text-muted">Bild nicht verfügbar</div> : <>
            <img src={source(crop, jobId, analysisId)} alt={`Track ${crop.track_id}, Frame ${crop.frame_number}`}
                loading="lazy" onError={() => setFailed(true)} className="block w-full h-full" />
            {box && <span data-testid="face-overlay" aria-label="RetinaFace-Gesichtsrahmen" className="absolute border-2 border-red-500 pointer-events-none" style={{
                left: `${box[0] / crop.width * 100}%`, top: `${box[1] / crop.height * 100}%`,
                width: `${Math.max(0, box[2] - box[0]) / crop.width * 100}%`, height: `${Math.max(0, box[3] - box[1]) / crop.height * 100}%`,
            }} />}
        </>}
    </div>;
}

export function CropDetailDialog({ crop, jobId, analysisId, onClose }: {
    crop: PersonCrop; jobId: string; analysisId: string; onClose: () => void;
}) {
    const box = crop.face_bbox;
    const fw = box ? box[2] - box[0] : 0, fh = box ? box[3] - box[1] : 0;
    return <div role="dialog" aria-modal="true" aria-label="Crop-Vorschau" className="fixed inset-0 z-[90] bg-black/90 flex flex-col items-center justify-center p-4 overflow-auto"
        onClick={e => { e.stopPropagation(); onClose(); }} onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } }}>
        <button autoFocus onClick={onClose} className="text-white mb-3">Vorschau schließen ✕</button>
        <div className="flex flex-wrap items-center justify-center gap-8" onClick={e => e.stopPropagation()}>
            <div style={{ width: `min(45vw, ${65 * crop.width / Math.max(1, crop.height)}vh)` }}><CropImage crop={crop} jobId={jobId} analysisId={analysisId} /></div>
            {box && fw > 0 && fh > 0 && <div className="flex flex-col items-center gap-2"><p className="text-white">Gesichtszoom</p>
                <div data-testid="face-zoom" className="relative overflow-hidden border border-red-500 bg-black" style={{ width: `min(42vw, 420px, ${55 * fw / fh}vh)`, aspectRatio: `${fw} / ${fh}` }}>
                    <img src={source(crop, jobId, analysisId)} alt={`Gesichtszoom: Track ${crop.track_id}, Frame ${crop.frame_number}`} className="absolute max-w-none"
                        style={{ width: `${crop.width / fw * 100}%`, height: `${crop.height / fh * 100}%`, left: `${-box[0] / fw * 100}%`, top: `${-box[1] / fh * 100}%` }} />
                </div></div>}
        </div>
        <p className="text-white mt-4">Track {crop.track_id} · Frame {crop.frame_number} · {crop.timestamp_s.toFixed(2)} s{crop.excluded ? ' · ausgeschlossen' : ''}</p>
    </div>;
}
