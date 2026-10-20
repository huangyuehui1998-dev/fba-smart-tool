// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - tanstackStart, viteReact, tailwindcss, tsConfigPaths, nitro (build-only using cloudflare as a default target),
//     componentTagger (dev-only), VITE_* env injection, @ path alias, React/TanStack dedupe,
//     error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@lovable.dev/vite-tanstack-config";
import type { Plugin } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** 本地 dev：直接返回 index.html，绕过 TanStack SSR 片段白屏 */
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
  // 优先读 .dev/ports.json（start_dev 写入），避免 shell 里残留的 FBA_BACKEND_PORT 指向僵死端口
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

console.log(
  `[vite] /api proxy -> ${resolveBackendTarget()} (dev 启动时读 .dev/ports.json；后端换端口后需重启前端)`,
);

export default defineConfig({
  tanstackStart: {
    server: { entry: "server" },
    client: { entry: "standalone-client" },
  /** 单机版：预渲染 SPA Shell，产出 dist/client/_shell.html 供 FastAPI 托管 */
    spa: {
      enabled: true,
      maskPath: "/",
    },
    /** 本地开发走 index.html + standalone-client，避免 SSR 片段导致白屏 */
    vite: {
      installDevServerMiddleware: false,
    },
  },
  vite: {
    plugins: [spaDevShellPlugin()],
    // 根路径托管 SPA 必须用 "/"，避免子路由刷新时相对路径解析错误
    base: "/",
    build: {
      assetsDir: "assets",
      // 确保 chunk 预加载路径以 / 开头，避免 /assets/*.js 内相对 assets/ → /assets/assets/
      assetsInlineLimit: 0,
    },
    server: {
      proxy: {
        "/api": {
          target: resolveBackendTarget(),
          changeOrigin: true,
          timeout: 0,
          proxyTimeout: 0,
          // S7：去掉了 router（vite 7 的 http-proxy-3 不支持该选项，原来就不生效）；后端换端口后需重启前端 dev
          configure: (proxy) => {
            proxy.on("proxyReq", (proxyReq, req) => {
              if (req.url?.includes("/stream")) {
                proxyReq.setHeader("Accept", "text/event-stream");
              }
            });
            proxy.on("proxyRes", (proxyRes, req) => {
              if (req.url?.includes("/stream")) {
                proxyRes.headers["cache-control"] = "no-cache";
                proxyRes.headers["x-accel-buffering"] = "no";
                delete proxyRes.headers["content-length"];
              }
            });
            proxy.on("error", (err, _req, res) => {
              const port = resolveBackendPort();
              if (res && "writeHead" in res && !res.headersSent) {
                res.writeHead(502, { "Content-Type": "application/json" });
                res.end(
                  JSON.stringify({
                    detail: `API 代理失败（${port}）：${err.message}。请重启后端或运行 scripts/start_dev.ps1`,
                  }),
                );
              }
            });
          },
        },
      },
    },
  },
});
