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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'
import { Loader2, CheckCircle, AlertCircle, Mail, Globe, Shield, Settings } from 'lucide-react'

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
}

export default function ConfigurationWizard() {
  const navigate = useNavigate()
  const [currentStep, setCurrentStep] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  
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
  })

  const steps = [
    { id: 'basic', title: 'Basic Setup', icon: Settings },
    { id: 'email', title: 'Email Configuration', icon: Mail },
    { id: 'security', title: 'Security Settings', icon: Shield },
    { id: 'features', title: 'Feature Flags', icon: Globe },
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

  const validateCurrentStep = () => {
    switch (currentStep) {
      case 0: // Basic Setup
        if (!settings.app_name.trim()) {
          setError('Application name is required')
          return false
        }
        if (!settings.from_email.trim()) {
          setError('From email is required')
          return false
        }
        break
      case 1: // Email Configuration
        if (!settings.smtp_server.trim()) {
          setError('SMTP server is required')
          return false
        }
        if (!settings.smtp_port || settings.smtp_port < 1 || settings.smtp_port > 65535) {
          setError('Valid SMTP port is required')
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
      const response = await api.post('/settings/configure', settings)

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
      case 0: // Basic Setup
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
        
      case 1: // Email Configuration
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
        
      case 2: // Security Settings
        return (
          <div className="space-y-4">
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
          </div>
        )
        
      case 3: // Feature Flags
        return (
          <div className="space-y-4">
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
            <TabsList className="grid w-full grid-cols-4">
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
