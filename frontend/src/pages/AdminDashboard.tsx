import React, { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { LogOut, Users, Mail, CheckCircle, Copy, Settings, MessageSquare, Code } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../services/api'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'

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
  role: 'user' | 'admin'
}

const AdminDashboard: React.FC = () => {
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [showRoleSelectionModal, setShowRoleSelectionModal] = useState(false)
  const [showEmbedModal, setShowEmbedModal] = useState(false)
  const [selectedRole, setSelectedRole] = useState<'general' | 'admin'>('general')
  const [invites, setInvites] = useState<Invite[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [inviteSuccess, setInviteSuccess] = useState<string | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const invitesPerPage = 5
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
      const inviteData = {
        email: data.email,
        role: selectedRole === 'general' ? 'user' : 'admin'
      }
      const response = await api.post('/admin/invite-user', inviteData)

      const invite = response.data
      setInvites([invite, ...invites])
      setInviteSuccess(`Invite sent to ${data.email} as ${selectedRole}`)
      reset()
      setShowInviteModal(false)
      setSelectedRole('general')
      
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

  const copyEmbedCode = () => {
    const embedCode = `<iframe src="${window.location.origin}/chat" width="800" height="600" frameborder="0"></iframe>`
    navigator.clipboard.writeText(embedCode)
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const scrollToInviteUsers = () => {
    const element = document.getElementById('invite-users-section')
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-blue-50">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-md shadow-lg border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">Admin Dashboard</h1>
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <div className="hidden sm:block">
                <span className="text-sm text-gray-600 font-medium">
                  Welcome, <span className="text-gray-900">{user?.email}</span>
                </span>
              </div>
              <button
                onClick={() => navigate('/admin/settings')}
                className="flex items-center px-4 py-2 rounded-lg text-sm font-medium text-gray-700 hover:text-gray-900 hover:bg-white/60 hover:shadow-md transition-all duration-200 border border-gray-200"
              >
                <Settings className="h-4 w-4 mr-2" />
                <span className="hidden sm:inline">Settings</span>
              </button>
              <button
                onClick={handleLogout}
                className="flex items-center px-4 py-2 rounded-lg text-sm font-medium text-white bg-gradient-to-r from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 shadow-md hover:shadow-lg transition-all duration-200"
              >
                <LogOut className="h-4 w-4 mr-2" />
                <span className="hidden sm:inline">Logout</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Success Message */}
      {inviteSuccess && (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-4">
          <div className="bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 text-green-800 px-6 py-4 rounded-xl flex items-center shadow-lg animate-pulse">
            <CheckCircle className="h-5 w-5 mr-3 text-green-600" />
            <span className="font-medium">{inviteSuccess}</span>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Admin Features Cards */}
        <h2 className="text-xl font-semibold mb-4">Quick Links</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          {/* <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Your Role</CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold capitalize">{user?.role}</div>
              <p className="text-xs text-muted-foreground">
                {user?.role === 'admin' ? 'Full system access' : 'Standard user access'}
              </p>
            </CardContent>
          </Card> */}

          {/* <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Account Status</CardTitle>
              <Settings className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">Active</div>
              <p className="text-xs text-muted-foreground">
                Account is in good standing
              </p>
            </CardContent>
          </Card> */}

           <Card className="group hover:shadow-xl transition-all duration-300 border-0 bg-gradient-to-br from-white to-blue-50/30">
              <CardHeader className="pb-4">
                <div className="flex items-center justify-between">
                  <div className="p-2 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg">
                    <Code className="h-5 w-5 text-white" />
                  </div>
                  <div className="text-xs text-blue-600 font-medium bg-blue-50 px-2 py-1 rounded-full">Integration</div>
                </div>
                <CardTitle className="text-lg font-bold text-gray-900 mt-3">Embed Chat</CardTitle>
                <CardDescription className="text-gray-600">
                  Get sample code to embed the chat interface in external websites
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button variant="outline" className="w-full bg-white/80 hover:bg-white border-blue-200 hover:border-blue-300 text-blue-700 hover:text-blue-800 shadow-sm hover:shadow-md transition-all duration-200" onClick={() => setShowEmbedModal(true)}>
                  <Code className="h-4 w-4 mr-2" />
                  Get Embed Code
                </Button>
              </CardContent>
            </Card>

          <Card className="group hover:shadow-xl transition-all duration-300 border-0 bg-gradient-to-br from-white to-purple-50/30">
              <CardHeader className="pb-4">
                <div className="flex items-center justify-between">
                  <div className="p-2 bg-gradient-to-br from-purple-500 to-pink-600 rounded-lg">
                    <Users className="h-5 w-5 text-white" />
                  </div>
                  <div className="text-xs text-purple-600 font-medium bg-purple-50 px-2 py-1 rounded-full">Management</div>
                </div>
                <CardTitle className="text-lg font-bold text-gray-900 mt-3">User Management</CardTitle>
                <CardDescription className="text-gray-600">
                  Manage invited users and view registrations
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button variant="outline" className="w-full bg-white/80 hover:bg-white border-purple-200 hover:border-purple-300 text-purple-700 hover:text-purple-800 shadow-sm hover:shadow-md transition-all duration-200" onClick={scrollToInviteUsers}>
                  <Users className="h-4 w-4 mr-2" />
                  View Users
                </Button>
              </CardContent>
            </Card>

          <Card className="group hover:shadow-xl transition-all duration-300 border-0 bg-gradient-to-br from-white to-green-50/30">
              <CardHeader className="pb-4">
                <div className="flex items-center justify-between">
                  <div className="p-2 bg-gradient-to-br from-green-500 to-emerald-600 rounded-lg">
                    <MessageSquare className="h-5 w-5 text-white" />
                  </div>
                  <div className="text-xs text-green-600 font-medium bg-green-50 px-2 py-1 rounded-full">Quick Access</div>
                </div>
                <CardTitle className="text-lg font-bold text-gray-900 mt-3">Quick Actions</CardTitle>
                <CardDescription className="text-gray-600">
                  Access the chat interface directly
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Link to="/chat">
                  <Button variant="outline" className="w-full bg-white/80 hover:bg-white border-green-200 hover:border-green-300 text-green-700 hover:text-green-800 shadow-sm hover:shadow-md transition-all duration-200">
                    <MessageSquare className="h-4 w-4 mr-2" />
                    Open Chat
                  </Button>
                </Link>
              </CardContent>
            </Card>
        </div>

        {/* Admin Tools Section */}
        {/* <div className="space-y-4 mb-8">
          <h2 className="text-xl font-semibold">Admin Tools</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            

            <Card>
              <CardHeader>
                <CardTitle>System Settings</CardTitle>
                <CardDescription>
                  Configure application settings, LLM, and knowledge base
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Link to="/admin/settings">
                  <Button variant="outline" className="w-full">
                    <Settings className="h-4 w-4 mr-2" />
                    Settings
                  </Button>
                </Link>
              </CardContent>
            </Card>
          </div>
        </div> */}

        {/* Embed Section */}
        <div className="space-y-4 mb-8">
          <h2 className="text-xl font-semibold">Analytics</h2>
          <div className="grid grid-cols-1 md:grid-cols-1 gap-4">
           
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-gradient-to-br from-blue-500 to-blue-600 overflow-hidden shadow-xl rounded-2xl transform hover:scale-105 transition-all duration-300">
            <div className="p-6">
              <div className="flex items-center">
                <div className="flex-shrink-0 bg-white/20 backdrop-blur-sm rounded-xl p-4">
                  <Users className="h-8 w-8 text-white" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-blue-100 truncate">
                      Total Invites
                    </dt>
                    <dd className="text-3xl font-bold text-white">
                      {invites.length}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-gradient-to-br from-green-500 to-emerald-600 overflow-hidden shadow-xl rounded-2xl transform hover:scale-105 transition-all duration-300">
            <div className="p-6">
              <div className="flex items-center">
                <div className="flex-shrink-0 bg-white/20 backdrop-blur-sm rounded-xl p-4">
                  <CheckCircle className="h-8 w-8 text-white" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-green-100 truncate">
                      Accepted Invites
                    </dt>
                    <dd className="text-3xl font-bold text-white">
                      {invites.filter(i => i.status === 'accepted').length}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-gradient-to-br from-amber-500 to-orange-600 overflow-hidden shadow-xl rounded-2xl transform hover:scale-105 transition-all duration-300">
            <div className="p-6">
              <div className="flex items-center">
                <div className="flex-shrink-0 bg-white/20 backdrop-blur-sm rounded-xl p-4">
                  <Mail className="h-8 w-8 text-white" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-amber-100 truncate">
                      Pending Invites
                    </dt>
                    <dd className="text-3xl font-bold text-white">
                      {invites.filter(i => i.status === 'pending').length}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Invite User Section */}
        <h3 className="text-2xl font-bold text-gray-900 mb-4">
          Users
        </h3>
        <p className="text-gray-600 mb-6">Manage team members and track their status</p>
        
<div id="invite-users-section" className="bg-white/80 backdrop-blur-sm shadow-xl rounded-2xl border border-gray-100">
          <div className="px-6 py-6 sm:p-8">
            <div className="flex justify-end mb-6 gap-4">
              <button
                onClick={() => setShowRoleSelectionModal(true)}
                className="inline-flex items-center px-6 py-3 border border-transparent text-sm font-medium rounded-xl shadow-lg text-white bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all duration-200 transform hover:scale-105"
              >
                <Mail className="h-5 w-5 mr-2" />
                Send Invite
              </button>
            </div>

            {/* Invites List */}
            <div className="mt-6">
              {invites.length === 0 ? (
                <div className="text-center py-16 bg-gradient-to-br from-gray-50 to-blue-50/30 rounded-xl">
                  <div className="mx-auto w-20 h-20 bg-gradient-to-br from-blue-100 to-purple-100 rounded-full flex items-center justify-center mb-4">
                    <Mail className="h-10 w-10 text-blue-600" />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">No invites sent</h3>
                  <p className="text-gray-600 max-w-sm mx-auto">
                    Get started by sending your first invite to grow your team.
                  </p>
                </div>
              ) : (
                <div className="overflow-hidden shadow-xl ring-1 ring-gray-200 rounded-xl">
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gradient-to-r from-gray-50 to-blue-50">
                        <tr>
                          <th scope="col" className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                            Email
                          </th>
                          <th scope="col" className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                            Role
                          </th>
                          <th scope="col" className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                            Status
                          </th>
                          <th scope="col" className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                            Created
                          </th>
                          <th scope="col" className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                            Actions
                          </th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-100">
                        {invites.slice((currentPage - 1) * invitesPerPage, currentPage * invitesPerPage).map((invite) => (
                          <tr key={invite.id} className="hover:bg-gray-50 transition-colors">
                            <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                              {invite.email}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <span className={`inline-flex px-3 py-1 text-xs font-semibold rounded-full ${
                                invite.role === 'admin' 
                                  ? 'bg-gradient-to-r from-purple-100 to-purple-200 text-purple-800 border border-purple-300' 
                                  : 'bg-gradient-to-r from-gray-100 to-gray-200 text-gray-800 border border-gray-300'
                              }`}>
                                {invite.role === 'admin' ? 'Admin' : 'User'}
                              </span>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <span className={`inline-flex px-3 py-1 text-xs font-semibold rounded-full ${
                                invite.status === 'accepted' 
                                  ? 'bg-gradient-to-r from-green-100 to-emerald-100 text-green-800 border border-green-300' 
                                  : invite.status === 'pending'
                                  ? 'bg-gradient-to-r from-yellow-100 to-amber-100 text-yellow-800 border border-yellow-300'
                                  : invite.status === 'expired'
                                  ? 'bg-gradient-to-r from-red-100 to-pink-100 text-red-800 border border-red-300'
                                  : 'bg-gradient-to-r from-gray-100 to-gray-200 text-gray-800 border border-gray-300'
                              }`}>
                                {invite.status.charAt(0).toUpperCase() + invite.status.slice(1)}
                              </span>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                              {new Date(invite.created_at).toLocaleDateString()}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                              {invite.status === 'pending' && (
                                <button
                                  onClick={() => copyInviteLink(invite.token)}
                                  className="inline-flex items-center px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-600 hover:text-blue-700 rounded-lg transition-all duration-200 border border-blue-200"
                                  title="Copy invite link"
                                >
                                  <Copy className="h-4 w-4 mr-1" />
                                  Copy
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  
                  {/* Pagination */}
                  {invites.length > invitesPerPage && (
                    <div className="px-6 py-4 bg-white border-t border-gray-200 flex items-center justify-between">
                      <div className="text-sm text-gray-700">
                        Showing {((currentPage - 1) * invitesPerPage) + 1} to {Math.min(currentPage * invitesPerPage, invites.length)} of {invites.length} invites
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                          disabled={currentPage === 1}
                          className="px-3 py-1 text-sm rounded-lg border border-gray-300 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          Previous
                        </button>
                        <button
                          onClick={() => setCurrentPage(p => Math.min(Math.ceil(invites.length / invitesPerPage), p + 1))}
                          disabled={currentPage >= Math.ceil(invites.length / invitesPerPage)}
                          className="px-3 py-1 text-sm rounded-lg border border-gray-300 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      {/* Role Selection Modal */}
      {showRoleSelectionModal && (
        <div className="fixed z-50 inset-0 overflow-y-auto">
          <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
            <div className="fixed inset-0 transition-opacity bg-gray-900/75 backdrop-blur-sm" aria-hidden="true"></div>

            <div className="inline-block align-bottom bg-white rounded-2xl text-left overflow-hidden shadow-2xl transform transition-all sm:my-8 sm:align-middle sm:max-w-lg sm:w-full">
              <div className="bg-gradient-to-br from-white to-blue-50/30 px-6 pt-6 pb-4 sm:p-6 sm:pb-4">
                <div className="sm:flex sm:items-start">
                  <div className="mx-auto flex-shrink-0 flex items-center justify-center h-14 w-14 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 sm:mx-0 sm:h-12 sm:w-12">
                    <Users className="h-7 w-7 text-white" />
                  </div>
                  <div className="mt-4 text-center sm:mt-0 sm:ml-4 sm:text-left flex-1">
                    <h3 className="text-xl font-bold text-gray-900">
                      Select Role for Invitation
                    </h3>
                    <div className="mt-4">
                      <p className="text-sm text-gray-600 mb-6">
                        Choose the role for the user you want to invite:
                      </p>
                      <div className="space-y-4">
                        <label className="flex items-center p-4 border-2 rounded-xl cursor-pointer hover:bg-gradient-to-r hover:from-blue-50 hover:to-purple-50 transition-all duration-200 ${selectedRole === 'general' ? 'border-blue-500 bg-gradient-to-r from-blue-50 to-purple-50' : 'border-gray-200'}">
                          <input
                            type="radio"
                            name="role"
                            value="general"
                            checked={selectedRole === 'general'}
                            onChange={(e) => setSelectedRole(e.target.value as 'general' | 'admin')}
                            className="mr-4 h-4 w-4 text-blue-600 focus:ring-blue-500"
                          />
                          <div className="flex-1">
                            <div className="font-semibold text-gray-900">General User</div>
                            <div className="text-sm text-gray-600 mt-1">Can access chat and basic features</div>
                          </div>
                        </label>
                        <label className="flex items-center p-4 border-2 rounded-xl cursor-pointer hover:bg-gradient-to-r hover:from-purple-50 hover:to-pink-50 transition-all duration-200 ${selectedRole === 'admin' ? 'border-purple-500 bg-gradient-to-r from-purple-50 to-pink-50' : 'border-gray-200'}">
                          <input
                            type="radio"
                            name="role"
                            value="admin"
                            checked={selectedRole === 'admin'}
                            onChange={(e) => setSelectedRole(e.target.value as 'general' | 'admin')}
                            className="mr-4 h-4 w-4 text-purple-600 focus:ring-purple-500"
                          />
                          <div className="flex-1">
                            <div className="font-semibold text-gray-900">Admin</div>
                            <div className="text-sm text-gray-600 mt-1">Full system access and user management</div>
                          </div>
                        </label>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div className="bg-gradient-to-r from-gray-50 to-blue-50 px-6 py-4 sm:px-6 sm:flex sm:flex-row-reverse">
                <button
                  type="button"
                  onClick={() => {
                    setShowRoleSelectionModal(false)
                    setShowInviteModal(true)
                  }}
                  className="w-full inline-flex justify-center rounded-xl border border-transparent shadow-lg px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-base font-semibold text-white hover:from-blue-600 hover:to-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:ml-3 sm:w-auto sm:text-sm transition-all duration-200 transform hover:scale-105"
                >
                  Continue
                </button>
                <button
                  type="button"
                  className="mt-3 w-full inline-flex justify-center rounded-xl border border-gray-300 shadow-sm px-6 py-3 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm transition-all duration-200"
                  onClick={() => {
                    setShowRoleSelectionModal(false)
                    setSelectedRole('general')
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Invite Modal */}
      {showInviteModal && (
        <div className="fixed z-50 inset-0 overflow-y-auto">
          <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
            <div className="fixed inset-0 transition-opacity bg-gray-900/75 backdrop-blur-sm" aria-hidden="true"></div>

            <div className="inline-block align-bottom bg-white rounded-2xl text-left overflow-hidden shadow-2xl transform transition-all sm:my-8 sm:align-middle sm:max-w-lg sm:w-full">
              <form onSubmit={handleSubmit(onInviteSubmit)}>
                <div className="bg-gradient-to-br from-white to-blue-50/30 px-6 pt-6 pb-4 sm:p-6 sm:pb-4">
                  <div className="sm:flex sm:items-start">
                    <div className="mx-auto flex-shrink-0 flex items-center justify-center h-14 w-14 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 sm:mx-0 sm:h-12 sm:w-12">
                      <Mail className="h-7 w-7 text-white" />
                    </div>
                    <div className="mt-4 text-center sm:mt-0 sm:ml-4 sm:text-left flex-1">
                      <h3 className="text-xl font-bold text-gray-900">
                        Invite User
                      </h3>
                      
                      {/* Selected Role Display */}
                      <div className="mt-4 p-4 bg-gradient-to-r from-blue-50 to-purple-50 border border-blue-200 rounded-xl">
                        <div className="flex items-center">
                          <div className="p-2 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg mr-3">
                            <Users className="h-5 w-5 text-white" />
                          </div>
                          <div>
                            <div className="text-sm font-semibold text-blue-900">
                              Role: {selectedRole === 'admin' ? 'Admin' : 'General User'}
                            </div>
                            <div className="text-xs text-blue-700 mt-1">
                              {selectedRole === 'admin' 
                                ? 'This user will have full system access' 
                                : 'This user will have standard access'}
                            </div>
                          </div>
                        </div>
                      </div>
                      
                      <div className="mt-6">
                        <label htmlFor="email" className="block text-sm font-semibold text-gray-700 mb-2">
                          Email Address
                        </label>
                        <input
                          {...register('email')}
                          type="email"
                          id="email"
                          className="mt-1 block w-full border border-gray-300 rounded-xl shadow-sm py-3 px-4 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 sm:text-sm transition-all duration-200"
                          placeholder="user@example.com"
                        />
                        {errors.email && (
                          <p className="mt-2 text-sm text-red-600 font-medium">{errors.email.message}</p>
                        )}
                        {errors.root && (
                          <p className="mt-2 text-sm text-red-600 font-medium">{errors.root.message}</p>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
                <div className="bg-gradient-to-r from-gray-50 to-blue-50 px-6 py-4 sm:px-6 sm:flex sm:flex-row-reverse">
                  <button
                    type="submit"
                    disabled={isLoading}
                    className="w-full inline-flex justify-center rounded-xl border border-transparent shadow-lg px-6 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-base font-semibold text-white hover:from-blue-600 hover:to-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:ml-3 sm:w-auto sm:text-sm disabled:opacity-50 transition-all duration-200 transform hover:scale-105"
                  >
                    {isLoading ? 'Sending...' : 'Send Invite'}
                  </button>
                  <button
                    type="button"
                    className="mt-3 w-full inline-flex justify-center rounded-xl border border-gray-300 shadow-sm px-6 py-3 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm transition-all duration-200"
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

      {/* Embed Modal */}
      {showEmbedModal && (
        <div className="fixed z-50 inset-0 overflow-y-auto">
          <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
            <div className="fixed inset-0 transition-opacity bg-gray-900/85 backdrop-blur-md" aria-hidden="true"></div>

            <div className="inline-block align-bottom bg-white rounded-2xl text-left overflow-hidden shadow-2xl transform transition-all sm:my-8 sm:align-middle sm:max-w-4xl sm:w-full">
              <div className="bg-gradient-to-br from-white via-blue-50/20 to-purple-50/20 px-6 pt-6 pb-4 sm:p-6 sm:pb-4">
                <div className="sm:flex sm:items-start">
                  <div className="mx-auto flex-shrink-0 flex items-center justify-center h-16 w-16 rounded-2xl bg-gradient-to-br from-blue-500 via-purple-500 to-pink-500 shadow-lg sm:mx-0 sm:h-14 sm:w-14">
                    <Code className="h-8 w-8 text-white" />
                  </div>
                  <div className="mt-4 text-center sm:mt-0 sm:ml-4 sm:text-left flex-1">
                    <h3 className="text-2xl font-bold bg-gradient-to-r from-gray-900 to-gray-700 bg-clip-text text-transparent">
                      Embed Chat in Your Website
                    </h3>
                    <p className="mt-2 text-sm text-gray-600 leading-relaxed">
                      Integrate your chat interface seamlessly into any website with our customizable embed options
                    </p>
                  </div>
                </div>
              </div>

              <div className="px-6 pb-6 sm:p-6 sm:pb-6">
                {/* Embed Code Section */}
                <div className="mb-6">
                  <div className="flex items-center justify-between mb-4">
                    <h4 className="text-lg font-semibold text-gray-900 flex items-center">
                      <div className="p-2 bg-gradient-to-br from-blue-100 to-purple-100 rounded-lg mr-3">
                        <Code className="h-5 w-5 text-blue-600" />
                      </div>
                      HTML Code
                    </h4>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded-full font-medium">Ready to use</span>
                      <button
                        onClick={copyEmbedCode}
                        className="inline-flex items-center px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white rounded-xl transition-all duration-200 text-sm font-semibold shadow-md hover:shadow-lg transform hover:scale-105"
                        title="Copy embed code"
                      >
                        <Copy className="h-4 w-4 mr-2" />
                        Copy Code
                      </button>
                    </div>
                  </div>
                  
                  <div className="bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 border border-gray-700 rounded-2xl p-6 shadow-xl">
                    <div className="flex items-center justify-between mb-4">
                      <span className="text-sm font-semibold text-gray-200 flex items-center">
                        <div className="w-3 h-3 bg-red-500 rounded-full mr-2"></div>
                        <div className="w-3 h-3 bg-yellow-500 rounded-full mr-2"></div>
                        <div className="w-3 h-3 bg-green-500 rounded-full mr-3"></div>
                        embed.html
                      </span>
                    </div>
                    <pre className="text-sm text-gray-100 p-4 rounded-xl overflow-x-auto bg-black/60 font-mono leading-relaxed">
                      <code>{`<iframe src="${window.location.origin}/chat" width="800" height="600" frameborder="0"></iframe>`}</code>
                    </pre>
                  </div>
                </div>

                {/* Customization Options */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                  {/* Size Options */}
                  <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-200 rounded-2xl p-6">
                    <h4 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                      <div className="p-2 bg-blue-500 rounded-lg mr-3">
                        <svg className="h-5 w-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                        </svg>
                      </div>
                      Size Options
                    </h4>
                    <div className="space-y-3">
                      <div className="flex items-center justify-between p-3 bg-white/70 rounded-lg border border-blue-200">
                        <span className="text-sm font-medium text-gray-700">Small</span>
                        <code className="text-xs bg-gray-800 text-gray-100 px-2 py-1 rounded font-mono">400×300</code>
                      </div>
                      <div className="flex items-center justify-between p-3 bg-white/70 rounded-lg border border-blue-200">
                        <span className="text-sm font-medium text-gray-700">Medium</span>
                        <code className="text-xs bg-gray-800 text-gray-100 px-2 py-1 rounded font-mono">800×600</code>
                      </div>
                      <div className="flex items-center justify-between p-3 bg-white/70 rounded-lg border border-blue-200">
                        <span className="text-sm font-medium text-gray-700">Large</span>
                        <code className="text-xs bg-gray-800 text-gray-100 px-2 py-1 rounded font-mono">100%×800</code>
                      </div>
                    </div>
                  </div>

                  {/* Style Options */}
                  <div className="bg-gradient-to-br from-purple-50 to-pink-50 border border-purple-200 rounded-2xl p-6">
                    <h4 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                      <div className="p-2 bg-purple-500 rounded-lg mr-3">
                        <svg className="h-5 w-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
                        </svg>
                      </div>
                      Style Options
                    </h4>
                    <div className="space-y-3">
                      <div className="flex items-center justify-between p-3 bg-white/70 rounded-lg border border-purple-200">
                        <span className="text-sm font-medium text-gray-700">Border</span>
                        <code className="text-xs bg-gray-800 text-gray-100 px-2 py-1 rounded font-mono">frameborder="0"</code>
                      </div>
                      <div className="flex items-center justify-between p-3 bg-white/70 rounded-lg border border-purple-200">
                        <span className="text-sm font-medium text-gray-700">Responsive</span>
                        <code className="text-xs bg-gray-800 text-gray-100 px-2 py-1 rounded font-mono">width="100%"</code>
                      </div>
                      <div className="flex items-center justify-between p-3 bg-white/70 rounded-lg border border-purple-200">
                        <span className="text-sm font-medium text-gray-700">Scrolling</span>
                        <code className="text-xs bg-gray-800 text-gray-100 px-2 py-1 rounded font-mono">scrolling="auto"</code>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Advanced Tips */}
                <div className="bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-2xl p-6">
                  <h4 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                    <div className="p-2 bg-amber-500 rounded-lg mr-3">
                      <svg className="h-5 w-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                    Pro Tips
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="flex items-start space-x-3">
                      <div className="flex-shrink-0 w-6 h-6 bg-amber-100 rounded-full flex items-center justify-center mt-0.5">
                        <span className="text-xs font-bold text-amber-600">1</span>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-800">Responsive Design</p>
                        <p className="text-xs text-gray-600 mt-1">Use CSS max-width and height for better mobile experience</p>
                      </div>
                    </div>
                    <div className="flex items-start space-x-3">
                      <div className="flex-shrink-0 w-6 h-6 bg-amber-100 rounded-full flex items-center justify-center mt-0.5">
                        <span className="text-xs font-bold text-amber-600">2</span>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-800">Loading Optimization</p>
                        <p className="text-xs text-gray-600 mt-1">Add loading="lazy" attribute for better performance</p>
                      </div>
                    </div>
                    <div className="flex items-start space-x-3">
                      <div className="flex-shrink-0 w-6 h-6 bg-amber-100 rounded-full flex items-center justify-center mt-0.5">
                        <span className="text-xs font-bold text-amber-600">3</span>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-800">Custom Styling</p>
                        <p className="text-xs text-gray-600 mt-1">Wrap iframe in a div for custom borders and shadows</p>
                      </div>
                    </div>
                    <div className="flex items-start space-x-3">
                      <div className="flex-shrink-0 w-6 h-6 bg-amber-100 rounded-full flex items-center justify-center mt-0.5">
                        <span className="text-xs font-bold text-amber-600">4</span>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-800">Security</p>
                        <p className="text-xs text-gray-600 mt-1">Add sandbox attribute for additional security</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-gradient-to-r from-gray-50 to-blue-50 px-6 py-4 sm:px-6 sm:flex sm:flex-row-reverse border-t border-gray-200">
                <button
                  type="button"
                  onClick={() => setShowEmbedModal(false)}
                  className="w-full inline-flex justify-center rounded-xl border border-transparent shadow-lg px-6 py-3 bg-gradient-to-r from-blue-500 to-purple-600 text-base font-semibold text-white hover:from-blue-600 hover:to-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:ml-3 sm:w-auto sm:text-sm transition-all duration-200 transform hover:scale-105"
                >
                  Done
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowEmbedModal(false)
                    window.open(`${window.location.origin}/chat`, '_blank')
                  }}
                  className="mt-3 w-full inline-flex justify-center rounded-xl border border-gray-300 shadow-sm px-6 py-3 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm transition-all duration-200"
                >
                  Preview Chat
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default AdminDashboard
