import React, { useEffect, useRef, useState } from 'react';
import PropTypes from 'prop-types';
import WaveSurfer from 'wavesurfer.js';
import RegionsPlugin from 'wavesurfer.js/dist/plugins/regions.esm.js';
import TimelinePlugin from 'wavesurfer.js/dist/plugins/timeline.esm.js';
import { useJob } from '../../hooks/useJob.jsx';

export function VideoTimeline({ videoRef }) {
    const containerRef = useRef(null);
    const wavesurferRef = useRef(null);
    const regionsRef = useRef(null);
    const { jobData, focusedSlot, handleUpdateSlotTiming } = useJob();

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
            waveColor: 'rgba(206, 212, 218, 0.5)',
            progressColor: 'rgba(0, 123, 255, 0.5)',
            height: 160,
            barWidth: 2,
            barAlign: 'top',
            barHeight: 0.6,
            normalize: true, // Auto scroll matches the playhead
            minPxPerSec: 50, // Initial zoom
            plugins: [
                TimelinePlugin.create({
                    insertPosition: 'beforebegin',
                    height: 25,
                    formatTimeCallback: formatTime,
                    style: {
                        fontSize: '10px',
                        color: 'rgba(255, 255, 255, 0.5)',
                        marginBottom: '8px'
                    }
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
                jobData.pauses.forEach((p) => {
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
                    contentDiv.style.justifyContent = 'space-between';
                    contentDiv.style.height = '100%';
                    contentDiv.style.padding = '2px';
                    contentDiv.style.boxSizing = 'border-box';
                    contentDiv.style.overflow = 'hidden'; // Keep hidden by default
                    // Force marginTop to 0px to override the injected calculation by the Wavesurfer Regions plugin
                    contentDiv.style.setProperty('margin-top', '0px', 'important');

                    const textSpan = document.createElement('span');
                    textSpan.innerText = `AD Slot ${idx + 1}`;
                    textSpan.style.backgroundColor = 'rgba(255,255,255,0.85)';
                    textSpan.style.padding = '2px 6px';
                    textSpan.style.borderRadius = '4px';
                    textSpan.style.marginBottom = '2px';
                    textSpan.style.fontSize = '0.85rem';
                    textSpan.style.fontWeight = 'bold';
                    textSpan.style.color = '#333';
                    textSpan.style.boxShadow = '0 1px 2px rgba(0,0,0,0.2)';
                    contentDiv.appendChild(textSpan);

                    // If we have images for this slot, embed them inside the slot region!
                    if (jobData.slot_map) {
                        const matchingThumbs = jobData.slot_map.filter(sm => sm.slot === s.slot || sm.slot === (idx + 1));

                        if (matchingThumbs.length > 0) {
                            const imgContainer = document.createElement('div');
                            imgContainer.style.display = 'flex';
                            imgContainer.style.gap = '6px';
                            imgContainer.style.flexWrap = 'nowrap';
                            imgContainer.style.flex = '1';
                            imgContainer.style.minHeight = '0';
                            imgContainer.style.width = '100%';
                            imgContainer.style.alignItems = 'flex-end'; // Align images to bottom
                            imgContainer.style.paddingBottom = '2px';

                            matchingThumbs.forEach(sm => {
                                const imgName = sm.img_path ? sm.img_path.split(/[\\/]/).pop() : null;
                                if (imgName) {
                                    const imgDom = document.createElement('img');
                                    imgDom.src = `/api/jobs/${jobData.job_id}/images/${imgName}`;
                                    imgDom.style.height = '60px'; // Fit within the empty bottom 40% of 160px height
                                    imgDom.style.borderRadius = '4px';
                                    imgDom.style.border = '2px solid rgba(255,255,255,0.7)';
                                    imgDom.style.boxShadow = '0 2px 4px rgba(0,0,0,0.5)';
                                    imgDom.style.objectFit = 'cover';
                                    imgDom.style.cursor = 'pointer'; // Show it's interactive
                                    imgDom.style.transition = 'all 0.2s ease-in-out';
                                    imgDom.style.zIndex = '10';
                                    imgDom.style.position = 'relative'; // Need position for z-index to work
                                    imgDom.style.transformOrigin = 'bottom left'; // Scale outwards and upwards
                                    
                                    // Hover effects
                                    imgDom.addEventListener('mouseenter', () => {
                                        contentDiv.style.overflow = 'visible'; // Let it Break out only on hover
                                        // Also need to allow the actual wavesurfer region parent element to overflow
                                        if (contentDiv.parentElement) {
                                              contentDiv.parentElement.style.zIndex = '100';
                                              contentDiv.parentElement.style.overflow = 'visible';
                                        }

                                        imgDom.style.transform = 'scale(2)'; // Simpler scale now that origin is bottom left
                                        imgDom.style.zIndex = '50';
                                        imgDom.style.boxShadow = '0 8px 16px rgba(0,0,0,0.8)';
                                        imgDom.style.border = '2px solid rgba(139, 92, 246, 1)'; // Violet border on hover
                                    });
                                    
                                    imgDom.addEventListener('mouseleave', () => {
                                        imgDom.style.transform = 'none';
                                        imgDom.style.zIndex = '10';
                                        imgDom.style.boxShadow = '0 2px 4px rgba(0,0,0,0.5)';
                                        imgDom.style.border = '2px solid rgba(255,255,255,0.7)';
                                        
                                        // Reset overflow
                                        contentDiv.style.overflow = 'hidden';
                                        if (contentDiv.parentElement) {
                                              contentDiv.parentElement.style.zIndex = '';
                                              // Wavesurfer handles its own wrapper overflow, resetting to '' is usually safe
                                              contentDiv.parentElement.style.overflow = '';
                                        }
                                    });

                                    imgContainer.appendChild(imgDom);
                                }
                            });
                            contentDiv.appendChild(imgContainer);
                        }
                    }

                    wsRegions.addRegion({
                        id: s.slot.toString(),
                        start: s.start_s,
                        end: s.end_s,
                        color: 'rgba(139, 92, 246, 0.25)', // Violet with opacity for AD slots
                        drag: true,
                        resize: true,
                        content: contentDiv,
                    });
                });
            }
        };

        wsRegions.on('region-updated', (region) => {
            console.log('Slot edited:', region.id, 'New start:', region.start, 'New end:', region.end);
            const slotId = parseInt(region.id, 10);
            if (!Number.isNaN(slotId) && handleUpdateSlotTiming) {
                handleUpdateSlotTiming(slotId, region.start, region.end);
            }
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
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [jobData, videoRef, handleUpdateSlotTiming]);


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
        if (focusedSlot != null && wavesurferRef.current) {
            let startTime = null;

            // Prefer gpt_records because they have stable slot IDs that match what SRTWidget uses
            if (jobData?.gpt_records?.length > 0) {
                const rec = jobData.gpt_records.find(r => r.slot === focusedSlot);
                if (rec) startTime = rec.start_s;
            }

            // Fallback to raw slots array if gpt_records didn't match
            if (startTime == null && jobData?.slots?.length > 0) {
                const slotData = jobData.slots.find(s => s.slot === focusedSlot);
                if (slotData) startTime = slotData.start_s;
            }

            if (startTime != null && videoRef.current) {
                videoRef.current.currentTime = startTime;
                wavesurferRef.current.setTime(startTime);
            }
        }
    }, [focusedSlot, jobData, videoRef]);

    if (!jobData?.video_path) {
        return null;
    }

    return (
        <div className="flex flex-col border-t border-border-subtle bg-bg-surface mt-2 rounded-t-xl overflow-hidden shadow-md">
            <div className="flex items-center justify-between px-4 py-2 bg-[#050505] border-b border-border-subtle">
                <div className="flex items-center gap-6">
                    <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted">
                        Timeline (Sprechpausen & AD-Slots)
                    </span>
                    {isBuffering && <span className="text-[10px] text-yellow-500 font-bold tracking-widest uppercase">⏳ Puffert...</span>}
                    <div className="flex items-center gap-3">
                        <button
                            className="material-icons-round text-[1.2rem] hover:text-violet-500 text-text-primary transition-colors flex items-center justify-center p-1 rounded-full hover:bg-white/5"
                            onClick={() => wavesurferRef.current?.playPause()}
                            title={isPlaying ? 'Pause' : 'Play'}
                        >
                            {isPlaying ? 'pause_circle_filled' : 'play_circle_filled'}
                        </button>
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                        <span className="material-icons-round text-text-muted text-[14px]">zoom_in</span>
                        <input
                            className="w-24 accent-violet-500 h-1 bg-white/10 rounded appearance-none"
                            type="range"
                            min="10"
                            max="500"
                            value={zoom}
                            onChange={(e) => setZoom(Number(e.target.value))}
                        />
                    </div>
                    <div className="text-[11px] font-mono px-2 py-1 bg-white/5 rounded border border-border-subtle text-text-primary">
                        {formatTime(currentTime)} / {formatTime(duration)}
                    </div>
                </div>
            </div>

            <div className="bg-[#0a0a0a] p-4 relative pt-2">
                <div ref={containerRef} className="w-full border-b border-border-subtle pb-2"></div>
            </div>
        </div>
    );
}

VideoTimeline.propTypes = {
    videoRef: PropTypes.shape({
        current: PropTypes.instanceOf(Element)
    })
};

