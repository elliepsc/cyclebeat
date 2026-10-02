import createClient from "openapi-fetch";

import type { paths } from "./schema";

// Fixed at build time (VITE_API_URL); the default is the local `make api`.
export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// `fetch` is looked up at call time so tests can stub `globalThis.fetch`.
export const client = createClient<paths>({
  baseUrl: API_URL,
  fetch: (request) => globalThis.fetch(request),
});
