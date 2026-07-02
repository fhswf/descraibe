/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_VERSION: string;
  readonly VITE_APP_BUILD_CHANNEL: string;
  readonly VITE_APP_COMMIT_SHA: string;
  readonly VITE_APP_REPOSITORY_URL: string;
  readonly VITE_APP_VERSION_LABEL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
