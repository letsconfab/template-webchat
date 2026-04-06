const API_BASE = '/api'
const WS_BASE = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.hostname}:8000/ws/chat`

// Generate or retrieve session ID
export function getSessionId(): string {
  let sessionId = sessionStorage.getItem('copilot-session-id')
  if (!sessionId) {
    sessionId = crypto.randomUUID()
    sessionStorage.setItem('copilot-session-id', sessionId)
  }
  return sessionId
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

  connect(settings: Settings): void {
    this.ws = new WebSocket(WS_BASE)
    
    this.ws.onopen = () => {
      // Send initial settings with session ID
      this.ws?.send(JSON.stringify({
        session_id: getSessionId(),
        provider: settings.provider,
        model: settings.model,
        api_key: settings.apiKey,
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

  sendMessage(message: string): void {
    this.ws?.send(JSON.stringify({ message }))
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
