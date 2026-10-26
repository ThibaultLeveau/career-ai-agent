import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  outputDir: "./test-results/artifacts",
  workers: 1,
  retries: 0,
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    browserName: "chromium",
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
