import React, { createContext, useContext, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { api } from '../services/api';

interface User {
  id: number;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<string>;
  register: (email: string, password: string) => Promise<void>;
  adminRegister: (email: string, password: string, confirmPassword: string) => Promise<void>;
  logout: () => void;
  isLoading: boolean;
  isAdmin: boolean;
  isAuthenticated: boolean;
  features: RuntimeFeatures;
}

export interface RuntimeFeatures {
  admin_replay_enabled: boolean;
  tester_correspondence_enabled: boolean;
  tester_email_notifications_enabled: boolean;
}

const defaultFeatures: RuntimeFeatures = {
  admin_replay_enabled: false,
  tester_correspondence_enabled: false,
  tester_email_notifications_enabled: false,
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [isLoading, setIsLoading] = useState(true);
  const [features, setFeatures] = useState<RuntimeFeatures>(defaultFeatures);

  const isAdmin = user?.role === 'admin';
  const isAuthenticated = !!token && !!user;

  useEffect(() => {
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      fetchUser();
    } else {
      setIsLoading(false);
    }
  }, [token]);

  const fetchUser = async () => {
    try {
      const response = await api.get('/auth/me');
      const featureResponse = await api.get('/settings/features');
      // Features must be set before user. AdminLogin navigates as soon as
      // `user` is set; ProtectedRoute would otherwise see default feature
      // flags and bounce email deep-links (e.g. /feedback/:id) to /chat.
      setFeatures(featureResponse.data);
      setUser(response.data);
    } catch (error) {
      console.error('Failed to fetch user:', error);
      localStorage.removeItem('token');
      setToken(null);
      delete api.defaults.headers.common['Authorization'];
    } finally {
      setIsLoading(false);
    }
  };

  const login = async (email: string, password: string): Promise<string> => {
  try {
    const response = await api.post('/auth/login', { email, password });
    const { access_token } = response.data;

    // Save token
    localStorage.setItem('token', access_token);
    setToken(access_token);
    api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;

    // Fetch user + features before exposing `user` so post-login navigation
    // to feature-gated routes (e.g. /feedback/:id) is not bounced to /chat.
    const userResponse = await api.get('/auth/me');
    const featureResponse = await api.get('/settings/features');
    setFeatures(featureResponse.data);
    setUser(userResponse.data);

    toast.success('Login successful!');

    // Return role
    return userResponse.data.role;
  } catch (error: any) {
    const message = error.response?.data?.detail || 'Login failed';
    toast.error(message);
    throw error;
  }
};

  const register = async (email: string, password: string) => {
    try {
      await api.post('/auth/register', { email, password });
      toast.success('Registration successful! Please login.');
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Registration failed';
      toast.error(message);
      throw error;
    }
  };

  const adminRegister = async (email: string, password: string, confirmPassword: string) => {
    try {
      await api.post('/auth/admin/register', { 
        email, 
        password, 
        confirm_password: confirmPassword 
      });
      toast.success('Admin registration successful! Please login.');
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Admin registration failed';
      toast.error(message);
      throw error;
    }
  };

  const logout = () => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
    setFeatures(defaultFeatures);
    delete api.defaults.headers.common['Authorization'];
    toast.success('Logged out successfully');
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        login,
        register,
        adminRegister,
        logout,
        isLoading,
        isAdmin,
        isAuthenticated,
        features,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
