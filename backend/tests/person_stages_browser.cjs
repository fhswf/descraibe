/* Isolated server: backend/tests/person_review_server.py; deterministic models, real API/SSE/video. */
const { chromium, expect } = require('../../frontend/node_modules/@playwright/test');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const base = process.argv[2];
  assert(/^http:\/\/127\.0\.0\.1:\d+$/.test(base), 'Explicit loopback fixture URL required');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await page.addInitScript(() => {
      window.__reviewCommits = 0;
      window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
        supportsFiber: true, inject: () => 1,
        onCommitFiberRoot: () => { window.__reviewCommits++; },
        onCommitFiberUnmount: () => {}, checkDCE: () => {},
      };
      window.__sizeWrites = 0;
      const original = Storage.prototype.setItem;
      Storage.prototype.setItem = function(key, value) {
        if (key.startsWith('descraibe.review.')) window.__sizeWrites++;
        return original.call(this, key, value);
      };
    });
    const errors = [], requests = [], batches = [], dialogs = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('dialog', async d => { dialogs.push(d.message()); await d.accept(); });
    page.on('request', r => {
      if (r.method() === 'POST') requests.push(new URL(r.url()).pathname);
      if (r.url().endsWith('/track-assignments') && r.method() === 'POST') batches.push(r.postDataJSON());
      assert(!/similar-faces|merge-suggestions|\/faces\//.test(r.url()), 'No old face routes in new UI');
    });
    // Earlier workflow steps are already complete in this frontend fixture.
    // GPT is intercepted: the test only exercises the handoff, never external services.
    await page.route('**/api/jobs/job', async route => {
      const response = await route.fetch();
      const data = await response.json();
      await route.fulfill({ response, json: { ...data, video_stats: { duration_s: 2, fps: 30 }, pauses_count: 1,
        transcript_meta: { segments_count: 1 }, slots_count: 1, images_count: 1 } });
    });
    await page.route('**/api/jobs/job/gpt', route => route.fulfill({ json: { status: 'started' } }));
    await page.goto(`${base}/?job=job`);
    await page.getByRole('button', { name: /Alle Schritte ausführen/ }).click();
    await expect.poll(() => requests.filter(p => /person-analysis\/(tracking|identities|attributes)$/.test(p)), { timeout: 20000 })
      .toEqual(['/api/jobs/job/person-analysis/tracking', '/api/jobs/job/person-analysis/identities', '/api/jobs/job/person-analysis/attributes']);
    const snapshot = async () => (await page.request.get(`${base}/api/jobs/job/persons`)).json();
    await expect.poll(async () => (await snapshot()).identities_ready).toBe(true);
    // Configuration may intentionally contain no GPT credentials/model on this host.
    await expect.poll(async () => requests.includes('/api/jobs/job/gpt') || dialogs.some(d => /GPT-Modell|Prompts fehlen/.test(d))).toBe(true);
    if (await page.getByRole('button', { name: /Ausführung anhalten/ }).count())
      await page.getByRole('button', { name: /Ausführung anhalten/ }).click();
    assert(!dialogs.some(d => /bestätigen|Bereinigung/.test(d)), 'Optional reviews never interrupt Run All');
    console.log('PASS: Run All -> tracking -> identities -> attributes automatically, without manual review');
    const nav = async n => {
      const review = page.getByRole('dialog', { name: 'Tracking-Review', exact: true });
      if (await review.count()) await review.getByRole('button', { name: 'Tracking-Review schließen', exact: true }).click();
      await page.locator('#step-nav > button').nth(n).click();
      if (n === 5) await page.getByRole('button', { name: 'Tracks prüfen', exact: true }).click();
    };
    const track = id => page.getByRole('region', { name: `Track ${id}`, exact: true });
    await nav(7);
    const openAttributes = async () => {
      await page.getByRole('button', { name: 'Attribute prüfen / bearbeiten', exact: true }).click();
      return page.getByRole('dialog', { name: 'Attribut-Review', exact: true });
    };
    const attributeReview = await openAttributes();
    const attributes = attributeReview.getByRole('region', { name: 'Attribute Person 1', exact: true });
    await expect(attributes.locator('input, select')).toHaveCount(13);
    await expect(attributes.locator('img')).toHaveCount(1);
    await expect.poll(() => attributes.locator('img').evaluate(img => img.naturalWidth)).toBeGreaterThan(0);
    await attributes.getByLabel('Name Person 1', { exact: true }).fill('Anna');
    await attributes.getByLabel('Haarfarbe Person 1', { exact: true }).fill('schwarz');
    await attributes.getByLabel('Oberbekleidung Person 1', { exact: true }).fill('Jacke');
    const patch = page.waitForRequest(r => r.method() === 'PATCH' && r.url().endsWith('/attribute-review'));
    await attributeReview.getByRole('button', { name: 'Änderungen speichern', exact: true }).click();
    const submitted = (await patch).postDataJSON();
    assert.equal(typeof submitted.version, 'string');
    assert.deepEqual(submitted.changes, [
      { person_id: 1, field: 'hair_color', value: 'schwarz' },
      { person_id: 1, field: 'upper_clothing', value: 'Jacke' },
    ]);
    await expect(attributeReview.getByRole('button', { name: 'Änderungen speichern', exact: true })).toBeDisabled();
    await attributeReview.getByRole('button', { name: 'Attribut-Review schließen', exact: true }).click();
    await nav(6);
    await expect(page.getByRole('article', { name: 'Person 1', exact: true })).toContainText('Anna');
    await page.reload(); await nav(7); await openAttributes();
    await expect(attributes.getByLabel('Name Person 1', { exact: true })).toHaveValue('Anna');
    await expect(attributes.getByLabel('Haarfarbe Person 1', { exact: true })).toHaveValue('schwarz');
    await expect(attributes.getByLabel('Oberbekleidung Person 1', { exact: true })).toHaveValue('Jacke');
    await expect(attributes.getByText('Gespeichert: schwarz', { exact: true })).toBeVisible();
    await attributes.getByLabel('Haarfarbe Person 1', { exact: true }).fill('braun');
    await attributes.getByRole('button', { name: 'Eingabe verwerfen: Haarfarbe Person 1', exact: true }).click();
    await expect(attributes.getByLabel('Haarfarbe Person 1', { exact: true })).toHaveValue('schwarz');
    // A name-only edit must not send an empty attribute PATCH. Failed edits remain staged.
    const attributeVersion = (await (await page.request.get(`${base}/api/jobs/job/person-analysis/attributes`)).json()).version;
    await attributes.getByLabel('Name Person 1', { exact: true }).fill('Anna Neu');
    await page.route('**/api/jobs/job/persons/1', route => route.fulfill({ status: 409, json: { error: 'Testkonflikt' } }), { times: 1 });
    await attributeReview.getByRole('button', { name: 'Änderungen speichern', exact: true }).click();
    await expect(attributeReview.getByRole('alert')).toHaveText('Testkonflikt');
    await expect(attributes.getByLabel('Name Person 1', { exact: true })).toHaveValue('Anna Neu');
    await attributeReview.getByRole('button', { name: 'Änderungen speichern', exact: true }).click();
    await expect(attributeReview.getByRole('button', { name: 'Änderungen speichern', exact: true })).toBeDisabled();
    const savedAttributes = await (await page.request.get(`${base}/api/jobs/job/person-analysis/attributes`)).json();
    assert.equal(savedAttributes.version, attributeVersion);
    assert.equal(savedAttributes.persons[0].name, 'Anna Neu');
    await page.reload(); await nav(7); await openAttributes();
    await expect(attributes.getByLabel('Name Person 1', { exact: true })).toHaveValue('Anna Neu');
    console.log('PASS: attribute dialog, shared name/attribute save, clustering without reload, name-only save/reload, failed name retained');
    await page.reload();
    await nav(5);
    await expect(track(1)).toBeVisible();
    const setSize = async (slider, value) => {
      await slider.fill(String(value));
      await expect(slider).toHaveValue(String(value));
    };
    const thumbnail = () => track(1).getByRole('button', { name: /Crop vergrößern/ }).first().locator('img');
    await setSize(page.getByRole('slider', { name: 'Bildgröße' }), 100);
    await expect.poll(async () => Math.round((await thumbnail().boundingBox()).height)).toBe(100);
    await setSize(page.getByRole('slider', { name: 'Bildgröße' }), 300);
    await expect.poll(async () => Math.round((await thumbnail().boundingBox()).height)).toBe(300);
    const ratiosAtSize = await track(1).getByTestId('face-overlay').first().evaluate(el => {
      const b = el.getBoundingClientRect(), p = el.parentElement.getBoundingClientRect();
      return [(b.x-p.x)/p.width, (b.y-p.y)/p.height, b.width/p.width, b.height/p.height];
    });
    [.25, .1, .5, .2].forEach((v, i) => assert(Math.abs(ratiosAtSize[i]-v) < .01));
    assert.equal(await page.evaluate(() => localStorage.getItem('descraibe.review.tracking.imageHeight')), '300');
    await page.reload(); await nav(5);
    await expect(page.getByRole('slider', { name: 'Bildgröße' })).toHaveValue('300');
    console.log('PASS: tracking slider changes actual image size, proportional bbox, localStorage/reload');

    await expect(track(2)).toHaveCount(0); // quality rejected
    await expect(track(5)).toHaveCount(0); // no faces
    await expect(track(1).getByRole('button', { name: /Crop vergrößern/ })).toHaveCount(5);
    await expect(track(1).getByRole('button', { name: 'Track zuweisen' })).toHaveCount(0);
    await track(1).getByRole('button', { name: /Crop vergrößern/ }).first().click();
    const preview = page.getByRole('dialog', { name: 'Crop-Vorschau', exact: true });
    await expect(preview).toBeVisible();
    const box = preview.getByTestId('face-overlay');
    const zoom = preview.getByTestId('face-zoom');
    await expect(zoom).toBeVisible();
    assert.equal(await zoom.locator('img').getAttribute('src'), await preview.getByRole('img', { name: 'Track 1, Frame 1', exact: true }).getAttribute('src'));
    await expect(zoom.locator('img')).toHaveCSS('width', /px$/);
    for (const width of [1440, 900]) {
      await page.setViewportSize({ width, height: 1000 });
      const ratios = await box.evaluate(el => { const b = el.getBoundingClientRect(), p = el.parentElement.getBoundingClientRect(); return [(b.x-p.x)/p.width, (b.y-p.y)/p.height, b.width/p.width, b.height/p.height]; });
      [.25, .1, .5, .2].forEach((v, i) => assert(Math.abs(ratios[i]-v) < .01));
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    if (process.argv[3]) await page.screenshot({ path: path.join(process.argv[3], 'stages-face-preview.png') });
    await preview.getByRole('button', { name: /Vorschau schließen/ }).click();
    await page.getByRole('button', { name: 'Face 1 ausschließen', exact: true }).click();
    await expect(page.getByText('1 Face-Änderungen vorgemerkt · 0 Split-Änderungen · 0 Track-Ausschlüsse vorgemerkt', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Review-Änderungen speichern', exact: true }).click();
    await expect.poll(async () => (await snapshot()).identities_ready).toBe(false);
    assert.deepEqual((await snapshot()).persons, []);
    const attributeSnapshot = async () => (await page.request.get(`${base}/api/jobs/job/person-analysis/attributes`)).json();
    assert.equal((await attributeSnapshot()).ready, false);
    assert.deepEqual((await attributeSnapshot()).persons, []);
    await page.reload(); await nav(5);
    await expect(page.getByRole('button', { name: 'Face 1 wiederherstellen', exact: true })).toBeVisible();
    await page.getByLabel('Tracks ohne brauchbares Gesicht anzeigen').check();
    await expect(track(5).getByRole('button', { name: /Crop vergrößern/ })).toHaveCount(5);
    await nav(6);
    await expect(page.getByRole('article', { name: 'Person 1', exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: /Personenzuordnung ausführen/ }).click();
    await expect.poll(async () => (await snapshot()).identities_ready).toBe(true);
    await expect(page.getByRole('article', { name: 'Person 1', exact: true })).toBeVisible();
    await expect(page.getByRole('slider', { name: 'Bildgröße' })).toHaveCount(0);
    await nav(7);
    await page.getByRole('button', { name: 'Attribute ausführen', exact: true }).click();
    await expect.poll(async () => (await attributeSnapshot()).ready).toBe(true);
    await openAttributes();
    await expect(attributes.getByLabel('Haarfarbe Person 1', { exact: true })).toHaveValue('Testwert');
    await attributeReview.getByRole('button', { name: 'Attribut-Review schließen', exact: true }).click();
    await nav(6);
    const overview = page.getByRole('article', { name: 'Person 1', exact: true }).locator('img');
    await expect(overview).toHaveCSS('height', '80px');
    await expect(overview).toHaveCSS('width', '64px');
    await page.getByRole('button', { name: 'Tracks von Person 1 verwalten', exact: true }).click();
    await setSize(page.getByRole('slider', { name: 'Bildgröße' }), 260);
    await expect(overview).toHaveCSS('height', '80px');
    await page.reload(); await nav(6);
    await expect(page.getByRole('slider', { name: 'Bildgröße' })).toHaveCount(0);
    await page.getByRole('button', { name: 'Tracks von Person 1 verwalten', exact: true }).click();
    await expect(page.getByRole('slider', { name: 'Bildgröße' })).toHaveValue('260');
    await expect(track(1).getByRole('button', { name: /Crop vergrößern/ })).toHaveCount(3);
    const management = page.getByRole('dialog', { name: 'Tracks verwalten', exact: true });
    await setSize(management.getByRole('slider', { name: 'Bildgröße' }), 140);
    await expect.poll(async () => Math.round((await thumbnail().boundingBox()).height)).toBe(140);
    await track(1).getByRole('button', { name: 'Track zuweisen' }).click();
    const sizePicker = page.getByRole('dialog', { name: 'Track 1 zuweisen', exact: true });
    await expect(sizePicker.getByRole('img').first()).toHaveCSS('height', '140px');
    await setSize(sizePicker.getByRole('slider', { name: 'Bildgröße' }), 220);
    await expect(sizePicker.getByRole('img').first()).toHaveCSS('height', '220px');
    await expect(overview).toHaveCSS('height', '80px');
    await sizePicker.getByRole('button', { name: 'Personenauswahl schließen' }).click();
    await expect(management.getByRole('slider', { name: 'Bildgröße' })).toHaveValue('220');
    await setSize(management.getByRole('slider', { name: 'Bildgröße' }), 140);
    await track(1).getByRole('button', { name: /Crop vergrößern/ }).first().click();
    await expect(preview.getByTestId('face-zoom')).toBeVisible();
    await preview.getByRole('button', { name: /Vorschau schließen/ }).click();
    assert.equal(await page.evaluate(() => localStorage.getItem('descraibe.review.persons.imageHeight')), '140');
    assert.equal(await page.evaluate(() => localStorage.getItem('descraibe.review.tracking.imageHeight')), '300');
    console.log('PASS: persons overview, cluster thumbnails, picker, detail, independent persisted sizes');

    await expect(page.getByRole('button', { name: /Face .* ausschließen/ })).toHaveCount(0);
    await page.getByRole('button', { name: 'Track-Verwaltung schließen', exact: true }).click();
    console.log('PASS: quality-only review, dynamic bbox at two viewport sizes, exclude/reload/invalidation/rerun, persons and attributes regenerated');

    await page.getByRole('button', { name: /Nicht zugeordnete Tracks/ }).click();
    await track(2).getByRole('button', { name: 'Track zuweisen' }).click();
    await page.getByRole('button', { name: '+ Neue Person', exact: true }).click();
    await track(5).getByRole('button', { name: 'Track zuweisen' }).click();
    await page.getByRole('button', { name: 'Nicht zugeordnet', exact: true }).click();
    await page.getByRole('button', { name: 'Alle Änderungen speichern' }).click();
    await expect(page.getByRole('article', { name: 'Person 2', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Person 2 bearbeiten', exact: true }).click();
    await page.getByLabel('Name', { exact: true }).fill('Ben');
    await page.getByLabel('Funktion', { exact: true }).fill('Moderatorin');
    await page.getByRole('button', { name: 'Speichern', exact: true }).click();
    await expect(page.getByRole('article', { name: 'Person 2', exact: true })).toContainText('Moderatorin');
    await page.getByRole('button', { name: /Nicht zugeordnete Tracks/ }).click();
    const batchCount = batches.length;
    for (const tid of [3, 4]) {
      await track(tid).getByRole('button', { name: 'Track zuweisen' }).click();
      const picker = page.getByRole('dialog', { name: `Track ${tid} zuweisen`, exact: true });
      await expect(picker.getByRole('img', { name: 'Beispiel Ben' })).toBeVisible();
      await picker.getByRole('button', { name: 'Ben (ID 2) auswählen' }).click();
    }
    assert.equal(batches.length, batchCount);
    await expect(page.getByText('2 Trackänderungen vorgemerkt', { exact: true })).toBeVisible();
    if (process.argv[3]) await page.screenshot({ path: path.join(process.argv[3], 'stages-track-batch.png') });
    await page.getByRole('button', { name: 'Alle Änderungen speichern' }).click();
    await expect.poll(() => batches.length).toBe(batchCount + 1);
    assert.equal(batches.at(-1).changes.length, 2);
    await expect(page.getByRole('article', { name: 'Person 2', exact: true })).toContainText('3 Auftritte');
    await page.getByRole('button', { name: 'Person 1 zusammenführen', exact: true }).click();
    await page.getByRole('button', { name: 'Ben (ID 2) auswählen' }).click();
    await expect(page.getByRole('article', { name: 'Person 1', exact: true })).toHaveCount(0);
    await expect(page.getByRole('article', { name: 'Person 2', exact: true })).toContainText('4 Auftritte');
    await page.reload(); await nav(6);
    await expect(page.getByRole('article', { name: 'Person 2', exact: true })).toContainText('Moderatorin');
    await page.getByRole('button', { name: 'Person 2 löschen', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Nicht zugeordnete Tracks (5)', exact: true })).toBeVisible();
    await nav(5);
    await page.getByRole('button', { name: 'Face 1 wiederherstellen', exact: true }).click();
    await page.getByRole('button', { name: 'Review-Änderungen speichern', exact: true }).click();
    await expect.poll(async () => (await snapshot()).identities_ready).toBe(false);
    assert.deepEqual((await snapshot()).persons, []);
    // Split and full undo invalidate dependent persons and attributes.
    await track(1).getByRole('button', { name: 'Vor Frame 29 teilen', exact: true }).click();
    await expect(page.getByText(/Vorgemerkt: Schnitt vor Frame 29/)).toBeVisible();
    await page.getByRole('button', { name: 'Review-Änderungen speichern' }).click();
    await expect(track(6)).toBeVisible();
    await expect(track(7)).toBeVisible();
    await expect(track(1)).toHaveCount(0);
    await expect(track(6).getByRole('button', { name: /Crop vergrößern/ })).toHaveCount(2);
    await expect(track(7).getByRole('button', { name: /Crop vergrößern/ })).toHaveCount(3);
    await nav(6);
    await page.getByRole('button', { name: /Personenzuordnung ausführen/ }).click();
    await expect.poll(async () => (await snapshot()).identities_ready).toBe(true);
    assert.deepEqual((await snapshot()).persons[0].track_ids, [6, 7]);
    await nav(5);
    await page.getByRole('button', { name: 'Alle Splits von Track 1 aufheben', exact: true }).first().click();
    await page.getByRole('button', { name: 'Review-Änderungen speichern' }).click();
    await expect(track(1)).toBeVisible();
    await expect(track(6)).toHaveCount(0);
    assert.deepEqual((await snapshot()).persons, []);
    assert.equal((await snapshot()).identities_ready, false);
    assert.equal((await attributeSnapshot()).ready, false);
    console.log('PASS: split selection, two disjoint segments, clustering uses segments, undo split removes dependent persons');

    // Scale the read-only review response to 96 tracks; all rows are mounted, without accordions.
    await page.getByRole('button', { name: 'Tracking-Review schließen', exact: true }).click();
    await page.route('**/api/jobs/job/person-analysis/tracking', async route => {
      const response = await route.fetch();
      const data = await response.json();
      const template = data.tracks.find(t => t.track_id === 1);
      data.tracks = Array.from({ length: 96 }, (_, i) => ({ ...template, track_id: i + 101, source_track_id: i + 101,
        observations: template.observations.map(c => ({ ...c, track_id: i + 101 })) }));
      data.original_tracks_count = 96;
      await route.fulfill({ response, json: data });
    });
    await page.reload(); await nav(5);
    const large = page.getByRole('dialog', { name: 'Tracking-Review', exact: true });
    await expect(large.getByRole('region')).toHaveCount(96);
    const drag = await large.getByRole('slider').evaluate(async slider => {
      const commits = window.__reviewCommits, writes = window.__sizeWrites;
      for (let i = 0; i < 50; i++) {
        slider.value = String(100 + (i % 14) * 20);
        slider.dispatchEvent(new Event('input', { bubbles: true }));
      }
      await new Promise(resolve => requestAnimationFrame(resolve));
      return { commitsBefore: commits, commits: window.__reviewCommits - commits,
        writes: window.__sizeWrites - writes, totalWrites: writes };
    });
    assert(drag.commitsBefore > 0, 'React commit instrumentation is active');
    assert.equal(drag.commits, 0, 'Dragging never commits a new React review tree');
    assert.equal(drag.writes, 0, 'No synchronous localStorage writes during input burst');
    await expect.poll(() => page.evaluate(() => window.__sizeWrites)).toBe(drag.totalWrites + 1);
    await expect(large.getByRole('slider')).toHaveValue('240');
    console.log('PASS: 96-track slider burst: zero React commits, one debounced storage write');
    const bounds = await large.locator('> div').first().boundingBox();
    assert(bounds.width > 1300 && bounds.height >= 900);
    await track(196).scrollIntoViewIfNeeded();
    await expect(track(196)).toBeVisible();
    if (process.argv[3]) await page.screenshot({ path: path.join(process.argv[3], 'tracking-review-96.png') });
    console.log('PASS: full-size 96-track review, one scroll area, larger crops, dynamic face zoom from the same image');
    assert.deepEqual(errors, []);
    console.log('PASS: whole-track batch, unassigned/new/assign, example/name/ID picker, metadata/reload, merge/delete, face restore invalidates dependent results');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
