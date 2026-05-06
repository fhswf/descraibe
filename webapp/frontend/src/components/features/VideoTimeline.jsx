import React, { useEffect, useRef, useState, useCallback } from 'react';
import PropTypes from 'prop-types';
import WaveSurfer from 'wavesurfer.js';
import RegionsPlugin from 'wavesurfer.js/dist/plugins/regions.esm.js';
import TimelinePlugin from 'wavesurfer.js/dist/plugins/timeline.esm.js';
import { useJob } from '../../hooks/useJob.jsx';

export function VideoTimeline({ videoRef, videoUrl, timelineJobData = null }) {
    const containerRef = useRef(null);
    const wavesurferRef = useRef(null);
    const regionsRef = useRef(null);
    const { jobData, focusedSlot, handleUpdateSlotTiming } = useJob();
    const activeJobData = timelineJobData || jobData;

    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [zoom, setZoom] = useState(50);
    const [isBuffering, setIsBuffering] = useState(false);

    // AD audio state
    const [adAudioEnabled, setAdAudioEnabled] = useState(false);
    const adAudiosRef = useRef({}); // slot_id -> HTMLAudioElement

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

        if (duration < 3600) {
            return `${mm}:${ss}`;
        }

        const hh = h.toString().padStart(2, '0');
        return `${hh}:${mm}:${ss}`;
    };

    // ── AD Audio sync ───────────────────────────────────────────────────────────
    // Preload all TTS audio elements when gpt_records are available
    useEffect(() => {
        const records = activeJobData?.gpt_records;
        if (!records || records.length === 0) return;

        const newAudios = {};
        records.forEach(rec => {
            if (!rec.slot) return;
            const el = new Audio(`/api/jobs/${activeJobData.job_id}/tts/${rec.slot}`);
            el.preload = 'none';
            newAudios[rec.slot] = { el, start_s: rec.start_s, end_s: rec.end_s };
        });
        adAudiosRef.current = newAudios;

        return () => {
            Object.values(newAudios).forEach(({ el }) => {
                el.pause();
                el.src = '';
            });
        };
    }, [activeJobData?.gpt_records, activeJobData?.job_id]);

    // Handle AD audio playback in sync with video
    const stopAllAd = useCallback(() => {
        Object.values(adAudiosRef.current).forEach(({ el }) => {
            el.pause();
            el.currentTime = 0;
        });
    }, []);

    // Poll video time and trigger AD audio clips at their start_s
    useEffect(() => {
        const video = videoRef.current;
        if (!video) return;

        // Track which slots already started in this play session
        const fired = new Set();

        const onTimeUpdate = () => {
            if (!adAudioEnabled) return;
            const t = video.currentTime;
            Object.entries(adAudiosRef.current).forEach(([slotId, { el, start_s, end_s }]) => {
                const sid = Number(slotId);
                if (t >= start_s && t < end_s) {
                    if (!fired.has(sid)) {
                        fired.add(sid);
                        el.currentTime = 0;
                        el.play().catch(() => {});
                    }
                } else if (t < start_s || t >= end_s) {
                    // reset so it can re-fire if user scrubs back
                    if (fired.has(sid) && t < start_s) {
                        fired.delete(sid);
                        el.pause();
                        el.currentTime = 0;
                    }
                }
            });
        };

        const onPause = () => stopAllAd();
        const onSeeked = () => {
            fired.clear();
            stopAllAd();
        };

        video.addEventListener('timeupdate', onTimeUpdate);
        video.addEventListener('pause', onPause);
        video.addEventListener('seeked', onSeeked);

        return () => {
            video.removeEventListener('timeupdate', onTimeUpdate);
            video.removeEventListener('pause', onPause);
            video.removeEventListener('seeked', onSeeked);
        };
    }, [videoRef, adAudioEnabled, stopAllAd]);

    // Stop AD audio when disabled
    useEffect(() => {
        if (!adAudioEnabled) stopAllAd();
    }, [adAudioEnabled, stopAllAd]);

    useEffect(() => {
        if (!containerRef.current || !activeJobData?.video_path || !videoUrl) return;

        const ws = WaveSurfer.create({
            container: containerRef.current,
            url: videoUrl,
            waveColor: 'rgba(206, 212, 218, 0.5)',
            progressColor: 'rgba(0, 123, 255, 0.5)',
            height: 160,
            barWidth: 2,
            barAlign: 'top',
            barHeight: 0.6,
            normalize: true,
            minPxPerSec: 50,
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
            media: videoRef.current,
            fetchParams: {
                cache: 'force-cache',
            },
        });

        const wsRegions = ws.registerPlugin(RegionsPlugin.create());
        regionsRef.current = wsRegions;

        // WaveSurfer's avoidOverlapping() sets marginTop via direct .style assignment
        // (inside a setTimeout(10ms)), bypassing !important. We use MutationObserver
        // to watch and reset it immediately whenever it's set.
        const marginObservers = [];
        const pinMarginTop = (el) => {
            if (!el) return;
            const obs = new MutationObserver(() => {
                if (el.style.marginTop && el.style.marginTop !== '0px') {
                    el.style.marginTop = '0px';
                }
            });
            obs.observe(el, { attributes: true, attributeFilter: ['style'] });
            marginObservers.push(obs);
        };

        // Pin immediately after each region is saved into the DOM
        wsRegions.on('region-created', (region) => {
            // region.content is the DOM element passed via the `content` option
            if (region.content instanceof HTMLElement) {
                pinMarginTop(region.content);
            }
        });

        let totalDuration = 0;
        const onReady = () => {
            totalDuration = ws.getDuration();
            setDuration(totalDuration);

            // ── Pause / Voice regions ──────────────────────────────────────────
            if (activeJobData.pauses && totalDuration > 0) {
                activeJobData.pauses.forEach((p) => {
                    wsRegions.addRegion({
                        start: p.start_s,
                        end: p.end_s,
                        color: 'rgba(255, 0, 0, 0.2)',
                        drag: false,
                        resize: false,
                        content: 'Pause',
                    });
                });

                let lastEnd = 0;
                activeJobData.pauses.forEach((p) => {
                    if (p.start_s > lastEnd) {
                        wsRegions.addRegion({
                            start: lastEnd,
                            end: p.start_s,
                            color: 'rgba(0, 0, 255, 0.2)',
                            drag: false,
                            resize: false,
                            content: 'Voice',
                        });
                    }
                    lastEnd = p.end_s;
                });
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

            // ── Transcript regions (hoverable text popovers) ──────────────────
            if (activeJobData.segments) {
                activeJobData.segments.forEach((segment, idx) => {
                    const text = String(segment.text || '').trim();
                    const start = Number(segment.start_s);
                    const end = Number(segment.end_s);
                    if (!text || !Number.isFinite(start) || !Number.isFinite(end) || end <= start) return;

                    const contentDiv = document.createElement('div');
                    contentDiv.style.position = 'relative';
                    contentDiv.style.display = 'flex';
                    contentDiv.style.alignItems = 'flex-end';
                    contentDiv.style.justifyContent = 'flex-start';
                    contentDiv.style.width = '100%';
                    contentDiv.style.height = '100%';
                    contentDiv.style.padding = '2px';
                    contentDiv.style.boxSizing = 'border-box';
                    contentDiv.style.overflow = 'visible';
                    contentDiv.style.cursor = 'pointer';

                    const badge = document.createElement('span');
                    badge.textContent = 'TXT';
                    badge.style.backgroundColor = 'rgba(20, 184, 166, 0.9)';
                    badge.style.color = '#031b18';
                    badge.style.borderRadius = '4px';
                    badge.style.padding = '1px 5px';
                    badge.style.fontSize = '0.65rem';
                    badge.style.fontWeight = '800';
                    badge.style.lineHeight = '1.4';
                    badge.style.boxShadow = '0 1px 3px rgba(0,0,0,0.35)';
                    badge.title = text;

                    const popover = document.createElement('div');
                    popover.textContent = text.length > 500 ? `${text.slice(0, 500)}...` : text;
                    popover.style.display = 'none';
                    popover.style.position = 'absolute';
                    popover.style.left = '0';
                    popover.style.bottom = '24px';
                    popover.style.width = 'min(320px, 70vw)';
                    popover.style.maxHeight = '160px';
                    popover.style.overflow = 'auto';
                    popover.style.padding = '10px 12px';
                    popover.style.borderRadius = '8px';
                    popover.style.border = '1px solid rgba(20,184,166,0.55)';
                    popover.style.background = 'rgba(9, 17, 24, 0.96)';
                    popover.style.color = '#e2e8f0';
                    popover.style.fontSize = '0.75rem';
                    popover.style.lineHeight = '1.4';
                    popover.style.whiteSpace = 'pre-wrap';
                    popover.style.boxShadow = '0 12px 30px rgba(0,0,0,0.45)';
                    popover.style.zIndex = '120';
                    popover.style.pointerEvents = 'none';

                    contentDiv.addEventListener('mouseenter', () => {
                        popover.style.display = 'block';
                        if (contentDiv.parentElement) {
                            contentDiv.parentElement.style.zIndex = '120';
                            contentDiv.parentElement.style.overflow = 'visible';
                        }
                    });

                    contentDiv.addEventListener('mouseleave', () => {
                        popover.style.display = 'none';
                        if (contentDiv.parentElement) {
                            contentDiv.parentElement.style.zIndex = '';
                            contentDiv.parentElement.style.overflow = '';
                        }
                    });

                    contentDiv.addEventListener('click', (e) => {
                        e.stopPropagation();
                        if (videoRef.current) {
                            videoRef.current.currentTime = start;
                        }
                    });

                    contentDiv.appendChild(badge);
                    contentDiv.appendChild(popover);

                    wsRegions.addRegion({
                        id: `transcript-${segment.index ?? idx}`,
                        start,
                        end,
                        color: 'rgba(20, 184, 166, 0.12)',
                        drag: false,
                        resize: false,
                        content: contentDiv,
                    });
                });
            }

            // ── AD Slot regions (draggable/resizable) ─────────────────────────
            if (activeJobData.slots) {
                activeJobData.slots.forEach((s, idx) => {
                    const contentDiv = document.createElement('div');
                    contentDiv.style.display = 'flex';
                    contentDiv.style.flexDirection = 'column';
                    contentDiv.style.alignItems = 'flex-start';
                    contentDiv.style.justifyContent = 'space-between';
                    contentDiv.style.height = '100%';
                    contentDiv.style.padding = '2px';
                    contentDiv.style.boxSizing = 'border-box';
                    contentDiv.style.overflow = 'hidden';
                    // marginTop is managed via MutationObserver (pinMarginTop) above

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

                    if (activeJobData.slot_map) {
                        const matchingThumbs = activeJobData.slot_map.filter(sm => sm.slot === s.slot || sm.slot === (idx + 1));

                        if (matchingThumbs.length > 0) {
                            const imgContainer = document.createElement('div');
                            imgContainer.style.display = 'flex';
                            imgContainer.style.gap = '6px';
                            imgContainer.style.flexWrap = 'nowrap';
                            imgContainer.style.flex = '1';
                            imgContainer.style.minHeight = '0';
                            imgContainer.style.width = '100%';
                            imgContainer.style.alignItems = 'flex-end';
                            imgContainer.style.paddingBottom = '2px';

                            matchingThumbs.forEach(sm => {
                                const imgName = sm.img_path ? sm.img_path.split(/[/\\]/).pop() : null;
                                if (imgName) {
                                    const imgDom = document.createElement('img');
                                    imgDom.src = `/api/jobs/${activeJobData.job_id}/images/${imgName}`;
                                    imgDom.style.height = '60px';
                                    imgDom.style.borderRadius = '4px';
                                    imgDom.style.border = '2px solid rgba(255,255,255,0.7)';
                                    imgDom.style.boxShadow = '0 2px 4px rgba(0,0,0,0.5)';
                                    imgDom.style.objectFit = 'cover';
                                    imgDom.style.cursor = 'pointer';
                                    imgDom.style.transition = 'all 0.2s ease-in-out';
                                    imgDom.style.zIndex = '10';
                                    imgDom.style.position = 'relative';
                                    imgDom.style.transformOrigin = 'bottom left';

                                    imgDom.addEventListener('mouseenter', () => {
                                        contentDiv.style.overflow = 'visible';
                                        if (contentDiv.parentElement) {
                                            contentDiv.parentElement.style.zIndex = '100';
                                            contentDiv.parentElement.style.overflow = 'visible';
                                        }
                                        imgDom.style.transform = 'scale(2)';
                                        imgDom.style.zIndex = '50';
                                        imgDom.style.boxShadow = '0 8px 16px rgba(0,0,0,0.8)';
                                        imgDom.style.border = '2px solid rgba(139, 92, 246, 1)';
                                    });

                                    imgDom.addEventListener('mouseleave', () => {
                                        imgDom.style.transform = 'none';
                                        imgDom.style.zIndex = '10';
                                        imgDom.style.boxShadow = '0 2px 4px rgba(0,0,0,0.5)';
                                        imgDom.style.border = '2px solid rgba(255,255,255,0.7)';
                                        contentDiv.style.overflow = 'hidden';
                                        if (contentDiv.parentElement) {
                                            contentDiv.parentElement.style.zIndex = '';
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
                        color: 'rgba(139, 92, 246, 0.25)',
                        drag: true,
                        resize: true,
                        content: contentDiv,
                    });
                });
            }

            // ── AD audio description regions (non-interactive, below AD slots) ─
            if (activeJobData.gpt_records) {
                activeJobData.gpt_records.filter(r => r.slot).forEach(rec => {
                    const contentEl = document.createElement('div');
                    contentEl.style.display = 'flex';
                    contentEl.style.alignItems = 'center';
                    contentEl.style.justifyContent = 'center';
                    contentEl.style.width = '100%';
                    contentEl.style.height = '100%';
                    contentEl.title = rec.text ? rec.text.slice(0, 80) : `AD ${rec.slot}`;

                    const icon = document.createElement('span');
                    icon.style.fontSize = '1rem';
                    icon.style.color = 'rgba(167,139,250,0.9)';
                    icon.style.padding = '4px 8px';
                    icon.style.borderRadius = '4px';
                    icon.style.cursor = 'pointer';
                    icon.style.transition = 'background-color 0.2s';
                    icon.textContent = '▶';

                    icon.addEventListener('mouseenter', () => {
                        icon.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
                    });
                    icon.addEventListener('mouseleave', () => {
                        icon.style.backgroundColor = 'transparent';
                    });

                    // Only the icon triggers playback toggle.
                    // stopPropagation prevents the click from bubbling to WaveSurfer's
                    // interaction handler, which would seek and immediately call stopAllAd().
                    icon.addEventListener('click', (e) => {
                        e.stopPropagation();
                        const entry = adAudiosRef.current[rec.slot];
                        if (!entry) return;
                        const { el } = entry;
                        if (el.paused) {
                            el.currentTime = 0;
                            el.play().catch(() => {});
                            icon.textContent = '■';
                        } else {
                            el.pause();
                            el.currentTime = 0;
                            icon.textContent = '▶';
                        }
                    });

                    contentEl.appendChild(icon);

                    // Reset icon when audio finishes or is stopped externally (e.g. stopAllAd)
                    const entry = adAudiosRef.current[rec.slot];
                    if (entry) {
                        const resetIcon = () => { icon.textContent = '▶'; };
                        entry.el.addEventListener('ended', resetIcon);
                        entry.el.addEventListener('pause', resetIcon);
                    }

                    wsRegions.addRegion({
                        id: `ad-audio-${rec.slot}`,
                        start: rec.start_s,
                        end: rec.end_s,
                        color: 'rgba(109, 40, 217, 0.35)',
                        drag: false,
                        resize: false,
                        content: contentEl,
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

        ws.on('ready', () => { onReady(); });
        ws.on('play', onPlay);
        ws.on('pause', onPause);
        ws.on('timeupdate', (ct) => { setCurrentTime(ct); });
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
            marginObservers.forEach(o => o.disconnect());
            ws.destroy();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeJobData, videoRef, videoUrl, handleUpdateSlotTiming]);


    useEffect(() => {
        if (wavesurferRef.current && duration > 0) {
            try {
                wavesurferRef.current.zoom(zoom);
            } catch (e) {
                console.warn('Wavesurfer zoom error:', e);
            }
        }
    }, [zoom, duration]);

    useEffect(() => {
        if (focusedSlot != null && wavesurferRef.current) {
            let startTime = null;

            if (activeJobData?.gpt_records?.length > 0) {
                const rec = activeJobData.gpt_records.find(r => r.slot === focusedSlot);
                if (rec) startTime = rec.start_s;
            }

            if (startTime == null && activeJobData?.slots?.length > 0) {
                const slotData = activeJobData.slots.find(s => s.slot === focusedSlot);
                if (slotData) startTime = slotData.start_s;
            }

            if (startTime != null && videoRef.current) {
                videoRef.current.currentTime = startTime;
                wavesurferRef.current.setTime(startTime);
            }
        }
    }, [focusedSlot, activeJobData, videoRef]);

    if (!activeJobData?.video_path) {
        return null;
    }

    const hasTtsRecords = activeJobData?.gpt_records?.some(r => r.slot);

    return (
        <div className="flex flex-col border-t border-border-subtle bg-bg-surface mt-2 rounded-t-xl overflow-hidden shadow-md">
            <div className="flex items-center justify-between px-4 py-2 bg-[#050505] border-b border-border-subtle">
                <div className="flex items-center gap-6">
                    <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted">
                        Timeline (Sprechpausen &amp; AD-Slots)
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

                    {/* AD Audio toggle */}
                    {hasTtsRecords && (
                        <button
                            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold transition-all border ${adAudioEnabled
                                ? 'bg-violet-600 text-white border-violet-500 shadow-sm shadow-violet-500/30'
                                : 'bg-white/5 text-text-muted border-border-subtle hover:border-violet-500/50 hover:text-violet-400'}`}
                            onClick={() => setAdAudioEnabled(v => !v)}
                            title={adAudioEnabled ? 'AD-Audio deaktivieren' : 'AD-Audio beim Abspielen ausgeben'}
                        >
                            <span className="material-icons-round text-[14px]">{adAudioEnabled ? 'volume_up' : 'volume_off'}</span>
                            AD-Audio
                        </button>
                    )}
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
                <div ref={containerRef} className="w-full"></div>
            </div>
        </div>
    );
}

VideoTimeline.propTypes = {
    videoRef: PropTypes.shape({
        current: PropTypes.instanceOf(Element)
    }),
    videoUrl: PropTypes.string.isRequired,
    timelineJobData: PropTypes.object
};
