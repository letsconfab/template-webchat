import { Link } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { Button } from '../ui/button'

interface AdminLayoutProps {
  title: string
  children: React.ReactNode
  actions?: React.ReactNode
  showBackToDashboard?: boolean
}

export function AdminLayout({
  title,
  children,
  actions,
  showBackToDashboard = true,
}: AdminLayoutProps) {
  const { logout } = useAuth()

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-4">
            {showBackToDashboard && (
              <Button variant="ghost" size="sm" asChild>
                <Link to="/admin/dashboard">← Dashboard</Link>
              </Button>
            )}
            <h1 className="truncate text-xl font-semibold text-foreground">{title}</h1>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {actions}
            <Button
              variant="destructive"
              size="sm"
              onClick={() => logout()}
            >
              <LogOut className="mr-2 h-4 w-4" />
              <span className="hidden sm:inline">Logout</span>
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {children}
      </main>
    </div>
  )
}
