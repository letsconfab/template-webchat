import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Folder } from 'lucide-react'

import LibraryLayout from '../components/library/LibraryLayout'
import { Alert, AlertDescription } from '../components/ui/alert'
import { INTEGRATE_SYSTEMS, integrateSystemPath, type IntegrateSystem } from '../lib/integrateSystems'
import { listLibrarySystems } from '../services/library'

function documentCountLabel(count: number): string {
  return count === 1 ? '1 document' : `${count} documents`
}

function FolderCardBody({ system, count }: { system: IntegrateSystem; count: number }) {
  return (
    <>
      <Folder
        aria-hidden="true"
        className={count > 0 ? 'h-6 w-6 shrink-0 text-brand-heart' : 'h-6 w-6 shrink-0'}
      />
      <div className="min-w-0">
        <h2 className="font-display text-xl font-semibold">{system.name}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {system.area} — {system.tagline}
        </p>
        <p className="mt-3 text-sm font-medium">
          {count > 0 ? documentCountLabel(count) : 'Coming soon'}
        </p>
      </div>
    </>
  )
}

export default function BrowseLibraryPage() {
  const [counts, setCounts] = useState<Record<string, number> | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    listLibrarySystems()
      .then((systems) => {
        if (active) setCounts(Object.fromEntries(systems.map((s) => [s.slug, s.document_count])))
      })
      .catch(() => {
        if (active) setError(true)
      })
    return () => {
      active = false
    }
  }, [])

  return (
    <LibraryLayout>
      <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
        <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground">
          <Link to="/library" className="text-link">
            Resource Library
          </Link>
          <span aria-hidden="true"> › </span>
          <span aria-current="page">Browse</span>
        </nav>
        <h1 className="mt-3 font-display text-4xl font-bold">Browse the Library</h1>
        <p className="mt-2 text-muted-foreground">
          Loving Systems in Practice and Field Guides, organized by INTEGRATE domain.
        </p>

        {error && (
          <Alert variant="destructive" className="mt-8">
            <AlertDescription>
              We couldn't load the library. Please refresh the page to try again.
            </AlertDescription>
          </Alert>
        )}

        {!error && !counts && (
          <p role="status" className="mt-8 text-muted-foreground">
            Loading the library…
          </p>
        )}

        {counts && (
          <ul aria-label="INTEGRATE Systems" className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {INTEGRATE_SYSTEMS.map((system) => {
              const count = counts[system.slug] ?? 0
              return (
                <li key={system.slug}>
                  {count > 0 ? (
                    <Link
                      to={integrateSystemPath(system)}
                      className="flex h-full gap-4 rounded-lg border bg-card p-5 text-card-foreground no-underline transition-colors hover:border-accent hover:bg-muted"
                    >
                      <FolderCardBody system={system} count={count} />
                    </Link>
                  ) : (
                    <div className="flex h-full gap-4 rounded-lg border border-dashed bg-muted p-5 text-muted-foreground">
                      <FolderCardBody system={system} count={count} />
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </LibraryLayout>
  )
}
