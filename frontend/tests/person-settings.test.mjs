// Run from frontend: node --test tests/person-stage-events.test.mjs
import { test } from 'node:test';
import { chromium, expect } from '@playwright/test';
import { createServer } from 'vite';

test('person settings persist, reset and reach each stage in automatic execution', async () => {
    const fixture = `
        import React from 'react';
        import { createRoot } from 'react-dom/client';
        import { JobProvider, useJob } from '/src/hooks/useJob.tsx';
        import { ConfigModal } from '/src/components/features/ConfigModal.tsx';
        function Review() {
            const job = useJob();
            return React.createElement(React.Fragment, null,
                React.createElement(ConfigModal),
                React.createElement('button', { onClick: () => job.setIsConfigModalOpen(true) }, 'Settings'),
                React.createElement('button', { onClick: job.runAllSteps }, 'Run all'),
                React.createElement('button', { onClick: job.handleRunPersons }, 'Cluster'),
                React.createElement('button', { onClick: () => job.fetchJobData('fixture', true) }, 'Refresh'),
                React.createElement('output', { id: 'state' }, JSON.stringify({
                    done: [...job.doneSteps], progress: job.progressData.identities,
                    step: job.currentStep, params: job.personParams
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
            window.emitCompletion = (phase) => {
                for (const stream of [...streams]) {
                    if (stream.url === '/api/jobs/fixture/stream') stream.onmessage?.({
                        data: JSON.stringify({ event: phase + '_done', data: { stage_version: 1 } }),
                    });
                }
            };
        });
        const requests = [];
        let trackingReady = false;
        let identitiesReady = false;
        await page.route('**/api/**', async route => {
            const request = route.request();
            const path = new URL(request.url()).pathname;
            let json = {};
            if (path === '/api/jobs/fixture') json = {
                job_id:'fixture', status:'idle', video_stats:{}, pauses_count:1, transcript_meta:{}, slots_count:1, images_count:1,
                person_stages:{tracking_ready:trackingReady, identities_ready:identitiesReady, similarity_threshold:0.214},
            };
            if (request.method() === 'POST' && path.includes('/person-analysis/')) requests.push({phase:path.split('/').pop(),body:request.postDataJSON()});
            await route.fulfill({json});
        });
        await page.goto(`${server.resolvedUrls.local[0]}events-test?job=fixture`);
        await page.getByRole('button',{name:'Settings',exact:true}).click();
        await page.getByRole('button',{name:'👤 Personen',exact:true}).click();
        await expect(page.getByLabel('Trackingabstand (Sekunden)',{exact:true})).toHaveValue('0.233');
        await expect(page.getByLabel('Clustering-Schwellenwert',{exact:true})).toHaveValue('0.214');
        await expect(page.getByLabel('Maximale Bilderzahl pro Person',{exact:true})).toHaveValue('5');
        await page.getByLabel('Trackingabstand (Sekunden)',{exact:true}).fill('0.1');
        await page.getByLabel('Clustering-Schwellenwert',{exact:true}).fill('0.4');
        await page.getByLabel('Maximale Bilderzahl pro Person',{exact:true}).fill('2');
        await expect(page.getByText('Einstellung geändert – betreffenden Schritt erneut ausführen.',{exact:true})).toBeVisible();
        await page.reload();
        await page.getByRole('button',{name:'Settings',exact:true}).click();
        await page.getByRole('button',{name:'👤 Personen',exact:true}).click();
        await expect(page.getByLabel('Trackingabstand (Sekunden)',{exact:true})).toHaveValue('0.1');
        await expect(page.getByLabel('Clustering-Schwellenwert',{exact:true})).toHaveValue('0.4');
        await expect(page.getByLabel('Maximale Bilderzahl pro Person',{exact:true})).toHaveValue('2');
        await page.getByRole('button',{name:'Schließen & Übernehmen',exact:true}).click();
        await page.getByRole('button',{name:'Run all',exact:true}).click();
        await expect.poll(()=>requests.length).toBe(1);
        expect(requests[0]).toEqual({phase:'tracking',body:{tracking_interval_seconds:0.1}});
        trackingReady = true;
        await page.evaluate(()=>window.emitCompletion('tracking'));
        await expect.poll(()=>requests.length).toBe(2);
        expect(requests[1]).toEqual({phase:'identities',body:{similarity_threshold:0.4}});
        identitiesReady = true;
        await page.evaluate(()=>window.emitCompletion('identities'));
        await expect.poll(()=>requests.length).toBe(3);
        expect(requests[2]).toEqual({phase:'attributes',body:{max_images:2}});
        await page.getByRole('button',{name:'Settings',exact:true}).click();
        await page.getByRole('button',{name:'Personen-Standardwerte wiederherstellen',exact:true}).click();
        await expect(page.getByLabel('Trackingabstand (Sekunden)',{exact:true})).toHaveValue('0.233');
        await expect(page.getByLabel('Clustering-Schwellenwert',{exact:true})).toHaveValue('0.214');
        await expect(page.getByLabel('Maximale Bilderzahl pro Person',{exact:true})).toHaveValue('5');
    } finally {
        await browser?.close();
        await server.close();
    }
});
