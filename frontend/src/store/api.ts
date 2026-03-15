import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'

export const api = createApi({
  reducerPath: 'api',
  baseQuery: fetchBaseQuery({
    baseUrl: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
  }),
  tagTypes: ['Document', 'Session', 'Settings', 'Project', 'GeneratedDocument', 'GeneratedDocumentVersion'],
  endpoints: () => ({}),
})
