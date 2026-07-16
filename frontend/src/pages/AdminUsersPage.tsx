import { AdminLayout } from '../components/admin/AdminLayout'
import { BulkInvitePanel } from '../components/admin/BulkInvitePanel'
import { UserList } from '../components/admin/UserList'

export default function AdminUsersPage() {
  return (
    <AdminLayout title="Users">
      <div className="space-y-8">
        <BulkInvitePanel />
        <UserList />
      </div>
    </AdminLayout>
  )
}
