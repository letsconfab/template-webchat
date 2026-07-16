import React, { useCallback, useEffect, useState } from 'react'
import { Button } from '../ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'
import { toast } from 'sonner'
import { api } from '../../services/api'

interface User {
  id: number
  email: string
  role: string
  is_active: boolean
  created_at: string
  updated_at: string
  last_login_at: string | null
  inferred_last_activity_at: string | null
  last_seen_at: string | null
  last_seen_source: 'login' | 'inferred' | null
  is_admin?: boolean
}

type StatusFilter = '' | 'active' | 'inactive'
type StaleFilter = '' | 'true' | 'false'

const PAGE_SIZE = 25

function formatLastSeen(user: User): { label: string; detail: string | null } {
  if (!user.last_seen_at) {
    return { label: 'Never seen', detail: null }
  }
  const when = new Date(user.last_seen_at).toLocaleString()
  const source =
    user.last_seen_source === 'login'
      ? 'login'
      : user.last_seen_source === 'inferred'
        ? 'inferred'
        : null
  return { label: when, detail: source }
}

export const UserList: React.FC = () => {
  const [users, setUsers] = useState<User[]>([])
  const [total, setTotal] = useState(0)
  const [skip, setSkip] = useState(0)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('')
  const [staleFilter, setStaleFilter] = useState<StaleFilter>('')
  const [isLoading, setIsLoading] = useState(true)
  const [unknownCount, setUnknownCount] = useState(0)

  const fetchUsers = useCallback(async () => {
    setIsLoading(true)
    try {
      const params: Record<string, string | number | boolean> = {
        skip,
        limit: PAGE_SIZE,
        sort_by: 'created_at',
        sort_order: 'desc',
      }
      if (statusFilter) params.status = statusFilter
      if (staleFilter === 'true') params.stale = true
      if (staleFilter === 'false') params.stale = false

      const response = await api.get('/admin/users', { params })
      const items: User[] = response.data.items || []
      setUsers(items)
      setTotal(response.data.total ?? 0)
      setUnknownCount(items.filter((u) => !u.last_seen_at).length)
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to fetch users'
      toast.error(message)
    } finally {
      setIsLoading(false)
    }
  }, [skip, statusFilter, staleFilter])

  useEffect(() => {
    fetchUsers()
  }, [fetchUsers])

  useEffect(() => {
    setSkip(0)
  }, [statusFilter, staleFilter])

  const deactivateUser = async (userId: number) => {
    try {
      await api.put(`/admin/users/${userId}`, { is_active: false })
      toast.success('User deactivated')
      fetchUsers()
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to deactivate user'
      toast.error(message)
    }
  }

  const activateUser = async (userId: number) => {
    try {
      await api.put(`/admin/users/${userId}`, { is_active: true })
      toast.success('User activated')
      fetchUsers()
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to activate user'
      toast.error(message)
    }
  }

  const changeUserRole = async (userId: number, currentRole: string) => {
    const newRole = currentRole === 'admin' ? 'user' : 'admin'
    try {
      await api.put(`/admin/users/${userId}`, { role: newRole })
      toast.success(`User role changed to ${newRole}`)
      fetchUsers()
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to update user role'
      toast.error(message)
    }
  }

  const page = Math.floor(skip / PAGE_SIZE) + 1
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>User Management</CardTitle>
          <CardDescription>
            Last seen is the later of a real login and inferred activity. Until the
            activity backfill finishes, many accounts show Never seen (unknown — not
            stale).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-4">
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted-foreground">Status</span>
              <select
                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
              >
                <option value="">All</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted-foreground">Stale (90+ days)</span>
              <select
                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                value={staleFilter}
                onChange={(e) => setStaleFilter(e.target.value as StaleFilter)}
              >
                <option value="">All</option>
                <option value="true">Stale only</option>
                <option value="false">Not stale</option>
              </select>
            </label>
            {!isLoading && unknownCount > 0 && (
              <p className="text-sm text-muted-foreground">
                {unknownCount} on this page have never been seen — backfill may be
                incomplete.
              </p>
            )}
          </div>

          {isLoading ? (
            <div className="py-8 text-center text-muted-foreground">Loading users…</div>
          ) : users.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">No users match.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last seen</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((user) => {
                  const seen = formatLastSeen(user)
                  return (
                    <TableRow key={user.id}>
                      <TableCell className="font-medium">{user.email}</TableCell>
                      <TableCell>
                        <Badge variant={user.role === 'admin' ? 'default' : 'secondary'}>
                          {user.role}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={user.is_active ? 'default' : 'destructive'}>
                          {user.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col gap-0.5">
                          <span>{seen.label}</span>
                          {seen.detail && (
                            <span className="text-xs text-muted-foreground">
                              via {seen.detail}
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        {new Date(user.created_at).toLocaleDateString()}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-2">
                          {user.is_active ? (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => deactivateUser(user.id)}
                            >
                              Deactivate
                            </Button>
                          ) : (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => activateUser(user.id)}
                            >
                              Activate
                            </Button>
                          )}
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => changeUserRole(user.id, user.role)}
                          >
                            Make {user.role === 'admin' ? 'User' : 'Admin'}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}

          <div className="flex items-center justify-between gap-4 pt-2">
            <p className="text-sm text-muted-foreground">
              {total} user{total === 1 ? '' : 's'} · page {page} of {totalPages}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={skip === 0}
                onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={skip + PAGE_SIZE >= total}
                onClick={() => setSkip(skip + PAGE_SIZE)}
              >
                Next
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
