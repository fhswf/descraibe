// Run from frontend: node --test tests/profile-image.test.mjs
import { test } from 'node:test';
import { Buffer } from 'node:buffer';
import { chromium, expect } from '@playwright/test';
import { createServer } from 'vite';

test('profile image selection saves, reopens, resets and rejects conflicts', async () => {
    const fixture = `
        import React from 'react';
        import { createRoot } from 'react-dom/client';
        import { FaceMergeDialog } from '/src/components/features/FaceMergeDialog.tsx';
        function Fixture() {
            const [open, setOpen] = React.useState(true);
            const [snapshot, setSnapshot] = React.useState({version:'1:1',analysis_id:'tracking-1',persons:[{person_id:1,name:'Test',profile_crop_id:null}],tracks:[{track_id:1,person_id:1,scene_id:1,start_s:0,end_s:2,review_observation_count:2,review_mode:'facemoe'}]});
            return open ? React.createElement(FaceMergeDialog, {
                person:snapshot.persons[0], snapshot, jobId:'fixture',
                onSaved:setSnapshot, onClose:()=>setOpen(false)
            }) : React.createElement('button',{onClick:()=>setOpen(true)},'Tracks öffnen');
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
        let version = 1;
        let conflict = false;
        const writes = [];
        await page.route('**/api/jobs/fixture/tracks/1/crops', route => route.fulfill({json:{
            version:`1:${version}`, analysis_id:'tracking-1', crops:[1,2].map(id=>({
                crop_id:id,face_id:id,excluded:false,track_id:1,frame_number:id,timestamp_s:id,width:100,height:200,face_bbox:null
            }))
        }}));
        await page.route('**/api/jobs/fixture/persons/1', route => {
            const body = route.request().postDataJSON();
            if(conflict) return route.fulfill({status:409,json:{error:'Personenstand geändert'}});
            expect(body.version).toBe(`1:${version}`);
            writes.push(body.profile_crop_id);
            version++;
            return route.fulfill({json:{version:`1:${version}`,analysis_id:'tracking-1',persons:[{person_id:1,name:'Test',profile_crop_id:body.profile_crop_id,representative_crop_id:body.profile_crop_id ?? 1}],tracks:[{track_id:1,person_id:1,scene_id:1,start_s:0,end_s:2,review_observation_count:2,review_mode:'facemoe'}]}});
        });
        await page.goto(`${server.resolvedUrls.local[0]}review-test`);
        await page.getByRole('button',{name:'Als Profilbild verwenden',exact:true}).nth(1).click();
        await expect(page.getByText('Profilbild gespeichert.', {exact:true})).toBeVisible();
        await expect(page.getByRole('button',{name:'Aktuelles Profilbild'})).toHaveCount(1);
        await page.getByRole('button',{name:'Track-Verwaltung schließen'}).click();
        await page.getByRole('button',{name:'Tracks öffnen'}).click();
        await expect(page.getByRole('button',{name:'Aktuelles Profilbild'})).toHaveCount(1);
        await page.getByRole('button',{name:'Automatische Bildwahl verwenden',exact:true}).click();
        await expect(page.getByText('Profilbild gespeichert.', {exact:true})).toBeVisible();
        expect(writes).toEqual([2,null]);
        await page.getByRole('button',{name:'Track zuweisen',exact:true}).click();
        await page.getByRole('button',{name:'Nicht zugeordnet',exact:true}).click();
        await expect(page.getByRole('button',{name:'Als Profilbild verwenden',exact:true})).toBeDisabled();
        await page.getByRole('button',{name:'Zurücknehmen',exact:true}).click();
        conflict = true;
        await page.getByRole('button',{name:'Als Profilbild verwenden',exact:true}).click();
        await expect(page.getByRole('alert')).toHaveText('Personenstand geändert');
        await expect(page.getByRole('dialog',{name:'Tracks verwalten'})).toBeVisible();
    } finally {
        await browser?.close();
        await server.close();
    }
});
