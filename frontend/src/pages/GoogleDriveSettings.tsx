import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Badge } from '../components/ui/badge'
import { Alert, AlertDescription } from '../components/ui/alert'
import { Loader2, RefreshCw, Unlink, ExternalLink, FolderOpen, CheckCircle, AlertCircle, FileText, ChevronRight } from 'lucide-react'

import { api } from '../services/api'

interface SyncFile {
  filename: string
  size: number
  modified: string
}

interface DriveSync {
  file_count: number
  last_sync: string | null
  running: boolean
  error: string | null
  needs_reconnect?: boolean
}

interface Pipeline {
  running: boolean
  last_update: string | null
  error: string | null
}

interface DriveStatus {
  connected: boolean
  root_folder_id: string | null
  sync: DriveSync
  files: SyncFile[]
  pipeline: Pipeline
}

interface FolderItem {
  id: string
  name: string
}

export default function GoogleDriveSettings() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<DriveStatus | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSyncing, setIsSyncing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [folders, setFolders] = useState<FolderItem[]>([])
  const [loadingFolders, setLoadingFolders] = useState(false)
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null)
  const [folderStack, setFolderStack] = useState<FolderItem[]>([])

  const loadStatus = useCallback(async () => {
    try {
      const token = localStorage.getItem('token')
      const response = await api.get('/drive/status', {
        headers: { Authorization: `Bearer ${token}` }
      })
      setStatus(response.data)
      setError(null)
    } catch (e) {
      setError('Failed to load Drive status')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadStatus()
    const interval = setInterval(loadStatus, 10000)
    return () => clearInterval(interval)
  }, [loadStatus])

  const handleConnect = async () => {
    try {
      const token = localStorage.getItem('token')
      const response = await api.get('/drive/auth-url', {
        headers: { Authorization: `Bearer ${token}` }
      })
      const { url } = response.data

      const popup = window.open(url, 'google-oauth', 'width=600,height=700')
      if (!popup) {
        setError('Popup blocked. Please allow popups for this site.')
        return
      }

      const expectedOrigin = new URL(import.meta.env.VITE_API_URL || window.location.origin).origin
      const handler = (event: MessageEvent) => {
        if (event.origin !== expectedOrigin) return
        if (event.data?.type === 'drive-connected') {
          window.removeEventListener('message', handler)
          loadStatus().then(() => {
            loadFolders('root')
          })
        }
      }
      window.addEventListener('message', handler)
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Failed to get auth URL')
    }
  }

  const loadFolders = async (parentId: string | null) => {
    setLoadingFolders(true)
    try {
      const token = localStorage.getItem('token')
      const params = parentId ? { parent_id: parentId } : {}
      const response = await api.get('/drive/folders', {
        params,
        headers: { Authorization: `Bearer ${token}` }
      })
      setFolders(response.data.folders || [])
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Failed to list folders')
    } finally {
      setLoadingFolders(false)
    }
  }

  const handleFolderClick = async (folder: FolderItem) => {
    setSelectedFolder(folder.id)
    try {
      const token = localStorage.getItem('token')
      await api.patch('/drive/root-folder', null, {
        params: { folder_id: folder.id, folder_name: folder.name },
        headers: { Authorization: `Bearer ${token}` }
      })
      loadStatus()
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Failed to set root folder')
    }
  }

  const handleEnterFolder = (folder: FolderItem) => {
    setFolderStack(prev => [...prev, folder])
    loadFolders(folder.id)
  }

  const handleBack = () => {
    const newStack = [...folderStack]
    newStack.pop()
    setFolderStack(newStack)
    const parent = newStack.length > 0 ? newStack[newStack.length - 1].id : 'root'
    loadFolders(parent)
  }

  const handleSyncNow = async () => {
    setIsSyncing(true)
    try {
      const token = localStorage.getItem('token')
      await api.post('/drive/sync-now', {}, {
        headers: { Authorization: `Bearer ${token}` }
      })
      setTimeout(loadStatus, 2000)
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Sync failed')
    } finally {
      setIsSyncing(false)
    }
  }

  const handleDisconnect = async () => {
    if (!confirm('Disconnect Google Drive? This will stop all syncing.')) return
    try {
      const token = localStorage.getItem('token')
      await api.post('/drive/disconnect', {}, {
        headers: { Authorization: `Bearer ${token}` }
      })
      setFolders([])
      setFolderStack([])
      loadStatus()
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Disconnect failed')
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  const syncStatus = status?.sync
  const pipeline = status?.pipeline
  const connected = status?.connected ?? false
  const hasRootFolder = !!status?.root_folder_id

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={() => navigate('/admin/dashboard')}>
              ← Back
            </Button>
            <div>
              <h1 className="text-3xl font-bold">Knowledge Sources</h1>
              <p className="text-muted-foreground">Connect Google Drive to index documents</p>
            </div>
          </div>
        </div>

        {error && (
          <Alert className="mb-6 border-red-200 bg-red-50">
            <AlertCircle className="h-4 w-4 text-red-600" />
            <AlertDescription className="text-red-700">{error}</AlertDescription>
          </Alert>
        )}

        {syncStatus?.needs_reconnect && (
          <Alert className="mb-6 border-amber-200 bg-amber-50">
            <AlertCircle className="h-4 w-4 text-amber-600" />
            <AlertDescription className="text-amber-800 flex items-center justify-between gap-4">
              <span>Google Drive authorization has expired. Reconnect to resume syncing.</span>
              <Button size="sm" onClick={handleConnect}>
                <ExternalLink className="h-4 w-4 mr-2" />
                Reconnect
              </Button>
            </AlertDescription>
          </Alert>
        )}

        {/* Connection Card */}
        <Card className="mb-6">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <FolderOpen className="h-5 w-5" />
                  Google Drive
                </CardTitle>
                <CardDescription>
                  Sync documents from Google Drive to the knowledge graph
                </CardDescription>
              </div>
              <Badge variant={connected ? "default" : "secondary"}>
                {connected ? 'Connected' : 'Not Connected'}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            {!connected ? (
              <div className="text-center py-8">
                <p className="text-muted-foreground mb-4">
                  Connect your Google Drive to sync documents for AI-powered search.
                </p>
                <p className="text-xs text-muted-foreground mb-6">
                  Uses read-only access. After connecting, you'll select which folder to index.
                </p>
                <Button onClick={handleConnect} size="lg">
                  <ExternalLink className="h-4 w-4 mr-2" />
                  Connect Google Drive
                </Button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <CheckCircle className="h-4 w-4 text-green-600" />
                    <span className="text-sm">Connected</span>
                    {status?.root_folder_id && (
                      <Badge variant="outline" className="text-xs">
                        Folder selected
                      </Badge>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleSyncNow}
                      disabled={isSyncing || !hasRootFolder}
                    >
                      {isSyncing ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-1" />
                      ) : (
                        <RefreshCw className="h-4 w-4 mr-1" />
                      )}
                      Sync Now
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleDisconnect}
                      className="text-red-600"
                    >
                      <Unlink className="h-4 w-4 mr-1" />
                      Disconnect
                    </Button>
                  </div>
                </div>

                {/* Folder Selection */}
                {!hasRootFolder && (
                  <div className="border rounded-lg p-4 bg-muted/30">
                    <h4 className="font-medium mb-2">Select a folder to index</h4>
                    <p className="text-sm text-muted-foreground mb-3">
                      Only files inside the selected folder will be synced.
                    </p>

                    {folderStack.length > 0 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleBack}
                        className="mb-2"
                      >
                        ← Back to {folderStack.length > 1 ? folderStack[folderStack.length - 2].name : 'root'}
                      </Button>
                    )}

                    {loadingFolders ? (
                      <div className="flex items-center gap-2 py-4">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span className="text-sm text-muted-foreground">Loading folders...</span>
                      </div>
                    ) : folders.length === 0 ? (
                      <div className="text-center py-4">
                        <p className="text-sm text-muted-foreground">No folders found.</p>
                        <Button
                          variant="link"
                          size="sm"
                          onClick={() => loadFolders('root')}
                          className="mt-1"
                        >
                          Refresh
                        </Button>
                      </div>
                    ) : (
                      <div className="border rounded-lg divide-y max-h-64 overflow-y-auto">
                        {folders.map((f) => (
                          <div
                            key={f.id}
                            className="flex items-center justify-between px-3 py-2 hover:bg-muted transition-colors"
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <FolderOpen className="h-4 w-4 text-blue-500 shrink-0" />
                              <span className="text-sm truncate">{f.name}</span>
                            </div>
                            <div className="flex gap-1 shrink-0">
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => handleEnterFolder(f)}
                                title="Open folder"
                              >
                                <ChevronRight className="h-4 w-4" />
                              </Button>
                              <Button
                                size="sm"
                                onClick={() => handleFolderClick(f)}
                              >
                                Select
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {selectedFolder && (
                      <p className="text-xs text-green-600 mt-2">
                        ✓ Folder selected. Sync will start automatically.
                      </p>
                    )}
                  </div>
                )}

                {/* Already has root folder */}
                {hasRootFolder && (
                  <div className="flex items-center justify-between bg-green-50 border border-green-200 rounded-lg px-4 py-3">
                    <div className="flex items-center gap-2">
                      <FolderOpen className="h-4 w-4 text-green-600" />
                      <span className="text-sm text-green-800">
                        Indexing folder: <strong>{status?.root_folder_id}</strong>
                      </span>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        loadFolders('root')
                        setFolderStack([])
                      }}
                    >
                      Change folder
                    </Button>
                  </div>
                )}

                {/* Stats */}
                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div className="bg-muted rounded-lg p-3">
                    <div className="text-2xl font-bold">{syncStatus?.file_count ?? 0}</div>
                    <div className="text-muted-foreground">Files cached</div>
                  </div>
                  <div className="bg-muted rounded-lg p-3">
                    <div className="text-2xl font-bold">
                      {syncStatus?.running ? (
                        <Loader2 className="h-5 w-5 animate-spin inline" />
                      ) : syncStatus?.error ? (
                        <span className="text-red-600">Error</span>
                      ) : syncStatus?.last_sync ? (
                        new Date(syncStatus.last_sync).toLocaleTimeString()
                      ) : (
                        'Never'
                      )}
                    </div>
                    <div className="text-muted-foreground">Last sync</div>
                  </div>
                  <div className="bg-muted rounded-lg p-3">
                    <div className="text-2xl font-bold">
                      {pipeline?.running ? (
                        <Loader2 className="h-5 w-5 animate-spin inline" />
                      ) : pipeline?.last_update ? (
                        new Date(pipeline.last_update).toLocaleTimeString()
                      ) : (
                        'Idle'
                      )}
                    </div>
                    <div className="text-muted-foreground">Index pipeline</div>
                  </div>
                </div>

                {/* Synced files list */}
                {status?.files && status.files.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium mb-2">Cached Files</h4>
                    <div className="border rounded-lg divide-y max-h-48 overflow-y-auto">
                      {status.files.map((file, idx) => (
                        <div key={idx} className="flex items-center gap-2 px-3 py-2 text-sm">
                          <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                          <span className="truncate">{file.filename}</span>
                          <span className="text-xs text-muted-foreground ml-auto">
                            {(file.size / 1024).toFixed(0)} KB
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Pipeline Status Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <RefreshCw className="h-4 w-4" />
              Index Pipeline
            </CardTitle>
            <CardDescription>
              Documents are automatically chunked, embedded, and added to the Neo4j knowledge graph
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Status</span>
                <span>{pipeline?.running ? 'Running' : 'Idle'}</span>
              </div>
              {pipeline?.last_update && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Last update</span>
                  <span>{new Date(pipeline.last_update).toLocaleString()}</span>
                </div>
              )}
              {pipeline?.error && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Error</span>
                  <span className="text-red-600">{pipeline.error}</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
