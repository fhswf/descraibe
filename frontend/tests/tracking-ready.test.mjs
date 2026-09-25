import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chromium, expect } from '@playwright/test';
import { createServer } from 'vite';

test('tracking results load only when ready and disappear after invalidation', async () => {
    const fixture = `
        import React from 'react';
        import { createRoot } from 'react-dom/client';
        import { JobProvider, useJob } from '/src/hooks/useJob.tsx';
        import { StepTracking } from '/src/components/features/StepTracking.tsx';
        function Fixture() {
            const job = useJob();
            return React.createElement(React.Fragment, null,
                React.createElement('button', { onClick: () => job.setCurrentStep(5) }, 'Show tracking'),
                React.createElement('button', { onClick: () => job.fetchJobData('fixture', true) }, 'Refresh'),
                React.createElement('output', { id: 'ready' }, String(job.jobData?.person_stages?.tracking_ready)),
                React.createElement(StepTracking));
        }
        createRoot(document.getElementById('root')).render(React.createElement(JobProvider, null, React.createElement(Fixture)));
    `;
    const server = await createServer({
        server: { host: '127.0.0.1', port: 0, open: false },
        plugins: [{
            name: 'tracking-ready-fixture',
            resolveId(id) { if (id === '/tracking-ready-fixture.js') return '\0tracking-ready-fixture'; },
            load(id) { if (id === '\0tracking-ready-fixture') return fixture; },
            configureServer(vite) {
                vite.middlewares.use('/tracking-ready-test', async (_req, res, next) => {
                    try {
                        res.setHeader('Content-Type', 'text/html');
                        res.end(await vite.transformIndexHtml('/tracking-ready-test', '<div id="root"></div><script type="module" src="/tracking-ready-fixture.js"></script>'));
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
        await page.addInitScript(() => {
            window.EventSource = class {
                close() {} addEventListener() {} removeEventListener() {}
            };
        });
        let ready = false;
        let fail = false;
        let requests = 0;
        await page.route('**/api/**', async route => {
            const path = new URL(route.request().url()).pathname;
            if (path === '/api/jobs/fixture/person-analysis/tracking') {
                requests++;
                return route.fulfill(fail || !ready
                    ? { status: 409, json: { error: 'Tracking-Daten beschädigt.' } }
                    : { json: { version: 1, analysis_id: 'tracking-1', tracks: [], excluded_face_observations: [], split_available: true } });
            }
            await route.fulfill({ json: path === '/api/jobs/fixture' ? {
                job_id: 'fixture', status: 'idle', video_path: 'video.mp4', video_stats: {},
                images_count: 1, person_stages: { tracking_ready: ready, tracking_revision: ready ? 1 : null, identities_ready: false },
            } : {} });
        });
        await page.goto(`${server.resolvedUrls.local[0]}tracking-ready-test?job=fixture`);
        await expect(page.locator('#ready')).toHaveText('false');
        await page.getByRole('button', { name: 'Show tracking', exact: true }).click();
        await expect(page.getByRole('button', { name: 'Tracking ausführen', exact: true })).toBeVisible();
        await page.waitForTimeout(150);
        assert.equal(requests, 0);
        ready = true;
        await page.getByRole('button', { name: 'Refresh', exact: true }).click();
        await expect(page.getByRole('button', { name: 'Tracks prüfen', exact: true })).toBeVisible();
        assert.equal(requests, 1);
        await page.getByRole('button', { name: 'Tracks prüfen', exact: true }).click();
        ready = false;
        await page.getByRole('button', { name: 'Refresh', exact: true }).click({ force: true });
        await expect(page.locator('#ready')).toHaveText('false');
        await expect(page.getByRole('dialog', { name: 'Tracking-Review', exact: true })).toHaveCount(0);
        await expect(page.getByRole('button', { name: 'Tracks prüfen', exact: true })).toHaveCount(0);
        assert.equal(requests, 1);
        // Genuine errors must still be visible when results are advertised as ready.
        ready = true;
        fail = true;
        await page.getByRole('button', { name: 'Refresh', exact: true }).click();
        await expect(page.getByRole('alert')).toHaveText('Tracking-Daten beschädigt.');
        assert.equal(requests, 2);
    } finally {
        await browser?.close();
        await server.close();
    }
});
