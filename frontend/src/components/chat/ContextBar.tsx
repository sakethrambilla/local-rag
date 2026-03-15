'use client'

import { useAppSelector } from '@/store'
import { selectContextStatus, selectSessionId } from '@/store/chatSlice'
import { useCompactSessionMutation } from '@/store/sessionsApi'

export function ContextBar() {
  const contextStatus = useAppSelector(selectContextStatus)
  const sessionId = useAppSelector(selectSessionId)
  const [compactSession, { isLoading }] = useCompactSessionMutation()

  if (!contextStatus) return null
  const { used_tokens, total_tokens, should_warn, should_block } = contextStatus
  if (!should_warn && !should_block) return null

  const usage_pct = total_tokens > 0 ? Math.round((used_tokens / total_tokens) * 100) : 0

  return (
    <div
      className={`flex items-center gap-3 rounded-xl px-3 py-2 text-[12px] ${
        should_block
          ? 'bg-destructive/8 text-destructive'
          : 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400'
      }`}
    >
      {/* Slim progress track */}
      <div className="flex flex-1 items-center gap-2">
        <div
          className={`h-[3px] flex-1 rounded-full ${
            should_block ? 'bg-destructive/20' : 'bg-amber-200/60 dark:bg-amber-700/30'
          }`}
        >
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              should_block ? 'bg-destructive' : 'bg-amber-500'
            }`}
            style={{ width: `${usage_pct}%` }}
          />
        </div>
        <span className="shrink-0 tabular-nums">
          {should_block ? 'Context full' : `${usage_pct}% context used`}
        </span>
      </div>

      {sessionId && (
        <button
          className="shrink-0 text-[11px] underline underline-offset-2 opacity-70 transition-opacity hover:opacity-100 disabled:cursor-not-allowed"
          disabled={isLoading}
          onClick={() => compactSession(sessionId)}
        >
          {isLoading ? 'Compacting…' : 'Compact'}
        </button>
      )}
    </div>
  )
}
