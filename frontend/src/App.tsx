import { useState, useEffect } from 'react'
import ChatInterface from './components/ChatInterface'
import SettingsModal from './components/SettingsModal'
import WelcomeScreen from './components/WelcomeScreen'
import { Settings, Trash2 } from 'lucide-react'
import { getSessionId } from './services/api'

function App() {
  const [showSettings, setShowSettings] = useState(false)
  const [settings, setSettings] = useState<{
    provider: string
    model: string
    apiKey: string
  } | null>(null)
  const [hasConfigured, setHasConfigured] = useState(false)

  // Load settings from localStorage on mount
  useEffect(() => {
    const savedSettings = localStorage.getItem('copilot-settings')
    if (savedSettings) {
      const parsed = JSON.parse(savedSettings)
      setSettings(parsed)
      setHasConfigured(true)
    }
  }, [])

  const handleSaveSettings = (newSettings: {
    provider: string
    model: string
    apiKey: string
  }) => {
    setSettings(newSettings)
    setHasConfigured(true)
    setShowSettings(false)
    // Save to localStorage
    localStorage.setItem('copilot-settings', JSON.stringify(newSettings))
  }

  const handleClearHistory = async () => {
    try {
      const sessionId = getSessionId()
      await fetch(`/api/chat-history?session_id=${sessionId}`, { method: 'DELETE' })
      // Force ChatInterface to refresh by remounting
      window.location.reload()
    } catch (error) {
      console.error('Failed to clear history:', error)
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Header */}
      <header className="border-b border-border px-4 py-3">
        <div className="flex items-center justify-between max-w-4xl mx-auto">
          <div className="flex items-center gap-2">
            <span className="text-2xl">❤️</span>
            <h1 className="text-xl font-semibold">AI Copilot</h1>
          </div>
          <div className="flex items-center gap-2">
            {hasConfigured && (
              <button
                onClick={handleClearHistory}
                className="p-2 hover:bg-muted rounded-lg transition-colors"
                aria-label="Clear chat history"
              >
                <Trash2 className="w-5 h-5" />
              </button>
            )}
            <button
              onClick={() => setShowSettings(true)}
              className="p-2 hover:bg-muted rounded-lg transition-colors"
              aria-label="Settings"
            >
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto p-4">
        {!hasConfigured ? (
          <WelcomeScreen
            onOpenSettings={() => setShowSettings(true)}
            onSaveSettings={handleSaveSettings}
          />
        ) : (
          <ChatInterface settings={settings} />
        )}
      </main>

      {/* Settings Modal */}
      {showSettings && (
        <SettingsModal
          isOpen={showSettings}
          onClose={() => setShowSettings(false)}
          onSave={handleSaveSettings}
          initialSettings={settings}
        />
      )}
    </div>
  )
}

export default App
