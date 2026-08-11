import { defineConfig, devices } from "@playwright/test";

const port = process.env.E2E_PORT ?? "3000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  use: { baseURL: `http://127.0.0.1:${port}`, trace: "retain-on-failure" },
  webServer: {
    command: `pnpm exec next dev -H 127.0.0.1 -p ${port}`,
    url: `http://127.0.0.1:${port}/motorcycles`,
    reuseExistingServer: !process.env.CI,
    env: { TM_FIXTURE_MODE: "true", OWNER_EMAIL: "owner@example.com" },
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] } },
  ],
});
