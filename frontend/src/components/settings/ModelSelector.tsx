'use client'

import { useListLlmModelsQuery, useUpdateSettingsMutation } from '@/store/settingsApi'
import { useAppDispatch, useAppSelector } from '@/store'
import { setLlmModel, selectLlmModel } from '@/store/settingsSlice'
import { Skeleton } from '@/components/ui/skeleton'
import { Key, Cpu, Check } from 'lucide-react'

function splitModelId(id: string): { llm_provider: string; llm_model: string } {
  const slash = id.indexOf('/')
  if (slash === -1) return { llm_provider: id, llm_model: id }
  return { llm_provider: id.slice(0, slash), llm_model: id.slice(slash + 1) }
}

function isLocalProvider(provider: string) {
  return provider === 'local' || provider === 'ollama'
}

export function ModelSelector() {
  const dispatch = useAppDispatch()
  const selectedModel = useAppSelector(selectLlmModel)
  const { data: models, isLoading } = useListLlmModelsQuery()
  const [updateSettings] = useUpdateSettingsMutation()

  const handleChange = (id: string) => {
    dispatch(setLlmModel(id))
    const { llm_provider, llm_model } = splitModelId(id)
    updateSettings({ llm_provider, llm_model })
  }

  if (isLoading) {
    return (
      <div className="space-y-1.5">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-10 rounded-xl" />)}
      </div>
    )
  }

  if (!models?.length) {
    return <p className="text-[12px] text-muted-foreground">No models available.</p>
  }

  return (
    <div className="space-y-1">
      {models.map((model) => {
        const isSelected = selectedModel === model.id
        const disabled = !model.available
        return (
          <button
            key={model.id}
            type="button"
            disabled={disabled}
            onClick={() => !disabled && handleChange(model.id)}
            className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
              isSelected
                ? 'bg-foreground text-background'
                : disabled
                  ? 'cursor-not-allowed opacity-40'
                  : 'hover:bg-accent'
            }`}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-[13px] font-medium truncate">{model.name}</span>
                {isLocalProvider(model.provider) && (
                  <span className={`flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[10px] ${isSelected ? 'bg-background/20 text-background/80' : 'bg-muted text-muted-foreground'}`}>
                    <Cpu className="h-2 w-2" />
                    Local
                  </span>
                )}
                {model.requires_key && (
                  <span className={`flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[10px] ${isSelected ? 'bg-background/20 text-background/80' : 'bg-muted text-muted-foreground'}`}>
                    <Key className="h-2 w-2" />
                    Key
                  </span>
                )}
              </div>
              <p className={`text-[11px] capitalize ${isSelected ? 'text-background/60' : 'text-muted-foreground'}`}>
                {model.provider}
                {model.context_window ? ` · ${(model.context_window / 1000).toFixed(0)}k ctx` : ''}
                {!model.available ? ' · Unavailable' : ''}
              </p>
            </div>
            {isSelected && <Check className="h-3.5 w-3.5 shrink-0" />}
          </button>
        )
      })}
    </div>
  )
}
