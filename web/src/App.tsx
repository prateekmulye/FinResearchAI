import { RouterProvider } from "react-router";

import { QueryProvider } from "@/lib/query";
import { router } from "@/router";

export function App() {
  return (
    <QueryProvider>
      <RouterProvider router={router} />
    </QueryProvider>
  );
}
