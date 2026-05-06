const CHUNK_SIZE = 5 * 1024 * 1024;

function uploadChunk(url, formData, onChunkProgress) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', url);

        xhr.upload.onprogress = (event) => {
            if (event.lengthComputable && onChunkProgress) {
                onChunkProgress(event.loaded, event.total);
            }
        };

        xhr.onload = () => {
            let data = null;
            try {
                data = xhr.responseText ? JSON.parse(xhr.responseText) : {};
            } catch (err) {
                reject(new Error(`Invalid upload response: ${err.message}`));
                return;
            }

            if (xhr.status >= 200 && xhr.status < 300) {
                resolve(data);
            } else {
                reject(new Error(data?.error || `Upload failed (${xhr.status})`));
            }
        };

        xhr.onerror = () => reject(new Error('Upload failed'));
        xhr.onabort = () => reject(new Error('Upload aborted'));
        xhr.send(formData);
    });
}

export async function uploadVideoInChunks({ jobId, file, onProgress }) {
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    let lastData = null;

    for (let i = 0; i < totalChunks; i += 1) {
        const start = i * CHUNK_SIZE;
        const end = Math.min(file.size, start + CHUNK_SIZE);
        const chunk = file.slice(start, end);

        const formData = new FormData();
        formData.append('filename', file.name);
        formData.append('chunkIndex', i);
        formData.append('totalChunks', totalChunks);
        formData.append('totalBytes', file.size);
        formData.append('chunk', chunk);

        lastData = await uploadChunk(`/api/jobs/${jobId}/video`, formData, (loaded) => {
            const uploadedBytes = Math.min(file.size, start + loaded);
            const percent = file.size > 0 ? Math.round((uploadedBytes / file.size) * 100) : 100;
            onProgress?.({
                percent,
                chunkIndex: i,
                totalChunks,
                uploadedBytes,
                totalBytes: file.size,
            });
        });

        const uploadedBytes = end;
        const percent = file.size > 0 ? Math.round((uploadedBytes / file.size) * 100) : 100;
        onProgress?.({
            percent,
            chunkIndex: i,
            totalChunks,
            uploadedBytes,
            totalBytes: file.size,
        });
    }

    return lastData;
}
