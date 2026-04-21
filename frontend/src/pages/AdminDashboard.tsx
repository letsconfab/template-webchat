import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { LogOut, Users, Mail, CheckCircle, Copy, Settings } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../services/api'

const inviteSchema = z.object({
  email: z.string().email('Invalid email address')
})

type InviteFormData = z.infer<typeof inviteSchema>

interface Invite {
  id: number
  email: string
  token: string
  status: 'pending' | 'accepted' | 'expired' | 'cancelled'
  created_at: string
  expiry_date: string
}

const AdminDashboard: React.FC = () => {
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [invites, setInvites] = useState<Invite[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [inviteSuccess, setInviteSuccess] = useState<string | null>(null)
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    setError
  } = useForm<InviteFormData>({
    resolver: zodResolver(inviteSchema)
  })

  // Load existing invites on component mount
  useEffect(() => {
    const loadInvites = async () => {
      try {
        const response = await api.get('/admin/invites')
        setInvites(response.data.invites || [])
      } catch (error: any) {
        console.error('Failed to load invites:', error)
      }
    }
    loadInvites()
  }, [])

  const onInviteSubmit = async (data: InviteFormData) => {
    setIsLoading(true)
    try {
      const response = await api.post('/admin/invite-user', data)

      const inviteData = response.data
      setInvites([inviteData, ...invites])
      setInviteSuccess(`Invite sent to ${data.email}`)
      reset()
      setShowInviteModal(false)
      
      // Clear success message after 3 seconds
      setTimeout(() => setInviteSuccess(null), 3000)
    } catch (error: any) {
      const message = error.response?.data?.detail || error.message || 'Failed to send invite'
      setError('root', { message })
    } finally {
      setIsLoading(false)
    }
  }

  const copyInviteLink = (token: string) => {
    const inviteLink = `${window.location.origin}/register?token=${token}`
    navigator.clipboard.writeText(inviteLink)
  }

  const handleLogout = () => {
    logout()
    navigate('/admin/login')
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <h1 className="text-xl font-bold text-gray-900">Admin Dashboard</h1>
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <span className="text-sm text-gray-700">
                Welcome, {user?.email}
              </span>
              <button
                onClick={() => navigate('/admin/settings')}
                className="flex items-center px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:text-gray-900 hover:bg-gray-100 transition-colors"
              >
                <Settings className="h-4 w-4 mr-2" />
                Settings
              </button>
              <button
                onClick={handleLogout}
                className="flex items-center px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:text-gray-900 hover:bg-gray-100 transition-colors"
              >
                <LogOut className="h-4 w-4 mr-2" />
                Logout
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Success Message */}
      {inviteSuccess && (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-4">
          <div className="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-md flex items-center">
            <CheckCircle className="h-4 w-4 mr-2" />
            {inviteSuccess}
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0 bg-blue-100 rounded-md p-3">
                  <Users className="h-6 w-6 text-blue-600" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      Total Invites
                    </dt>
                    <dd className="text-lg font-medium text-gray-900">
                      {invites.length}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0 bg-green-100 rounded-md p-3">
                  <CheckCircle className="h-6 w-6 text-green-600" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      Accepted Invites
                    </dt>
                    <dd className="text-lg font-medium text-gray-900">
                      {invites.filter(i => i.status === 'accepted').length}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white overflow-hidden shadow rounded-lg">
            <div className="p-5">
              <div className="flex items-center">
                <div className="flex-shrink-0 bg-yellow-100 rounded-md p-3">
                  <Mail className="h-6 w-6 text-yellow-600" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      Pending Invites
                    </dt>
                    <dd className="text-lg font-medium text-gray-900">
                      {invites.filter(i => i.status === 'pending').length}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Invite User Section */}
        <div className="bg-white shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg leading-6 font-medium text-gray-900">
                Invite Users
              </h3>
              <button
                onClick={() => setShowInviteModal(true)}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
              >
                <Mail className="h-4 w-4 mr-2" />
                Send Invite
              </button>
            </div>

            {/* Invites List */}
            <div className="mt-6">
              {invites.length === 0 ? (
                <div className="text-center py-12">
                  <Mail className="mx-auto h-12 w-12 text-gray-400" />
                  <h3 className="mt-2 text-sm font-medium text-gray-900">No invites sent</h3>
                  <p className="mt-1 text-sm text-gray-500">
                    Get started by sending your first invite.
                  </p>
                </div>
              ) : (
                <div className="overflow-hidden shadow ring-1 ring-black ring-opacity-5 md:rounded-lg">
                  <table className="min-w-full divide-y divide-gray-300">
                    <thead className="bg-gray-50">
                      <tr>
                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Email
                        </th>
                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Status
                        </th>
                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Created
                        </th>
                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {invites.map((invite) => (
                        <tr key={invite.id}>
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                            {invite.email}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap">
                            <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                              invite.status === 'accepted' 
                                ? 'bg-green-100 text-green-800' 
                                : invite.status === 'pending'
                                ? 'bg-yellow-100 text-yellow-800'
                                : invite.status === 'expired'
                                ? 'bg-red-100 text-red-800'
                                : 'bg-gray-100 text-gray-800'
                            }`}>
                              {invite.status.charAt(0).toUpperCase() + invite.status.slice(1)}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            {new Date(invite.created_at).toLocaleDateString()}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                            {invite.status === 'pending' && (
                              <button
                                onClick={() => copyInviteLink(invite.token)}
                                className="text-blue-600 hover:text-blue-900 transition-colors"
                                title="Copy invite link"
                              >
                                <Copy className="h-4 w-4" />
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      {/* Invite Modal */}
      {showInviteModal && (
        <div className="fixed z-10 inset-0 overflow-y-auto">
          <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
            <div className="fixed inset-0 transition-opacity" aria-hidden="true">
              <div className="absolute inset-0 bg-gray-500 opacity-75"></div>
            </div>

            <div className="inline-block align-bottom bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-lg sm:w-full">
              <form onSubmit={handleSubmit(onInviteSubmit)}>
                <div className="bg-white px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
                  <div className="sm:flex sm:items-start">
                    <div className="mx-auto flex-shrink-0 flex items-center justify-center h-12 w-12 rounded-full bg-blue-100 sm:mx-0 sm:h-10 sm:w-10">
                      <Mail className="h-6 w-6 text-blue-600" />
                    </div>
                    <div className="mt-3 text-center sm:mt-0 sm:ml-4 sm:text-left flex-1">
                      <h3 className="text-lg leading-6 font-medium text-gray-900">
                        Invite User
                      </h3>
                      <div className="mt-4">
                        <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                          Email Address
                        </label>
                        <input
                          {...register('email')}
                          type="email"
                          id="email"
                          className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                          placeholder="user@example.com"
                        />
                        {errors.email && (
                          <p className="mt-1 text-sm text-red-600">{errors.email.message}</p>
                        )}
                        {errors.root && (
                          <p className="mt-1 text-sm text-red-600">{errors.root.message}</p>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
                <div className="bg-gray-50 px-4 py-3 sm:px-6 sm:flex sm:flex-row-reverse">
                  <button
                    type="submit"
                    disabled={isLoading}
                    className="w-full inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-blue-600 text-base font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:ml-3 sm:w-auto sm:text-sm disabled:opacity-50"
                  >
                    {isLoading ? 'Sending...' : 'Send Invite'}
                  </button>
                  <button
                    type="button"
                    className="mt-3 w-full inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm"
                    onClick={() => {
                      setShowInviteModal(false)
                      reset()
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default AdminDashboard
