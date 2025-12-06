/// <reference types="vite/client" />

// Declare the shape of Vite's import.meta.env so TypeScript knows about `env`
// and our custom variable VITE_API_URL.
interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}


