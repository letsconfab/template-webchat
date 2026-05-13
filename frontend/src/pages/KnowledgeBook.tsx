import React, { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { LogOut, BookOpen, Plus, FileText, Clock, Upload, FileEdit, RefreshCw, File, X, Folder, FolderOpen, ChevronRight, ChevronDown, Eye, History } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../services/api'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Button } from '../components/ui/button'

interface WikiPage {
  id: number
  title: string
  content?: string
  source_type: 'upload' | 'insight' | 'note' | 'folder'
  parent_id?: number
  is_folder: boolean
  created_at: string
  updated_at: string
  version: number
}

interface TreeNode extends WikiPage {
  children: TreeNode[]
}

const TreeItem: React.FC<{ 
  node: TreeNode; 
  level: number; 
  selectedPage: WikiPage | null; 
  onSelect: (page: WikiPage) => void;
  onDelete: (id: number) => void;
}> = ({ node, level, selectedPage, onSelect, onDelete }) => {
  const [expanded, setExpanded] = useState(false)

  return (
    <div>
      <div
        className={`flex items-center gap-1 py-2 px-2 rounded-lg hover:bg-gray-100 cursor-pointer ${
          selectedPage?.id === node.id ? 'bg-blue-50 border border-blue-200' : ''
        }`}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
        onClick={() => {
          if (node.is_folder) {
            setExpanded(!expanded)
          }
          onSelect(node)
        }}
      >
        {node.is_folder ? (
          <>
            {expanded ? (
              <ChevronDown className="h-4 w-4 text-gray-400" />
            ) : (
              <ChevronRight className="h-4 w-4 text-gray-400" />
            )}
            {expanded ? (
              <FolderOpen className="h-4 w-4 text-blue-500" />
            ) : (
              <Folder className="h-4 w-4 text-blue-500" />
            )}
          </>
        ) : (
          <>
            <div className="w-4" />
            <FileText className="h-4 w-4 text-gray-500" />
          </>
        )}
        <span className="flex-1 text-sm text-gray-700 truncate">{node.title}</span>
        <button
          onClick={(e) => {
            e.stopPropagation()
            onDelete(node.id)
          }}
          className="text-red-400 hover:text-red-600 p-1 opacity-0 hover:opacity-100"
        >
          <X className="h-3 w-3" />
        </button>
      </div>
      {node.is_folder && expanded && node.children.map(child => (
        <TreeItem key={child.id} node={child} level={level + 1} selectedPage={selectedPage} onSelect={onSelect} onDelete={onDelete} />
      ))}
    </div>
  )
}

const KnowledgeBook: React.FC = () => {
  const [inputs, setInputs] = useState<WikiPage[]>([])
  const [outputs, setOutputs] = useState<WikiPage[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [selectedPage, setSelectedPage] = useState<WikiPage | null>(null)
const [showAddInputModal, setShowAddInputModal] = useState(false)
  const [showHistoryModal, setShowHistoryModal] = useState(false)
  const [addInputTab, setAddInputTab] = useState<'note' | 'document'>('note')
  const [noteContent, setNoteContent] = useState('')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    loadWikiPages()
  }, [])

  const loadWikiPages = async () => {
    try {
      const response = await api.get('/wiki')
      const data = response.data
      setInputs(data.inputs || [])
      setOutputs(data.outputs || [])
    } catch (error) {
      console.error('Failed to load wiki pages:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleDelete = async (pageId: number) => {
    if (!confirm('Are you sure you want to delete this?')) return
    try {
      await api.delete(`/wiki/${pageId}`)
      if (selectedPage?.id === pageId) setSelectedPage(null)
      loadWikiPages()
    } catch (error) {
      console.error('Failed to delete:', error)
    }
  }

  const buildTree = (pages: WikiPage[]): TreeNode[] => {
    const map: { [key: number]: TreeNode } = {}
    const roots: TreeNode[] = []

    pages.forEach(p => {
      map[p.id] = { ...p, children: [] }
    })

    pages.forEach(p => {
      if (p.parent_id && map[p.parent_id]) {
        map[p.parent_id].children.push(map[p.id])
      } else {
        roots.push(map[p.id])
      }
    })

    return roots
  }

  const handleUploadDocument = async () => {
    if (!uploadFile) return
    setIsSubmitting(true)
    try {
      const formData = new FormData()
      formData.append('file', uploadFile)
      await api.post('/knowledge/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setShowAddInputModal(false)
      setUploadFile(null)
      loadWikiPages()
    } catch (error) {
      console.error('Failed to upload document:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleCreateNote = async () => {
    console.log('handleCreateNote called, noteContent:', noteContent)
    if (!noteContent.trim()) {
      console.log('Empty note, returning')
      return
    }
    
    setIsSubmitting(true)
    try {
      console.log('Sending POST to /wiki with content:', noteContent.substring(0, 50))
      const response = await api.post('/wiki', {
        content: noteContent,
        source_type: 'note'
      })
      console.log('Note created successfully:', response.data)
      setShowAddInputModal(false)
      setNoteContent('')
      // Refresh after delay to ensure auto-merge completes
      setTimeout(() => {
        // Clear selection and reload to show new content
        setSelectedPage(null)
        loadWikiPages().then(() => {
          // Select the first output after reload
          setTimeout(() => {
            const firstOutput = [...outputs].sort((a, b) => 
              new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
            )[0]
            if (firstOutput) setSelectedPage(firstOutput)
          }, 100)
        })
      }, 1000)
    } catch (error: any) {
      console.error('Failed to create note:', error)
      if (error.response) {
        console.error('Error response:', error.response.status, error.response.data)
        alert(`Error: ${error.response.data?.detail || error.response.statusText}`)
      } else if (error.request) {
        console.error('No response received')
        alert('Network error - no response from server')
      } else {
        console.error('Error:', error.message)
        alert(`Error: ${error.message}`)
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-blue-50">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-md shadow-lg border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <Link to="/admin/dashboard" className="flex-shrink-0">
                <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                  Knowledge Book
                </h1>
              </Link>
            </div>
            <div className="flex items-center space-x-4">
              
              <Link
                to="/admin/dashboard"
                className="flex items-center px-4 py-2 rounded-lg text-sm font-medium text-gray-700 hover:text-gray-900 hover:bg-white/60 hover:shadow-md transition-all duration-200 border border-gray-200"
              >
                <BookOpen className="h-4 w-4 mr-2" />
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
        {/* Content Area */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Wiki/Outputs List */}
          <Card className="lg:col-span-1">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center">
                <BookOpen className="h-5 w-5 mr-2 text-blue-600" />
                Contents
              </CardTitle>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => setShowHistoryModal(true)}>
                  <History className="h-4 w-4 mr-1" /> History
                </Button>
                <Button size="sm" onClick={() => {
                  setShowAddInputModal(true)
                  setAddInputTab('note')
                }} className="bg-green-600 hover:bg-green-700">
                  + Add
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {outputs.length === 0 ? (
                <div className="text-center py-8">
                  <div className="mx-auto w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mb-3">
                    <BookOpen className="h-6 w-6 text-gray-400" />
                  </div>
                  <p className="text-sm text-gray-600">No contents yet</p>
                  <p className="text-xs text-gray-500 mt-1">Add notes to create content</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {buildTree(outputs).map((node) => (
                    <TreeItem key={node.id} node={node} level={0} selectedPage={selectedPage} onSelect={setSelectedPage} onDelete={handleDelete} />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Page Content */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <div className="flex items-center">
                  <FileText className="h-5 w-5 mr-2 text-gray-500" />
                  {selectedPage ? selectedPage.title : 'Select a page'}
                </div>
                {selectedPage && (
                  <div className="flex items-center gap-4">
                    <span className="text-sm text-gray-500">
                      Last updated: {new Date(selectedPage.updated_at).toLocaleDateString()}
                    </span>
                    <button
                      onClick={() => handleDelete(selectedPage.id)}
                      className="text-red-500 hover:text-red-700 text-sm flex items-center gap-1"
                    >
                      <X className="h-4 w-4" /> Delete
                    </button>
                  </div>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {selectedPage ? (
                <div className="prose prose-sm max-w-none">
                  <div className="text-gray-700 whitespace-pre-wrap">{selectedPage.content}</div>
                </div>
              ) : (
                <div className="text-center py-16 text-gray-500">
                  <div className="mx-auto w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
                    <FileText className="h-8 w-8 text-gray-400" />
                  </div>
                  <p>Select a page to view its content</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </main>

      {/* Add Input Modal */}
      {showAddInputModal && (
        <div className="fixed z-50 inset-0 overflow-y-auto">
          <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
            <div className="fixed inset-0 bg-gray-900/75 backdrop-blur-sm" aria-hidden="true"></div>

            <div className="inline-block align-bottom bg-white rounded-2xl text-left overflow-hidden shadow-2xl transform transition-all sm:my-8 sm:align-middle sm:max-w-2xl sm:w-full max-h-[90vh]">
              <div className="bg-gradient-to-br from-white to-green-50/30 px-6 pt-6 pb-4">
                <h3 className="text-xl font-bold text-gray-900 flex items-center justify-between">
                  <div className="flex items-center">
                    <FileEdit className="h-5 w-5 mr-2 text-green-600" />
                    Inputs
                  </div>
                  <button
                    onClick={() => setAddInputTab(addInputTab === 'note' ? 'document' : 'note')}
                    disabled={isSubmitting}
                    className={`text-sm ${isSubmitting ? 'text-gray-400 cursor-not-allowed' : 'text-blue-600 hover:text-blue-800'}`}
                  >
                    {addInputTab === 'note' ? '+ Document' : '+ Note'}
                  </button>
                </h3>
              </div>

              <div className="px-6 pb-6 overflow-y-auto max-h-[60vh]">
                {addInputTab === 'note' ? (
                  <>
                    <div className="mb-4">
                      <label className="block text-sm font-medium text-gray-700 mb-2">Content (Markdown)</label>
                      <textarea
                        value={noteContent}
                        onChange={(e) => setNoteContent(e.target.value)}
                        rows={8}
                        className="w-full border border-gray-300 rounded-xl py-3 px-4 focus:outline-none focus:ring-2 focus:ring-green-500 font-mono text-sm"
                        placeholder="Write your note in markdown..."
                      />
                    </div>
                  </>
                ) : (
                  <>
                    <div className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:border-blue-400 transition-colors">
                      <input
                        type="file"
                        id="file-upload"
                        className="hidden"
                        accept=".pdf,.docx,.doc,.txt,.md"
                        onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                      />
                      <label htmlFor="file-upload" className="cursor-pointer">
                        <Upload className="h-12 w-12 text-gray-400 mx-auto mb-3" />
                        <p className="text-sm text-gray-600 font-medium">
                          {uploadFile ? uploadFile.name : 'Click to upload a document'}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">PDF, DOCX, TXT, MD</p>
                      </label>
                      {uploadFile && (
                        <button
                          onClick={() => setUploadFile(null)}
                          className="mt-3 text-red-500 text-sm flex items-center justify-center"
                        >
                          <X className="h-4 w-4 mr-1" /> Remove
                        </button>
                      )}
                    </div>
                  </>
                )}
              </div>

              <div className="bg-gray-50 px-6 py-4 sm:px-6 sm:flex sm:flex-row-reverse">
                {addInputTab === 'note' ? (
                  <Button
                    onClick={handleCreateNote}
                    disabled={isSubmitting || !noteContent.trim()}
                    className="w-full bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700 sm:ml-3 sm:w-auto"
                  >
                    {isSubmitting ? 'Saving...' : 'Save Note'}
                  </Button>
                ) : (
                  <Button
                    onClick={handleUploadDocument}
                    disabled={isSubmitting || !uploadFile}
                    className="w-full bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 sm:ml-3 sm:w-auto"
                  >
                    {isSubmitting ? 'Uploading...' : 'Upload Document'}
                  </Button>
                )}
                <Button
                  variant="outline"
                  onClick={() => { 
                    setShowAddInputModal(false); 
                    setNoteContent(''); 
                    setUploadFile(null);
                  }}
                  className="mt-3 w-full sm:mt-0 sm:ml-3 sm:w-auto"
                >
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* History Modal */}
      {showHistoryModal && (
        <div className="fixed z-50 inset-0 overflow-y-auto">
          <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
            <div className="fixed inset-0 bg-gray-900/75 backdrop-blur-sm" aria-hidden="true"></div>

            <div className="inline-block align-bottom bg-white rounded-2xl text-left overflow-hidden shadow-2xl transform transition-all sm:my-8 sm:align-middle sm:max-w-2xl sm:w-full max-h-[80vh]">
              <div className="bg-gradient-to-br from-white to-gray-50/30 px-6 pt-6 pb-4">
                <h3 className="text-xl font-bold text-gray-900 flex items-center">
                  <History className="h-5 w-5 mr-2 text-gray-600" />
                  Input History
                </h3>
              </div>

              <div className="px-6 pb-6 overflow-y-auto max-h-[60vh]">
                {inputs.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">No inputs yet</div>
                ) : (
                  <div className="space-y-3">
                    {[...inputs].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).map((input) => (
                      <div key={input.id} className="p-4 bg-gray-50 rounded-lg border border-gray-200">
                        <div className="text-sm text-gray-500 mb-2">
                          {new Date(input.created_at).toLocaleString()}
                        </div>
                        <div className="text-gray-800 whitespace-pre-wrap font-mono text-sm">{input.content}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="bg-gray-50 px-6 py-4 sm:px-6">
                <Button variant="outline" onClick={() => setShowHistoryModal(false)} className="w-full">
                  Close
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default KnowledgeBook