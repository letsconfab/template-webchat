import { useState } from 'react'
import { ExternalLink, FileText } from 'lucide-react'

import { Badge } from './ui/badge'
import { INTEGRATE_SYSTEMS } from '../lib/integrateSystems'
import { openLibraryDocument } from '../services/libraryDocuments'

/** A document the Librarian cited, as sent on the answer's `end` frame. */
export interface LibrarianCitation {
  id: string
  title: string
  type: string
  systems: string[]
  url?: string
}

const REFERENCE_TYPE = 'Reference'

function systemName(slug: string): string {
  return INTEGRATE_SYSTEMS.find((system) => system.slug === slug)?.name ?? slug
}

/**
 * The documents behind a Librarian answer. A Library Document shows a chip
 * per spotlighted INTEGRATE System; a Reference Document shows a
 * "Reference" badge instead.
 */
export function LibrarianCitations({ citations }: { citations: LibrarianCitation[] }) {
  const [failedId, setFailedId] = useState<string | null>(null)

  const open = async (id: string) => {
    setFailedId(null)
    try {
      await openLibraryDocument(id)
    } catch (error) {
      console.error('Failed to open library document:', error)
      setFailedId(id)
    }
  }

  return (
    <div className="mt-3 border-t pt-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Sources
      </p>
      <ul aria-label="Sources" className="mt-2 flex flex-wrap gap-2">
        {citations.map((citation) => {
          const isReference = citation.type === REFERENCE_TYPE
          return (
            <li
              key={citation.id}
              className="flex max-w-full flex-wrap items-center gap-1.5 rounded-lg border bg-background px-2.5 py-1.5"
            >
              <button
                type="button"
                onClick={() => void open(citation.id)}
                className="inline-flex min-w-0 items-center gap-1.5 rounded text-left text-sm font-medium text-link underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <FileText aria-hidden="true" className="h-4 w-4 shrink-0 text-accent" />
                <span className="break-words">{citation.title}</span>
                <ExternalLink aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="sr-only">(opens in a new tab)</span>
              </button>
              {isReference ? (
                <Badge variant="outline" className="font-normal">
                  {REFERENCE_TYPE}
                </Badge>
              ) : (
                citation.systems.map((slug) => (
                  <Badge key={slug} variant="secondary" className="font-normal">
                    {systemName(slug)}
                  </Badge>
                ))
              )}
              {failedId === citation.id && (
                <span role="alert" className="w-full text-xs text-destructive">
                  Couldn't open this document. Try again.
                </span>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
