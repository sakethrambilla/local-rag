import { api } from './api'
import type { SessionMeta, Session } from '@/types'

interface UpdateSessionArgs {
  id: string
  title: string
}

export const sessionsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    listSessions: builder.query<SessionMeta[], void>({
      query: () => '/sessions/',
      providesTags: ['Session'],
    }),
    getSession: builder.query<Session, string>({
      query: (id) => `/sessions/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Session', id }],
    }),
    createSession: builder.mutation<SessionMeta, void>({
      query: () => ({
        url: '/sessions/',
        method: 'POST',
        body: { title: 'New Chat' },     // backend requires body
      }),
      invalidatesTags: ['Session'],
    }),
    updateSession: builder.mutation<SessionMeta, UpdateSessionArgs>({
      query: ({ id, title }) => ({
        url: `/sessions/${id}`,
        method: 'PUT',
        body: { title },
      }),
      invalidatesTags: (_result, _error, { id }) => [{ type: 'Session', id }, 'Session'],
      onQueryStarted: async ({ id, title }, { dispatch, queryFulfilled }) => {
        const patch = dispatch(
          sessionsApi.util.updateQueryData('listSessions', undefined, (draft) => {
            const session = draft.find((s) => s.id === id)
            if (session) session.title = title
          })
        )
        try {
          await queryFulfilled
        } catch {
          patch.undo()
        }
      },
    }),
    deleteSession: builder.mutation<void, string>({
      query: (id) => ({
        url: `/sessions/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Session'],
    }),
    compactSession: builder.mutation<void, string>({
      query: (id) => ({
        url: `/sessions/${id}/compact`,
        method: 'POST',
      }),
      invalidatesTags: (_result, _error, id) => [{ type: 'Session', id }],
    }),
  }),
})

export const {
  useListSessionsQuery,
  useGetSessionQuery,
  useCreateSessionMutation,
  useUpdateSessionMutation,
  useDeleteSessionMutation,
  useCompactSessionMutation,
} = sessionsApi
