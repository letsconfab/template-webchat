import { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import ConfigurationChecker from './components/ConfigurationChecker'
import Register from './pages/Register'
import AdminRegister from './pages/AdminRegister'
import AdminLogin from './pages/AdminLogin'
import Login from './pages/Login'
import Chat from './pages/Chat'
import AdminDashboard from './pages/AdminDashboard'
import ConfigurationWizard from './pages/ConfigurationWizard'
import AdminSettings from './pages/AdminSettings'

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
          {configStatus?.app_name || 'Admin Invite System'}
        </h1>
        <p className="text-muted-foreground mb-8">Choose your login type</p>
        <div className="space-y-4">
          <div className="space-x-4">
            <a
              href="/login"
              className="inline-block px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
            >
              User Login
            </a>
            <a
              href="/register"
              className="inline-block px-6 py-3 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors"
            >
              User Register
            </a>
            <a
              href="/admin/login"
              className="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Admin Login
            </a>
          </div>
          <div>
            <a
              href="/admin/register"
              className="inline-block px-6 py-3 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors"
            >
              Admin Register
            </a>
          </div>
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
                {/* User Routes */}
                <Route path="/login" element={<Login />} />
                <Route path="/register" element={<Register />} />
                <Route 
                  path="/chat" 
                  element={
                    <ProtectedRoute>
                      <Chat />
                    </ProtectedRoute>
                  } 
                />
                
                {/* Admin Routes */}
                <Route path="/admin/register" element={<AdminRegister />} />
                <Route path="/admin/login" element={<AdminLogin />} />
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
