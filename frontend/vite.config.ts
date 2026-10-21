import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { visualizer } from "rollup-plugin-visualizer";
import { defineConfig, type Plugin } from "vite";
import tsconfigPaths from "vite-tsconfig-paths";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** 本地 dev：无扩展名的路径都回 index.html，刷新子路由不会 404。 */
function spaDevShellPlugin(): Plugin {
  return {
    name: "fba-spa-dev-shell",
    configureServer(server) {
      return () => {
        server.middlewares.use(async (req, res, next) => {
          const url = (req.url || "").split("?")[0];
          if (req.method !== "GET" && req.method !== "HEAD") return next();
          if (
            url.startsWith("/@") ||
            url.startsWith("/api") ||
            url.startsWith("/assets") ||
            url.startsWith("/src") ||
            url.startsWith("/node_modules") ||
            /\.[a-zA-Z0-9]+$/.test(url)
          ) {
            return next();
          }
          try {
            const indexPath = path.resolve(server.config.root, "index.html");
            let html = await fs.promises.readFile(indexPath, "utf8");
            html = await server.transformIndexHtml(url, html);
            res.statusCode = 200;
            res.setHeader("Content-Type", "text/html");
            res.end(html);
          } catch (err) {
            next(err);
          }
        });
      };
    },
  };
}

function resolveBackendPort(): number {
  const portsFile = path.resolve(__dirname, "../.dev/ports.json");
  try {
    const data = JSON.parse(fs.readFileSync(portsFile, "utf-8")) as { backend?: number };
    if (data.backend && data.backend > 0) return data.backend;
  } catch {
    // fall through
  }

  const fromEnv = Number(process.env.FBA_BACKEND_PORT);
  if (fromEnv > 0) return fromEnv;

  return 8002;
}

function resolveBackendTarget(): string {
  return `http://127.0.0.1:${resolveBackendPort()}`;
}

/** 只保留 en-* / zh-* 断词表，其余语言包收成一个空模块。 */
function univerHyphenStubPlugin(): Plugin {
  const virtual = "\0univer-hyphen-stub";
  return {
    name: "univer-hyphen-stub",
    enforce: "pre",
    resolveId(id) {
      if (id === "univer-hyphen-stub" || id === virtual) return virtual;
      return null;
    },
    load(id) {
      if (id === virtual) return "export default null;\n";
      return null;
    },
    transform(code, id) {
      if (!id.includes("@univerjs/engine-render") || !code.includes("PATTERN_LOADERS")) return null;
      const next = code.replace(/import\(\s*(["'])\.\/(?!en-|zh-)[^"']+\1\s*\)/g, 'import("univer-hyphen-stub")');
      if (next === code) return null;
      return { code: next, map: null };
    },
  };
}

function apiProxy() {
  return {
    "/api": {
      target: resolveBackendTarget(),
      changeOrigin: true,
      timeout: 0,
      proxyTimeout: 0,
      configure: (proxy: { on: (event: string, handler: (...args: never[]) => void) => void }) => {
        proxy.on("proxyReq", ((proxyReq: { setHeader: (name: string, value: string) => void }, req: { url?: string }) => {
          if (req.url?.includes("/stream")) {
            proxyReq.setHeader("Accept", "text/event-stream");
          }
        }) as never);
        proxy.on("proxyRes", ((proxyRes: { headers: Record<string, string | undefined> }, req: { url?: string }) => {
          if (req.url?.includes("/stream")) {
            proxyRes.headers["cache-control"] = "no-cache";
            proxyRes.headers["x-accel-buffering"] = "no";
            delete proxyRes.headers["content-length"];
          }
        }) as never);
        proxy.on("error", ((err: Error, _req: unknown, res: { headersSent?: boolean; writeHead?: (code: number, headers: Record<string, string>) => void; end: (body: string) => void }) => {
          const port = resolveBackendPort();
          if (res && res.writeHead && !res.headersSent) {
            res.writeHead(502, { "Content-Type": "application/json" });
            res.end(
              JSON.stringify({
                detail: `API 代理失败（${port}）：${err.message}。请重启后端或运行 scripts/start_dev.ps1`,
              }),
            );
          }
        }) as never);
      },
    },
  };
}

console.log(
  `[vite] /api proxy -> ${resolveBackendTarget()} (dev 启动时读 .dev/ports.json；后端换端口后需重启前端)`,
);

export default defineConfig({
  plugins: [
    univerHyphenStubPlugin(),
    tanstackRouter({ target: "react", autoCodeSplitting: true }),
    react(),
    tailwindcss(),
    tsconfigPaths(),
    spaDevShellPlugin(),
    visualizer({
      filename: path.resolve(__dirname, "../review/work/v4_bundle.html"),
      gzipSize: true,
      template: "treemap",
    }),
  ],
  base: "/",
  build: {
    outDir: "dist/client",
    emptyOutDir: true,
    assetsDir: "assets",
    assetsInlineLimit: 0,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("@univerjs")) return "univer";
        },
      },
    },
  },
  server: {
    proxy: apiProxy(),
  },
  preview: {
    proxy: apiProxy(),
  },
});
