import { test } from 'node:test';
import { chromium, expect } from '@playwright/test';
import { createServer } from 'vite';

test('person function is shared by cluster and attribute review, survives reload and can be cleared', async () => {
    const server = await createServer({
        server: { host: '127.0.0.1', port: 0, open: false },
        plugins: [{
            name: 'person-metadata-fixture', enforce: 'pre',
            resolveId(id) { if (id === '/metadata-fixture.js') return '\0metadata-fixture'; },
            load(id) {
                if (id.replaceAll('\\', '/').endsWith('/src/hooks/useJob.tsx')) return `
                    import React from 'react';
                    export const Context = React.createContext(null);
                    export const useJob = () => React.useContext(Context);
                `;
                if (id === '\0metadata-fixture') return `
                    import React from 'react';
                    import { createRoot } from 'react-dom/client';
                    import { Context } from '/src/hooks/useJob.tsx';
                    import { StepAttributes } from '/src/components/features/StepAttributes.tsx';
                    import { StepPersons } from '/src/components/features/StepPersons.tsx';
                    function Fixture() {
                        const [step, setStep] = React.useState(7);
                        const [revision, setRevision] = React.useState(0);
                        const value = { currentStep:step, jobData:{job_id:'fixture',status:'idle',persons_version:revision,
                            person_stages:{identities_ready:true,tracking_ready:true}}, progressData:{},
                            fetchJobData:async()=>setRevision(v=>v+1),handleRunAttributes:()=>{},handleRunPersons:()=>{} };
                        return React.createElement(Context.Provider,{value},
                            React.createElement('button',{onClick:()=>setStep(step===7?6:7)},'Wechseln'),
                            step===7?React.createElement(StepAttributes):React.createElement(StepPersons));
                    }
                    createRoot(document.getElementById('root')).render(React.createElement(Fixture));
                `;
            },
            configureServer(vite) {
                vite.middlewares.use('/metadata-test', async (_req, res, next) => {
                    try {
                        res.setHeader('Content-Type','text/html');
                        res.end(await vite.transformIndexHtml('/metadata-test','<div id="root"></div><script type="module" src="/metadata-fixture.js"></script>'));
                    } catch(error) { next(error); }
                });
            },
        }],
    });
    let browser;
    try {
        await server.listen();
        browser = await chromium.launch({ channel:'msedge', headless:true });
        const page = await browser.newPage();
        const person = {person_id:1,name:'Person 1',function:'',description:'Alte freie Beschreibung',appearances_count:1,track_ids:[1],appearances:[],status:'ok',images:[],attributes:{}};
        let revision = 1;
        const review = () => ({persons:[person],version:`1:${revision}`,analysis_id:'1',tracks:[],unassigned_tracks:[],review_available:true});
        const errors = [];
        page.on('pageerror', error=>errors.push(error.message));
        await page.route('**/api/**', async route => {
            const path = new URL(route.request().url()).pathname;
            if (route.request().method()==='POST') {
                const body = route.request().postDataJSON();
                expect(body.version).toBe(`1:${revision}`);
                expect(body).not.toHaveProperty('description');
                for (const field of ['name','function']) if(field in body) person[field]=body[field].trim();
                revision++;
            }
            await route.fulfill({json:path.endsWith('/attributes') ? {ready:true,stale:false,version:'a1',persons:[person],fields:[],labels:{}} : review()});
        });
        await page.goto(`${server.resolvedUrls.local[0]}metadata-test`);
        await page.getByRole('button',{name:'Attribute prüfen / bearbeiten',exact:true}).click();
        await page.getByLabel('Name Person 1',{exact:true}).fill('Anna');
        await page.getByLabel('Funktion Person 1',{exact:true}).fill('Försterin');
        await page.getByRole('button',{name:'Änderungen speichern',exact:true}).click();
        await expect(page.getByText('Gespeichert: Försterin',{exact:true})).toBeVisible();
        await page.getByRole('button',{name:'Attribut-Review schließen'}).click();
        await page.getByRole('button',{name:'Wechseln'}).click();
        await expect(page.getByText('Försterin',{exact:true})).toBeVisible();
        await page.getByRole('button',{name:'Person 1 bearbeiten',exact:true}).click();
        await expect(page.getByLabel('Beschreibung',{exact:true})).toHaveCount(0);
        await expect(page.getByText('Alte freie Beschreibung',{exact:true})).toHaveCount(0);
        await expect(page.getByLabel('Name',{exact:true})).toHaveValue('Anna');
        await expect(page.getByLabel('Funktion',{exact:true})).toHaveValue('Försterin');
        await page.getByLabel('Funktion',{exact:true}).fill('Moderatorin');
        await page.getByRole('button',{name:'Speichern',exact:true}).click();
        await page.getByRole('button',{name:'Wechseln'}).click();
        await page.getByRole('button',{name:'Attribute prüfen / bearbeiten',exact:true}).click();
        await expect(page.getByLabel('Funktion Person 1',{exact:true})).toHaveValue('Moderatorin');
        await page.reload();
        await page.getByRole('button',{name:'Attribute prüfen / bearbeiten',exact:true}).click();
        await expect(page.getByLabel('Funktion Person 1',{exact:true})).toHaveValue('Moderatorin');
        await page.getByLabel('Funktion Person 1',{exact:true}).fill('');
        await page.getByRole('button',{name:'Änderungen speichern',exact:true}).click();
        await expect(page.getByText('Gespeichert: —',{exact:true})).toBeVisible();
        await page.reload();
        await page.getByRole('button',{name:'Attribute prüfen / bearbeiten',exact:true}).click();
        await expect(page.getByLabel('Funktion Person 1',{exact:true})).toHaveValue('');
        expect(errors).toEqual([]);
    } finally { await browser?.close(); await server.close(); }
});
