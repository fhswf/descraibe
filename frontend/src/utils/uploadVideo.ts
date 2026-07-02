import type { UploadProgress, UploadOptions } from '../types';

const CHUNK_SIZE = 5 * 1024 * 1024;

interface UploadChunkResult {
  video_path?: string;
  job_id?: string;
  [key: string]: unknown;
}

function uploadChunk(url: string, formData: FormData, onChunkProgress?: (_loaded: number, _total: number) => void): Promise<UploadChunkResult> {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', url);

        xhr.upload.onprogress = (event) => {
            if (event.lengthComputable && onChunkProgress) {
                onChunkProgress(event.loaded, event.total);
            }
        };

        xhr.onload = () => {
            let data: UploadChunkResult = {};
            try {
                data = xhr.responseText ? JSON.parse(xhr.responseText) : {};
            } catch (err) {
                reject(new Error(`Invalid upload response: ${(err as Error).message}`));
                return;
            }

            if (xhr.status >= 200 && xhr.status < 300) {
                resolve(data);
            } else {
                reject(new Error((data?.error as string) || `Upload failed (${xhr.status})`));
            }
        };

        xhr.onerror = () => reject(new Error('Upload failed'));
        xhr.onabort = () => reject(new Error('Upload aborted'));
        xhr.send(formData);
    });
}

export async function uploadVideoInChunks({ jobId, file, onProgress }: UploadOptions): Promise<UploadChunkResult | null> {
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    let lastData: UploadChunkResult | null = null;

    for (let i = 0; i < totalChunks; i += 1) {
        const start = i * CHUNK_SIZE;
        const end = Math.min(file.size, start + CHUNK_SIZE);
        const chunk = file.slice(start, end);

        const formData = new FormData();
        formData.append('filename', file.name);
        formData.append('chunkIndex', String(i));
        formData.append('totalChunks', String(totalChunks));
        formData.append('totalBytes', String(file.size));
        formData.append('chunk', chunk);

        lastData = await uploadChunk(`/api/jobs/${jobId}/video`, formData, (loaded) => {
            const uploadedBytes = Math.min(file.size, start + loaded);
            const percent = file.size > 0 ? Math.round((uploadedBytes / file.size) * 100) : 100;
            const progress: UploadProgress = {
                percent,
                chunkIndex: i,
                totalChunks,
                uploadedBytes,
                totalBytes: file.size,
            };
            onProgress?.(progress);
        });

        const uploadedBytes = end;
        const percent = file.size > 0 ? Math.round((uploadedBytes / file.size) * 100) : 100;
        const progress: UploadProgress = {
            percent,
            chunkIndex: i,
            totalChunks,
            uploadedBytes,
            totalBytes: file.size,
        };
        onProgress?.(progress);
    }

    return lastData;
}
