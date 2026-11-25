import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The browser talks only to Vite. Vite forwards requests to the two backends,
// so no CORS setup is needed during development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Pipecat bot: session start and WebRTC offer/answer
      "/start": "http://localhost:7860",
      "/sessions": "http://localhost:7860",
      // Dashboard API: doctors, slots, appointments
      "/clinic": "http://localhost:8000",
    },
  },
});
