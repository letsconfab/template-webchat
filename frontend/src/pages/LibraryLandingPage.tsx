import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Folder, MessageSquare, type LucideIcon } from 'lucide-react'

import LibraryLayout from '../components/library/LibraryLayout'
import { Button } from '../components/ui/button'
import { INTEGRATE_SYSTEMS, integrateSystemPath } from '../lib/integrateSystems'

interface PathCardProps {
  icon: LucideIcon
  title: string
  children: ReactNode
  cta: string
  to: string
}

function PathCard({ icon: Icon, title, children, cta, to }: PathCardProps) {
  return (
    <div className="flex flex-col rounded-lg border bg-card p-6 text-card-foreground shadow-sm">
      <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-md bg-secondary">
        <Icon aria-hidden="true" className="h-5 w-5 text-brand-heart" />
      </div>
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="mt-2 flex-1 text-muted-foreground">{children}</p>
      <Button asChild className="mt-6 self-start">
        <Link to={to}>{cta}</Link>
      </Button>
    </div>
  )
}

export default function LibraryLandingPage() {
  return (
    <LibraryLayout>
      <section className="bg-surface-hero">
        <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
          {/* Large bold text (>= 18.66px): text-primary meets AA large-text contrast on the hero band. */}
          <p className="text-xl font-bold uppercase tracking-widest text-primary">MEMBERS-ONLY</p>
          <h1 className="mt-3 font-display text-4xl font-bold sm:text-5xl">ALO Resource Library</h1>
          <p className="mt-4 max-w-2xl text-lg">
            Every Loving System in Practice and INTEGRATE Field Guide the Consortium has published,
            organized two ways. Choose how you'd like to find what you need.
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
        <div className="grid gap-6 md:grid-cols-2">
          <PathCard icon={Folder} title="Browse the Library" cta="Access the Library" to="/library/browse">
            Search with your eyes. Click through folders of Loving Systems in Practice and Field
            Guides, organized by INTEGRATE domain.
          </PathCard>
          <PathCard icon={MessageSquare} title="Ask the Librarian" cta="Speak with the Librarian" to="/chat">
            Search with your heart. Ask ALO's librarian a question in plain language, and it will
            answer only from the Consortium's own library.
          </PathCard>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-16 sm:px-6">
        <h2 className="font-display text-3xl font-bold">What's Inside</h2>
        <p className="mt-2 text-muted-foreground">
          Both paths draw on the same library, organized around the nine INTEGRATE domains.
        </p>
        <ul aria-label="INTEGRATE Systems" className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {INTEGRATE_SYSTEMS.map((system) => (
            <li key={system.slug}>
              <Link
                to={integrateSystemPath(system)}
                className="block h-full rounded-lg border bg-card p-5 text-card-foreground no-underline transition-colors hover:border-accent hover:bg-muted"
              >
                <h3 className="font-display text-xl font-semibold">{system.name}</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {system.area} — {system.tagline}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </LibraryLayout>
  )
}
