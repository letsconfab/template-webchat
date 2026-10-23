import { api } from './api'

/** One INTEGRATE System as listed by `GET /api/library/systems`. */
export interface LibrarySystemSummary {
  slug: string
  name: string
  document_count: number
}

/** A browsable Library Document within a System listing. */
export interface LibraryDocumentSummary {
  id: string
  title: string
  organization: string | null
  type: string
  systems: string[]
  modified_time: string | null
}

export interface LibrarySystemDetail {
  slug: string
  name: string
  documents: LibraryDocumentSummary[]
}

export async function listLibrarySystems(): Promise<LibrarySystemSummary[]> {
  const response = await api.get<LibrarySystemSummary[]>('/library/systems')
  return response.data
}

export async function getLibrarySystem(slug: string): Promise<LibrarySystemDetail> {
  const response = await api.get<LibrarySystemDetail>(`/library/systems/${encodeURIComponent(slug)}`)
  return response.data
}

function libraryDocumentFilePath(id: string): string {
  return `/library/documents/${encodeURIComponent(id)}/file`
}

/** The browser blocked the new tab, so the document wasn't fetched. */
export class PopupBlockedError extends Error {
  constructor() {
    super('The browser blocked the new tab')
    this.name = 'PopupBlockedError'
  }
}

// Long enough for the new tab to load the PDF before the blob is released.
const OBJECT_URL_LIFETIME_MS = 60_000

/**
 * Open a document's PDF in a new tab. API auth is a bearer header, which a
 * plain link can't send, so the PDF is fetched as a blob and opened from an
 * object URL. The tab is opened before the fetch so popup blockers still see
 * it as a response to the click; a later open would be blocked, so a blocked
 * tab fails fast with PopupBlockedError.
 */
export async function openLibraryDocument(id: string): Promise<void> {
  const tab = window.open('', '_blank')
  if (!tab) throw new PopupBlockedError()
  try {
    const response = await api.get<ArrayBuffer>(libraryDocumentFilePath(id), {
      responseType: 'arraybuffer',
    })
    const url = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }))
    tab.location.href = url
    window.setTimeout(() => URL.revokeObjectURL(url), OBJECT_URL_LIFETIME_MS)
  } catch (error) {
    tab.close()
    throw error
  }
}
