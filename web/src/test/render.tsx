import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import { type ReactNode } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";

/** A query client with retries off so tests fail fast and deterministically. */
function testClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: Infinity },
    },
  });
}

/** Wrap a tree in Query + a memory router, for component-level tests. */
export function renderWithProviders(
  ui: ReactNode,
  options?: { route?: string } & Omit<RenderOptions, "wrapper">,
) {
  const router = createMemoryRouter([{ path: "*", element: <>{ui}</> }], {
    initialEntries: [options?.route ?? "/"],
  });
  return render(
    <QueryClientProvider client={testClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
    options,
  );
}

/** Render a full set of routes (for shell tests that need real navigation). */
export function renderRoutes(
  routes: Parameters<typeof createMemoryRouter>[0],
  initialEntry = "/",
) {
  const router = createMemoryRouter(routes, { initialEntries: [initialEntry] });
  return render(
    <QueryClientProvider client={testClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}
