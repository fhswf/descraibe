import { useEffect, useState } from 'react';
import type { CacheStatus, CachedVideoResult } from '../types';

const VIDEO_CACHE_DIR = 'video-cache';

function supportsOPFS(): boolean {
    return Boolean(navigator.storage?.getDirectory);
}

function safeName(value: string | undefined): string {
    return String(value || 'video').replace(/[^a-zA-Z0-9._-]/g, '_');
}

async function getCachedFile(fileName: string): Promise<File | null> {
    const root = await navigator.storage.getDirectory();
    const dir = await root.getDirectoryHandle(VIDEO_CACHE_DIR, { create: true });
    try {
        const handle = await dir.getFileHandle(fileName);
        const file = await handle.getFile();
        return file.size > 0 ? file : null;
    } catch (err) {
        if ((err as DOMException).name === 'NotFoundError') return null;
        throw err;
    }
}

async function writeResponseToOPFS(response: Response, fileName: string): Promise<void> {
    const root = await navigator.storage.getDirectory();
    const dir = await root.getDirectoryHandle(VIDEO_CACHE_DIR, { create: true });
    const handle = await dir.getFileHandle(fileName, { create: true });
    const writable = await handle.createWritable();

    if (!response.body) {
        await writable.write(await response.blob());
        await writable.close();
        return;
    }

    const reader = response.body.getReader();
    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            await writable.write(value);
        }
    } catch (err) {
        await writable.abort();
        throw err;
    }

    await writable.close();
}

async function loadCachedVideo(remoteUrl: string, cacheKey: string): Promise<File | null> {
    const fileName = `${safeName(cacheKey)}.mp4`;
    const cached = await getCachedFile(fileName);
    if (cached) return cached;

    const response = await fetch(remoteUrl, { cache: 'force-cache' });
    if (!response.ok) {
        throw new Error(`Video fetch failed: ${response.status}`);
    }

    await writeResponseToOPFS(response, fileName);
    return getCachedFile(fileName);
}

export function useCachedVideoUrl(remoteUrl: string | null, cacheKey: string | null): CachedVideoResult {
    const [cachedUrl, setCachedUrl] = useState<string | null>(null);
    const [cacheStatus, setCacheStatus] = useState<CacheStatus>('idle');

    useEffect(() => {
        let cancelled = false;
        let objectUrl: string | null = null;

        queueMicrotask(() => {
            if (cancelled) return;
            setCachedUrl(null);
            setCacheStatus(remoteUrl ? 'loading' : 'idle');
        });

        if (!remoteUrl || !cacheKey || !supportsOPFS()) {
            queueMicrotask(() => {
                if (cancelled) return;
                setCachedUrl(remoteUrl);
                setCacheStatus(remoteUrl ? 'network' : 'idle');
            });
            return undefined;
        }

        navigator.storage?.persist?.().catch(() => {});

        loadCachedVideo(remoteUrl, cacheKey)
            .then(file => {
                if (cancelled || !file) return;
                objectUrl = URL.createObjectURL(file);
                setCachedUrl(objectUrl);
                setCacheStatus('opfs');
            })
            .catch(err => {
                console.warn('Falling back to network video URL:', err);
                if (!cancelled) {
                    setCachedUrl(remoteUrl);
                    setCacheStatus('network');
                }
            });

        return () => {
            cancelled = true;
            if (objectUrl) URL.revokeObjectURL(objectUrl);
        };
    }, [remoteUrl, cacheKey]);

    return { videoUrl: cachedUrl, cacheStatus };
}
