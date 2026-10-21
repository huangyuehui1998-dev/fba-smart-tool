/**
 * 纯 Vite SPA 入口。挂到 index.html 的 #root，不用 TanStack Start / hydrateRoot。
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "@tanstack/react-router";

import "./styles.css";
import { getRouter } from "./router";

const root = document.getElementById("root");
if (!root) {
  throw new Error("index.html 缺少 #root");
}

createRoot(root).render(
  <StrictMode>
    <RouterProvider router={getRouter()} />
  </StrictMode>,
);
