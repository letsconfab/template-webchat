import { useEffect, useState } from 'react'
import { AlertCircle, ChevronRight, ExternalLink, Loader2 } from 'lucide-react'

import { api } from '../../services/api'

interface LibrarySystem {
  slug: string
  name: string
}

interface AdminLibraryDocument {
  file_id: string
  title: string
  organization: string | null
  type: string
  systems: string[]
  status: string | null
}

interface AdminLibraryIssue {
  row: number | null
  code: string
  detail: string | null
  file_id: string | null
  title: string | null
  link: string | null
}

interface AdminLibrary {
  manifest_url: string | null
  synced_at: string | null
  systems: LibrarySystem[]
  documents: AdminLibraryDocument[]
  issues: AdminLibraryIssue[]
}

const REFERENCE_TYPE = 'Reference'

// Plain-language reasons for the issue codes the Library Manifest sync writes.
const ISSUE_REASONS: Record<string, string> = {
  manifest_unreachable:
    'The Library Manifest could not be read. Check that it is shared with the connected Google account.',
  unreachable:
    'The file could not be opened. Check that it still exists and is shared with the connected Google account.',
  missing_title: 'The Title cell is empty.',
  no_system: 'No INTEGRATE System is ticked.',
  bad_link: 'The File cell is not a Google Doc or Drive file link.',
  duplicate_file: 'This file is already listed on another row.',
  unsupported_type: 'The file is not a Google Doc or a PDF.',
  bad_type: 'The Type is not LSP, Field Guide, or Reference.',
  download_failed: 'The file could not be saved on the server. The next sync will try again.',
}

// Failures where the sync's own detail (an HTTP status or error) says why.
const SHOWS_CAUSE = new Set(['manifest_unreachable', 'unreachable', 'download_failed'])

function issueReason(issue: AdminLibraryIssue): string {
  return ISSUE_REASONS[issue.code] ?? issue.detail ?? issue.code
}

function byTitle(a: AdminLibraryDocument, b: AdminLibraryDocument) {
  return a.title.localeCompare(b.title, undefined, { sensitivity: 'base' })
}

interface LibraryContentsProps {
  // Changing this reloads the contents (after Sync now or a newer sync).
  refreshKey: string
}

export function LibraryContents({ refreshKey }: LibraryContentsProps) {
  const [library, setLibrary] = useState<AdminLibrary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const token = localStorage.getItem('token')
    api
      .get<AdminLibrary>('/admin/library', { headers: { Authorization: `Bearer ${token}` } })
      .then(response => {
        if (cancelled) return
        setLibrary(response.data)
        setError(null)
      })
      .catch(() => {
        if (!cancelled) setError('Failed to load library contents')
      })
    return () => {
      cancelled = true
    }
  }, [refreshKey])

  if (!library) {
    return (
      <section aria-label="Library contents" className="space-y-2">
        <h4 className="text-sm font-medium">Library contents</h4>
        {error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        )}
      </section>
    )
  }

  const browsable = library.documents.filter(d => d.type !== REFERENCE_TYPE)
  const groups = [
    ...library.systems.map(system => ({
      key: system.slug,
      name: system.name,
      documents: browsable.filter(d => d.systems.includes(system.slug)).sort(byTitle),
    })),
    {
      key: 'references',
      name: 'References',
      documents: library.documents.filter(d => d.type === REFERENCE_TYPE).sort(byTitle),
    },
  ]

  return (
    <section aria-label="Library contents" className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-sm font-medium">Library contents</h4>
        {library.manifest_url && (
          <a
            href={library.manifest_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-sm text-link underline-offset-4 hover:underline"
          >
            Open the Library Manifest
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        )}
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}

      {library.issues.length > 0 && (
        <div className="rounded-lg border border-destructive/40 p-3">
          <h5 id="library-needs-attention" className="flex items-center gap-2 text-sm font-medium text-destructive">
            <AlertCircle className="h-4 w-4" aria-hidden="true" />
            Needs attention
          </h5>
          <ul aria-labelledby="library-needs-attention" className="mt-2 divide-y text-sm">
            {library.issues.map((issue, idx) => (
              <li key={`${issue.row ?? 'manifest'}-${issue.code}-${idx}`} className="py-2">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-muted-foreground">
                    {issue.row ? `Row ${issue.row}` : 'Manifest'}
                  </span>
                  <IssueSubject issue={issue} />
                </div>
                <p className="text-foreground">{issueReason(issue)}</p>
                {SHOWS_CAUSE.has(issue.code) && issue.detail && (
                  <p className="text-xs text-muted-foreground">{issue.detail}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="divide-y rounded-lg border">
        {groups.map(group => (
          <details key={group.key} data-testid="library-group" className="group px-3 py-2">
            <summary className="flex cursor-pointer list-none items-center gap-2 text-sm">
              <ChevronRight
                className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-90"
                aria-hidden="true"
              />
              <span className="font-medium">{group.name}</span>
              <span className="ml-auto rounded-full bg-muted px-2 text-xs text-muted-foreground">
                {group.documents.length}
              </span>
            </summary>
            {group.documents.length === 0 ? (
              <p className="py-2 pl-6 text-sm text-muted-foreground">No documents.</p>
            ) : (
              <ul className="py-1 pl-6 text-sm">
                {group.documents.map(doc => (
                  <li key={doc.file_id} className="flex flex-wrap items-baseline gap-x-2 py-1">
                    <span>{doc.title}</span>
                    <span className="text-xs text-muted-foreground">{doc.type}</span>
                    {doc.status && doc.status !== 'ok' && (
                      <span className="text-xs text-destructive">Kept from an earlier sync (see Needs attention)</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </details>
        ))}
      </div>
    </section>
  )
}

function IssueSubject({ issue }: { issue: AdminLibraryIssue }) {
  if (issue.link) {
    return (
      <a
        href={issue.link}
        target="_blank"
        rel="noopener noreferrer"
        className="text-link underline-offset-4 hover:underline"
      >
        {issue.title || 'Open the file in Drive'}
      </a>
    )
  }
  return issue.title ? <span className="font-medium">{issue.title}</span> : null
}
