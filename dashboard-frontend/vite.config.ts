import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig, type Plugin } from "vite";

const root = process.cwd();

function dashboardStyles(): Plugin {
  return {
    name: "dashboard-styles-from-typescript",
    generateBundle() {
      const source = readFileSync(resolve(root, "src/styles.ts"), "utf8");
      const tick = String.fromCharCode(96);
      const opener = "String.raw" + tick;
      const startAt = source.indexOf(opener);
      const endAt = source.lastIndexOf(tick + ";");
      if (startAt < 0 || endAt <= startAt) {
        this.error("Could not extract the stylesheet from src/styles.ts.");
      }
      const css = source.slice(startAt + opener.length, endAt);
      this.emitFile({ type: "asset", fileName: "app.css", source: css });
    }
  };
}

export default defineConfig({
  plugins: [dashboardStyles()],
  build: {
    outDir: resolve(root, "dist"),
    emptyOutDir: true,
    minify: "esbuild",
    cssCodeSplit: false,
    reportCompressedSize: false,
    lib: {
      entry: resolve(root, "src/main.tsx"),
      name: "LemegetonDashboard",
      formats: ["iife"],
      fileName: () => "app.js"
    },
    rollupOptions: { output: { inlineDynamicImports: true } }
  }
});
