import { lazy } from "react";
import { createBrowserRouter } from "react-router";

import { AppShell } from "@/components/shell/AppShell";

/**
 * Router (react-router v7 library mode). Pages are lazy-loaded so the initial
 * bundle is just the glass shell; each route's chunk (and the heavy viz deps
 * WP-7..10 add — xyflow, charts) loads on demand. The AppShell wraps the Outlet
 * in <Suspense>, so a styled fallback shows during the fetch.
 */
const AnalyzePage = lazy(() =>
  import("@/pages/AnalyzePage").then((m) => ({ default: m.AnalyzePage })),
);
const LibraryPage = lazy(() =>
  import("@/pages/LibraryPage").then((m) => ({ default: m.LibraryPage })),
);
const RunDetailPage = lazy(() =>
  import("@/pages/RunDetailPage").then((m) => ({ default: m.RunDetailPage })),
);
const MarketPage = lazy(() =>
  import("@/pages/MarketPage").then((m) => ({ default: m.MarketPage })),
);
const EvalPage = lazy(() =>
  import("@/pages/EvalPage").then((m) => ({ default: m.EvalPage })),
);
const NotFoundPage = lazy(() =>
  import("@/pages/NotFoundPage").then((m) => ({ default: m.NotFoundPage })),
);

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <AnalyzePage /> },
      { path: "library", element: <LibraryPage /> },
      { path: "library/:runId", element: <RunDetailPage /> },
      { path: "market", element: <MarketPage /> },
      { path: "eval", element: <EvalPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
