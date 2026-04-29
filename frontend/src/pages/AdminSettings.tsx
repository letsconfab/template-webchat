import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Textarea } from '../components/ui/textarea'
import { Switch } from '../components/ui/switch'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Alert, AlertDescription } from '../components/ui/alert'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'
import { Badge } from '../components/ui/badge'
import { Loader2, Save, RotateCcw, CheckCircle, AlertCircle, Mail, Globe, Shield, Settings, Bot, Database, Upload, RefreshCw } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

interface SystemSettings {
  id: number
  app_name: string
  app_description: string
  company_name: string
  smtp_server: string
  smtp_port: number
  smtp_username: string
  smtp_password: string
  from_email: string
  use_tls: boolean
  frontend_url: string
  session_timeout_minutes: number
  max_login_attempts: number
  email_notifications_enabled: boolean
  user_registration_enabled: boolean
  // LLM Configuration
  llm_provider: string
  llm_model: string
  llm_api_key: string
  // Foundry Configuration
  foundry_url: string
  foundry_confab_id: number | null
  is_configured: boolean
  configured_at: string
  configured_by: string
  created_at: string
  updated_at: string
}

export default function AdminSettings() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isSyncing, setIsSyncing] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [settings, setSettings] = useState<SystemSettings | null>(null)
  const [hasChanges, setHasChanges] = useState(false)
  const [knowledgeStatus, setKnowledgeStatus] = useState<{document_count: number, llm_provider: string, llm_model: string} | null>(null)
  const [activeTab, setActiveTab] = useState('basic')

  useEffect(() => {
    if (!user || user.role !== 'admin') {
      navigate('/admin/login')
      return
    }
    loadSettings()
    loadKnowledgeStatus()
  }, [user, navigate])

  const loadSettings = async () => {
    try {
      const response = await fetch('/api/settings/current', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      })

      if (!response.ok) {
        throw new Error('Failed to load settings')
      }

      const data = await response.json()
      setSettings(data)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Failed to load settings')
    } finally {
      setIsLoading(false)
    }
  }

  const loadKnowledgeStatus = async () => {
    try {
      const response = await fetch('/api/knowledge/status')
      if (response.ok) {
        const data = await response.json()
        setKnowledgeStatus(data)
      }
    } catch (error) {
      console.error('Failed to load knowledge status:', error)
    }
  }

  const handleSyncFromFoundry = async () => {
    if (!settings?.foundry_url || !settings.foundry_confab_id) {
      setError('Please configure Foundry URL and Confab ID first')
      return
    }
    
    setIsSyncing(true)
    setError(null)
    setSuccess(null)
    
    try {
      // For now, we need the user's Foundry token - in production this would be stored
      // For demo, we'll show an alert asking for token
      const token = prompt('Please enter your Foundry access token:')
      if (!token) {
        setIsSyncing(false)
        return
      }
      
      const response = await fetch('/api/knowledge/sync-foundry', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          foundry_url: settings.foundry_url,
          access_token: token,
          confab_id: settings.foundry_confab_id
        })
      })
      
      if (!response.ok) {
        throw new Error('Failed to sync from Foundry')
      }
      
      const result = await response.json()
      setSuccess(`Synced ${result.synced_count} documents from Foundry`)
      loadKnowledgeStatus()
    } catch (error: any) {
      setError(error.message || 'Failed to sync from Foundry')
    } finally {
      setIsSyncing(false)
    }
  }

  const handleUploadDocument = async () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.pdf,.doc,.docx,.txt,.csv,.xlsx'
    
    input.onchange = async (e: any) => {
      const file = e.target.files[0]
      if (!file) return
      
      setIsUploading(true)
      setError(null)
      setSuccess(null)
      
      try {
        const reader = new FileReader()
        reader.readAsDataURL(file)
        reader.onload = async () => {
          const base64 = (reader.result as string).split(',')[1]
          
          const response = await fetch('/api/knowledge/documents', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${localStorage.getItem('token')}`
            },
            body: JSON.stringify({
              filename: file.name,
              content_base64: base64
            })
          })
          
          if (!response.ok) {
            throw new Error('Failed to upload document')
          }
          
          setSuccess(`Uploaded: ${file.name}`)
          loadKnowledgeStatus()
          setIsUploading(false)
        }
      } catch (error: any) {
        setError(error.message || 'Failed to upload document')
        setIsUploading(false)
      }
    }
    
    input.click()
  }

  const handleInputChange = (field: keyof SystemSettings, value: string | number | boolean) => {
    if (!settings) return
    
    setSettings(prev => ({
      ...prev!,
      [field]: value
    }))
    setHasChanges(true)
  }

  const handleSave = async () => {
    if (!settings) return

    setIsSaving(true)
    setError(null)
    setSuccess(null)

    try {
      const response = await fetch('/api/settings/current', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify(settings),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to save settings')
      }

      const updatedSettings = await response.json()
      setSettings(updatedSettings)
      setHasChanges(false)
      setSuccess('Settings saved successfully!')
      
      setTimeout(() => setSuccess(null), 3000)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Failed to save settings')
    } finally {
      setIsSaving(false)
    }
  }

  const handleResetConfiguration = async () => {
    if (!confirm('Are you sure you want to reset the configuration? This will require re-running the setup wizard.')) {
      return
    }

    try {
      const response = await fetch('/api/settings/reset-configuration', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      })

      if (!response.ok) {
        throw new Error('Failed to reset configuration')
      }

      navigate('/setup')
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Failed to reset configuration')
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  if (!settings) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Alert className="max-w-md">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Failed to load settings. Please try again.
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-3xl font-bold">System Settings</h1>
            <p className="text-muted-foreground">
              Manage your application configuration
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={handleResetConfiguration}
              className="text-red-600 hover:text-red-700"
            >
              <RotateCcw className="h-4 w-4 mr-2" />
              Reset Configuration
            </Button>
            <Button
              onClick={handleSave}
              disabled={!hasChanges || isSaving}
            >
              {isSaving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="h-4 w-4 mr-2" />
                  Save Changes
                </>
              )}
            </Button>
          </div>
        </div>

        {/* Status Badge */}
        <div className="mb-6">
          <div className="flex items-center gap-2">
            <Badge variant={settings.is_configured ? "default" : "secondary"}>
              {settings.is_configured ? "Configured" : "Not Configured"}
            </Badge>
            {settings.configured_at && (
              <span className="text-sm text-muted-foreground">
                Configured on {new Date(settings.configured_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>

        {error && (
          <Alert className="mb-6 border-red-200 bg-red-50">
            <AlertCircle className="h-4 w-4 text-red-600" />
            <AlertDescription className="text-red-700">{error}</AlertDescription>
          </Alert>
        )}

        {success && (
          <Alert className="mb-6 border-green-200 bg-green-50">
            <CheckCircle className="h-4 w-4 text-green-600" />
            <AlertDescription className="text-green-700">{success}</AlertDescription>
          </Alert>
        )}

       <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-6">
            <TabsTrigger value="basic">
              <Settings className="h-4 w-4 mr-2" />
              Basic
            </TabsTrigger>
            <TabsTrigger value="email">
              <Mail className="h-4 w-4 mr-2" />
              Email
            </TabsTrigger>
            <TabsTrigger value="llm">
              <Bot className="h-4 w-4 mr-2" />
              AI
            </TabsTrigger>
            <TabsTrigger value="knowledge">
              <Database className="h-4 w-4 mr-2" />
              Knowledge
            </TabsTrigger>
            <TabsTrigger value="security">
              <Shield className="h-4 w-4 mr-2" />
              Security
            </TabsTrigger>
            <TabsTrigger value="features">
              <Globe className="h-4 w-4 mr-2" />
              Features
            </TabsTrigger>
          </TabsList>

          <TabsContent value="basic" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Basic Settings</CardTitle>
                <CardDescription>
                  Configure basic application information
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label htmlFor="app_name">Application Name</Label>
                  <Input
                    id="app_name"
                    value={settings.app_name}
                    onChange={(e) => handleInputChange('app_name', e.target.value)}
                  />
                </div>
                
                <div>
                  <Label htmlFor="app_description">Application Description</Label>
                  <Textarea
                    id="app_description"
                    value={settings.app_description}
                    onChange={(e) => handleInputChange('app_description', e.target.value)}
                    rows={3}
                  />
                </div>
                
                <div>
                  <Label htmlFor="company_name">Company Name</Label>
                  <Input
                    id="company_name"
                    value={settings.company_name}
                    onChange={(e) => handleInputChange('company_name', e.target.value)}
                  />
                </div>
                
                <div>
                  <Label htmlFor="from_email">From Email Address</Label>
                  <Input
                    id="from_email"
                    type="email"
                    value={settings.from_email}
                    onChange={(e) => handleInputChange('from_email', e.target.value)}
                  />
                </div>
                
                <div>
                  <Label htmlFor="frontend_url">Frontend URL</Label>
                  <Input
                    id="frontend_url"
                    value={settings.frontend_url}
                    onChange={(e) => handleInputChange('frontend_url', e.target.value)}
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="email" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Email Configuration</CardTitle>
                <CardDescription>
                  Configure SMTP settings for email notifications
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label htmlFor="smtp_server">SMTP Server</Label>
                  <Input
                    id="smtp_server"
                    value={settings.smtp_server}
                    onChange={(e) => handleInputChange('smtp_server', e.target.value)}
                  />
                </div>
                
                <div>
                  <Label htmlFor="smtp_port">SMTP Port</Label>
                  <Input
                    id="smtp_port"
                    type="number"
                    value={settings.smtp_port}
                    onChange={(e) => handleInputChange('smtp_port', parseInt(e.target.value))}
                    min={1}
                    max={65535}
                  />
                </div>
                
                <div>
                  <Label htmlFor="smtp_username">SMTP Username</Label>
                  <Input
                    id="smtp_username"
                    value={settings.smtp_username}
                    onChange={(e) => handleInputChange('smtp_username', e.target.value)}
                  />
                </div>
                
                <div>
                  <Label htmlFor="smtp_password">SMTP Password</Label>
                  <Input
                    id="smtp_password"
                    type="password"
                    value={settings.smtp_password}
                    onChange={(e) => handleInputChange('smtp_password', e.target.value)}
                  />
                </div>
                
                <div className="flex items-center space-x-2">
                  <Switch
                    id="use_tls"
                    checked={settings.use_tls}
                    onCheckedChange={(checked) => handleInputChange('use_tls', checked)}
                  />
                  <Label htmlFor="use_tls">Use TLS/SSL</Label>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="llm" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>AI Configuration</CardTitle>
                <CardDescription>
                  Configure the AI provider for chat functionality
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label htmlFor="llm_provider">LLM Provider</Label>
                  <select
                    id="llm_provider"
                    value={settings.llm_provider || 'openai'}
                    onChange={(e) => handleInputChange('llm_provider', e.target.value)}
                    className="w-full h-10 px-3 rounded-md border border-input bg-background"
                  >
                    <option value="openai">OpenAI</option>
                    <option value="groq">Groq</option>
                    <option value="ollama">Ollama</option>
                    <option value="sarvam">Sarvam</option>
                  </select>
                </div>
                
                <div>
                  <Label htmlFor="llm_model">Model</Label>
                  <Input
                    id="llm_model"
                    value={settings.llm_model || ''}
                    onChange={(e) => handleInputChange('llm_model', e.target.value)}
                    placeholder="gpt-4o-mini"
                  />
                </div>
                
                <div>
                  <Label htmlFor="llm_api_key">API Key</Label>
                  <Input
                    id="llm_api_key"
                    type="password"
                    value={settings.llm_api_key || ''}
                    onChange={(e) => handleInputChange('llm_api_key', e.target.value)}
                    placeholder="Enter your API key"
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="knowledge" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Knowledge Base</CardTitle>
                <CardDescription>
                  Manage documents and sync from Foundry
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="bg-muted rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium">Documents</span>
                    <Button variant="outline" size="sm" onClick={loadKnowledgeStatus}>
                      <RefreshCw className="h-4 w-4 mr-2" />
                      Refresh
                    </Button>
                  </div>
                  {knowledgeStatus ? (
                    <div className="space-y-1">
                      <p className="text-sm">
                        <span className="font-medium">{knowledgeStatus.document_count}</span> documents in knowledge base
                      </p>
                      <p className="text-xs text-muted-foreground">
                        AI: {knowledgeStatus.llm_provider} / {knowledgeStatus.llm_model}
                      </p>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      Click refresh to load status
                    </p>
                  )}
                </div>
                
                <div>
                  <Label htmlFor="foundry_url">Foundry URL</Label>
                  <Input
                    id="foundry_url"
                    value={settings.foundry_url || ''}
                    onChange={(e) => handleInputChange('foundry_url', e.target.value)}
                    placeholder="https://foundry.yourcompany.com"
                  />
                </div>
                
                <div>
                  <Label htmlFor="foundry_confab_id">Connected Confab ID</Label>
                  <Input
                    id="foundry_confab_id"
                    type="number"
                    value={settings.foundry_confab_id || ''}
                    onChange={(e) => handleInputChange('foundry_confab_id', e.target.value ? parseInt(e.target.value) : null)}
                    placeholder="Leave empty to disconnect"
                  />
                </div>
                
                <div className="flex gap-2">
                  <Button 
                    variant="outline" 
                    onClick={handleUploadDocument}
                    disabled={isUploading}
                  >
                    {isUploading ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <Upload className="h-4 w-4 mr-2" />
                    )}
                    Upload Document
                  </Button>
                  <Button 
                    variant="outline" 
                    onClick={handleSyncFromFoundry}
                    disabled={isSyncing}
                  >
                    {isSyncing ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <RefreshCw className="h-4 w-4 mr-2" />
                    )}
                    Sync from Foundry
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="security" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Security Settings</CardTitle>
                <CardDescription>
                  Configure security and session management
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label htmlFor="session_timeout_minutes">Session Timeout (minutes)</Label>
                  <Input
                    id="session_timeout_minutes"
                    type="number"
                    value={settings.session_timeout_minutes}
                    onChange={(e) => handleInputChange('session_timeout_minutes', parseInt(e.target.value))}
                    min={5}
                    max={1440}
                  />
                </div>
                
                <div>
                  <Label htmlFor="max_login_attempts">Maximum Login Attempts</Label>
                  <Input
                    id="max_login_attempts"
                    type="number"
                    value={settings.max_login_attempts}
                    onChange={(e) => handleInputChange('max_login_attempts', parseInt(e.target.value))}
                    min={1}
                    max={20}
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="features" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Feature Flags</CardTitle>
                <CardDescription>
                  Enable or disable application features
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <Label htmlFor="email_notifications_enabled">Email Notifications</Label>
                    <p className="text-sm text-muted-foreground">Enable email notifications for users</p>
                  </div>
                  <Switch
                    id="email_notifications_enabled"
                    checked={settings.email_notifications_enabled}
                    onCheckedChange={(checked) => handleInputChange('email_notifications_enabled', checked)}
                  />
                </div>
                
                <div className="flex items-center justify-between">
                  <div>
                    <Label htmlFor="user_registration_enabled">User Registration</Label>
                    <p className="text-sm text-muted-foreground">Allow users to register themselves</p>
                  </div>
                  <Switch
                    id="user_registration_enabled"
                    checked={settings.user_registration_enabled}
                    onCheckedChange={(checked) => handleInputChange('user_registration_enabled', checked)}
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
