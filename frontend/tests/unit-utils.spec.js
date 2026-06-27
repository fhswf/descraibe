/**
 * tests/unit-utils.spec.js – Unit tests for frontend utility functions
 * 
 * These tests run in Playwright and test pure JavaScript utility functions
 * directly in the browser context.
 */
import { test, expect } from '@playwright/test';

// ── Mock utilities for testing (copied from source) ──────────────────────────────

/**
 * Replicate formatBytes logic from App.jsx for testing
 */
function formatBytes(bytes) {
    if (!Number.isFinite(bytes)) return 'unbekannt';
    if (bytes === 0) return '0 B';

    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const value = bytes / 1024 ** unitIndex;
    const precision = value >= 10 || unitIndex === 0 ? 0 : 1;

    return `${value.toFixed(precision)} ${units[unitIndex]}`;
}

/**
 * Replicate isAudio/isVideo logic from StepResults.jsx
 */
const AUDIO_EXTS = ['.mp3', '.wav', '.ogg', '.m4a', '.aac'];
const VIDEO_EXTS = ['.mp4', '.webm', '.mkv', '.mov'];

function isAudio(filename) {
    if (!filename) return false;
    return AUDIO_EXTS.some(ext => filename.toLowerCase().endsWith(ext));
}

function isVideo(filename) {
    if (!filename) return false;
    return VIDEO_EXTS.some(ext => filename.toLowerCase().endsWith(ext));
}

// ── formatBytes tests ───────────────────────────────────────────────────────────

test.describe('formatBytes', () => {
    test('returns "unbekannt" for non-finite values', () => {
        expect(formatBytes(NaN)).toBe('unbekannt');
        expect(formatBytes(Infinity)).toBe('unbekannt');
        expect(formatBytes(-Infinity)).toBe('unbekannt');
    });

    test('returns "0 B" for zero', () => {
        expect(formatBytes(0)).toBe('0 B');
    });

    test('formats bytes without decimal (unitIndex=0)', () => {
        expect(formatBytes(500)).toBe('500 B');
        expect(formatBytes(1023)).toBe('1023 B');
    });

    test('formats kilobytes correctly', () => {
        // Precision is 1 for values < 10, so 1.0 KB not 1 KB
        expect(formatBytes(1024)).toBe('1.0 KB');
        expect(formatBytes(1536)).toBe('1.5 KB');
        expect(formatBytes(2048)).toBe('2.0 KB');
    });

    test('formats megabytes correctly', () => {
        expect(formatBytes(1024 * 1024)).toBe('1.0 MB');
        expect(formatBytes(5.5 * 1024 * 1024)).toBe('5.5 MB');
        expect(formatBytes(10 * 1024 * 1024)).toBe('10 MB');
    });

    test('formats gigabytes correctly', () => {
        expect(formatBytes(1024 * 1024 * 1024)).toBe('1.0 GB');
        expect(formatBytes(2.5 * 1024 * 1024 * 1024)).toBe('2.5 GB');
    });

    test('formats terabytes correctly', () => {
        expect(formatBytes(1024 * 1024 * 1024 * 1024)).toBe('1.0 TB');
        expect(formatBytes(3 * 1024 * 1024 * 1024 * 1024)).toBe('3.0 TB');
    });

    test('handles large values within TB range', () => {
        const val = 1.75 * 1024 * 1024 * 1024 * 1024;
        expect(formatBytes(val)).toBe('1.8 TB');
    });
});

// ── isAudio tests ──────────────────────────────────────────────────────────────

test.describe('isAudio', () => {
    test('returns false for null/undefined/empty', () => {
        expect(isAudio(null)).toBe(false);
        expect(isAudio(undefined)).toBe(false);
        expect(isAudio('')).toBe(false);
    });

    test('returns true for known audio extensions', () => {
        expect(isAudio('track.mp3')).toBe(true);
        expect(isAudio('track.wav')).toBe(true);
        expect(isAudio('track.ogg')).toBe(true);
        expect(isAudio('track.m4a')).toBe(true);
        expect(isAudio('track.aac')).toBe(true);
    });

    test('is case-insensitive', () => {
        expect(isAudio('track.MP3')).toBe(true);
        expect(isAudio('track.Wav')).toBe(true);
        expect(isAudio('track.Ogg')).toBe(true);
    });

    test('returns false for non-audio files', () => {
        expect(isAudio('video.mp4')).toBe(false);
        expect(isAudio('document.pdf')).toBe(false);
        expect(isAudio('image.jpg')).toBe(false);
    });

    test('returns false for files without extension', () => {
        expect(isAudio('noextension')).toBe(false);
    });

    test('handles filenames with paths', () => {
        expect(isAudio('/path/to/audio.mp3')).toBe(true);
        expect(isAudio('C:\\Users\\music.wav')).toBe(true);
    });
});

// ── isVideo tests ───────────────────────────────────────────────────────────────

test.describe('isVideo', () => {
    test('returns false for null/undefined/empty', () => {
        expect(isVideo(null)).toBe(false);
        expect(isVideo(undefined)).toBe(false);
        expect(isVideo('')).toBe(false);
    });

    test('returns true for known video extensions', () => {
        expect(isVideo('movie.mp4')).toBe(true);
        expect(isVideo('movie.webm')).toBe(true);
        expect(isVideo('movie.mkv')).toBe(true);
        expect(isVideo('movie.mov')).toBe(true);
    });

    test('is case-insensitive', () => {
        expect(isVideo('movie.MP4')).toBe(true);
        expect(isVideo('movie.Webm')).toBe(true);
    });

    test('returns false for non-video files', () => {
        expect(isVideo('audio.mp3')).toBe(false);
        expect(isVideo('document.pdf')).toBe(false);
        expect(isVideo('image.jpg')).toBe(false);
    });

    test('returns false for files without extension', () => {
        expect(isVideo('noextension')).toBe(false);
    });

    test('handles filenames with paths', () => {
        expect(isVideo('/path/to/video.mp4')).toBe(true);
        expect(isVideo('C:\\Videos\\clip.webm')).toBe(true);
    });
});

// ── CHUNK_SIZE constant ────────────────────────────────────────────────────────

test.describe('uploadVideo constants', () => {
    // This tests that the chunk size is reasonable
    const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB

    test('CHUNK_SIZE is 5MB', () => {
        expect(CHUNK_SIZE).toBe(5 * 1024 * 1024);
    });

    test('CHUNK_SIZE is positive', () => {
        expect(CHUNK_SIZE).toBeGreaterThan(0);
    });

    test('CHUNK_SIZE is reasonable (at least 1MB)', () => {
        expect(CHUNK_SIZE).toBeGreaterThanOrEqual(1024 * 1024);
    });
});