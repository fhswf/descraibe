// playwright.config.js
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],

  use: {
    baseURL: 'http://localhost:5000',
    headless: true,
    viewport: { width: 1280, height: 800 },
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Start the Flask backend automatically before the test run.
  // `reuseExistingServer: !process.env.CI` reuses a running dev server locally
  // but always starts a fresh one in CI.
  //
  // Prerequisites: run `uv sync` in the webapp/ directory at least once so
  // that `uv run --no-sync` can find the venv immediately.
  webServer: {
    command: 'uv run --no-sync flask --app backend.app run --host 0.0.0.0 --port 5000',
    url: 'http://localhost:5000/api/ping',
    timeout: 120_000,         // allow up to 2 min for pandas/flask imports on slow machines
    reuseExistingServer: !process.env.CI,
    env: {
      // Disable the reloader: it forks a child process that confuses Playwright's
      // process-lifecycle management and can cause double-listen on port 5000.
      FLASK_ENV: 'testing',
      FLASK_DEBUG: '0',
    },
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
