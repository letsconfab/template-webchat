import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ExternalLink, FileText, MessageSquare } from 'lucide-react'

import LibraryLayout from '../components/library/LibraryLayout'
import { Alert, AlertDescription } from '../components/ui/alert'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { INTEGRATE_SYSTEMS, integrateSystemPath, type IntegrateSystem } from '../lib/integrateSystems'
import { getLibrarySystem, openLibraryDocument, type LibraryDocumentSummary } from '../services/library'

const updatedFormat = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  timeZone: 'UTC',
})

function updatedLabel(modifiedTime: string | null): string | null {
  if (!modifiedTime) return null
  const date = new Date(modifiedTime)
  return Number.isNaN(date.getTime()) ? null : `Updated ${updatedFormat.format(date)}`
}

function DocumentRow({ document, system }: { document: LibraryDocumentSummary; system: IntegrateSystem }) {
  const [opening, setOpening] = useState(false)
  const [openFailed, setOpenFailed] = useState(false)
  const updated = updatedLabel(document.modified_time)
  const otherSystems = INTEGRATE_SYSTEMS.filter(
    (other) => other.slug !== system.slug && document.systems.includes(other.slug),
  )

  const handleOpen = async () => {
    setOpening(true)
    setOpenFailed(false)
    try {
      await openLibraryDocument(document.id)
    } catch {
      setOpenFailed(true)
    } finally {
      setOpening(false)
    }
  }

  return (
    <li className="flex flex-col gap-4 rounded-lg border bg-card p-5 text-card-foreground sm:flex-row sm:items-start sm:justify-between">
      <div className="flex min-w-0 gap-3">
        <FileText aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
        <div className="min-w-0">
          <h2 className="break-words text-lg font-semibold">{document.title}</h2>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-muted-foreground">
            <Badge variant="secondary">{document.type}</Badge>
            {updated && <span>{updated}</span>}
          </div>
          {otherSystems.length > 0 && (
            <ul aria-label="Also in" className="mt-3 flex flex-wrap gap-2">
              {otherSystems.map((other) => (
                <li key={other.slug}>
                  <Link
                    to={integrateSystemPath(other)}
                    className="inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium text-foreground no-underline hover:border-accent hover:bg-muted"
                  >
                    {other.name}
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {openFailed && (
            <Alert variant="destructive" className="mt-3 py-2">
              <AlertDescription>We couldn't open this document. Please try again.</AlertDescription>
            </Alert>
          )}
        </div>
      </div>
      <Button
        variant="outline"
        className="shrink-0 self-start"
        onClick={handleOpen}
        disabled={opening}
        aria-label="Open"
        title={`Open ${document.title} in a new tab`}
      >
        <ExternalLink aria-hidden="true" className="mr-2 h-4 w-4" />
        {opening ? 'Opening…' : 'Open'}
      </Button>
    </li>
  )
}

export default function LibrarySystemPage() {
  const { slug = '' } = useParams()
  const system = INTEGRATE_SYSTEMS.find((candidate) => candidate.slug === slug)
  const [documents, setDocuments] = useState<LibraryDocumentSummary[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!system) return
    let active = true
    setDocuments(null)
    setError(false)
    getLibrarySystem(system.slug)
      .then((detail) => {
        if (active) setDocuments(detail.documents)
      })
      .catch(() => {
        if (active) setError(true)
      })
    return () => {
      active = false
    }
  }, [system])

  if (!system) {
    return (
      <LibraryLayout>
        <div className="mx-auto max-w-4xl px-4 py-16 sm:px-6">
          <h1 className="font-display text-4xl font-bold">Folder not found</h1>
          <p className="mt-3 text-muted-foreground">
            There's no INTEGRATE System at this address.
          </p>
          <Button asChild className="mt-6">
            <Link to="/library/browse">Back to Browse the Library</Link>
          </Button>
        </div>
      </LibraryLayout>
    )
  }

  return (
    <LibraryLayout>
      <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
        <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground">
          <Link to="/library" className="text-link">
            Resource Library
          </Link>
          <span aria-hidden="true"> › </span>
          <Link to="/library/browse" className="text-link">
            Browse
          </Link>
          <span aria-hidden="true"> › </span>
          <span aria-current="page">{system.name}</span>
        </nav>
        <h1 className="mt-3 font-display text-4xl font-bold">{system.name}</h1>
        <p className="mt-2 text-lg text-muted-foreground">
          {system.area} — {system.tagline}
        </p>

        {error && (
          <Alert variant="destructive" className="mt-8">
            <AlertDescription>
              We couldn't load these documents. Please refresh the page to try again.
            </AlertDescription>
          </Alert>
        )}

        {!error && !documents && (
          <p role="status" className="mt-8 text-muted-foreground">
            Loading documents…
          </p>
        )}

        {documents && documents.length > 0 && (
          <ul aria-label="Documents" className="mt-8 space-y-4">
            {documents.map((document) => (
              <DocumentRow key={document.id} document={document} system={system} />
            ))}
          </ul>
        )}

        {documents && documents.length === 0 && (
          <p className="mt-8 rounded-lg border border-dashed bg-muted p-6 text-muted-foreground">
            There are no documents in {system.name} yet. Check back soon.
          </p>
        )}

        <aside
          aria-label="Ask the Librarian"
          className="mt-12 flex flex-col gap-4 rounded-lg bg-secondary p-6 text-secondary-foreground sm:flex-row sm:items-center sm:justify-between"
        >
          <p className="text-lg font-semibold">Have a question about {system.name}?</p>
          <Button asChild>
            <Link to="/chat">
              <MessageSquare aria-hidden="true" className="mr-2 h-4 w-4" />
              Ask the Librarian
            </Link>
          </Button>
        </aside>
      </div>
    </LibraryLayout>
  )
}
