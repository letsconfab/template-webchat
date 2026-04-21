import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

interface ConfigStatus {
  is_configured: boolean
  needs_setup: boolean
  configured_at?: string
  app_name?: string
}

const ConfigurationChecker: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isLoading, setIsLoading] = useState(true)
  const [configStatus, setConfigStatus] = useState<ConfigStatus | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    checkConfigurationStatus()
  }, [])

  const checkConfigurationStatus = async () => {
    try {
      const response = await fetch('/api/settings/config-status')
      const data = await response.json()
      setConfigStatus(data)
      
      // If not configured, redirect to setup
      if (data.needs_setup) {
        navigate('/setup')
        return
      }
    } catch (error) {
      console.error('Failed to check configuration status:', error)
      // If we can't check status, assume configuration is needed
      navigate('/setup')
    } finally {
      setIsLoading(false)
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  // If configuration is needed, the redirect will happen in useEffect
  if (configStatus?.needs_setup) {
    return null
  }

  return <>{children}</>
}

export default ConfigurationChecker
