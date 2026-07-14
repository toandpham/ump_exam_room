import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Component tests run under jsdom; the React plugin gives us JSX/Fast-Refresh
// transform. We deliberately skip the Tailwind plugin (no styling needed in tests).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test-setup.ts"],
  },
});
