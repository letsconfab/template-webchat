import type { ReactNode } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { LogOut } from 'lucide-react'

import BrandLogo from '../BrandLogo'
import { Button } from '../ui/button'
import { useAuth } from '../../contexts/AuthContext'
import { cn } from '../../lib/utils'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'text-sm no-underline hover:underline',
    isActive ? 'font-semibold text-foreground' : 'text-muted-foreground',
  )

/**
 * Shared chrome for the Resource Library pages and the Librarian: a slim
 * header with the brand logo, library navigation, and the user menu.
 */
export default function LibraryLayout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  // The website's Members Portal page, set per deployment; hidden when unset.
  const membersPortalUrl = import.meta.env.VITE_MEMBERS_PORTAL_URL

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="border-b bg-background">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
          <Link to="/library" className="no-underline" aria-label="Resource Library home">
            <BrandLogo />
          </Link>
          <nav aria-label="Resource Library" className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <NavLink to="/library" end className={navLinkClass}>
              Resource Library
            </NavLink>
            <NavLink to="/chat" className={navLinkClass}>
              Ask the Librarian
            </NavLink>
            {membersPortalUrl && (
              <a
                href={membersPortalUrl}
                className="text-sm text-muted-foreground no-underline hover:underline"
              >
                Members Portal
              </a>
            )}
          </nav>
          <div className="flex items-center gap-3">
            {user && (
              <span className="hidden max-w-[16rem] truncate text-sm text-muted-foreground sm:inline">
                {user.email}
              </span>
            )}
            <Button variant="outline" size="sm" onClick={handleLogout}>
              <LogOut aria-hidden="true" className="mr-2 h-4 w-4" />
              Log out
            </Button>
          </div>
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <footer className="border-t">
        <div className="mx-auto max-w-6xl px-4 py-6 text-sm text-muted-foreground sm:px-6">
          © 2026 A Loving Organization
        </div>
      </footer>
    </div>
  )
}
