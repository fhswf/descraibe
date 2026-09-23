import { useReviewImageSize } from '../../hooks/useReviewImageSize';

export function ReviewImageSizeControl({ stage }: { stage: 'tracking' | 'persons' }) {
    const initial = stage === 'tracking' ? 240 : 180;
    const ref = useReviewImageSize(stage, initial);
    return <label ref={ref} data-review-size-control className="flex flex-wrap items-center gap-3 text-sm">
        Bildgröße <input type="range" aria-label="Bildgröße" min={100} max={360} step={20}
            defaultValue={initial} className="w-40 accent-violet-600" />
        <output>{initial} px Höhe (max.)</output>
    </label>;
}
