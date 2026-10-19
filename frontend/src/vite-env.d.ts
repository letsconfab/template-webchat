/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  /** Absolute URL of the website's Members Portal page, linked from the library header. */
  readonly VITE_MEMBERS_PORTAL_URL?: string
}
