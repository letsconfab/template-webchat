import { api } from './api'

// Long enough for the new tab to load the PDF before the blob is released.
const OBJECT_URL_LIFETIME_MS = 60_000

/**
 * Open a Library or Reference Document's PDF in a new tab. API auth is a
 * bearer header, which a plain link can't send, so the PDF is fetched as a
 * blob and opened from an object URL. The tab is opened before the fetch so
 * popup blockers still see it as a response to the click.
 */
export async function openLibraryDocument(id: string): Promise<void> {
  const tab = window.open('', '_blank')
  try {
    const response = await api.get<ArrayBuffer>(
      `/library/documents/${encodeURIComponent(id)}/file`,
      { responseType: 'arraybuffer' },
    )
    const url = URL.createObjectURL(
      new Blob([response.data], { type: 'application/pdf' }),
    )
    if (tab) {
      tab.location.href = url
    } else {
      window.open(url, '_blank')
    }
    window.setTimeout(() => URL.revokeObjectURL(url), OBJECT_URL_LIFETIME_MS)
  } catch (error) {
    tab?.close()
    throw error
  }
}
