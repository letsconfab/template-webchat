import React, { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { LogOut, Lightbulb, Check, X, FileText, Clock } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../services/api'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Button } from '../components/ui/button'

interface Insight {
  id: number
  content: string
  source_message: string
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
  reviewed_at?: string
  reviewed_by?: string
}

const InsightsReview: React.FC = () => {
  const [insights, setInsights] = useState<Insight[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'pending' | 'approved' | 'rejected'>('pending')
  const [currentPage, setCurrentPage] = useState(1)
  const insightsPerPage = 10
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    loadInsights()
  }, [filter])

  const loadInsights = async () => {
    try {
      const response = await api.get('/insights', { params: { status_filter: filter === 'pending' ? undefined : filter } })
      setInsights(response.data || [])
    } catch (error) {
      console.error('Failed to load insights:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleApprove = async (id: number) => {
    try {
      await api.post(`/insights/${id}/approve`)
      setInsights(insights.map(i => 
        i.id === id ? { ...i, status: 'approved', reviewed_at: new Date().toISOString() } : i
      ))
    } catch (error) {
      console.error('Failed to approve insight:', error)
    }
  }

  const handleReject = async (id: number) => {
    try {
      await api.post(`/insights/${id}/reject`)
      setInsights(insights.map(i => 
        i.id === id ? { ...i, status: 'rejected', reviewed_at: new Date().toISOString() } : i
      ))
    } catch (error) {
      console.error('Failed to reject insight:', error)
    }
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const filteredInsights = insights.filter(i => filter === 'all' || i.status === filter)
  const paginatedInsights = filteredInsights.slice(
    (currentPage - 1) * insightsPerPage,
    currentPage * insightsPerPage
  )
  const totalPages = Math.ceil(filteredInsights.length / insightsPerPage)

  const pendingCount = insights.filter(i => i.status === 'pending').length
  const approvedCount = insights.filter(i => i.status === 'approved').length
  const rejectedCount = insights.filter(i => i.status === 'rejected').length

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-blue-50">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-md shadow-lg border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <Link to="/admin/dashboard" className="flex-shrink-0">
                <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                  Insights Review
                </h1>
              </Link>
            </div>
            <div className="flex items-center space-x-4">
              <Link
                to="/admin/dashboard"
                className="flex items-center px-4 py-2 rounded-lg text-sm font-medium text-gray-700 hover:text-gray-900 hover:bg-white/60 hover:shadow-md transition-all duration-200 border border-gray-200"
              >
                <FileText className="h-4 w-4 mr-2" />
                <span className="hidden sm:inline">Admin</span>
              </Link>
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

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card className="bg-gradient-to-br from-amber-500 to-orange-600 text-white">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-amber-100 text-sm font-medium">Pending Review</p>
                  <p className="text-3xl font-bold mt-1">{pendingCount}</p>
                </div>
                <div className="p-3 bg-white/20 rounded-xl">
                  <Clock className="h-8 w-8" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-green-500 to-emerald-600 text-white">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-green-100 text-sm font-medium">Approved</p>
                  <p className="text-3xl font-bold mt-1">{approvedCount}</p>
                </div>
                <div className="p-3 bg-white/20 rounded-xl">
                  <Check className="h-8 w-8" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-gray-500 to-slate-600 text-white">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-gray-100 text-sm font-medium">Rejected</p>
                  <p className="text-3xl font-bold mt-1">{rejectedCount}</p>
                </div>
                <div className="p-3 bg-white/20 rounded-xl">
                  <X className="h-8 w-8" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filter */}
        <div className="flex items-center gap-4 mb-6">
          <span className="text-sm font-medium text-gray-700">Filter:</span>
          <div className="flex gap-2">
            {(['pending', 'approved', 'rejected'] as const).map((f) => (
              <button
                key={f}
                onClick={() => { setFilter(f); setCurrentPage(1); }}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  filter === f
                    ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white shadow-md'
                    : 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-200'
                }`}
              >
                {f.charAt(0).toUpperCase() + f.slice(1)}
                {f === 'pending' && ` (${pendingCount})`}
              </button>
            ))}
          </div>
        </div>

        {/* Insights List */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <Lightbulb className="h-5 w-5 mr-2 text-amber-500" />
              Knowledge Insights
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="text-center py-8 text-gray-500">Loading insights...</div>
            ) : filteredInsights.length === 0 ? (
              <div className="text-center py-12">
                <div className="mx-auto w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
                  <Lightbulb className="h-8 w-8 text-gray-400" />
                </div>
                <p className="text-gray-600">No insights to review</p>
              </div>
            ) : (
              <div className="space-y-4">
                {paginatedInsights.map((insight) => (
                  <div
                    key={insight.id}
                    className="p-4 bg-gray-50 rounded-xl border border-gray-100"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2">
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                            insight.status === 'pending' 
                              ? 'bg-amber-100 text-amber-800'
                              : insight.status === 'approved'
                              ? 'bg-green-100 text-green-800'
                              : 'bg-gray-100 text-gray-800'
                          }`}>
                            {insight.status.charAt(0).toUpperCase() + insight.status.slice(1)}
                          </span>
                          <span className="text-xs text-gray-500">
                            {new Date(insight.created_at).toLocaleString()}
                          </span>
                        </div>
                        <p className="text-sm text-gray-900">{insight.content}</p>
                        {insight.source_message && (
                          <p className="text-xs text-gray-500 mt-2 italic">
                            Source: {insight.source_message.slice(0, 100)}...
                          </p>
                        )}
                      </div>
                      {insight.status === 'pending' && (
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-green-600 hover:text-green-700 hover:bg-green-50 border-green-200"
                            onClick={() => handleApprove(insight.id)}
                          >
                            <Check className="h-4 w-4" />
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-red-600 hover:text-red-700 hover:bg-red-50 border-red-200"
                            onClick={() => handleReject(insight.id)}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-6 pt-4 border-t border-gray-200">
                <div className="text-sm text-gray-600">
                  Showing {((currentPage - 1) * insightsPerPage) + 1} to {Math.min(currentPage * insightsPerPage, filteredInsights.length)} of {filteredInsights.length}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="px-3 py-1 text-sm rounded-lg border border-gray-300 hover:bg-gray-50 disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage >= totalPages}
                    className="px-3 py-1 text-sm rounded-lg border border-gray-300 hover:bg-gray-50 disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  )
}

export default InsightsReview