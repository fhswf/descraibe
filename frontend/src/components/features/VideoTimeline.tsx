import React, { useEffect, useRef, useState, useCallback } from 'react';
import WaveSurfer from 'wavesurfer.js';
import RegionsPlugin from 'wavesurfer.js/dist/plugins/regions.esm.js';
import TimelinePlugin from 'wavesurfer.js/dist/plugins/timeline.esm.js';
import { useJob } from '../../hooks/useJob.jsx';
import { GPTRecord, Slot, JobData } from '../../types/index.js';

interface VideoTimelineProps {
    videoRef: React.RefObject<HTMLVideoElement | null>;
    videoUrl: string;
    timelineJobData?: JobData | null;
}

interface Pause {
    start_s: number;
    end_s: number;
}

interface Segment {
    text?: string;
    start_s?: number;
    end_s?: number;
    index?: number;
}

interface SlotMap {
    slot: number;
    img_path?: string;
    start_s?: number;
    end_s?: number;
}

interface TimelineJobData extends JobData {
    pauses?: Pause[];
    segments?: Segment[];
    slot_map?: SlotMap[];
}

interface AdAudioEntry {
    el: HTMLAudioElement;
    start_s: number;
    end_s: number;
}

export function VideoTimeline({ videoRef, videoUrl, timelineJobData = null }: VideoTimelineProps) {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const wavesurferRef = useRef<WaveSurfer | null>(null);
    const regionsRef = useRef<ReturnType<typeof RegionsPlugin.create> | null>(null);
    const marginObserversRef = useRef<MutationObserver[]>([]);
    const activeJobDataRef = useRef<TimelineJobData | null>(null);
    const handleUpdateSlotTimingRef = useRef<((_slotId: number, _start: number, _end: number) => Promise<void>) | null>(null);
    const { jobData, focusedSlot, handleUpdateSlotTiming } = useJob();
    const activeJobData = timelineJobData || (jobData as TimelineJobData | null);

    // Update refs in useEffect to avoid ref updates during render
    useEffect(() => {
        activeJobDataRef.current = activeJobData;
        handleUpdateSlotTimingRef.current = handleUpdateSlotTiming;
    }, [activeJobData, handleUpdateSlotTiming]);

    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [zoom, setZoom] = useState(50);
    const [isBuffering, setIsBuffering] = useState(false);

    const [adAudioEnabled, setAdAudioEnabled] = useState(false);
    const adAudiosRef = useRef<Record<number, AdAudioEntry>>({});

    const clearMarginObservers = useCallback(() => {
        marginObserversRef.current.forEach(o => o.disconnect());
        marginObserversRef.current = [];
    }, []);

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

    const formatTime = (seconds: number): string => {
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

    const gptRecordsSignature = JSON.stringify(activeJobData?.gpt_records || []);
    const regionSignature = JSON.stringify({
        job_id: activeJobData?.job_id || null,
        pauses: activeJobData?.pauses || [],
        segments: activeJobData?.segments || [],
        slots: activeJobData?.slots || [],
        slot_map: activeJobData?.slot_map || [],
        gpt_records: activeJobData?.gpt_records || []
    });
    const focusedSlotSignature = JSON.stringify({
        slots: activeJobData?.slots || [],
        gpt_records: activeJobData?.gpt_records || []
    });

    useEffect(() => {
        const currentJobData = activeJobDataRef.current;
        const records = currentJobData?.gpt_records;
        if (!records || records.length === 0) return;

        const newAudios: Record<number, AdAudioEntry> = {};
        records.forEach(rec => {
            const slotId = rec.slot;
            if (slotId == null) return;
            const el = new Audio(`/api/jobs/${currentJobData!.job_id}/tts/${slotId}`);
            el.preload = 'none';
            newAudios[slotId] = { el, start_s: rec.start_s ?? 0, end_s: rec.end_s ?? 0 };
        });
        adAudiosRef.current = newAudios;

        return () => {
            Object.values(newAudios).forEach(({ el }) => {
                el.pause();
                el.src = '';
            });
        };
    }, [gptRecordsSignature]);

    const stopAllAd = useCallback(() => {
        Object.values(adAudiosRef.current).forEach(({ el }) => {
            el.pause();
            el.currentTime = 0;
        });
    }, []);

    useEffect(() => {
        const video = videoRef.current;
        if (!video) return;

        const fired = new Set<number>();

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
            media: videoRef.current ?? undefined,
            fetchParams: {
                cache: 'force-cache',
            },
        });

        const wsRegions = ws.registerPlugin(RegionsPlugin.create());
        regionsRef.current = wsRegions;

        const pinMarginTop = (el: HTMLElement | null) => {
            if (!el) return;
            const obs = new MutationObserver(() => {
                if (el.style.marginTop && el.style.marginTop !== '0px') {
                    el.style.marginTop = '0px';
                }
            });
            obs.observe(el, { attributes: true, attributeFilter: ['style'] });
            marginObserversRef.current.push(obs);
        };

        wsRegions.on('region-created', (region) => {
            if (region.content instanceof HTMLElement) {
                pinMarginTop(region.content);
            }
        });

        const onReady = () => {
            setDuration(ws.getDuration());
        };

        wsRegions.on('region-updated', (region) => {
            console.log('Slot edited:', region.id, 'New start:', region.start, 'New end:', region.end);
            const slotId = parseInt(region.id, 10);
            const updateSlotTiming = handleUpdateSlotTimingRef.current;
            if (!Number.isNaN(slotId) && updateSlotTiming) {
                updateSlotTiming(slotId, region.start, region.end);
            }
        });

        wavesurferRef.current = ws;

        const onPlay = () => setIsPlaying(true);
        const onPause = () => setIsPlaying(false);
        const onTimeUpdate = (ct: number) => { setCurrentTime(ct); };
        const onInteraction = (newTime: number) => {
            if (videoRef.current) {
                videoRef.current.currentTime = newTime;
            }
        };

        ws.on('ready', onReady);
        ws.on('play', onPlay);
        ws.on('pause', onPause);
        ws.on('timeupdate', onTimeUpdate);
        ws.on('interaction', onInteraction);

        return () => {
            ws.un('ready', onReady);
            ws.un('play', onPlay);
            ws.un('pause', onPause);
            ws.un('timeupdate', onTimeUpdate);
            ws.un('interaction', onInteraction);
            clearMarginObservers();
            regionsRef.current = null;
            ws.destroy();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [clearMarginObservers, videoRef, videoUrl]);

    useEffect(() => {
        const wsRegions = regionsRef.current;
        const currentJobData = activeJobDataRef.current;
        if (!wsRegions || !currentJobData?.video_path || duration <= 0) return;

        clearMarginObservers();
        wsRegions.clearRegions();

        if (currentJobData.pauses) {
            currentJobData.pauses.forEach((p: Pause) => {
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
            currentJobData.pauses.forEach((p: Pause) => {
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
            if (duration > lastEnd) {
                wsRegions.addRegion({
                    start: lastEnd,
                    end: duration,
                    color: 'rgba(0, 0, 255, 0.2)',
                    drag: false,
                    resize: false,
                    content: 'Voice',
                });
            }
        }

        if (currentJobData.segments) {
            currentJobData.segments.forEach((segment: Segment, idx: number) => {
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

                contentDiv.addEventListener('click', (e: MouseEvent) => {
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

        if (currentJobData.slots) {
            currentJobData.slots.forEach((s: Slot, idx: number) => {
                const slotNum = s.slot ?? (idx + 1);
                const start = s.start_s ?? s.start;
                const end = s.end_s ?? s.end;
                if (start == null || end == null) return;

                const contentDiv = document.createElement('div');
                contentDiv.style.display = 'flex';
                contentDiv.style.flexDirection = 'column';
                contentDiv.style.alignItems = 'flex-start';
                contentDiv.style.justifyContent = 'space-between';
                contentDiv.style.height = '100%';
                contentDiv.style.padding = '2px';
                contentDiv.style.boxSizing = 'border-box';
                contentDiv.style.overflow = 'hidden';

                const textSpan = document.createElement('span');
                textSpan.innerText = `AD Slot ${slotNum}`;
                textSpan.style.backgroundColor = 'rgba(255,255,255,0.85)';
                textSpan.style.padding = '2px 6px';
                textSpan.style.borderRadius = '4px';
                textSpan.style.marginBottom = '2px';
                textSpan.style.fontSize = '0.85rem';
                textSpan.style.fontWeight = 'bold';
                textSpan.style.color = '#333';
                textSpan.style.boxShadow = '0 1px 2px rgba(0,0,0,0.2)';
                contentDiv.appendChild(textSpan);

                if (currentJobData.slot_map) {
                    const matchingThumbs = currentJobData.slot_map.filter((sm: SlotMap) => sm.slot === slotNum);

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

                        matchingThumbs.forEach((sm: SlotMap) => {
                            const imgName = sm.img_path ? sm.img_path.split(/[/\\]/).pop() : null;
                            if (imgName) {
                                const imgDom = document.createElement('img');
                                imgDom.src = `/api/jobs/${currentJobData.job_id}/images/${imgName}`;
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
                    id: String(slotNum),
                    start,
                    end,
                    color: 'rgba(139, 92, 246, 0.25)',
                    drag: true,
                    resize: true,
                    content: contentDiv,
                });
            });
        }

        if (currentJobData.gpt_records) {
            currentJobData.gpt_records.filter((r: GPTRecord) => r.slot != null).forEach((rec: GPTRecord) => {
                const recSlot = rec.slot!;
                const recStart = rec.start_s ?? 0;
                const recEnd = rec.end_s ?? 0;

                const contentEl = document.createElement('div');
                contentEl.style.display = 'flex';
                contentEl.style.alignItems = 'center';
                contentEl.style.justifyContent = 'center';
                contentEl.style.width = '100%';
                contentEl.style.height = '100%';
                contentEl.title = rec.text ? rec.text.slice(0, 80) : `AD ${recSlot}`;

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

                icon.addEventListener('click', (e: MouseEvent) => {
                    e.stopPropagation();
                    const entry = adAudiosRef.current[recSlot];
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

                const entry = adAudiosRef.current[recSlot];
                if (entry) {
                    const resetIcon = () => { icon.textContent = '▶'; };
                    entry.el.addEventListener('ended', resetIcon);
                    entry.el.addEventListener('pause', resetIcon);
                }

                wsRegions.addRegion({
                    id: `ad-audio-${recSlot}`,
                    start: recStart,
                    end: recEnd,
                    color: 'rgba(109, 40, 217, 0.35)',
                    drag: false,
                    resize: false,
                    content: contentEl,
                });
            });
        }
    }, [clearMarginObservers, duration, regionSignature, videoRef]);

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
            const currentJobData = activeJobDataRef.current;
            let startTime: number | undefined;

            if (currentJobData?.gpt_records?.length && currentJobData.gpt_records.length > 0) {
                const rec = currentJobData.gpt_records.find((r: GPTRecord) => r.slot === focusedSlot);
                if (rec) startTime = rec.start_s;
            }

            if (startTime == null && currentJobData?.slots?.length && currentJobData.slots.length > 0) {
                const slotData = currentJobData.slots.find((s: Slot) => s.slot === focusedSlot);
                if (slotData) startTime = slotData.start_s;
            }

            if (startTime != null && startTime !== undefined && videoRef.current) {
                videoRef.current.currentTime = startTime;
                wavesurferRef.current.setTime(startTime);
            }
        }
    }, [focusedSlot, focusedSlotSignature, videoRef]);

    if (!activeJobData?.video_path) {
        return null;
    }

    const hasTtsRecords = activeJobData?.gpt_records?.some((r: GPTRecord) => r.slot);

    return (
        <div className="flex flex-col border-t border-border-subtle bg-bg-surface mt-2 rounded-t-xl overflow-hidden shadow-md">
            <div className="flex items-center justify-between px-4 py-2 bg-bg-card border-b border-border-subtle">
                <div className="flex items-center gap-6">
                    <span className="text-[10px] font-bold uppercase tracking-widest text-text-muted">
                        Timeline (Sprechpausen &amp; AD-Slots)
                    </span>
                    {isBuffering && <span className="text-[10px] text-yellow-500 font-bold tracking-widest uppercase">⏳ Puffert...</span>}
                    <div className="flex items-center gap-3">
                        <button
                            className="material-icons-round text-[1.2rem] hover:text-violet-500 text-text-primary transition-colors flex items-center justify-center p-1 rounded-full hover:bg-bg-surface"
                            onClick={() => wavesurferRef.current?.playPause()}
                            title={isPlaying ? 'Pause' : 'Play'}
                        >
                            {isPlaying ? 'pause_circle_filled' : 'play_circle_filled'}
                        </button>
                    </div>

                    {hasTtsRecords && (
                        <button
                            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold transition-all border ${adAudioEnabled
                                ? 'bg-violet-600 text-white border-violet-500 shadow-sm shadow-violet-500/30'
                                : 'bg-bg-surface text-text-muted border-border-subtle hover:border-violet-500/50 hover:text-violet-400'}`}
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
                            className="w-24 accent-violet-500 h-1 bg-bg-surface rounded appearance-none"
                            type="range"
                            min="10"
                            max="500"
                            value={zoom}
                            onChange={(e) => setZoom(Number(e.target.value))}
                        />
                    </div>
                    <div className="text-[11px] font-mono px-2 py-1 bg-bg-surface rounded border border-border-subtle text-text-primary">
                        {formatTime(currentTime)} / {formatTime(duration)}
                    </div>
                </div>
            </div>

            <div className="bg-bg-base p-4 relative pt-2">
                <div ref={containerRef} className="w-full"></div>
            </div>
        </div>
    );
}
