import { z } from "zod"

/**
 * Common fields present on every persisted entity returned by the backend.
 * All timestamps are Unix epoch seconds (number), not ISO strings.
 */
export const baseSchema = z.object({
  id: z.string().uuid(),
  createdAt: z.number().int().positive(),
  updatedAt: z.number().int().positive(),
})

export type Base = z.infer<typeof baseSchema>
