import { z } from "zod"

const accuracyModeSchema = z.enum(["fast", "balanced", "max"])

/**
 * The chat input form — what the user types before sending a query.
 */
const chatQuerySchema = z.object({
  query: z
    .string()
    .min(1, "Query cannot be empty")
    .max(4000, "Query must be 4000 characters or fewer")
    .trim(),
})

/**
 * Full query request sent to POST /query/stream (includes context from Redux).
 */
const queryRequestSchema = z.object({
  query: z.string().min(1),
  session_id: z.string().uuid().nullable(),
  accuracy_mode: accuracyModeSchema.optional(),
})

export { chatQuerySchema, queryRequestSchema }

export type ChatQuery = z.infer<typeof chatQuerySchema>
export type QueryRequest = z.infer<typeof queryRequestSchema>
