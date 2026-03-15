import { z } from "zod"
import { baseSchema } from "./baseSchema"

// Full session entity shape
const sessionSchema = baseSchema.extend({
  title: z.string(),
  messageCount: z.number().int().nonnegative(),
})

// Create: no id/timestamps — backend assigns them
const createSessionSchema = sessionSchema.omit({
  id: true,
  createdAt: true,
  updatedAt: true,
  messageCount: true,
}).partial()  // title is optional; backend auto-generates one

// Rename (inline edit in SessionSidebar)
const renameSessionSchema = z.object({
  title: z
    .string()
    .min(1, "Title cannot be empty")
    .max(100, "Title must be 100 characters or fewer")
    .trim(),
})

// Delete: just needs the UUID
const deleteSessionSchema = z.object({
  id: z.string().uuid("Invalid session ID"),
})

export {
  sessionSchema,
  createSessionSchema,
  renameSessionSchema,
  deleteSessionSchema,
}

export type Session = z.infer<typeof sessionSchema>
export type CreateSession = z.infer<typeof createSessionSchema>
export type RenameSession = z.infer<typeof renameSessionSchema>
export type DeleteSession = z.infer<typeof deleteSessionSchema>
