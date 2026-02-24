import React, { useEffect, useRef, useState } from 'react';
import WaveSurfer from 'wavesurfer.js';
import RegionsPlugin from 'wavesurfer.js/dist/plugins/regions.esm.js';
import TimelinePlugin from 'wavesurfer.js/dist/plugins/timeline.esm.js';
import { useJob } from '../../hooks/useJob.jsx';

export function VideoTimeline({ videoRef }) {
    const containerRef = useRef(null);
    const timelineRef = useRef(null);
    const wavesurferRef = useRef(null);
    const regionsRef = useRef(null);
    const { jobData, focusedSlot } = useJob();

    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [zoom, setZoom] = useState(50); // Default zoom level
    const [isBuffering, setIsBuffering] = useState(false);

    // Track buffering state from the video element
    useEffect(() => {
        const video = videoRef.current;
        if (!video) return;

        const handleWaiting = () => setIsBuffering(true);
        const handlePlaying = () => setIsBuffering(false);
        const handleCanPlay = () => setIsBuffering(false);

        video.addEventListener('waiting', handleWaiting);
        video.addEventListener('playing', handlePlaying);
        video.addEventListener('canplay', handleCanPlay);

        return () => {
            video.removeEventListener('waiting', handleWaiting);
            video.removeEventListener('playing', handlePlaying);
            video.removeEventListener('canplay', handleCanPlay);
        };
    }, [videoRef]);

    const formatTime = (seconds) => {
        if (!seconds || isNaN(seconds)) seconds = 0;
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        const mm = m.toString().padStart(2, '0');
        const ss = s.toFixed(2).padStart(5, '0');

        // If duration is less than an hour, don't show hours
        if (duration < 3600) {
            return `${mm}:${ss}`;
        }

        const hh = h.toString().padStart(2, '0');
        return `${hh}:${mm}:${ss}`;
    };

    useEffect(() => {
        if (!containerRef.current || !jobData?.video_path) return;

        // Initialize Wavesurfer
        const ws = WaveSurfer.create({
            container: containerRef.current,
            waveColor: '#ced4da',
            progressColor: '#007bff',
            height: 60,
            barWidth: 2,
            normalize: true, // Auto scroll matches the playhead
            minPxPerSec: 50, // Initial zoom
            plugins: [
                TimelinePlugin.create({
                    container: timelineRef.current,
                    formatTimeCallback: formatTime,
                }),
            ],
            media: videoRef.current, // Sync with the video element!
        });

        const wsRegions = ws.registerPlugin(RegionsPlugin.create());
        regionsRef.current = wsRegions;

        let totalDuration = 0;
        const onReady = () => {
            totalDuration = ws.getDuration();
            setDuration(totalDuration);

            // Once duration is known, we can calculate voice regions
            // NOTE: For VAD / Pauses, we draw regions
            if (jobData.pauses && totalDuration > 0) {
                // First, draw the Pause regions
                jobData.pauses.forEach((p, idx) => {
                    wsRegions.addRegion({
                        start: p.start_s,
                        end: p.end_s,
                        color: 'rgba(255, 0, 0, 0.2)', // Red for Pause
                        drag: false,
                        resize: false,
                        content: 'Pause',
                    });
                });

                // Calculate Voice regions (gaps between pauses)
                let lastEnd = 0;
                jobData.pauses.forEach((p) => {
                    if (p.start_s > lastEnd) {
                        wsRegions.addRegion({
                            start: lastEnd,
                            end: p.start_s,
                            color: 'rgba(0, 0, 255, 0.2)', // Blue/Green for Voice
                            drag: false,
                            resize: false,
                            content: 'Voice',
                        });
                    }
                    lastEnd = p.end_s;
                });
                // Final voice region if video extends beyond final pause
                if (totalDuration > lastEnd) {
                    wsRegions.addRegion({
                        start: lastEnd,
                        end: totalDuration,
                        color: 'rgba(0, 0, 255, 0.2)',
                        drag: false,
                        resize: false,
                        content: 'Voice',
                    });
                }
            }

            // --- 2. Create Ad-Slots (Interactive Regions) ---
            if (jobData.slots) {
                jobData.slots.forEach((s, idx) => {
                    const contentDiv = document.createElement('div');
                    contentDiv.style.display = 'flex';
                    contentDiv.style.flexDirection = 'column';
                    contentDiv.style.alignItems = 'flex-start';
                    contentDiv.style.height = '100%';
                    contentDiv.style.padding = '2px';
                    contentDiv.style.boxSizing = 'border-box';
                    contentDiv.style.overflow = 'hidden';

                    const textSpan = document.createElement('span');
                    textSpan.innerText = `AD Slot ${idx + 1}`;
                    textSpan.style.backgroundColor = 'rgba(255,255,255,0.7)';
                    textSpan.style.padding = '0 4px';
                    textSpan.style.borderRadius = '2px';
                    textSpan.style.marginBottom = '2px';
                    textSpan.style.fontSize = '0.85rem';
                    contentDiv.appendChild(textSpan);

                    // If we have images for this slot, embed them inside the slot region!
                    if (jobData.slot_map) {
                        const matchingThumbs = jobData.slot_map.filter(sm => sm.slot === s.slot || sm.slot === (idx + 1));

                        if (matchingThumbs.length > 0) {
                            const imgContainer = document.createElement('div');
                            imgContainer.style.display = 'flex';
                            imgContainer.style.gap = '4px';
                            imgContainer.style.flexWrap = 'nowrap';
                            imgContainer.style.height = '100%';

                            matchingThumbs.forEach(sm => {
                                const imgName = sm.img_path ? sm.img_path.split(/[\\/]/).pop() : null;
                                if (imgName) {
                                    const imgDom = document.createElement('img');
                                    imgDom.src = `/api/jobs/${jobData.job_id}/images/${imgName}`;
                                    imgDom.style.height = '60px'; // fit inside timeline
                                    imgDom.style.borderRadius = '4px';
                                    imgDom.style.border = '1px solid #adb5bd';
                                    imgDom.style.objectFit = 'cover';
                                    imgDom.style.pointerEvents = 'none'; // prevent drag interference
                                    imgContainer.appendChild(imgDom);
                                }
                            });
                            contentDiv.appendChild(imgContainer);
                        }
                    }

                    wsRegions.addRegion({
                        start: s.start_s,
                        end: s.end_s,
                        color: 'rgba(40, 167, 69, 0.4)', // green with opacity
                        drag: true,
                        resize: true,
                        content: contentDiv,
                    });
                });
            }
        };

        wsRegions.on('region-updated', (region) => {
            console.log('Slot edited:', region.id, 'New start:', region.start, 'New end:', region.end);
            // In a full implementation, we would dispatch a context update or API call here
            // to persist the new boundaries of the slot to the backend.
        });

        wavesurferRef.current = ws;

        const onPlay = () => setIsPlaying(true);
        const onPause = () => setIsPlaying(false);

        ws.on('ready', () => {
            onReady();
        });

        ws.on('play', onPlay);
        ws.on('pause', onPause);
        ws.on('timeupdate', (ct) => {
            setCurrentTime(ct);
        });

        // Sync video when user clicks or drags the timeline
        ws.on('interaction', (newTime) => {
            if (videoRef.current) {
                videoRef.current.currentTime = newTime;
            }
        });

        return () => {
            ws.un('ready', onReady);
            ws.un('play', onPlay);
            ws.un('pause', onPause);
            ws.un('timeupdate');
            ws.un('interaction');
            ws.destroy();
        };
    }, [jobData, videoRef]);

    // Update zoom when slider changes
    useEffect(() => {
        if (wavesurferRef.current && duration > 0) {
            try {
                wavesurferRef.current.zoom(zoom);
            } catch (e) {
                console.warn('Wavesurfer zoom error:', e);
            }
        }
    }, [zoom, duration]);

    // Jump to focused slot
    useEffect(() => {
        if (focusedSlot && wavesurferRef.current && jobData?.slots) {
            const slotData = jobData.slots.find((s, idx) => s.slot === focusedSlot || (idx + 1) === focusedSlot);
            if (slotData && videoRef.current) {
                videoRef.current.currentTime = slotData.start_s;
            }
        }
    }, [focusedSlot, jobData]);

    if (!jobData?.video_path) {
        return null;
    }

    return (
        <div className="timeline-wrapper">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '5px' }}>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: '10px', margin: 0 }}>
                    Timeline (Sprechpausen & AD-Slots)
                    {isBuffering && <span style={{ fontSize: '0.8rem', color: '#ffc107', fontWeight: 'bold' }}>⏳ Lade / Puffert...</span>}
                </h4>
                <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
                    <button
                        className="btn btn-secondary"
                        style={{ padding: '4px 10px', fontSize: '0.9rem', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '4px' }}
                        onClick={() => wavesurferRef.current?.playPause()}
                        title={isPlaying ? 'Pause' : 'Play'}
                    >
                        {isPlaying ? '⏸' : '▶'}
                    </button>
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                        {formatTime(currentTime)} / {formatTime(duration)}
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <label htmlFor="zoomSlider" style={{ fontSize: '0.85rem', margin: 0 }}>Zoom:</label>
                        <input
                            id="zoomSlider"
                            type="range"
                            min="10"
                            max="500"
                            value={zoom}
                            onChange={(e) => setZoom(Number(e.target.value))}
                            style={{ margin: 0 }}
                        />
                    </div>
                </div>
            </div>

            {/* 
               We use a single scrolling container for BOTH wavesurfer and the thumbnails.
               Because wavesurfer generates an internal wrapper with `width: 100%; overflow: auto` by default,
               we can instead hide the internal scrollbar via CSS or just attach the thumbnail track structurally
               so its container matches wavesurfer's.
               Wait, Wavesurfer 7 internal wrapper handles scroll exclusively.
               Let's attach a visual exact replica.
            */}

            <div ref={timelineRef} style={{ height: '30px', marginTop: '10px' }}></div>
            <div ref={containerRef} style={{ width: '100%', borderBottom: '1px solid var(--border)' }}></div>
        </div>
    );
}

