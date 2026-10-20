/**
 * 单机版 / 本地 dev 客户端入口。
 * FastAPI 托管的 index.html 是同步脚本拼出来的空壳，和 RootDocument 的首屏不是同一棵树。
 * 对 document 做 hydrateRoot 会在 <html> 上触发 React #418，恢复失败时标题和 #root 会被清掉，页面变成白屏。
 * 因此无论有没有 $_TSR，都用 createRoot 整页渲染。有 $_TSR 时仍走 StartClient，以便读路由清单。
 */
import { StrictMode, startTransition } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "@tanstack/react-router";
import { StartClient } from "@tanstack/react-start/client";

import "./styles.css";
import { getRouter } from "./router";

declare global {
  interface Window {
    $_TSR?: unknown;
  }
}

function mount() {
  const tree = window.$_TSR ? (
    <StrictMode>
      <StartClient />
    </StrictMode>
  ) : (
    <StrictMode>
      <RouterProvider router={getRouter()} />
    </StrictMode>
  );
  createRoot(document).render(tree);
}

startTransition(mount);
