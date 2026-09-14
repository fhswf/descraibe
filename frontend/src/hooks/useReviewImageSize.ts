import { useEffect, useRef } from 'react';

/** Update only presentation DOM; dragging must not rerender the review tree. */
export function useReviewImageSize(stage: 'tracking' | 'persons', initial: number) {
    const ref = useRef<HTMLLabelElement>(null);
    useEffect(() => {
        const label = ref.current;
        const scope = label?.closest<HTMLElement>('[data-review-size]');
        const input = label?.querySelector('input');
        if (!label || !scope || !input) return;
        const key = `descraibe.review.${stage}.imageHeight`;
        const clamp = (value: number) => Math.min(360, Math.max(100, value));
        let timer: ReturnType<typeof setTimeout> | undefined;
        let dirty = false;
        const apply = (height: number) => {
            scope.dataset.imageHeight = String(height);
            scope.style.setProperty('--review-image-height', `${height}px`);
            scope.style.setProperty('--review-card-width', `${Math.max(130, height * .75 + 24)}px`);
            scope.querySelectorAll<HTMLLabelElement>('[data-review-size-control]').forEach(control => {
                const slider = control.querySelector('input');
                const output = control.querySelector('output');
                if (slider) slider.value = String(height);
                if (output) output.textContent = `${height} px Höhe (max.)`;
            });
        };
        let stored = scope.dataset.imageHeight;
        if (!stored) { try { stored = localStorage.getItem(key) || undefined; } catch { /* Storage optional. */ } }
        const value = Number(stored);
        apply(Number.isFinite(value) && value > 0 ? clamp(value) : initial);
        const flush = () => {
            clearTimeout(timer);
            if (!dirty) return;
            try { localStorage.setItem(key, scope.dataset.imageHeight!); } catch { /* Session-only. */ }
            dirty = false;
        };
        const update = () => {
            const next = Number(input.value);
            if (!Number.isFinite(next)) return;
            apply(clamp(next));
            dirty = true;
            clearTimeout(timer);
            timer = setTimeout(flush, 250);
        };
        input.addEventListener('input', update);
        input.addEventListener('change', flush);
        window.addEventListener('pagehide', flush);
        return () => {
            flush();
            input.removeEventListener('input', update);
            input.removeEventListener('change', flush);
            window.removeEventListener('pagehide', flush);
        };
    }, [stage, initial]);
    return ref;
}
