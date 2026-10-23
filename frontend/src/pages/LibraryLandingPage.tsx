import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Folder, MessageSquare, type LucideIcon } from 'lucide-react'

import MockupSiteLayout, { mockup } from '../components/library/MockupSiteLayout'
import { INTEGRATE_SYSTEMS, integrateSystemPath } from '../lib/integrateSystems'
import { cn } from '../lib/utils'

interface PathCardProps {
  icon: LucideIcon
  title: string
  children: ReactNode
  cta: string
  to: string
}

function PathCard({ icon: Icon, title, children, cta, to }: PathCardProps) {
  return (
    <div className="flex flex-col rounded-2xl bg-[#FDF8EE] p-10 text-left">
      <div className="mb-7 flex h-14 w-14 items-center justify-center rounded-xl bg-[#FBEBC0]">
        <Icon aria-hidden="true" className={cn('h-6 w-6', mockup.red)} />
      </div>
      <h2 className={cn(mockup.display, 'text-[32px] leading-tight')}>{title}</h2>
      <p className={cn('mt-4 flex-1 text-[17px] leading-relaxed', mockup.muted)}>{children}</p>
      <Link
        to={to}
        className={cn(
          'mt-6 self-start rounded-md px-8 py-4 text-base font-bold uppercase tracking-wider text-white no-underline hover:opacity-90',
          mockup.bgRed,
        )}
      >
        {cta}
      </Link>
    </div>
  )
}

export default function LibraryLandingPage() {
  return (
    <MockupSiteLayout>
      <section className={mockup.hero}>
        <div className="mx-auto max-w-6xl px-4 py-24 text-center sm:px-8">
          <p className={cn('text-sm font-bold uppercase tracking-[0.2em]', mockup.red)}>MEMBERS-ONLY</p>
          <h1 className={cn(mockup.display, mockup.red, 'mt-3 text-6xl sm:text-7xl')}>ALO Resource Library</h1>
          <p className="mx-auto mt-6 max-w-2xl text-xl leading-relaxed text-[#3D342D]">
            Every Loving System in Practice and INTEGRATE Field Guide the Consortium has published,
            organized two ways. Choose how you'd like to find what you need.
          </p>
          <div className="mx-auto mt-14 grid max-w-5xl gap-8 md:grid-cols-2">
            <PathCard icon={Folder} title="Browse the Library" cta="Access the Library" to="/library/browse">
              Search with your eyes. Click through folders of Loving Systems in Practice and Field
              Guides, organized by INTEGRATE domain.
            </PathCard>
            <PathCard icon={MessageSquare} title="Ask the Librarian" cta="Speak with the Librarian" to="/chat">
              Search with your heart. Ask ALO's librarian a question in plain language, and it will
              answer only from the Consortium's own library.
            </PathCard>
          </div>
        </div>
      </section>

      <section className={mockup.cream}>
        <div className="mx-auto max-w-6xl px-4 py-24 text-center sm:px-8">
          <h2 className={cn(mockup.display, mockup.red, 'text-5xl')}>What's Inside</h2>
          <p className="mt-5 text-xl text-[#3D342D]">
            Both paths draw on the same library, organized around the nine INTEGRATE domains.
          </p>
          <ul aria-label="INTEGRATE Systems" className="mt-14 grid gap-5 text-left sm:grid-cols-2 lg:grid-cols-3">
            {INTEGRATE_SYSTEMS.map((system) => (
              <li key={system.slug}>
                <Link
                  to={integrateSystemPath(system)}
                  className="block h-full rounded-xl border border-[#F0E2B6] bg-[#FDF8EE] px-7 py-8 no-underline transition-colors hover:border-[#A8231C] hover:bg-white"
                >
                  <h3 className={cn(mockup.display, mockup.ink, 'text-xl')}>{system.name}</h3>
                  <p className={cn('mt-1 text-[15px] leading-snug', mockup.muted)}>
                    {system.area} — {system.tagline}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </MockupSiteLayout>
  )
}
