import { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import ConfigurationChecker from './components/ConfigurationChecker'
import AdminRegister from './pages/AdminRegister'
import AdminLogin from './pages/AdminLogin'
import AdminDashboard from './pages/AdminDashboard'
import ConfigurationWizard from './pages/ConfigurationWizard'
import AdminSettings from './pages/AdminSettings'
import ChatPage from './pages/ChatPage'

function AppContent() {
  const [isLoading, setIsLoading] = useState(true)
  const [configStatus, setConfigStatus] = useState<any>(null)
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

  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-8">
          {configStatus?.app_name || 'WebChat'}
        </h1>
        <p className="text-muted-foreground mb-8">Please login to continue</p>
        <div className="space-x-4">
          <a
            href="/login"
            className="inline-block px-6 py-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
          >
            Login
          </a>
          <a
            href="/register"
            className="inline-block px-6 py-3 bg-secondary text-secondary-foreground rounded-lg hover:bg-secondary/90 transition-colors"
          >
            Register
          </a>
        </div>
      </div>
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          {/* Configuration Wizard - accessible without configuration check */}
          <Route path="/setup" element={<ConfigurationWizard />} />
          
          {/* Routes that require configuration check */}
          <Route path="/*" element={
            <ConfigurationChecker>
              <Routes>
                {/* Public Routes */}
                <Route path="/login" element={<AdminLogin />} />
                <Route path="/register" element={<AdminRegister />} />
                <Route path="/admin/login" element={<AdminLogin />} />
                <Route path="/admin/register" element={<AdminRegister />} />
                
                {/* Protected Routes - require authentication */}
                <Route 
                  path="/dashboard" 
                  element={
                    <ProtectedRoute requireAdmin>
                      <AdminDashboard />
                    </ProtectedRoute>
                  } 
                />
                <Route 
                  path="/chat" 
                  element={
                    <ProtectedRoute>
                      <ChatPage />
                    </ProtectedRoute>
                  } 
                />
                
                {/* Admin Routes */}
                <Route 
                  path="/admin/dashboard" 
                  element={
                    <ProtectedRoute requireAdmin>
                      <AdminDashboard />
                    </ProtectedRoute>
                  } 
                />
                <Route 
                  path="/admin/settings" 
                  element={
                    <ProtectedRoute requireAdmin>
                      <AdminSettings />
                    </ProtectedRoute>
                  } 
                />
                
                {/* Default Landing Page */}
                <Route path="/" element={<AppContent />} />
                
                {/* Redirect unknown routes to home */}
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </ConfigurationChecker>
          } />
        </Routes>
      </Router>
    </AuthProvider>
  )
}

export default App
