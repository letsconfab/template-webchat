import type { ReactNode } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { Heart } from 'lucide-react'

import { useAuth } from '../../contexts/AuthContext'
import { cn } from '../../lib/utils'

/**
 * Demo chrome that mirrors the ALO website mockup ("Resource Library.png"):
 * site-style header and footer in the mockup's yellow/red palette. Used only
 * by the Resource Library landing page; the rest of the library keeps
 * LibraryLayout and the ALO brand tokens.
 */

const SITE_URL = 'https://www.alovingorganization.org'
// The mockup's site links. Only the home page URL is known, so the other
// pages point there until ALO confirms their paths.
const SITE_LINKS = {
  home: SITE_URL,
  about: SITE_URL,
  freeResources: SITE_URL,
  contact: SITE_URL,
  donate: SITE_URL,
  join: SITE_URL,
}

export const mockup = {
  red: 'text-[#A8231C]',
  bgRed: 'bg-[#A8231C]',
  ink: 'text-[#2A211C]',
  muted: 'text-[#5B524A]',
  hero: 'bg-[#F7DD91]',
  cream: 'bg-[#FDF8EE]',
  display: "font-['Anton',sans-serif] uppercase tracking-tight",
  body: "font-['Work_Sans',sans-serif]",
}

const navLinkClass = ({ isActive = false }: { isActive?: boolean } = {}) =>
  cn(
    'text-[15px] font-semibold no-underline hover:underline',
    isActive ? mockup.ink : mockup.red,
  )

function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn(mockup.display, mockup.red, 'text-2xl leading-none', className)}>
      A Loving Organization
    </span>
  )
}

export default function MockupSiteLayout({ children }: { children: ReactNode }) {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const membersPortalUrl = import.meta.env.VITE_MEMBERS_PORTAL_URL || SITE_URL

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className={cn('flex min-h-screen flex-col bg-white', mockup.body, mockup.ink)}>
      <header className="bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-4 sm:px-8 xl:flex-nowrap">
          <Link to="/library" className="flex items-center gap-3 no-underline" aria-label="Resource Library home">
            <span className={cn('flex h-10 w-10 items-center justify-center rounded-full', mockup.bgRed)}>
              <Heart aria-hidden="true" className="h-4 w-4 fill-white text-white" />
            </span>
            <Wordmark className="text-[28px]" />
          </Link>
          <nav aria-label="Resource Library" className="flex flex-wrap items-center gap-x-7 gap-y-2">
            <a href={SITE_LINKS.home} className={navLinkClass()}>Home</a>
            <a href={SITE_LINKS.about} className={navLinkClass()}>About</a>
            <a href={SITE_LINKS.freeResources} className={navLinkClass()}>Free Resources</a>
            <NavLink to="/library" end className={navLinkClass}>Resource Library</NavLink>
            <a href={membersPortalUrl} className={navLinkClass()}>Members Portal</a>
          </nav>
          <div className="flex shrink-0 items-center gap-3">
            <a
              href={SITE_LINKS.donate}
              className={cn(
                'rounded-md border-2 border-[#A8231C] px-7 py-3 text-sm font-bold uppercase tracking-wider no-underline hover:bg-[#FDF0EE]',
                mockup.red,
              )}
            >
              Donate
            </a>
            <a
              href={SITE_LINKS.join}
              className={cn(
                'rounded-md px-7 py-3 text-sm font-bold uppercase tracking-wider text-white no-underline hover:opacity-90',
                mockup.bgRed,
              )}
            >
              Join ALO
            </a>
          </div>
        </div>
      </header>

      <main className="flex-1">{children}</main>

      <footer className={mockup.hero}>
        <div className="mx-auto max-w-7xl px-4 sm:px-8">
          <div className="flex flex-wrap items-center justify-between gap-6 border-b border-[#E9CC74] py-10">
            <Wordmark />
            <nav aria-label="Site" className="flex flex-wrap items-center gap-x-7 gap-y-2">
              {[
                ['Home', SITE_LINKS.home],
                ['About', SITE_LINKS.about],
                ['Free Resources', SITE_LINKS.freeResources],
                ['Contact', SITE_LINKS.contact],
                ['Members Portal', membersPortalUrl],
                ['Donate', SITE_LINKS.donate],
              ].map(([label, href]) => (
                <a key={label} href={href} className="text-[15px] font-semibold text-[#3D342D] no-underline hover:underline">
                  {label}
                </a>
              ))}
            </nav>
          </div>
          <div className={cn('flex flex-wrap items-center justify-center gap-x-6 gap-y-2 py-6 text-sm', mockup.muted)}>
            <span>© 2026 All rights reserved A Loving Organization</span>
            <button type="button" onClick={handleLogout} className="underline hover:no-underline">
              Log out
            </button>
          </div>
        </div>
      </footer>
    </div>
  )
}
