/* Run ONLY against the isolated five-track fixture created from test_person_review.py.
   node backend/tests/person_review_browser.cjs http://127.0.0.1:5179 <screenshot-dir>
   Uses the project's existing Playwright dependency and installed Microsoft Edge. */
const { chromium, expect } = require('../../frontend/node_modules/@playwright/test');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const base = process.argv[2];
  assert(base && /^http:\/\/127\.0\.0\.1:\d+$/.test(base), 'Explicit loopback test URL required');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [], oldRoutes = [], batches = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', dialog => dialog.accept());
    page.on('request', request => {
      if (/similar-faces|merge-suggestions|\/faces\//.test(request.url())) oldRoutes.push(request.url());
      if (request.method() === 'POST' && request.url().endsWith('/track-assignments')) batches.push(request.postDataJSON());
    });
    const data = await (await page.request.get(`${base}/api/jobs/job/persons`)).json();
    assert.equal(data.revision, 1, 'Requires a fresh isolated fixture');
    assert.equal(data.tracks.length, 5);
    assert.equal(data.persons[0].name, 'Anna');
    await page.goto(`${base}/?job=job`);
    await page.locator('#step-nav > button').nth(6).click();
    await expect(page.getByRole('article', { name: 'Person 1', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Tracks von Person 1 verwalten', exact: true }).click();
    const track = id => page.getByRole('region', { name: `Track ${id}`, exact: true });
    await expect(track(1).getByRole('button', { name: /Crop vergrößern/ })).toHaveCount(1);
    await expect(track(1)).toContainText('1 FaceMoE-Vorschauen');
    // Der API-Endpunkt liefert standardmaessig bis zu acht gespeicherte Vorschauen.
    await expect(track(2).getByRole('button', { name: /Crop vergrößern/ })).toHaveCount(8);
    await track(1).getByRole('button', { name: /Crop vergrößern/ }).first().click();
    const preview = page.getByRole('dialog', { name: 'Crop-Vorschau', exact: true });
    await expect(preview).toBeVisible();
    const overlay = preview.getByTestId('face-overlay');
    await expect(overlay).toHaveCSS('left', /px$/);
    const ratios = await overlay.evaluate(el => {
      const b = el.getBoundingClientRect(), p = el.parentElement.getBoundingClientRect();
      return [(b.x-p.x)/p.width, (b.y-p.y)/p.height, b.width/p.width, b.height/p.height];
    });
    [0.1, 0.1, 0.3, 0.2].forEach((v, i) => assert(Math.abs(ratios[i] - v) < .01));
    if (process.argv[3]) await page.screenshot({ path: path.join(process.argv[3], 'review-crop.png') });
    await preview.getByRole('button', { name: /Vorschau schließen/ }).click();
    console.log('PASS: current evidence/fallback previews and proportional bbox');
    // Zwei Zuordnungen vormerken; erst Speichern darf eine Anfrage senden.
    await track(1).getByRole('button', { name: 'Track zuweisen' }).click();
    const picker = page.getByRole('dialog', { name: 'Track 1 zuweisen', exact: true });
    await expect(picker.getByRole('img', { name: 'Beispiel Ben' })).toBeVisible();
    await picker.getByRole('button', { name: 'Ben (ID 2) auswählen' }).click();
    await track(2).getByRole('button', { name: 'Track zuweisen' }).click();
    await page.getByRole('button', { name: 'Nicht zugeordnet', exact: true }).click();
    await expect(page.getByText('2 Trackänderungen vorgemerkt', { exact: true })).toBeVisible();
    assert.equal(batches.length, 0, 'Staging must not persist');
    if (process.argv[3]) await page.screenshot({ path: path.join(process.argv[3], 'review-staged.png') });
    await page.getByRole('button', { name: 'Alle Änderungen speichern' }).click();
    await expect(page.getByRole('dialog', { name: 'Tracks verwalten', exact: true })).toHaveCount(0);
    assert.equal(batches.length, 1);
    assert.equal(batches[0].changes.length, 2);
    await expect(page.getByRole('article', { name: 'Person 1', exact: true })).toHaveCount(0);
    await expect(page.getByRole('article', { name: 'Person 2', exact: true })).toContainText('2 Auftritte');
    console.log('PASS: crop sampling/enlargement, proportional bbox, image/name/ID picker, two staged changes saved in one batch');

    await page.getByRole('button', { name: /Nicht zugeordnete Tracks/ }).click();
    await track(4).getByRole('button', { name: 'Track zuweisen' }).click();
    await page.getByRole('button', { name: '+ Neue Person', exact: true }).click();
    await expect(page.getByText('Keine gespeicherten Crops für diesen Track.')).toBeVisible();
    await track(5).getByRole('button', { name: 'Track zuweisen' }).click();
    await page.getByRole('button', { name: 'Nicht zugeordnet', exact: true }).click();
    await expect(page.getByText('1 Trackänderungen vorgemerkt', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Alle Änderungen speichern' }).click();
    await page.getByRole('button', { name: 'Person 3 bearbeiten', exact: true }).click();
    await page.getByLabel('Name', { exact: true }).fill('Carla');
    await page.getByLabel('Funktion', { exact: true }).fill('Moderatorin');
    await page.getByRole('button', { name: 'Speichern', exact: true }).click();
    await expect(page.getByRole('article', { name: 'Person 3', exact: true })).toContainText('Moderatorin');
    await page.reload();
    await page.locator('#step-nav > button').nth(6).click();
    await expect(page.getByRole('article', { name: 'Person 3', exact: true })).toContainText('Carla');
    await expect(page.getByRole('article', { name: 'Person 3', exact: true })).toContainText('Moderatorin');
    console.log('PASS: unassigned/new person/leave unassigned, empty crops, name and function survive reload');

    // Eine direkte API-Aenderung macht den offenen Entwurf veraltet.
    await page.getByRole('button', { name: 'Tracks von Person 3 verwalten', exact: true }).click();
    await track(4).getByRole('button', { name: 'Track zuweisen' }).click();
    await page.getByRole('button', { name: 'Ben (ID 2) auswählen' }).click();
    const latest = await (await page.request.get(`${base}/api/jobs/job/persons`)).json();
    await page.request.post(`${base}/api/jobs/job/persons/2`, { data: { version: latest.version, name: 'Ben aktualisiert' } });
    await page.getByRole('button', { name: 'Alle Änderungen speichern' }).click();
    await expect(page.getByRole('dialog', { name: 'Tracks verwalten', exact: true }).getByRole('alert')).toContainText('neu laden');
    await expect(page.getByText('1 Trackänderungen vorgemerkt', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Track-Verwaltung schließen' }).click();
    await page.reload();
    await page.locator('#step-nav > button').nth(6).click();
    await page.getByRole('button', { name: 'Person 3 zusammenführen', exact: true }).click();
    await page.getByRole('button', { name: 'Ben aktualisiert (ID 2) auswählen' }).click();
    await expect(page.getByRole('article', { name: 'Person 3', exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: 'Person 2 löschen', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Nicht zugeordnete Tracks (5)', exact: true })).toBeVisible();
    await page.reload();
    await page.locator('#step-nav > button').nth(6).click();
    await expect(page.getByRole('button', { name: 'Nicht zugeordnete Tracks (5)', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Nicht zugeordnete Tracks (5)', exact: true }).click();
    await track(1).getByRole('button', { name: 'Track zuweisen' }).click();
    await page.getByRole('button', { name: '+ Neue Person', exact: true }).click();
    await page.getByRole('button', { name: 'Alle Änderungen speichern' }).click();
    await expect(page.getByRole('article', { name: 'Person 1', exact: true })).toBeVisible();
    assert.deepEqual(oldRoutes, []);
    assert.deepEqual(errors, []);
    console.log('PASS: stale conflict retains draft, merge/delete move whole tracks, all-unassigned reload, recreation, no old face routes or page errors');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
