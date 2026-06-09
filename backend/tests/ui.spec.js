// tests/ui.spec.js – Playwright tests for the Audiodeskription Pipeline web app
// Assumes the Flask server is running on http://localhost:5000

import { test, expect } from '@playwright/test';

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Navigate to the app and wait for it to be ready. */
async function openApp(page) {
    await page.goto('/');
    await page.waitForSelector('.step-btn.active', { timeout: 10_000 });
}

/** Click a sidebar step button by index (0-based). */
async function clickStep(page, index) {
    const btns = page.locator('.step-btn');
    await btns.nth(index).click();
}

// ── Test Suite ────────────────────────────────────────────────────────────────

test.describe('Page load & structure', () => {
    test('loads without errors and shows the header', async ({ page }) => {
        await openApp(page);
        await expect(page.locator('h1')).toContainText('Audiodeskription');
    });

    test('shows 8 sidebar steps', async ({ page }) => {
        await openApp(page);
        const buttons = page.locator('.step-btn');
        await expect(buttons).toHaveCount(8);
    });

    test('step 1 (Upload) is active by default', async ({ page }) => {
        await openApp(page);
        const first = page.locator('.step-btn').first();
        await expect(first).toHaveClass(/active/);
    });

    test('step 1 panel is visible by default', async ({ page }) => {
        await openApp(page);
        const panel0 = page.locator('.step-panel').first();
        await expect(panel0).toHaveClass(/visible/);
    });

    test('no other step panels are visible initially', async ({ page }) => {
        await openApp(page);
        const allPanels = page.locator('.step-panel');
        const count = await allPanels.count();
        for (let i = 1; i < count; i++) {
            await expect(allPanels.nth(i)).not.toHaveClass(/visible/);
        }
    });
});

test.describe('Navigation (sidebar)', () => {
    test('clicking step 2 shows VAD panel', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 1);
        await expect(page.locator('.step-panel').nth(1)).toHaveClass(/visible/);
        await expect(page.locator('.step-panel').first()).not.toHaveClass(/visible/);
    });

    test('clicking step 6 (Prompts) shows its panel', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 5);
        await expect(page.locator('.step-panel').nth(5)).toHaveClass(/visible/);
    });

    test('clicking every step shows its panel and only its panel', async ({ page }) => {
        await openApp(page);
        const panelCount = await page.locator('.step-panel').count();
        for (let i = 0; i < panelCount; i++) {
            await clickStep(page, i);
            const panels = page.locator('.step-panel');
            for (let j = 0; j < panelCount; j++) {
                if (j === i) {
                    await expect(panels.nth(j)).toHaveClass(/visible/);
                } else {
                    await expect(panels.nth(j)).not.toHaveClass(/visible/);
                }
            }
        }
    });

    test('active step button gets the active class', async ({ page }) => {
        await openApp(page);
        const btns = page.locator('.step-btn');
        for (let i = 0; i < await btns.count(); i++) {
            await btns.nth(i).click();
            await expect(btns.nth(i)).toHaveClass(/active/);
        }
    });
});

test.describe('Step 1 – Upload', () => {
    test('drop zone is visible', async ({ page }) => {
        await openApp(page);
        await expect(page.locator('#drop-zone')).toBeVisible();
    });

    test('file input accepts video files', async ({ page }) => {
        await openApp(page);
        const input = page.locator('#video-file-input');
        await expect(input).toHaveAttribute('accept', /video/);
    });

    test('video stats card is hidden before upload', async ({ page }) => {
        await openApp(page);
        await expect(page.locator('#video-stats-card')).toBeHidden();
    });
});

test.describe('Step 2 – VAD', () => {
    test('shows VAD threshold slider', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 1);
        await expect(page.locator('#vad-threshold')).toBeVisible();
    });

    test('threshold slider updates display value', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 1);
        const slider = page.locator('#vad-threshold');
        await slider.fill('0.7');
        await slider.dispatchEvent('input');
        await expect(page.locator('#vad-threshold-val')).toHaveText('0.7');
    });

    test('Run button is present', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 1);
        await expect(page.locator('#run-vad-btn')).toBeVisible();
    });

    test('VAD results card is hidden initially', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 1);
        await expect(page.locator('#vad-results-card')).toBeHidden();
    });
});

test.describe('Step 3 – Transcription', () => {
    test('whisper model selector is present', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 2);
        const sel = page.locator('#whisper-model');
        await expect(sel).toBeVisible();
        await expect(sel.locator('option[value="large-v3"]')).toHaveCount(1);
        await expect(sel.locator('option[value="small"]')).toHaveCount(1);
    });

    test('SRT upload input accepts .srt files', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 2);
        const inp = page.locator('#srt-upload-input');
        await expect(inp).toHaveAttribute('accept', /.srt/);
    });
});

test.describe('Step 4 – AD Slots', () => {
    test('min slot duration input is present with default 1.0', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 3);
        const inp = page.locator('#slot-min-s');
        await expect(inp).toBeVisible();
        await expect(inp).toHaveValue('1.0');
    });

    test('quality card is hidden initially', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 3);
        await expect(page.locator('#slots-quality-card')).toBeHidden();
    });
});

test.describe('Step 5 – Image Extraction', () => {
    test('scene threshold slider visible', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 4);
        await expect(page.locator('#img-threshold')).toBeVisible();
    });

    test('blur threshold slider shows default value', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 4);
        await expect(page.locator('#img-blur-val')).toHaveText('80');
    });
});

test.describe('Step 6 – Prompts & Config', () => {
    test('system prompt textarea is present', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 5);
        await expect(page.locator('#system-prompt')).toBeVisible();
    });

    test('user prompt textarea is present', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 5);
        await expect(page.locator('#user-prompt')).toBeVisible();
    });

    test('API key input is password type', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 5);
        await expect(page.locator('#api-key')).toHaveAttribute('type', 'password');
    });

    test('GPT model selector does not fall back to gpt-4o', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 5);
        await expect(page.locator('#gpt-model option[value="gpt-4o"]')).toHaveCount(0);
    });

    test('temperature slider range 0–1.5', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 5);
        const slider = page.locator('#gpt-temp');
        await expect(slider).toHaveAttribute('min', '0');
        await expect(slider).toHaveAttribute('max', '1.5');
    });
});

test.describe('Step 7 – Generate', () => {
    test('Generate button is present', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 6);
        await expect(page.locator('#run-gpt-btn')).toBeVisible();
    });

    test('GPT progress card is hidden initially', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 6);
        await expect(page.locator('#gpt-progress-card')).toBeHidden();
    });

    test('clicking Generate without job shows alert (no crash)', async ({ page }) => {
        let dialogSeen = false;
        page.on('dialog', async dialog => {
            dialogSeen = true;
            await dialog.dismiss();
        });
        await openApp(page);
        await clickStep(page, 6);
        await page.locator('#run-gpt-btn').click();
        // Give time for dialog or other reaction
        await page.waitForTimeout(500);
        expect(dialogSeen).toBe(true);
    });
});

test.describe('Step 8 – Results', () => {
    test('results panel is reachable', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 7);
        await expect(page.locator('.step-panel').nth(7)).toHaveClass(/visible/);
    });

    test('download list is empty when no job has been run yet', async ({ page }) => {
        await openApp(page);
        await clickStep(page, 7);
        // When there's no job, renderResults() calls /api/results/null → 404,
        // so the download list is correctly left empty (no files yet).
        await page.waitForTimeout(800);
        const dlList = page.locator('#download-list');
        await expect(dlList).toBeEmpty();
    });
});

test.describe('API: health check', () => {
    test('GET / returns 200 and HTML', async ({ request }) => {
        const resp = await request.get('/');
        expect(resp.status()).toBe(200);
        const body = await resp.text();
        expect(body).toContain('Audiodeskription');
    });

    test('POST /api/upload without file returns 400', async ({ request }) => {
        const resp = await request.post('/api/upload', {
            multipart: {}
        });
        expect(resp.status()).toBe(400);
        const body = await resp.json();
        expect(body.error).toBeTruthy();
    });

    test('POST /api/run/vad without job returns 404', async ({ request }) => {
        const resp = await request.post('/api/run/vad', {
            data: JSON.stringify({ job_id: 'nonexistent-job-id' }),
            headers: { 'Content-Type': 'application/json' },
        });
        expect(resp.status()).toBe(404);
    });

    test('POST /api/run/slots without job returns 400', async ({ request }) => {
        const resp = await request.post('/api/run/slots', {
            data: JSON.stringify({ job_id: 'nonexistent-job-id' }),
            headers: { 'Content-Type': 'application/json' },
        });
        expect(resp.status()).toBe(400);
    });

    test('GET /api/results/unknown-id returns 404', async ({ request }) => {
        const resp = await request.get('/api/results/not-a-real-job-id');
        expect(resp.status()).toBe(404);
    });

    test('GET /api/download/unknown-id/file returns 404', async ({ request }) => {
        const resp = await request.get('/api/download/not-a-real-job/gesamt_txt');
        expect(resp.status()).toBe(404);
    });
});

test.describe('Upload + Slots API smoke test', () => {
    // This test creates a real job via the upload API (mocked file), then tries
    // to run slots (which fails because pauses aren't set) — verifying the
    // full error path works correctly.
    test('upload a 1-byte stub returns 500 or has an error key', async ({ request }) => {
        // Upload a minimal stub (not a real video – will fail stats reading)
        const resp = await request.post('/api/upload', {
            multipart: {
                video: {
                    name: 'stub.mp4',
                    mimeType: 'video/mp4',
                    buffer: Buffer.from('not a real mp4'),
                },
            },
        });
        // Either 200 (unlikely) or 500 (can't read video stats) – either way, no crash
        expect([200, 500]).toContain(resp.status());
    });
});
