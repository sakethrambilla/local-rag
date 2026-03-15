import { z } from "zod"

const accuracyModeSchema = z.enum(["fast", "balanced", "max"])

// Full settings entity (mirrors AppSettings from backend)
const settingsSchema = z.object({
  llm_provider: z.string().min(1, "LLM provider is required"),
  llm_model: z.string().min(1, "LLM model is required"),
  embedding_provider: z.string().min(1, "Embedding provider is required"),
  embedding_model: z.string().min(1, "Embedding model is required"),
  accuracy_mode: accuracyModeSchema,
  openai_api_key: z.string().nullable().optional(),
  anthropic_api_key: z.string().nullable().optional(),
  gemini_api_key: z.string().nullable().optional(),
})

const updateSettingsSchema = settingsSchema.partial()

/**
 * API keys sub-form — used in SettingsPanel.
 * Each key is optional; if provided it must match the expected prefix format.
 */
const apiKeysSchema = z.object({
  openai_api_key: z
    .string()
    .refine((v) => v === "" || v.startsWith("sk-"), {
      message: "OpenAI key must start with sk-",
    })
    .optional()
    .or(z.literal("")),
  anthropic_api_key: z
    .string()
    .refine((v) => v === "" || v.startsWith("sk-ant-"), {
      message: "Anthropic key must start with sk-ant-",
    })
    .optional()
    .or(z.literal("")),
  gemini_api_key: z
    .string()
    .optional()
    .or(z.literal("")),
})

export {
  accuracyModeSchema,
  settingsSchema,
  updateSettingsSchema,
  apiKeysSchema,
}

export type AccuracyModeValue = z.infer<typeof accuracyModeSchema>
export type Settings = z.infer<typeof settingsSchema>
export type UpdateSettings = z.infer<typeof updateSettingsSchema>
export type ApiKeys = z.infer<typeof apiKeysSchema>
