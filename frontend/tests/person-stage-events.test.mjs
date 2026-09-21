// Run from frontend: node --test tests/person-stage-events.test.mjs
import { test } from 'node:test';
import { chromium, expect } from '@playwright/test';
import { createServer } from 'vite';

test('repeated identity revision completes again after review, but duplicate events do not restart attributes', async () => {
    const fixture = `
        import React from 'react';
        import { createRoot } from 'react-dom/client';
        import { JobProvider, useJob } from '/src/hooks/useJob.tsx';
        function Review() {
            const job = useJob();
            return React.createElement(React.Fragment, null,
                React.createElement('button', { onClick: job.runAllSteps }, 'Run all'),
                React.createElement('button', { onClick: job.handleRunPersons }, 'Cluster'),
                React.createElement('button', { onClick: () => job.fetchJobData('fixture', true) }, 'Refresh'),
                React.createElement('output', { id: 'state' }, JSON.stringify({
                    done: [...job.doneSteps], progress: job.progressData.identities,
                    step: job.currentStep
                })));
        }
        createRoot(document.getElementById('root')).render(React.createElement(JobProvider, null, React.createElement(Review)));
    `;
    const server = await createServer({
        server: { host: '127.0.0.1', port: 0, open: false },
        plugins: [{
            name: 'person-stage-events-fixture',
            resolveId(id) { if (id === '/events-fixture.js') return '\0events-fixture'; },
            load(id) { if (id === '\0events-fixture') return fixture; },
            configureServer(vite) {
                vite.middlewares.use('/events-test', async (_req, res, next) => {
                    try {
                        res.setHeader('Content-Type', 'text/html');
                        res.end(await vite.transformIndexHtml('/events-test', '<div id="root"></div><script type="module" src="/events-fixture.js"></script>'));
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
            const streams = new Set();
            window.EventSource = class {
                constructor(url) { this.url = url; streams.add(this); }
                close() { streams.delete(this); }
                addEventListener() {}
                removeEventListener() {}
            };
            window.emitCompletion = (event = 'identities_done') => {
                for (const stream of [...streams]) {
                    if (stream.url === '/api/jobs/fixture/stream') stream.onmessage?.({
                        data: JSON.stringify({ event, data: { stage_version: 1 } }),
                    });
                }
            };
        });
        let identitiesReady = false;
        let identityStarts = 0;
        let attributeStarts = 0;
        await page.route('**/api/**', async route => {
            const request = route.request();
            const path = new URL(request.url()).pathname;
            let json = {};
            if (path === '/api/jobs/fixture') json = {
                job_id: 'fixture', status: 'idle', video_stats: {}, pauses_count: 1,
                transcript_meta: {}, slots_count: 1, images_count: 1,
                person_stages: { tracking_ready: true, identities_ready: identitiesReady },
            };
            if (request.method() === 'POST' && path.endsWith('/identities')) identityStarts++;
            if (request.method() === 'POST' && path.endsWith('/attributes')) attributeStarts++;
            await route.fulfill({ json });
        });
        await page.goto(`${server.resolvedUrls.local[0]}events-test?job=fixture`);
        const state = async () => JSON.parse(await page.locator('#state').textContent());
        await expect.poll(async () => (await state()).done.includes(5)).toBe(true);
        // First completion in this browser session, using a manual start.
        await page.getByRole('button', { name: 'Cluster', exact: true }).click();
        await expect.poll(() => identityStarts).toBe(1);
        identitiesReady = true;
        await page.evaluate(() => window.emitCompletion());
        await expect.poll(async () => (await state()).progress).toBeNull();
        // A tracking review invalidates persons.json; the next identity revision is 1 again.
        identitiesReady = false;
        await page.getByRole('button', { name: 'Refresh', exact: true }).click();
        await expect.poll(async () => (await state()).done.includes(6)).toBe(false);
        await page.getByRole('button', { name: 'Run all', exact: true }).click();
        await expect.poll(() => identityStarts).toBe(2);
        identitiesReady = true;
        await page.evaluate(() => window.emitCompletion());
        await expect.poll(() => attributeStarts).toBe(1);
        await expect.poll(async () => (await state()).progress).toBeNull();
        await expect.poll(async () => (await state()).done.includes(6)).toBe(true);
        // A duplicate completion must not start another attribute job or refresh the job.
        const requests = [];
        page.on('request', request => requests.push(request.url()));
        await page.evaluate(() => { window.emitCompletion(); window.emitCompletion(); });
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        expect(attributeStarts).toBe(1);
        expect(requests.filter(url => url.includes('/api/jobs/fixture'))).toHaveLength(0);
        // The retired combined-stage event must not bypass attributes and start GPT.
        const beforeLegacyEvent = await state();
        await page.evaluate(() => window.emitCompletion('persons_done'));
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        expect(await state()).toEqual(beforeLegacyEvent);
        expect(requests.filter(url => url.endsWith('/gpt'))).toHaveLength(0);
    } finally {
        await browser?.close();
        await server.close();
    }
});
