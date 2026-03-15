"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useAppDispatch, useAppSelector } from "@/store";
import {
  setOpenaiApiKey,
  setAnthropicApiKey,
  setGeminiApiKey,
  setAccuracyMode,
  selectAccuracyMode,
} from "@/store/settingsSlice";
import {
  useGetHealthQuery,
  useGetSettingsQuery,
  useUpdateSettingsMutation,
} from "@/store/settingsApi";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ModelSelector } from "./ModelSelector";
import { EmbeddingSelector } from "./EmbeddingSelector";
import { AlertTriangle, Eye, EyeOff, Check } from "lucide-react";
import { apiKeysSchema, type ApiKeys } from "@/schema/settingsSchema";
import type { AccuracyMode } from "@/types";

const ACCURACY_OPTIONS: {
  value: AccuracyMode;
  label: string;
  description: string;
}[] = [
  { value: "fast", label: "Fast", description: "BM25 · top-3 · no HyDE" },
  {
    value: "balanced",
    label: "Balanced",
    description: "Hybrid + MMR reranking",
  },
  {
    value: "max",
    label: "Max Quality",
    description: "HyDE + hybrid + MMR · slower",
  },
];

function ApiKeyField({
  label,
  fieldName,
  placeholder,
  register,
  error,
}: {
  label: string;
  fieldName: keyof ApiKeys;
  placeholder: string;
  register: ReturnType<typeof useForm<ApiKeys>>["register"];
  error?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium text-muted-foreground">
        {label}
      </label>
      <div className="flex gap-2">
        <Input
          type={show ? "text" : "password"}
          placeholder={placeholder}
          className="h-10 rounded-xl text-sm font-mono"
          {...register(fieldName)}
        />
        <button
          type="button"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border text-muted-foreground transition-colors hover:text-foreground"
          onClick={() => setShow((v) => !v)}
        >
          {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

function Section({
  title,
  children,
  description,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground/60">
          {title}
        </p>
        {description && (
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {children}
    </div>
  );
}

export function SettingsView() {
  const dispatch = useAppDispatch();
  const accuracyMode = useAppSelector(selectAccuracyMode);
  const { data: health } = useGetHealthQuery();
  const { data: settings } = useGetSettingsQuery();
  const [updateSettings, { isLoading: isSaving }] = useUpdateSettingsMutation();

  const {
    register,
    handleSubmit,
    formState: { errors, isDirty },
    reset,
  } = useForm<ApiKeys>({
    resolver: zodResolver(apiKeysSchema),
    defaultValues: {
      openai_api_key: "",
      anthropic_api_key: "",
      gemini_api_key: "",
    },
  });

  const onSubmit = async (data: ApiKeys) => {
    const { openai_api_key, anthropic_api_key, gemini_api_key } = data;
    if (openai_api_key) dispatch(setOpenaiApiKey(openai_api_key));
    if (anthropic_api_key) dispatch(setAnthropicApiKey(anthropic_api_key));
    if (gemini_api_key) dispatch(setGeminiApiKey(gemini_api_key));
    await updateSettings({
      ...(openai_api_key && { openai_api_key }),
      ...(anthropic_api_key && { anthropic_api_key }),
      ...(gemini_api_key && { gemini_api_key }),
    });
    reset();
  };

  return (
    <div className="flex h-full w-full flex-col">
      {/* Header */}
      <div className="border-b border-border/60 px-8 py-5 w-full">
        <h2 className="text-xl font-semibold tracking-tight">Settings</h2>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Models, embeddings, and API keys
        </p>
      </div>

      <div className="flex flex-col w-full h-full overflow-y-auto px-8 py-6">
        <div className="max-w-xl space-y-10">
          {/* Re-index warning */}
          {health?.reindex_required && (
            <div className="flex items-start gap-3 rounded-2xl border border-amber-200/60 bg-amber-50/80 px-4 py-3.5 text-sm text-amber-800 dark:border-amber-700/30 dark:bg-amber-900/20 dark:text-amber-300">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-medium">Re-index required</p>
                <p className="mt-0.5 text-sm opacity-80">
                  {health.reindex_message ??
                    "Embedding model changed. Re-upload documents to rebuild the index."}
                </p>
              </div>
            </div>
          )}

          {/* Storage stats */}
          {health?.storage && (
            <Section title="Storage">
              <div className="grid grid-cols-2 gap-x-6 gap-y-4 rounded-2xl border border-border/60 bg-muted/30 px-5 py-4">
                {[
                  { label: "Documents", value: health.storage.total_documents },
                  {
                    label: "Chunks",
                    value: health.storage.total_chunks.toLocaleString(),
                  },
                  { label: "Vector backend", value: health.vector_backend },
                  {
                    label: "Embedding",
                    value:
                      health.embedding_model.split("/").pop() ??
                      health.embedding_model,
                  },
                ].map(({ label, value }) => (
                  <div key={label}>
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="mt-0.5 truncate text-base font-medium">
                      {value}
                    </p>
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
            <div className="space-y-1.5">
              {ACCURACY_OPTIONS.map((opt) => {
                const isSelected = accuracyMode === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => dispatch(setAccuracyMode(opt.value))}
                    className={`flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left transition-colors ${
                      isSelected
                        ? "bg-foreground text-background"
                        : "hover:bg-accent"
                    }`}
                  >
                    <div className="flex-1">
                      <p className="text-sm font-medium">{opt.label}</p>
                      <p
                        className={`text-xs ${isSelected ? "text-background/60" : "text-muted-foreground"}`}
                      >
                        {opt.description}
                      </p>
                    </div>
                    {isSelected && <Check className="h-4 w-4 shrink-0" />}
                  </button>
                );
              })}
            </div>
          </Section>

          {/* Results per query */}
          <Section
            title="Results per Query"
            description="Number of source chunks returned to the LLM."
          >
            <div className="flex gap-2">
              {[3, 5, 8, 10].map((n) => {
                const current = settings?.final_top_k ?? 5;
                const isSelected = current === n;
                return (
                  <button
                    key={n}
                    type="button"
                    onClick={() => updateSettings({ final_top_k: n })}
                    className={`flex flex-1 flex-col items-center rounded-xl px-3 py-3 transition-colors ${
                      isSelected
                        ? "bg-foreground text-background"
                        : "border border-border/60 hover:bg-accent"
                    }`}
                  >
                    <span className="text-lg font-semibold">{n}</span>
                    <span
                      className={`text-xs ${isSelected ? "text-background/60" : "text-muted-foreground"}`}
                    >
                      {n === 3
                        ? "focused"
                        : n === 5
                          ? "default"
                          : n === 8
                            ? "broad"
                            : "max"}
                    </span>
                  </button>
                );
              })}
            </div>
          </Section>

          {/* API Keys */}
          <Section
            title="API Keys"
            description="Keys are sent to the backend only, never stored in the browser."
          >
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
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
                className="rounded-xl h-10 px-5"
                disabled={isSaving || !isDirty}
              >
                {isSaving ? "Saving…" : "Save keys"}
              </Button>
            </form>
          </Section>
        </div>
      </div>
    </div>
  );
}
