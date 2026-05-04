import React, { useState, useEffect } from 'react'
import { useNavigate, Link, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Eye, EyeOff, UserPlus, CheckCircle } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../services/api'

const registerSchema = z.object({
  email: z.string().email('Invalid email address'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  confirmPassword: z.string().min(8, 'Password must be at least 8 characters')
}).refine((data) => data.password === data.confirmPassword, {
  message: "Passwords don't match",
  path: ["confirmPassword"],
})

type RegisterFormData = z.infer<typeof registerSchema>

const AdminRegister: React.FC = () => {
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [inviteToken, setInviteToken] = useState<string | null>(null)
  const [inviteData, setInviteData] = useState<{ email: string; role: string } | null>(null)
  const [isInviteVerified, setIsInviteVerified] = useState(false)
  const [inviteAccepted, setInviteAccepted] = useState(false)
  const [emailInviteStatus, setEmailInviteStatus] = useState<{ has_invite: boolean; role: string | null; message: string | null; already_registered: boolean } | null>(null)
  const [registrationSuccess, setRegistrationSuccess] = useState(false)
  const [searchParams] = useSearchParams()
  const { register: registerUser, logout, isAuthenticated } = useAuth()
  const navigate = useNavigate()

  const {
    register,
    handleSubmit,
    formState: { errors },
    setError,
    setValue
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema)
  })

  // Check for invite token on component mount - logout any existing session first
  useEffect(() => {
    const token = searchParams.get('token')
    if (token) {
      // Clear any existing session before proceeding with invite
      if (isAuthenticated) {
        logout()
      }
      setInviteToken(token)
      verifyInviteToken(token)
    }
  }, [searchParams])

  const verifyInviteToken = async (token: string) => {
    try {
      const response = await api.get(`/accept-invite/${token}`)
      const { email, role } = response.data
      setInviteData({ email, role })
      setValue('email', email)
      setIsInviteVerified(true)
    } catch (error: any) {
      console.error('Invalid or expired invite token:', error)
      setIsInviteVerified(false)
    }
  }

  const checkInviteByEmail = async (email: string) => {
    if (!email || !email.includes('@')) {
      setEmailInviteStatus(null)
      return
    }

    try {
      const response = await api.get(`/check-invite/${encodeURIComponent(email)}`)
      setEmailInviteStatus(response.data)
    } catch (error: any) {
      console.error('Error checking invite status:', error)
      setEmailInviteStatus(null)
    }
  }

  // Debounced email check
  const [emailTimeout, setEmailTimeout] = useState<number | null>(null)
  
  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const email = e.target.value
    // Clear existing timeout
    if (emailTimeout) {
      clearTimeout(emailTimeout)
    }
    // Set new timeout to check invite after 500ms
    const timeout = setTimeout(() => {
      checkInviteByEmail(email)
    }, 500)
    setEmailTimeout(timeout)
  }

  const onSubmit = async (data: RegisterFormData) => {
    setIsLoading(true)
    try {
      if (inviteToken && isInviteVerified && inviteData) {
        // Register using invite token
        await api.post(`/accept-invite/${inviteToken}`, {
          token: inviteToken,
          password: data.password
        })
        setRegistrationSuccess(true)
      } else {
        // Regular registration with default role
        await registerUser(data.email, data.password)
        setRegistrationSuccess(true)
      }
    } catch (error: any) {
      if (error.response?.data?.detail) {
        setError('root', { message: error.response.data.detail })
      } else {
        setError('root', { message: 'Registration failed. Please try again.' })
      }
    } finally {
      setIsLoading(false)
    }
  }

  if (registrationSuccess) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-green-50 to-emerald-100 flex items-center justify-center p-4">
        <div className="max-w-md w-full text-center">
          <div className="mx-auto h-16 w-16 bg-green-500 rounded-full flex items-center justify-center mb-6">
            <CheckCircle className="h-8 w-8 text-white" />
          </div>
          <h2 className="text-3xl font-bold text-gray-900 mb-4">
            Registration Successful!
          </h2>
          <p className="text-gray-600 mb-8">
            Your account has been created. You can now login to access the chat application.
          </p>
          <a
            href="/login"
            className="inline-block w-full py-3 px-4 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition-colors"
          >
            Go to Login
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 bg-blue-600 rounded-lg flex items-center justify-center">
            <UserPlus className="h-6 w-6 text-white" />
          </div>
          <h2 className="mt-6 text-3xl font-bold text-gray-900">
            Create Account
          </h2>
          <p className="mt-2 text-sm text-gray-600">
            Register to access the chat application
          </p>
        </div>

        <div className="bg-white shadow-xl rounded-lg p-8">
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
            {errors.root && (
              <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-md text-sm">
                {errors.root.message}
              </div>
            )}

            {/* Invite Verification - Require explicit acceptance */}
            {isInviteVerified && inviteData && !inviteAccepted && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-6 text-center">
                <CheckCircle className="h-12 w-12 text-green-600 mx-auto mb-3" />
                <h3 className="text-lg font-semibold text-green-800 mb-2">
                  You've been invited!
                </h3>
                <p className="text-sm text-green-700 mb-4">
                  You've been invited to join as a <span className="font-medium">{inviteData.role === 'admin' ? 'Admin' : 'General User'}</span>
                </p>
                <p className="text-sm text-gray-600 mb-4">
                  Email: <span className="font-medium">{inviteData.email}</span>
                </p>
                <button
                  type="button"
                  onClick={() => setInviteAccepted(true)}
                  className="w-full py-3 px-4 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition-colors"
                >
                  Accept Invitation
                </button>
              </div>
            )}

            {isInviteVerified && inviteData && inviteAccepted && (
              <div className="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-md text-sm flex items-center">
                <CheckCircle className="h-4 w-4 mr-2" />
                <div>
                  <div className="font-medium">Invitation Accepted</div>
                  <div className="text-xs mt-1">
                    Role: {inviteData.role === 'admin' ? 'Admin' : 'General User'}
                  </div>
                </div>
              </div>
            )}

            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                Email Address
              </label>
              <input
                {...register('email')}
                type="email"
                id="email"
                readOnly={isInviteVerified && inviteAccepted}
                disabled={isInviteVerified && !inviteAccepted}
                className={`w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${isInviteVerified ? 'bg-gray-50 cursor-not-allowed' : ''}`}
                placeholder="abc@example.com"
                onChange={(e) => {
                  register('email').onChange(e)
                  handleEmailChange(e)
                }}
              />
              {errors.email && (
                <p className="mt-1 text-sm text-red-600">{errors.email.message}</p>
              )}
              {emailInviteStatus?.has_invite && (
                <div className="mt-2 bg-green-50 border border-green-200 text-green-800 px-3 py-2 rounded-md text-sm flex items-center">
                  <CheckCircle className="h-4 w-4 mr-2" />
                  {emailInviteStatus.message}
                </div>
              )}
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-2">
                Password
              </label>
              <div className="relative">
                <input
                  {...register('password')}
                  type={showPassword ? 'text' : 'password'}
                  id="password"
                  disabled={isInviteVerified && !inviteAccepted}
                  className={`w-full px-3 py-2 pr-10 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${isInviteVerified && !inviteAccepted ? 'bg-gray-100 cursor-not-allowed' : ''}`}
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-0 pr-3 flex items-center"
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4 text-gray-400" />
                  ) : (
                    <Eye className="h-4 w-4 text-gray-400" />
                  )}
                </button>
              </div>
              {errors.password && (
                <p className="mt-1 text-sm text-red-600">{errors.password.message}</p>
              )}
            </div>

            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 mb-2">
                Confirm Password
              </label>
              <div className="relative">
                <input
                  {...register('confirmPassword')}
                  type={showConfirmPassword ? 'text' : 'password'}
                  id="confirmPassword"
                  disabled={isInviteVerified && !inviteAccepted}
                  className={`w-full px-3 py-2 pr-10 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${isInviteVerified && !inviteAccepted ? 'bg-gray-100 cursor-not-allowed' : ''}`}
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-0 pr-3 flex items-center"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                >
                  {showConfirmPassword ? (
                    <EyeOff className="h-4 w-4 text-gray-400" />
                  ) : (
                    <Eye className="h-4 w-4 text-gray-400" />
                  )}
                </button>
              </div>
              {errors.confirmPassword && (
                <p className="mt-1 text-sm text-red-600">{errors.confirmPassword.message}</p>
              )}
            </div>

            <div>
              <button
                type="submit"
                disabled={isLoading || (isInviteVerified && !inviteAccepted)}
                className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isLoading ? (
                  <div className="flex items-center">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    Creating Account...
                  </div>
                ) : (
                  <div className="flex items-center">
                    <UserPlus className="h-4 w-4 mr-2" />
                    {inviteToken && isInviteVerified ? 'Complete Registration' : 'Create Account'}
                  </div>
                )}
              </button>
            </div>

            <div className="text-center">
              <p className="text-sm text-gray-600">
                Already have an account?{' '}
                <Link
                  to="/login"
                  className="font-medium text-blue-600 hover:text-blue-500 transition-colors"
                >
                  Sign in here
                </Link>
              </p>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}

export default AdminRegister
