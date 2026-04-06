import { useState, useEffect } from 'react'
import { X, Check, AlertCircle } from 'lucide-react'
import { getProviders, getModels, validateKey, type Settings } from '../services/api'

interface SettingsModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (settings: Settings) => void
  initialSettings: Settings | null
}

export default function SettingsModal({ isOpen, onClose, onSave, initialSettings }: SettingsModalProps) {
  const [step, setStep] = useState<'provider' | 'apiKey' | 'model' | 'done'>('provider')
  const [provider, setProvider] = useState(initialSettings?.provider || 'openai')
  const [apiKey, setApiKey] = useState(initialSettings?.apiKey || '')
  const [model, setModel] = useState(initialSettings?.model || '')
  const [providers, setProviders] = useState<any[]>([])
  const [models, setModels] = useState<string[]>([])
  const [isValidating, setIsValidating] = useState(false)
  const [isValid, setIsValid] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (isOpen) {
      loadProviders()
      setError(null)
      if (initialSettings) {
        setProvider(initialSettings.provider)
        setApiKey(initialSettings.apiKey)
        setModel(initialSettings.model)
        setStep('model')
        // Pre-load models for the current provider
        loadModels(initialSettings.provider, initialSettings.apiKey)
      }
    }
  }, [isOpen, initialSettings])

  const loadProviders = async () => {
    const data = await getProviders()
    setProviders(data)
  }

  const handleProviderSelect = async (selectedProvider: string) => {
    setProvider(selectedProvider)
    const selected = providers.find(p => p.id === selectedProvider)
    if (selected && !selected.requires_api_key) {
      // Skip API key step for Ollama
      setStep('model')
      loadModels(selectedProvider, '')
    } else {
      setStep('apiKey')
    }
  }

  const handleApiKeySubmit = async () => {
    setIsValidating(true)
    const valid = await validateKey({ provider, model: '', apiKey })
    setIsValid(valid)
    setIsValidating(false)

    if (valid) {
      setStep('model')
      loadModels(provider, apiKey)
    }
  }

  const loadModels = async (prov: string, key: string) => {
    setLoading(true)
    setError(null)
    try {
      const modelsList = await getModels({ provider: prov, model: '', apiKey: key })
      setModels(modelsList)
      if (modelsList.length > 0) {
        setModel(modelsList[0])
      } else {
        setError('No models available for this provider')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch models')
    } finally {
      setLoading(false)
    }
  }

  const handleSave = () => {
    onSave({ provider, model, apiKey })
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-background rounded-lg shadow-lg max-w-md w-full mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="text-lg font-semibold">Configure LLM Settings</h2>
          <button onClick={onClose} className="p-1 hover:bg-muted rounded">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Step 1: Select Provider */}
          {step === 'provider' && (
            <div className="space-y-4">
              <h3 className="font-medium">Select LLM Provider</h3>
              <div className="space-y-2">
                {providers.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => handleProviderSelect(p.id)}
                    className="w-full p-4 border border-border rounded-lg hover:bg-muted transition-colors text-left"
                  >
                    <div className="font-medium">{p.name}</div>
                    <div className="text-sm text-muted-foreground">
                      {p.requires_api_key ? 'Requires API key' : 'No API key needed'}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 2: Enter API Key */}
          {step === 'apiKey' && (
            <div className="space-y-4">
              <h3 className="font-medium">Enter API Key</h3>
              <p className="text-sm text-muted-foreground">
                Enter your {providers.find(p => p.id === provider)?.name} API key
              </p>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-..."
                className="w-full p-3 border border-border rounded-lg bg-background"
              />
              
              {isValid === true && (
                <div className="flex items-center gap-2 text-green-600 text-sm">
                  <Check className="w-4 h-4" />
                  API key validated successfully
                </div>
              )}
              
              {isValid === false && (
                <div className="flex items-center gap-2 text-red-600 text-sm">
                  <AlertCircle className="w-4 h-4" />
                  Invalid API key
                </div>
              )}

              <div className="flex gap-2">
                <button
                  onClick={() => setStep('provider')}
                  className="flex-1 p-2 border border-border rounded-lg hover:bg-muted"
                >
                  Back
                </button>
                <button
                  onClick={handleApiKeySubmit}
                  disabled={!apiKey || isValidating}
                  className="flex-1 p-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50"
                >
                  {isValidating ? 'Validating...' : 'Continue'}
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Select Model */}
          {step === 'model' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-medium">Select Model</h3>
                <div className="flex gap-4">
                  {initialSettings && providers.find(p => p.id === provider)?.requires_api_key && (
                    <button
                      onClick={() => setStep('apiKey')}
                      className="text-sm text-primary hover:underline"
                    >
                      Change API Key
                    </button>
                  )}
                  {initialSettings && (
                    <button
                      onClick={() => setStep('provider')}
                      className="text-sm text-primary hover:underline"
                    >
                      Change Provider
                    </button>
                  )}
                </div>
              </div>
              {error && (
                <div className="flex items-center gap-2 text-red-600 text-sm bg-red-50 p-3 rounded-lg">
                  <AlertCircle className="w-4 h-4" />
                  {error}
                </div>
              )}
              {loading ? (
                <div className="text-center py-4">Loading models...</div>
              ) : models && models.length > 0 ? (
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {models.map((m) => (
                    <button
                      key={m}
                      onClick={() => setModel(m)}
                      className={`w-full p-3 border rounded-lg text-left transition-colors ${
                        model === m
                          ? 'border-primary bg-primary/10'
                          : 'border-border hover:bg-muted'
                      }`}
                    >
                      {m}
                    </button>
                  ))}
                </div>
              ) : (
                <div className="text-center py-4 text-muted-foreground space-y-3">
                  <p>{error ? 'Failed to fetch models' : 'No models available'}</p>
                  {error && (
                    <button
                      onClick={() => loadModels(provider, apiKey)}
                      className="text-primary hover:underline"
                    >
                      Retry
                    </button>
                  )}
                </div>
              )}

              <div className="flex gap-2">
                {!providers.find(p => p.id === provider)?.requires_api_key && (
                  <button
                    onClick={() => setStep('provider')}
                    className="flex-1 p-2 border border-border rounded-lg hover:bg-muted"
                  >
                    Back
                  </button>
                )}
                <button
                  onClick={handleSave}
                  disabled={!model}
                  className="flex-1 p-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50"
                >
                  Save Settings
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
