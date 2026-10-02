/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the CycleBeat API, fixed at build time. Defaults to http://localhost:8000. */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
