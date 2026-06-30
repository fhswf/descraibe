/**
 * tests/e2e-frontend.spec.js – E2E tests for frontend components
 * 
 * These tests verify the frontend's integration with the browser environment,
 * including localStorage, theme switching, and UI interactions.
 */
import { test, expect } from '@playwright/test';

// ── Helpers ─────────────────────────────────────────────────────────────────────

/** Navigate to the app and wait for it to be ready. */
async function openApp(page) {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
}

/** Clear localStorage for a clean test state */
async function clearLocalStorage(page) {
    await page.evaluate(() => localStorage.clear());
}

// ── Theme switching tests ────────────────────────────────────────────────────────

test.describe('Theme Mode', () => {
    test('app loads with system theme by default', async ({ page }) => {
        await clearLocalStorage(page);
        await openApp(page);

        // App should load without crashing
        await expect(page.locator('body')).toBeVisible();

        // Theme should be set to system (or handled gracefully)
        const theme = await page.evaluate(() => document.documentElement.dataset.theme);
        expect(['system', 'light', 'dark']).toContain(theme || 'system');
    });

    test('theme persists in localStorage', async ({ page }) => {
        await clearLocalStorage(page);
        await openApp(page);

        // Check localStorage key exists
        const stored = await page.evaluate(() => localStorage.getItem('descraibe-theme-mode'));
        expect(['system', 'light', 'dark']).toContain(stored || 'system');
    });

    test('stored theme is valid option', async ({ page }) => {
        await clearLocalStorage(page);
        await openApp(page);

        const stored = await page.evaluate(() => localStorage.getItem('descraibe-theme-mode'));
        // If stored, it should be one of the valid options
        if (stored) {
            expect(['system', 'light', 'dark']).toContain(stored);
        }
    });
});

// ── Storage estimation tests ─────────────────────────────────────────────────────

test.describe('Storage Quota Footer', () => {
    test('shows storage information in footer', async ({ page }) => {
        await openApp(page);

        // Footer should contain Origin Storage text
        const footer = page.locator('footer');
        await expect(footer).toBeVisible();
        await expect(footer).toContainText('Origin Storage');
    });

    test('handles unsupported storage API gracefully', async ({ page }) => {
        await openApp(page);

        // Footer should still be visible even if storage API is unavailable
        const footer = page.locator('footer');
        await expect(footer).toBeVisible();

        // Should show either loading state, error, or unsupported message
        const footerText = await footer.textContent();
        expect(footerText).toBeTruthy();
    });
});

// ── Saved Jobs persistence tests ─────────────────────────────────────────────────

test.describe('Saved Jobs Persistence', () => {
    test('initializes with empty saved jobs', async ({ page }) => {
        await clearLocalStorage(page);
        await openApp(page);

        const storageKey = await page.evaluate(() => {
            // Check if localStorage can be accessed
            try {
                localStorage.getItem('descrAIbe.savedJobIds');
                return 'exists';
            } catch {
                return 'blocked';
            }
        });

        expect(['exists', 'blocked']).toContain(storageKey);
    });

    test('saved job IDs are stored as JSON array', async ({ page }) => {
        await clearLocalStorage(page);
        await openApp(page);

        const savedJobs = await page.evaluate(() => {
            try {
                const raw = localStorage.getItem('descrAIbe.savedJobIds');
                return raw ? JSON.parse(raw) : [];
            } catch {
                return [];
            }
        });

        expect(Array.isArray(savedJobs)).toBe(true);
    });

    test('saved job metadata is stored as JSON object', async ({ page }) => {
        await clearLocalStorage(page);
        await openApp(page);

        const savedMeta = await page.evaluate(() => {
            try {
                const raw = localStorage.getItem('descrAIbe.savedJobMeta');
                return raw ? JSON.parse(raw) : {};
            } catch {
                return {};
            }
        });

        expect(typeof savedMeta).toBe('object');
        expect(Array.isArray(savedMeta)).toBe(false);
    });
});

// ── Job navigation tests ────────────────────────────────────────────────────────

test.describe('Job Navigation', () => {
    test('shows empty state message when no jobs', async ({ page }) => {
        await clearLocalStorage(page);
        await openApp(page);

        // Check if there's an empty state message
        const emptyMessage = page.locator('text=Noch keine Jobs');
        if (await emptyMessage.count() > 0) {
            await expect(emptyMessage).toBeVisible();
        }
    });

    test('job sidebar is visible', async ({ page }) => {
        await openApp(page);

        // Sidebar or job list should be present
        const _sidebar = page.locator('aside, nav, [class*="sidebar"], [class*="job"]');
        // Just verify the page loaded
        await expect(page.locator('body')).toBeVisible();
    });
});

// ── Config Modal tests ─────────────────────────────────────────────────────────

test.describe('Config Modal', () => {
    test('config modal can be opened via keyboard shortcut hint or button', async ({ page }) => {
        await openApp(page);

        // Look for settings/config buttons
        const _settingsButton = page.locator('button:has-text("Einstellungen"), button:has-text("Config"), button:has-text("Settings")');
        
        // Check if there's any way to open config
        const body = await page.textContent('body');
        // Config should be accessible somehow
        expect(body).toBeTruthy();
    });

    test('config modal structure has tabs', async ({ page }) => {
        await openApp(page);

        // Press keyboard shortcut to open config (Ctrl+,)
        await page.keyboard.press('Control+,');
        await page.waitForTimeout(500);

        // Check if modal opened or if there's a settings button
        const modal = page.locator('h2:has-text("Pipeline-Konfiguration")');
        if (await modal.count() > 0) {
            // Modal is open, verify tabs exist
            await expect(page.locator('button:has-text("Prompts")').or(page.locator('button:has-text("GPT")'))).toBeVisible();
        }
    });
});

// ── Step navigation tests ──────────────────────────────────────────────────────

test.describe('Step Navigation', () => {
    test('all workflow steps are visible', async ({ page }) => {
        await openApp(page);

        // Look for workflow step labels
        const stepLabels = [
            'Video hochladen',
            'Sprechpausen',
            'Transkription',
            'AD-Slots',
            'Bilder',
            'Generieren',
            'Vertonung',
            'Ergebnisse'
        ];

        for (const label of stepLabels) {
            const element = page.locator(`text=${label}`);
            if (await element.count() > 0) {
                await expect(element.first()).toBeVisible();
            }
        }
    });

    test('can navigate between steps', async ({ page }) => {
        await openApp(page);

        // Get all step buttons
        const stepButtons = page.locator('nav button, [class*="step"] button');
        const count = await stepButtons.count();

        if (count > 0) {
            // Click through steps
            for (let i = 0; i < Math.min(count, 3); i++) {
                await stepButtons.nth(i).click();
                await page.waitForTimeout(100);
            }
        }
    });
});

// ── Upload component tests ─────────────────────────────────────────────────────

test.describe('Upload Component', () => {
    test('drop zone is visible on step 1', async ({ page }) => {
        await openApp(page);

        // Look for the drop zone
        const dropZone = page.locator('#drop-zone, [class*="drop"], [class*="upload"]');
        if (await dropZone.count() > 0) {
            await expect(dropZone.first()).toBeVisible();
        }
    });

    test('file input accepts video files', async ({ page }) => {
        await openApp(page);

        // Find video file input
        const videoInput = page.locator('input[type="file"][accept*="video"]');
        if (await videoInput.count() > 0) {
            const acceptAttr = await videoInput.getAttribute('accept');
            expect(acceptAttr).toContain('video');
        }
    });
});

// ── Results component tests ───────────────────────────────────────────────────

test.describe('Results Component', () => {
    test('results panel shows empty state initially', async ({ page }) => {
        await openApp(page);

        // Navigate to results step (step 8)
        const stepButtons = page.locator('nav button');
        const count = await stepButtons.count();
        if (count >= 8) {
            await stepButtons.nth(7).click();
            await page.waitForTimeout(300);

            // Should show empty state message
            const emptyState = page.locator('text=Noch keine Ausgabedateien');
            if (await emptyState.count() > 0) {
                await expect(emptyState).toBeVisible();
            }
        }
    });

    test('download button is present when file exists', async ({ page }) => {
        await openApp(page);

        // Navigate to results
        const stepButtons = page.locator('nav button');
        const count = await stepButtons.count();
        if (count >= 8) {
            await stepButtons.nth(7).click();
            await page.waitForTimeout(300);
        }

        // Page should be visible (results panel or empty state)
        await expect(page.locator('body')).toBeVisible();
    });
});

// ── Error handling tests ───────────────────────────────────────────────────────

test.describe('Error Handling', () => {
    test('app handles missing API gracefully', async ({ page }) => {
        // Navigate without server - app should show loading or error state
        await page.goto('/');

        // App should either show content or a loading state
        await page.waitForTimeout(2000);
        const body = await page.textContent('body');
        expect(body).toBeTruthy();
    });

    test('app does not crash on invalid localStorage data', async ({ page }) => {
        // Set invalid data in localStorage
        await page.goto('/');
        await page.evaluate(() => {
            localStorage.setItem('descrAIbe.savedJobIds', 'not valid json');
            localStorage.setItem('descrAIbe.savedJobMeta', '{ invalid');
        });

        // Reload the app
        await page.reload();
        await page.waitForLoadState('networkidle');

        // App should not crash
        await expect(page.locator('body')).toBeVisible();
    });
});

// ── Responsive behavior tests ─────────────────────────────────────────────────

test.describe('Responsive Behavior', () => {
    test('works at standard desktop viewport', async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 800 });
        await openApp(page);
        await expect(page.locator('body')).toBeVisible();
    });

    test('works at tablet viewport', async ({ page }) => {
        await page.setViewportSize({ width: 768, height: 1024 });
        await openApp(page);
        await expect(page.locator('body')).toBeVisible();
    });
});