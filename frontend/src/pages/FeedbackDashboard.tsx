import React, { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { LogOut, ThumbsUp, ThumbsDown, MessageSquare, Filter, BarChart3, ChevronDown, ChevronRight, Loader2, Tags } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../services/api'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'

interface Feedback {
  id: number
  user_id: number
  user_email?: string | null
  rating?: number | null
  feedback_type: 'thumbs_up' | 'thumbs_down'
  message?: string | null
  categories?: string[] | null
  chat_message_id?: number | null
  created_at: string
}

interface FeedbackStats {
  total: number
  positive: number
  negative: number
  positive_percentage: number
  negative_percentage: number
  recent_negative_count: number
  categories: Record<string, number>
}

interface ContextMessage {
  role: string
  content: string
  created_at: string
}

const CATEGORY_LABELS: Record<string, string> = {
  inaccurate: 'Inaccurate',
  incomplete: 'Incomplete',
  off_topic: 'Off topic',
  outdated: 'Outdated',
  too_long: 'Too long',
  other: 'Other',
}

const FeedbackDashboard: React.FC = () => {
  const [feedbackList, setFeedbackList] = useState<Feedback[]>([])
  const [stats, setStats] = useState<FeedbackStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'thumbs_up' | 'thumbs_down'>('all')
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [contextCache, setContextCache] = useState<Record<number, ContextMessage[]>>({})
  const [contextLoadingId, setContextLoadingId] = useState<number | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const feedbackPerPage = 10
  const { logout } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    loadFeedback()
  }, [])

  const loadFeedback = async () => {
    try {
      const [listResponse, statsResponse] = await Promise.all([
        api.get('/feedback/admin', { params: { limit: 200 } }),
        api.get('/feedback/stats'),
      ])
      setFeedbackList(listResponse.data.feedback || [])
      setStats(statsResponse.data)
    } catch (error) {
      console.error('Failed to load feedback:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const toggleExpand = async (feedback: Feedback) => {
    if (expandedId === feedback.id) {
      setExpandedId(null)
      return
    }
    setExpandedId(feedback.id)

    if (feedback.chat_message_id && contextCache[feedback.id] === undefined) {
      setContextLoadingId(feedback.id)
      try {
        const response = await api.get(`/feedback/${feedback.id}/context`)
        setContextCache(prev => ({ ...prev, [feedback.id]: response.data.messages || [] }))
      } catch (error) {
        console.error('Failed to load feedback context:', error)
        setContextCache(prev => ({ ...prev, [feedback.id]: [] }))
      } finally {
        setContextLoadingId(null)
      }
    }
  }

  const activeCategories = Object.keys(stats?.categories || {})

  const filteredFeedback = feedbackList.filter(f => {
    if (filter !== 'all' && f.feedback_type !== filter) return false
    if (categoryFilter && !(f.categories || []).includes(categoryFilter)) return false
    return true
  })

  const paginatedFeedback = filteredFeedback.slice(
    (currentPage - 1) * feedbackPerPage,
    currentPage * feedbackPerPage
  )

  const totalPages = Math.ceil(filteredFeedback.length / feedbackPerPage)

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-blue-50">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-md shadow-lg border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <Link to="/admin/dashboard" className="flex-shrink-0">
                <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                  Feedback Dashboard
                </h1>
              </Link>
            </div>
            <div className="flex items-center space-x-4">
              <Link
                to="/admin/dashboard"
                className="flex items-center px-4 py-2 rounded-lg text-sm font-medium text-gray-700 hover:text-gray-900 hover:bg-white/60 hover:shadow-md transition-all duration-200 border border-gray-200"
              >
                <BarChart3 className="h-4 w-4 mr-2" />
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
        {/* Stats Cards (last 30 days, from /feedback/stats) */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <Card className="bg-gradient-to-br from-green-500 to-emerald-600 text-white">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-green-100 text-sm font-medium">Thumbs Up (30d)</p>
                  <p className="text-3xl font-bold mt-1">{stats?.positive ?? 0}</p>
                  <p className="text-green-100 text-xs mt-1">{stats?.positive_percentage ?? 0}% of total</p>
                </div>
                <div className="p-3 bg-white/20 rounded-xl">
                  <ThumbsUp className="h-8 w-8" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-red-500 to-pink-600 text-white">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-red-100 text-sm font-medium">Thumbs Down (30d)</p>
                  <p className="text-3xl font-bold mt-1">{stats?.negative ?? 0}</p>
                  <p className="text-red-100 text-xs mt-1">{stats?.recent_negative_count ?? 0} in last 24h</p>
                </div>
                <div className="p-3 bg-white/20 rounded-xl">
                  <ThumbsDown className="h-8 w-8" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-blue-500 to-purple-600 text-white">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-blue-100 text-sm font-medium">Total (30d)</p>
                  <p className="text-3xl font-bold mt-1">{stats?.total ?? 0}</p>
                </div>
                <div className="p-3 bg-white/20 rounded-xl">
                  <MessageSquare className="h-8 w-8" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-amber-500 to-orange-600 text-white">
            <CardContent className="p-6">
              <div className="flex items-start justify-between">
                <div className="min-w-0">
                  <p className="text-amber-100 text-sm font-medium">Top Issues (30d)</p>
                  {activeCategories.length === 0 ? (
                    <p className="text-amber-100 text-sm mt-2">No categories yet</p>
                  ) : (
                    <div className="mt-2 space-y-1">
                      {Object.entries(stats?.categories || {})
                        .sort(([, a], [, b]) => b - a)
                        .slice(0, 3)
                        .map(([slug, count]) => (
                          <p key={slug} className="text-sm truncate">
                            <span className="font-semibold">{count}</span> {CATEGORY_LABELS[slug] || slug}
                          </p>
                        ))}
                    </div>
                  )}
                </div>
                <div className="p-3 bg-white/20 rounded-xl">
                  <Tags className="h-8 w-8" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-4 mb-6">
          <div className="flex items-center">
            <Filter className="h-5 w-5 text-gray-500 mr-2" />
            <span className="text-sm font-medium text-gray-700">Filter:</span>
          </div>
          <div className="flex gap-2">
            {(['all', 'thumbs_up', 'thumbs_down'] as const).map((f) => (
              <button
                key={f}
                onClick={() => { setFilter(f); setCurrentPage(1); }}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  filter === f
                    ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white shadow-md'
                    : 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-200'
                }`}
              >
                {f === 'all' ? 'All' : f === 'thumbs_up' ? 'Thumbs Up' : 'Thumbs Down'}
              </button>
            ))}
          </div>
          {activeCategories.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {activeCategories.map((slug) => (
                <button
                  key={slug}
                  onClick={() => {
                    setCategoryFilter(prev => (prev === slug ? null : slug))
                    setCurrentPage(1)
                  }}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all duration-200 ${
                    categoryFilter === slug
                      ? 'bg-amber-500 text-white border-amber-500 shadow-md'
                      : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  {CATEGORY_LABELS[slug] || slug}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Feedback List */}
        <Card>
          <CardHeader>
            <CardTitle>User Feedback</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="text-center py-8 text-gray-500">Loading feedback...</div>
            ) : filteredFeedback.length === 0 ? (
              <div className="text-center py-12">
                <div className="mx-auto w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
                  <MessageSquare className="h-8 w-8 text-gray-400" />
                </div>
                <p className="text-gray-600">No feedback yet</p>
              </div>
            ) : (
              <div className="space-y-4">
                {paginatedFeedback.map((feedback) => (
                  <div
                    key={feedback.id}
                    className="bg-gray-50 rounded-xl border border-gray-100"
                  >
                    <button
                      onClick={() => toggleExpand(feedback)}
                      className="w-full flex items-start gap-4 p-4 text-left hover:bg-gray-100 rounded-xl transition-colors"
                    >
                      <div className={`p-2 rounded-lg ${
                        feedback.feedback_type === 'thumbs_up'
                          ? 'bg-green-100 text-green-600'
                          : 'bg-red-100 text-red-600'
                      }`}>
                        {feedback.feedback_type === 'thumbs_up' ? (
                          <ThumbsUp className="h-5 w-5" />
                        ) : (
                          <ThumbsDown className="h-5 w-5" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-900 line-clamp-2">
                          {feedback.message || (
                            <span className="text-gray-400 italic">No comment</span>
                          )}
                        </p>
                        {(feedback.categories || []).length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {(feedback.categories || []).map((slug) => (
                              <span
                                key={slug}
                                className="px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-800 border border-amber-200"
                              >
                                {CATEGORY_LABELS[slug] || slug}
                              </span>
                            ))}
                          </div>
                        )}
                        <p className="text-xs text-gray-500 mt-1">
                          {new Date(feedback.created_at).toLocaleString()}
                          {feedback.user_email && ` • ${feedback.user_email}`}
                        </p>
                      </div>
                      <div className="text-gray-400 mt-1">
                        {expandedId === feedback.id ? (
                          <ChevronDown className="h-5 w-5" />
                        ) : (
                          <ChevronRight className="h-5 w-5" />
                        )}
                      </div>
                    </button>

                    {expandedId === feedback.id && (
                      <div className="px-4 pb-4 border-t border-gray-100 pt-3">
                        {feedback.message && (
                          <div className="mb-3">
                            <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Comment</p>
                            <p className="text-sm text-gray-800 whitespace-pre-wrap">{feedback.message}</p>
                          </div>
                        )}
                        <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Conversation Context</p>
                        {!feedback.chat_message_id ? (
                          <p className="text-sm text-gray-400 italic">
                            No conversation context available for this feedback.
                          </p>
                        ) : contextLoadingId === feedback.id ? (
                          <div className="flex items-center gap-2 text-sm text-gray-500 py-2">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Loading context...
                          </div>
                        ) : (contextCache[feedback.id] || []).length === 0 ? (
                          <p className="text-sm text-gray-400 italic">
                            No conversation context available for this feedback.
                          </p>
                        ) : (
                          <div className="space-y-2">
                            {(contextCache[feedback.id] || []).map((m, i) => (
                              <div
                                key={i}
                                className={`p-3 rounded-lg text-sm ${
                                  m.role === 'user'
                                    ? 'bg-blue-50 border border-blue-100 text-blue-900'
                                    : 'bg-white border border-gray-200 text-gray-800'
                                }`}
                              >
                                <p className="text-xs font-semibold text-gray-500 mb-1">
                                  {m.role === 'user' ? 'User' : 'Assistant'}
                                </p>
                                <p className="whitespace-pre-wrap line-clamp-6">{m.content}</p>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-6 pt-4 border-t border-gray-200">
                <div className="text-sm text-gray-600">
                  Showing {((currentPage - 1) * feedbackPerPage) + 1} to {Math.min(currentPage * feedbackPerPage, filteredFeedback.length)} of {filteredFeedback.length}
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

export default FeedbackDashboard
