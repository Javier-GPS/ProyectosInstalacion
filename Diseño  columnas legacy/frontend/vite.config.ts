import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Puerto fijo en 3000: coincide con el CORS ya configurado en el backend
// (app/main.py -> CORSMiddleware allow_origins=["http://localhost:3000"]).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    strictPort: true,
  },
});
