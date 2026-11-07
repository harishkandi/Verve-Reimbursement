import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The API runs separately on :8000; proxying keeps the app on one origin in dev.
    proxy: { "/api": "http://localhost:8000" },
  },
});
