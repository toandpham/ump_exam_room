import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Component tests under jsdom; React plugin for JSX transform (no Tailwind needed).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test-setup.ts"],
  },
});
