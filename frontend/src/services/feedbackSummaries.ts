import { z } from 'zod'

const summaryEntrySchema = z.object({
  artifact_id: z.string().min(1),
  title: z.string().min(1),
  generated_at: z.string().min(1),
  window_start: z.string().min(1),
  window_end: z.string().min(1),
  content_url: z.string().min(1),
  asset_base_url: z.string().min(1),
})

const indexSchema = z.object({
  schema_version: z.literal(1),
  summaries: z.array(summaryEntrySchema),
})

export type FeedbackSummaryEntry = z.infer<typeof summaryEntrySchema>

export type FeedbackSummariesIndexResult =
  | { status: 'unavailable' }
  | { status: 'empty'; summaries: [] }
  | { status: 'ready'; summaries: FeedbackSummaryEntry[] }

export type FeedbackSummariesIndexState =
  | { status: 'loading' }
  | FeedbackSummariesIndexResult

export type FeedbackSummaryContentState =
  | { status: 'loading' }
  | { status: 'unavailable' }
  | { status: 'not_found' }
  | {
      status: 'found'
      entry: FeedbackSummaryEntry
      markdown: string
    }

const INDEX_URL = '/static/feedback-summaries/index.json'

async function fetchText(url: string): Promise<string | null> {
  try {
    const response = await fetch(url, { credentials: 'same-origin' })
    if (!response.ok) return null
    return await response.text()
  } catch {
    return null
  }
}

export async function loadFeedbackSummariesIndex(): Promise<FeedbackSummariesIndexResult> {
  const text = await fetchText(INDEX_URL)
  if (text === null) {
    return { status: 'unavailable' }
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return { status: 'unavailable' }
  }

  const result = indexSchema.safeParse(parsed)
  if (!result.success) {
    return { status: 'unavailable' }
  }

  if (result.data.summaries.length === 0) {
    return { status: 'empty', summaries: [] }
  }

  return { status: 'ready', summaries: result.data.summaries }
}

export async function loadFeedbackSummary(
  artifactId: string,
): Promise<Exclude<FeedbackSummaryContentState, { status: 'loading' }>> {
  const index = await loadFeedbackSummariesIndex()
  if (index.status === 'unavailable') {
    return { status: 'unavailable' }
  }
  if (index.status === 'empty') {
    return { status: 'not_found' }
  }

  const entry = index.summaries.find((item) => item.artifact_id === artifactId)
  if (!entry) {
    return { status: 'not_found' }
  }

  const markdown = await fetchText(entry.content_url)
  if (markdown === null) {
    return { status: 'unavailable' }
  }

  return { status: 'found', entry, markdown }
}

export function formatSummaryDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: 'UTC',
    timeZoneName: 'short',
  }).format(date)
}

/** Exact evidence-window label using the packaged ISO-8601 UTC timestamps. */
export function formatEvidenceWindow(windowStart: string, windowEnd: string): string {
  return `${windowStart} – ${windowEnd}`
}
