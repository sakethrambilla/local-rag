'use client'

import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useAppDispatch, useAppSelector } from '@/store'
import {
  setOpenaiApiKey,
  setAnthropicApiKey,
  setGeminiApiKey,
  setAccuracyMode,
  selectAccuracyMode,
} from '@/store/settingsSlice'
import { useGetHealthQuery, useGetSettingsQuery, useUpdateSettingsMutation } from '@/store/settingsApi'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { ModelSelector } from './ModelSelector'
import { EmbeddingSelector } from './EmbeddingSelector'
import { AlertTriangle, Eye, EyeOff, Check } from 'lucide-react'
import { apiKeysSchema, type ApiKeys } from '@/schema/settingsSchema'
import type { AccuracyMode } from '@/types'

interface SettingsPanelProps {
  open: boolean
  onClose: () => void
}

const ACCURACY_OPTIONS: { value: AccuracyMode; label: string; description: string }[] = [
  { value: 'fast',     label: 'Fast',        description: 'BM25 · top-3 · no HyDE' },
  { value: 'balanced', label: 'Balanced',    description: 'Hybrid + MMR reranking' },
  { value: 'max',      label: 'Max Quality', description: 'HyDE + hybrid + MMR · slower' },
]

function ApiKeyField({
  label,
  fieldName,
  placeholder,
  register,
  error,
}: {
  label: string
  fieldName: keyof ApiKeys
  placeholder: string
  register: ReturnType<typeof useForm<ApiKeys>>['register']
  error?: string
}) {
  const [show, setShow] = useState(false)
  return (
    <div className="space-y-1.5">
      <label className="text-[11px] font-medium text-muted-foreground">{label}</label>
      <div className="flex gap-1.5">
        <Input
          type={show ? 'text' : 'password'}
          placeholder={placeholder}
          className="h-8 rounded-xl text-[12px] font-mono"
          {...register(fieldName)}
        />
        <button
          type="button"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-border text-muted-foreground transition-colors hover:text-foreground"
          onClick={() => setShow((v) => !v)}
        >
          {show ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
        </button>
      </div>
      {error && <p className="text-[11px] text-destructive">{error}</p>}
    </div>
  )
}

function Section({ title, children, description }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60">{title}</p>
        {description && <p className="mt-0.5 text-[11px] text-muted-foreground">{description}</p>}
      </div>
      {children}
    </div>
  )
}

export function SettingsPanel({ open, onClose }: SettingsPanelProps) {
  const dispatch = useAppDispatch()
  const accuracyMode = useAppSelector(selectAccuracyMode)
  const { data: health } = useGetHealthQuery()
  const { data: settings } = useGetSettingsQuery()
  const [updateSettings, { isLoading: isSaving }] = useUpdateSettingsMutation()

  const {
    register,
    handleSubmit,
    formState: { errors, isDirty },
    reset,
  } = useForm<ApiKeys>({
    resolver: zodResolver(apiKeysSchema),
    defaultValues: { openai_api_key: '', anthropic_api_key: '', gemini_api_key: '' },
  })

  const onSubmit = async (data: ApiKeys) => {
    const { openai_api_key, anthropic_api_key, gemini_api_key } = data
    if (openai_api_key) dispatch(setOpenaiApiKey(openai_api_key))
    if (anthropic_api_key) dispatch(setAnthropicApiKey(anthropic_api_key))
    if (gemini_api_key) dispatch(setGeminiApiKey(gemini_api_key))
    await updateSettings({
      ...(openai_api_key && { openai_api_key }),
      ...(anthropic_api_key && { anthropic_api_key }),
      ...(gemini_api_key && { gemini_api_key }),
    })
    reset()
  }

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="flex w-[420px] flex-col gap-0 overflow-hidden p-0 sm:w-[460px]">
        <SheetHeader className="border-b border-border/60 px-5 py-4">
          <SheetTitle className="text-[15px] font-semibold tracking-tight">Settings</SheetTitle>
          <SheetDescription className="text-[12px]">
            Models, embeddings, and API keys
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-7">

          {/* Re-index warning */}
          {health?.reindex_required && (
            <div className="flex items-start gap-2.5 rounded-xl border border-amber-200/60 bg-amber-50/80 px-3.5 py-3 text-[12px] text-amber-800 dark:border-amber-700/30 dark:bg-amber-900/20 dark:text-amber-300">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <div>
                <p className="font-medium">Re-index required</p>
                <p className="mt-0.5 opacity-80">
                  {health.reindex_message ?? 'Embedding model changed. Re-upload documents to rebuild the index.'}
                </p>
              </div>
            </div>
          )}

          {/* Storage stats */}
          {health?.storage && (
            <Section title="Storage">
              <div className="grid grid-cols-2 gap-x-4 gap-y-2.5 rounded-xl border border-border/60 bg-muted/30 px-4 py-3.5">
                {[
                  { label: 'Documents', value: health.storage.total_documents },
                  { label: 'Chunks', value: health.storage.total_chunks.toLocaleString() },
                  { label: 'Vector backend', value: health.vector_backend },
                  { label: 'Embedding', value: health.embedding_model.split('/').pop() ?? health.embedding_model },
                ].map(({ label, value }) => (
                  <div key={label}>
                    <p className="text-[10px] text-muted-foreground">{label}</p>
                    <p className="truncate text-[13px] font-medium">{value}</p>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* LLM */}
          <Section title="Language Model">
            <ModelSelector />
          </Section>

          {/* Embeddings */}
          <Section
            title="Embedding Model"
            description="Changing embeddings requires re-indexing all documents."
          >
            <EmbeddingSelector />
          </Section>

          {/* Accuracy */}
          <Section title="Accuracy Mode">
            <div className="space-y-1">
              {ACCURACY_OPTIONS.map((opt) => {
                const isSelected = accuracyMode === opt.value
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => dispatch(setAccuracyMode(opt.value))}
                    className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
                      isSelected ? 'bg-foreground text-background' : 'hover:bg-accent'
                    }`}
                  >
                    <div className="flex-1">
                      <p className="text-[13px] font-medium">{opt.label}</p>
                      <p className={`text-[11px] ${isSelected ? 'text-background/60' : 'text-muted-foreground'}`}>
                        {opt.description}
                      </p>
                    </div>
                    {isSelected && <Check className="h-3.5 w-3.5 shrink-0" />}
                  </button>
                )
              })}
            </div>
          </Section>

          {/* Results per query */}
          <Section
            title="Results per Query"
            description="Number of source chunks returned to the LLM. Higher values improve multi-file coverage but use more context."
          >
            <div className="flex gap-2">
              {[3, 5, 8, 10].map((n) => {
                const current = settings?.final_top_k ?? 5
                const isSelected = current === n
                return (
                  <button
                    key={n}
                    type="button"
                    onClick={() => updateSettings({ final_top_k: n })}
                    className={`flex flex-1 flex-col items-center rounded-xl px-3 py-2.5 transition-colors ${
                      isSelected ? 'bg-foreground text-background' : 'border border-border/60 hover:bg-accent'
                    }`}
                  >
                    <span className="text-[15px] font-semibold">{n}</span>
                    <span className={`text-[10px] ${isSelected ? 'text-background/60' : 'text-muted-foreground'}`}>
                      {n === 3 ? 'focused' : n === 5 ? 'default' : n === 8 ? 'broad' : 'max'}
                    </span>
                  </button>
                )
              })}
            </div>
          </Section>

          {/* Min chunk score */}
          <Section
            title="Relevance Threshold"
            description="Minimum reranker score for a chunk to be sent to the LLM. Chunks scoring below this are dropped. Off = include all chunks."
          >
            <div className="flex gap-2">
              {([
                { value: 0,    label: 'Off',      sub: 'all chunks' },
                { value: 0.1,  label: '0.1',      sub: 'light' },
                { value: 0.25, label: '0.25',     sub: 'moderate' },
                { value: 0.5,  label: '0.5',      sub: 'strict' },
              ] as const).map(({ value, label, sub }) => {
                const current = settings?.min_chunk_score ?? 0
                const isSelected = current === value
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => updateSettings({ min_chunk_score: value })}
                    className={`flex flex-1 flex-col items-center rounded-xl px-2 py-2.5 transition-colors ${
                      isSelected ? 'bg-foreground text-background' : 'border border-border/60 hover:bg-accent'
                    }`}
                  >
                    <span className="text-[14px] font-semibold">{label}</span>
                    <span className={`text-[10px] ${isSelected ? 'text-background/60' : 'text-muted-foreground'}`}>
                      {sub}
                    </span>
                  </button>
                )
              })}
            </div>
          </Section>

          {/* API Keys */}
          <Section title="API Keys" description="Keys are sent to the backend only, never stored in the browser.">
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
              <ApiKeyField
                label="OpenAI"
                fieldName="openai_api_key"
                placeholder="sk-…"
                register={register}
                error={errors.openai_api_key?.message}
              />
              <ApiKeyField
                label="Anthropic"
                fieldName="anthropic_api_key"
                placeholder="sk-ant-…"
                register={register}
                error={errors.anthropic_api_key?.message}
              />
              <ApiKeyField
                label="Google Gemini"
                fieldName="gemini_api_key"
                placeholder="AIza…"
                register={register}
                error={errors.gemini_api_key?.message}
              />
              <Button
                type="submit"
                size="sm"
                className="rounded-xl"
                disabled={isSaving || !isDirty}
              >
                {isSaving ? 'Saving…' : 'Save keys'}
              </Button>
            </form>
          </Section>

        </div>
      </SheetContent>
    </Sheet>
  )
}
