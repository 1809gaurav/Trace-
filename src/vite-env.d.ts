/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AUTH_MODE?: 'none' | 'apikey' | 'jwt';
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
