'use client'

import { useListEmbeddingModelsQuery, useUpdateSettingsMutation } from '@/store/settingsApi'
import { useAppDispatch, useAppSelector } from '@/store'
import { setEmbeddingModel, selectEmbeddingModel } from '@/store/settingsSlice'
import { Skeleton } from '@/components/ui/skeleton'
import { Key, Cpu, Check } from 'lucide-react'

function splitModelId(id: string): { embedding_provider: string; embedding_model: string } {
  const slash = id.indexOf('/')
  if (slash === -1) return { embedding_provider: id, embedding_model: id }
  return { embedding_provider: id.slice(0, slash), embedding_model: id.slice(slash + 1) }
}

function isLocalProvider(provider: string) {
  return provider === 'local' || provider === 'ollama'
}

export function EmbeddingSelector() {
  const dispatch = useAppDispatch()
  const selectedModel = useAppSelector(selectEmbeddingModel)
  const { data: models, isLoading } = useListEmbeddingModelsQuery()
  const [updateSettings] = useUpdateSettingsMutation()

  const handleChange = (id: string) => {
    dispatch(setEmbeddingModel(id))
    const { embedding_provider, embedding_model } = splitModelId(id)
    updateSettings({ embedding_provider, embedding_model })
  }

  if (isLoading) {
    return (
      <div className="space-y-1.5">
        {[1, 2].map((i) => <Skeleton key={i} className="h-10 rounded-xl" />)}
      </div>
    )
  }

  if (!models?.length) {
    return <p className="text-[12px] text-muted-foreground">No embedding models available.</p>
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
                {model.dimensions} dims · {model.provider}
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
