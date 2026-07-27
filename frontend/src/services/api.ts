import axios from 'axios';

const API_BASE = '/api';
const WS_BASE = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.hostname}${window.location.port ? ':' + window.location.port : ''}/ws/chat`;

const AUTH_PAGE_PATHS = new Set(['/login', '/register', '/setup']);

/**
 * Where to send the browser after a 401. Returns null when already on an auth
 * page so an existing `returnTo` query is not wiped by a hard redirect loop.
 */
export function loginRedirectForUnauthorized(
  pathname: string,
  search: string = '',
): string | null {
  if (AUTH_PAGE_PATHS.has(pathname)) {
    return null;
  }
  const returnTo = `${pathname}${search}`;
  if (!returnTo.startsWith('/') || returnTo.startsWith('//')) {
    return '/login';
  }
  return `/login?returnTo=${encodeURIComponent(returnTo)}`;
}

/** Persist a same-origin relative path for post-login recovery after a 401. */
export function rememberPostLoginReturnTo(returnTo: string): void {
  if (!returnTo.startsWith('/') || returnTo.startsWith('//')) {
    return;
  }
  try {
    sessionStorage.setItem('postLoginReturnTo', returnTo);
  } catch {
    // Ignore sessionStorage failures (private mode quotas, etc.).
  }
}

// Create axios instance
export const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor to include auth token
api.interceptors.request.use(
  (config) => {
    const token = window.localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Add response interceptor to handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      window.localStorage.removeItem('token');
      const href = loginRedirectForUnauthorized(
        window.location.pathname,
        window.location.search,
      );
      if (href) {
        rememberPostLoginReturnTo(`${window.location.pathname}${window.location.search}`);
        window.location.href = href;
      }
    }
    return Promise.reject(error);
  }
);

// Generate or retrieve session ID
export function getSessionId(): string {
  let sessionId = sessionStorage.getItem('copilot-session-id');
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    sessionStorage.setItem('copilot-session-id', sessionId);
  }
  return sessionId;
}

export function setSessionId(sessionId: string): void {
  sessionStorage.setItem('copilot-session-id', sessionId);
}

export function clearSessionId(): void {
  sessionStorage.removeItem('copilot-session-id');
}

export interface ChatSessionSummary {
  id: number
  client_uuid: string
  title: string
  created_at: string
  updated_at: string
}

export interface JourneySummary {
  id: number
  title: string
  purpose: string
  starter_prompt: string
  icon: string | null
  display_order: number
  is_active: boolean
  knowledge_source_labels: string[]
}

export async function listChatSessions(): Promise<ChatSessionSummary[]> {
  const response = await api.get<ChatSessionSummary[]>('/chat-sessions')
  return response.data
}

export async function createChatSession(): Promise<ChatSessionSummary> {
  const response = await api.post<ChatSessionSummary>('/chat-sessions')
  return response.data
}

export async function renameChatSession(
  clientUuid: string,
  title: string,
): Promise<ChatSessionSummary> {
  const response = await api.patch<ChatSessionSummary>(`/chat-sessions/${clientUuid}`, {
    title,
  })
  return response.data
}

export async function deleteChatSession(clientUuid: string): Promise<void> {
  await api.delete(`/chat-sessions/${clientUuid}`)
}

export async function listActiveJourneys(): Promise<JourneySummary[]> {
  const response = await api.get<JourneySummary[]>('/journeys')
  return response.data
}

export interface Provider {
  id: string
  name: string
  requires_api_key: boolean
}

export interface Settings {
  provider: string
  model: string
  apiKey: string
}

export async function getProviders(): Promise<Provider[]> {
  const response = await fetch(`${API_BASE}/providers`)
  const data = await response.json()
  return data.providers
}

export async function getModels(settings: Settings): Promise<string[]> {
  const response = await fetch(`${API_BASE}/models`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      provider: settings.provider,
      model: settings.model,
      api_key: settings.apiKey,
    }),
  })
  const data = await response.json()
  return data.models
}

export async function validateKey(settings: Settings): Promise<boolean> {
  const response = await fetch(`${API_BASE}/validate-key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      provider: settings.provider,
      model: settings.model,
      api_key: settings.apiKey,
    }),
  })
  const data = await response.json()
  return data.valid
}

export class ChatWebSocket {
  private ws: WebSocket | null = null
  private messageHandlers: ((data: any) => void)[] = []
  private errorHandler: ((error: any) => void) | null = null
  private connectionHandler: ((connected: boolean) => void) | null = null

  connect(settings: Settings, sessionId?: string): void {
    this.ws = new WebSocket(WS_BASE)
    
    this.ws.onopen = () => {
      // Authenticate before the server reads session data or chat settings.
      this.ws?.send(JSON.stringify({
        type: 'auth',
        token: window.localStorage.getItem('token'),
        session_id: sessionId || getSessionId(),
        provider: settings.provider,
        model: settings.model,
      }))
      this.connectionHandler?.(true)
    }

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      this.messageHandlers.forEach(handler => handler(data))
    }

    this.ws.onerror = (error) => {
      this.errorHandler?.(error)
      this.connectionHandler?.(false)
    }

    this.ws.onclose = () => {
      this.connectionHandler?.(false)
    }
  }

  sendMessage(message: string, journeyId?: number | null): void {
    this.ws?.send(JSON.stringify({
      message,
      ...(journeyId != null ? { journey_id: journeyId } : {}),
    }))
  }

  onMessage(handler: (data: any) => void): void {
    this.messageHandlers.push(handler)
  }

  onError(handler: (error: any) => void): void {
    this.errorHandler = handler
  }

  onConnection(handler: (connected: boolean) => void): void {
    this.connectionHandler = handler
  }

  disconnect(): void {
    this.ws?.close()
    this.ws = null
    this.messageHandlers = []
  }
}

// Expose for debugging
(window as any).__API_INSTANCE__ = api;
