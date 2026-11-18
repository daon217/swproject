const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: '.', testMatch: '*.spec.js', timeout: 60000,
  outputDir: process.env.UI_TEST_OUTPUT || 'test-results',
  expect: { timeout: 10000 }, workers: 1, retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { browserName: 'chromium', viewport: { width: 1280, height: 900 },
    screenshot: 'on', trace: 'retain-on-failure',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } : {},
  },
});
