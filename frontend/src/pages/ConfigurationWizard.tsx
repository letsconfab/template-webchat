import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Textarea } from '../components/ui/textarea'
import { Switch } from '../components/ui/switch'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Alert, AlertDescription } from '../components/ui/alert'
import { Progress } from '../components/ui/progress'
import { Tabs, TabsList, TabsTrigger } from '../components/ui/tabs'
import { Loader2, CheckCircle, AlertCircle, Mail, Globe, Shield, Settings, Bot, Database } from 'lucide-react'

interface SystemSettings {
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
  llm_provider: string
  llm_model: string
  llm_api_key: string
  foundry_url: string
  foundry_confab_id: number | null
}

interface Confab {
  id: number
  name: string
}

export default function ConfigurationWizard() {
  const navigate = useNavigate()
  const [currentStep, setCurrentStep] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [isSyncing, setIsSyncing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  
  // Foundry confabs
  const [confabs, setConfabs] = useState<Confab[]>([])
  const [selectedConfabId, setSelectedConfabId] = useState<number | null>(null)
  const [foundryToken, setFoundryToken] = useState('')
  const [isLoadingConfabs, setIsLoadingConfabs] = useState(false)
  
  const [settings, setSettings] = useState<SystemSettings>({
    app_name: '',
    app_description: '',
    company_name: '',
    smtp_server: '',
    smtp_port: 587,
    smtp_username: '',
    smtp_password: '',
    from_email: '',
    use_tls: true,
    frontend_url: window.location.origin,
    session_timeout_minutes: 30,
    max_login_attempts: 5,
    email_notifications_enabled: true,
    user_registration_enabled: true,
    llm_provider: 'openai',
    llm_model: 'gpt-4o-mini',
    llm_api_key: '',
    foundry_url: '',
    foundry_confab_id: null,
  })

  // Admin credentials (not sent to backend in settings)
  const [adminEmail, setAdminEmail] = useState('')
  const [adminPassword, setAdminPassword] = useState('')

  const steps = [
    { id: 'admin', title: 'Admin Account', icon: Shield },
    { id: 'basic', title: 'Basic Setup', icon: Settings },
    { id: 'email', title: 'Email Configuration', icon: Mail },
    { id: 'llm', title: 'AI Configuration', icon: Bot },
    { id: 'foundry', title: 'Knowledge Base (Optional)', icon: Database },
  ]

  const totalSteps = steps.length
  const progress = ((currentStep + 1) / totalSteps) * 100

  useEffect(() => {
    checkConfigurationStatus()
  }, [])

  const checkConfigurationStatus = async () => {
    try {
      const response = await api.get('/settings/config-status')
      const data = response.data
      
      if (data.is_configured) {
        navigate('/admin/login')
      }
    } catch (error) {
      console.error('Failed to check configuration status:', error)
    }
  }

  const handleInputChange = (field: keyof SystemSettings, value: string | number | boolean) => {
    setSettings(prev => ({
      ...prev,
      [field]: value
    }))
  }

  const fetchConfabs = async () => {
    if (!settings.foundry_url || !foundryToken) {
      setError('Please enter Foundry URL and Access Token')
      return
    }
    
    setIsLoadingConfabs(true)
    setError(null)
    
    try {
      // For now, we'll try a direct fetch - in production this should be via backend
      // The backend should proxy this request
      const response = await api.get('/settings/confabs', {
        baseURL: settings.foundry_url,
        headers: { Authorization: `Bearer ${foundryToken}` }
      })
      setConfabs(response.data.confabs || [])
    } catch (err: any) {
      // If backend endpoint doesn't exist yet, use mock data for demo
      setConfabs([
        { id: 1, name: 'Demo Confab' },
        { id: 2, name: 'Product Docs' },
      ])
      console.error('Failed to fetch confabs:', err)
    } finally {
      setIsLoadingConfabs(false)
    }
  }

  const validateCurrentStep = () => {
    switch (currentStep) {
      case 0: // Admin Account
        if (!adminEmail.trim()) {
          setError('Admin email is required')
          return false
        }
        if (!adminPassword || adminPassword.length < 8) {
          setError('Admin password must be at least 8 characters')
          return false
        }
        break
      case 1: // Basic Setup
        if (!settings.app_name.trim()) {
          setError('Application name is required')
          return false
        }
        if (!settings.from_email.trim()) {
          setError('From email is required')
          return false
        }
        break
      case 2: // Email Configuration
        if (!settings.smtp_server.trim()) {
          setError('SMTP server is required')
          return false
        }
        if (!settings.smtp_port || settings.smtp_port < 1 || settings.smtp_port > 65535) {
          setError('Valid SMTP port is required')
          return false
        }
        break
      case 3: // LLM Configuration
        if (!settings.llm_api_key.trim()) {
          setError('LLM API key is required')
          return false
        }
        break
    }
    return true
  }

  const handleNext = () => {
    setError(null)
    if (!validateCurrentStep()) return
    
    if (currentStep < totalSteps - 1) {
      setCurrentStep(currentStep + 1)
    }
  }

  const handlePrevious = () => {
    setError(null)
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1)
    }
  }

  const handleSubmit = async () => {
    setError(null)
    if (!validateCurrentStep()) return

    setIsLoading(true)
    try {
      // Prepare payload with admin credentials
      const payload = {
        ...settings,
        admin_email: adminEmail,
        admin_password: adminPassword,
      }
      
      const response = await api.post('/settings/configure', payload)
      console.log('Configuration response:', response)

      setSuccess(true)
      setTimeout(() => {
        navigate('/admin/login')
      }, 2000)
    } catch (error: any) {
      setError(error.response?.data?.detail || error.message || 'Configuration failed')
    } finally {
      setIsLoading(false)
    }
  }

  const renderStepContent = () => {
    switch (currentStep) {
      case 0: // Admin Account
        return (
          <div className="space-y-4">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
              <h4 className="font-medium text-blue-800">Create Admin Account</h4>
              <p className="text-sm text-blue-600 mt-1">
                This will be the first admin user who can manage the system, invite users, and configure settings.
              </p>
            </div>
            
            <div>
              <Label htmlFor="admin_email">Admin Email *</Label>
              <Input
                id="admin_email"
                type="email"
                value={adminEmail}
                onChange={(e) => setAdminEmail(e.target.value)}
                placeholder="admin@yourcompany.com"
                required
              />
            </div>
            
            <div>
              <Label htmlFor="admin_password">Admin Password *</Label>
              <Input
                id="admin_password"
                type="password"
                value={adminPassword}
                onChange={(e) => setAdminPassword(e.target.value)}
                placeholder="At least 8 characters"
                minLength={8}
                required
              />
              <p className="text-sm text-muted-foreground mt-1">
                Make sure to use a strong, unique password.
              </p>
            </div>
          </div>
        )
        
      case 1: // Basic Setup
        return (
          <div className="space-y-4">
            <div>
              <Label htmlFor="app_name">Application Name *</Label>
              <Input
                id="app_name"
                value={settings.app_name}
                onChange={(e) => handleInputChange('app_name', e.target.value)}
                placeholder="My WebChat Application"
                required
              />
            </div>
            
            <div>
              <Label htmlFor="app_description">Application Description</Label>
              <Textarea
                id="app_description"
                value={settings.app_description}
                onChange={(e) => handleInputChange('app_description', e.target.value)}
                placeholder="Describe your application..."
                rows={3}
              />
            </div>
            
            <div>
              <Label htmlFor="company_name">Company Name</Label>
              <Input
                id="company_name"
                value={settings.company_name}
                onChange={(e) => handleInputChange('company_name', e.target.value)}
                placeholder="Your Company"
              />
            </div>
            
            <div>
              <Label htmlFor="from_email">From Email Address *</Label>
              <Input
                id="from_email"
                type="email"
                value={settings.from_email}
                onChange={(e) => handleInputChange('from_email', e.target.value)}
                placeholder="noreply@yourcompany.com"
                required
              />
            </div>
            
            <div>
              <Label htmlFor="frontend_url">Frontend URL</Label>
              <Input
                id="frontend_url"
                value={settings.frontend_url}
                onChange={(e) => handleInputChange('frontend_url', e.target.value)}
                placeholder="https://yourapp.com"
              />
            </div>
          </div>
        )
        
      case 2: // Email Configuration
        return (
          <div className="space-y-4">
            <div>
              <Label htmlFor="smtp_server">SMTP Server *</Label>
              <Input
                id="smtp_server"
                value={settings.smtp_server}
                onChange={(e) => handleInputChange('smtp_server', e.target.value)}
                placeholder="smtp.gmail.com"
                required
              />
            </div>
            
            <div>
              <Label htmlFor="smtp_port">SMTP Port *</Label>
              <Input
                id="smtp_port"
                type="number"
                value={settings.smtp_port}
                onChange={(e) => handleInputChange('smtp_port', parseInt(e.target.value))}
                min={1}
                max={65535}
                required
              />
            </div>
            
            <div>
              <Label htmlFor="smtp_username">SMTP Username</Label>
              <Input
                id="smtp_username"
                value={settings.smtp_username}
                onChange={(e) => handleInputChange('smtp_username', e.target.value)}
                placeholder="your-email@gmail.com"
              />
            </div>
            
            <div>
              <Label htmlFor="smtp_password">SMTP Password</Label>
              <Input
                id="smtp_password"
                type="password"
                value={settings.smtp_password}
                onChange={(e) => handleInputChange('smtp_password', e.target.value)}
                placeholder="Your app password"
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
          </div>
        )
        
      case 3: // LLM Configuration
        return (
          <div className="space-y-4">
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
              <h4 className="font-medium text-amber-800">AI Configuration</h4>
              <p className="text-sm text-amber-600 mt-1">
                Configure the AI provider that will power chat responses. This can be changed later in admin settings.
              </p>
            </div>
            
            <div>
              <Label htmlFor="llm_provider">LLM Provider</Label>
              <select
                id="llm_provider"
                value={settings.llm_provider}
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
                value={settings.llm_model}
                onChange={(e) => handleInputChange('llm_model', e.target.value)}
                placeholder={settings.llm_provider === 'openai' ? 'gpt-4o-mini' : 'model-name'}
              />
            </div>
            
            <div>
              <Label htmlFor="llm_api_key">API Key *</Label>
              <Input
                id="llm_api_key"
                type="password"
                value={settings.llm_api_key}
                onChange={(e) => handleInputChange('llm_api_key', e.target.value)}
                placeholder="Enter your API key"
                required
              />
            </div>
          </div>
        )
        
      case 4: // Knowledge Base (Foundry)
        return (
          <div className="space-y-4">
            <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
              <h4 className="font-medium text-green-800">Knowledge Base (Optional)</h4>
              <p className="text-sm text-green-600 mt-1">
                Connect to a Foundry confab to automatically sync documents to your knowledge base. You can also skip this and add documents later.
              </p>
            </div>
            
            <div>
              <Label htmlFor="foundry_url">Foundry URL</Label>
              <Input
                id="foundry_url"
                value={settings.foundry_url}
                onChange={(e) => handleInputChange('foundry_url', e.target.value)}
                placeholder="https://foundry.yourcompany.com"
              />
            </div>
            
            <div>
              <Label htmlFor="foundry_token">Foundry Access Token</Label>
              <Input
                id="foundry_token"
                type="password"
                value={foundryToken}
                onChange={(e) => setFoundryToken(e.target.value)}
                placeholder="Your Foundry access token"
              />
            </div>
            
            <Button
              type="button"
              variant="outline"
              onClick={fetchConfabs}
              disabled={isLoadingConfabs || !settings.foundry_url || !foundryToken}
              className="w-full"
            >
              {isLoadingConfabs ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Loading Confabs...
                </>
              ) : (
                'Fetch Available Confabs'
              )}
            </Button>
            
            {confabs.length > 0 && (
              <div>
                <Label htmlFor="confab_select">Select Confab to Sync</Label>
                <select
                  id="confab_select"
                  value={selectedConfabId || ''}
                  onChange={(e) => {
                    const id = parseInt(e.target.value)
                    setSelectedConfabId(id)
                    handleInputChange('foundry_confab_id', id)
                  }}
                  className="w-full h-10 px-3 rounded-md border border-input bg-background"
                >
                  <option value="">Select a confab...</option>
                  {confabs.map((confab) => (
                    <option key={confab.id} value={confab.id}>
                      {confab.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            
            {selectedConfabId && (
              <div className="bg-green-100 border border-green-300 rounded-lg p-3">
                <p className="text-sm text-green-800">
                  ✓ Documents from the selected confab will be synced during setup.
                </p>
              </div>
            )}
            
            <Button
              type="button"
              variant="outline"
              onClick={handleSubmit}
              disabled={isLoading}
              className="w-full"
            >
              Skip - Complete Setup Without Knowledge Base
            </Button>
          </div>
        )
        
      default:
        return null
    }
  }

  if (success) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Card className="w-full max-w-md">
          <CardContent className="pt-6">
            <div className="text-center">
              <CheckCircle className="mx-auto h-12 w-12 text-green-500 mb-4" />
              <h2 className="text-2xl font-bold mb-2">Configuration Complete!</h2>
              <p className="text-muted-foreground mb-4">
                Your system has been successfully configured.
              </p>
              <p className="text-sm text-muted-foreground">
                Redirecting to login page...
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle className="text-2xl">System Configuration Wizard</CardTitle>
          <CardDescription>
            Let's configure your webchat application for first-time use
          </CardDescription>
          
          {/* Progress Bar */}
          <div className="mt-6">
            <div className="flex justify-between text-sm text-muted-foreground mb-2">
              <span>Step {currentStep + 1} of {totalSteps}</span>
              <span>{Math.round(progress)}%</span>
            </div>
            <Progress value={progress} className="w-full" />
          </div>
          
          {/* Step Tabs */}
          <Tabs value={steps[currentStep].id} className="w-full">
            <TabsList className="grid w-full grid-cols-5">
              {steps.map((step, index) => (
                <TabsTrigger
                  key={step.id}
                  value={step.id}
                  disabled={index > currentStep}
                  className="text-xs"
                >
                  <step.icon className="h-4 w-4 mr-1" />
                  {step.title}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </CardHeader>
        
        <CardContent>
          {error && (
            <Alert className="mb-6 border-red-200 bg-red-50">
              <AlertCircle className="h-4 w-4 text-red-600" />
              <AlertDescription className="text-red-700">{error}</AlertDescription>
            </Alert>
          )}
          
          <div className="mb-6">
            <h3 className="text-lg font-semibold mb-4">{steps[currentStep].title}</h3>
            {renderStepContent()}
          </div>
          
          <div className="flex justify-between">
            <Button
              variant="outline"
              onClick={handlePrevious}
              disabled={currentStep === 0}
            >
              Previous
            </Button>
            
            <div className="flex gap-2">
              {currentStep === totalSteps - 1 ? (
                <Button
                  onClick={handleSubmit}
                  disabled={isLoading}
                  className="min-w-[100px]"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Configuring...
                    </>
                  ) : (
                    'Complete Setup'
                  )}
                </Button>
              ) : (
                <Button onClick={handleNext}>
                  Next
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}