import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import type { RuntimeFeatures } from '../contexts/AuthContext'

interface ProtectedRouteProps {
  children: React.ReactNode
  requireAdmin?: boolean
  requiredFeature?: keyof RuntimeFeatures
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ 
  children, 
  requireAdmin = false,
  requiredFeature,
}) => {
  const { isAuthenticated, isAdmin, isLoading, features } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  if (!isAuthenticated) {
    const returnTo = `${location.pathname}${location.search}`
    return <Navigate to={`/login?returnTo=${encodeURIComponent(returnTo)}`} replace />
  }

  if (requireAdmin && !isAdmin) {
    return <Navigate to="/login" replace />
  }

  if (requiredFeature && !features[requiredFeature]) {
    return <Navigate to={isAdmin ? '/admin/dashboard' : '/chat'} replace />
  }

  return <>{children}</>
}

export default ProtectedRoute
