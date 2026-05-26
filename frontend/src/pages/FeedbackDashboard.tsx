import React, { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { LogOut, ThumbsUp, ThumbsDown, MessageSquare, Filter, BarChart3, X, User, Clock } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../services/api'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'

interface Feedback {
  id: number
  user_id: number
  rating?: number | null
  feedback_type: 'thumbs_up' | 'thumbs_down'
  message?: string | null
  chat_message_id?: number | null
  user_email?: string | null
  message_content?: string | null
  created_at: string
}

interface FeedbackContext {
  feedback: Feedback
  messages: Array<{
    role: string
    content: string
    created_at: string
  }>
}

const FeedbackDashboard: React.FC = () => {
  const [feedbackList, setFeedbackList] = useState<Feedback[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'thumbs_up' | 'thumbs_down'>('all')
  const [currentPage, setCurrentPage] = useState(1)
  const [selectedContext, setSelectedContext] = useState<FeedbackContext | null>(null)
  const [contextLoading, setContextLoading] = useState(false)
  const feedbackPerPage = 10
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    loadFeedback()
  }, [])

  const loadFeedback = async () => {
    try {
      const response = await api.get('/feedback/admin')
      setFeedbackList(response.data.feedback || [])
    } catch (error) {
      console.error('Failed to load feedback:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const loadFeedbackContext = async (feedbackId: number) => {
    setContextLoading(true)
    try {
      const response = await api.get(`/feedback/${feedbackId}/context`)
      setSelectedContext(response.data)
    } catch (error) {
      console.error('Failed to load feedback context:', error)
    } finally {
      setContextLoading(false)
    }
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const filteredFeedback = feedbackList.filter(f => 
    filter === 'all' ? true : f.feedback_type === filter
  )

  const paginatedFeedback = filteredFeedback.slice(
    (currentPage - 1) * feedbackPerPage,
    currentPage * feedbackPerPage
  )

  const totalPages = Math.ceil(filteredFeedback.length / feedbackPerPage)
  const thumbsUpCount = feedbackList.filter(f => f.feedback_type === 'thumbs_up').length
  const thumbsDownCount = feedbackList.filter(f => f.feedback_type === 'thumbs_down').length

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
        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card className="bg-gradient-to-br from-green-500 to-emerald-600 text-white">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-green-100 text-sm font-medium">Thumbs Up</p>
                  <p className="text-3xl font-bold mt-1">{thumbsUpCount}</p>
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
                  <p className="text-red-100 text-sm font-medium">Thumbs Down</p>
                  <p className="text-3xl font-bold mt-1">{thumbsDownCount}</p>
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
                  <p className="text-blue-100 text-sm font-medium">Total Feedback</p>
                  <p className="text-3xl font-bold mt-1">{feedbackList.length}</p>
                </div>
                <div className="p-3 bg-white/20 rounded-xl">
                  <MessageSquare className="h-8 w-8" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filter */}
        <div className="flex items-center gap-4 mb-6">
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
                    className="flex items-start gap-4 p-4 bg-gray-50 rounded-xl border border-gray-100 hover:bg-gray-100 cursor-pointer transition-colors"
                    onClick={() => loadFeedbackContext(feedback.id)}
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
                        {feedback.message_content || feedback.message || 'No message captured'}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {new Date(feedback.created_at).toLocaleString()}
                        {feedback.user_email && ` • ${feedback.user_email}`}
                      </p>
                    </div>
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

      {selectedContext && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex min-h-screen items-center justify-center p-4">
            <div className="fixed inset-0 bg-slate-900/70 backdrop-blur-sm" onClick={() => setSelectedContext(null)} />
            <div className="relative z-10 w-full max-w-2xl overflow-hidden rounded-3xl border border-white/40 bg-white shadow-2xl">
              <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
                <div>
                  <h2 className="text-lg font-semibold">Feedback Details</h2>
                  <p className="text-sm text-slate-500">Chat context for this feedback</p>
                </div>
                <button
                  type="button"
                  className="rounded-full p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                  onClick={() => setSelectedContext(null)}
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="px-6 py-4">
                {contextLoading ? (
                  <div className="text-center py-8 text-gray-500">Loading context...</div>
                ) : (
                  <>
                    <div className="mb-4 flex items-center gap-4 rounded-xl bg-slate-50 p-4">
                      <div className={`p-2 rounded-lg ${
                        selectedContext.feedback.feedback_type === 'thumbs_up' 
                          ? 'bg-green-100 text-green-600' 
                          : 'bg-red-100 text-red-600'
                      }`}>
                        {selectedContext.feedback.feedback_type === 'thumbs_up' ? (
                          <ThumbsUp className="h-5 w-5" />
                        ) : (
                          <ThumbsDown className="h-5 w-5" />
                        )}
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2 text-sm">
                          <User className="h-4 w-4 text-slate-500" />
                          <span className="font-medium text-slate-900">
                            {selectedContext.feedback.user_email || 'Unknown User'}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-slate-500 mt-1">
                          <Clock className="h-3 w-3" />
                          {new Date(selectedContext.feedback.created_at).toLocaleString()}
                        </div>
                      </div>
                    </div>

                    <div className="space-y-3">
                      <h3 className="text-sm font-semibold text-slate-700">Last 5 Messages</h3>
                      {selectedContext.messages.length === 0 ? (
                        <p className="text-sm text-slate-500">No chat messages found</p>
                      ) : (
                        <div className="space-y-2 max-h-80 overflow-y-auto">
                          {selectedContext.messages.slice(-5).map((msg, idx) => (
                            <div
                              key={idx}
                              className={`p-3 rounded-lg text-sm ${
                                msg.role === 'user'
                                  ? 'bg-blue-50 text-blue-900 ml-8'
                                  : 'bg-slate-100 text-slate-900 mr-8'
                              }`}
                            >
                              <div className="flex items-center justify-between gap-2 mb-1">
                                <span className="text-xs font-medium text-slate-600">
                                  {msg.role === 'user' ? 'User' : 'Assistant'}
                                </span>
                                <span className="text-xs text-slate-400">
                                  {new Date(msg.created_at).toLocaleString()}
                                </span>
                              </div>
                              <p className="whitespace-pre-wrap">{msg.content}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default FeedbackDashboard
