// Run from frontend: node --test tests/review-previews.test.mjs
import { test } from 'node:test';
import { Buffer } from 'node:buffer';
import { chromium, expect } from '@playwright/test';
import { createServer } from 'vite';

test('tracking review expands all faces and keeps exclusions reversible', async () => {
    const fixture = `
        import React from 'react';
        import { createRoot } from 'react-dom/client';
        import { TrackRow } from '/src/components/features/FaceMergeDialog.tsx';
        const crops = Array.from({ length: 26 }, (_, i) => ({
            crop_id: i + 1, face_id: i + 1, track_id: 1, frame_number: i + 1,
            timestamp_s: i / 2, width: 100, height: 200,
            face_bbox: [10, 10, 40, 50], excluded: i === 0 || i === 25,
            evidence_status: 'retinaface'
        }));
        function Fixture() {
            const [exclusions, setExclusions] = React.useState({});
            return React.createElement(TrackRow, {
                track: { track_id: 1, scene_id: 1, start_s: 0, end_s: 13,
                    review_observation_count: 26, review_mode: 'retinaface' },
                initialCrops: crops, jobId: 'fixture', analysisId: 'tracking-1',
                version: '1', persons: [], disabled: false, allowExclusions: true,
                showAssignments: false, exclusions,
                onExclude: (id, excluded) => setExclusions(prev => ({ ...prev, [id]: excluded })),
                onChoose() {}, onUndo() {}, onEnlarge() {}
            });
        }
        createRoot(document.getElementById('root')).render(React.createElement(Fixture));
    `;
    const server = await createServer({
        server: { host: '127.0.0.1', port: 0, open: false },
        plugins: [{
            name: 'review-test-fixture',
            resolveId(id) { if (id === '/review-fixture.js') return '\0review-fixture'; },
            load(id) { if (id === '\0review-fixture') return fixture; },
            configureServer(vite) {
                vite.middlewares.use('/review-test', async (_request, response, next) => {
                    try {
                        const html = await vite.transformIndexHtml('/review-test',
                            '<html><body><div id="root"></div><script type="module" src="/review-fixture.js"></script></body></html>');
                        response.setHeader('Content-Type', 'text/html');
                        response.end(html);
                    } catch (error) { next(error); }
                });
            },
        }],
    });
    let browser;
    try {
        await server.listen();
        browser = await chromium.launch({ channel: 'msedge', headless: true });
        const page = await browser.newPage();
        await page.route('**/api/jobs/fixture/person-crops/**', route => route.fulfill({
            contentType: 'image/gif', body: Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7', 'base64'),
        }));
        await page.goto(`${server.resolvedUrls.local[0]}review-test`);
        const images = page.getByRole('button', { name: 'Crop vergrößern:', exact: false });
        await expect(images).toHaveCount(12);
        await expect(page.getByRole('button', { name: 'Face 1 wiederherstellen', exact: true })).toBeVisible();
        await page.getByRole('button', { name: 'Weitere Bilder anzeigen (12 / 26)' }).click();
        await expect(images).toHaveCount(24);
        await page.getByRole('button', { name: 'Weitere Bilder anzeigen (24 / 26)' }).click();
        await expect(images).toHaveCount(26);
        await expect(page.getByRole('button', { name: 'Weitere Bilder anzeigen', exact: false })).toHaveCount(0);
        await page.getByRole('button', { name: 'Face 26 wiederherstellen', exact: true }).click();
        await expect(page.getByRole('button', { name: 'Face 26 ausschließen', exact: true })).toBeVisible();
        await page.getByRole('button', { name: 'Face 26 ausschließen', exact: true }).click();
        await expect(page.getByRole('button', { name: 'Face 26 wiederherstellen', exact: true })).toBeVisible();
        await expect(images).toHaveCount(26);
    } finally {
        await browser?.close();
        await server.close();
    }
});
