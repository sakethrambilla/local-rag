import { api } from './api'
import type { AppSettings, AppSettingsUpdate, ModelOption, EmbeddingOption, HealthResponse } from '@/types'

export const settingsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getSettings: builder.query<AppSettings, void>({
      query: () => '/settings',
      providesTags: ['Settings'],
    }),
    updateSettings: builder.mutation<AppSettings, AppSettingsUpdate>({
      query: (settings) => ({
        url: '/settings',
        method: 'PUT',
        body: settings,
      }),
      invalidatesTags: ['Settings'],
    }),
    listLlmModels: builder.query<ModelOption[], void>({
      query: () => '/models/llm',
      providesTags: ['Settings'],
    }),
    listEmbeddingModels: builder.query<EmbeddingOption[], void>({
      query: () => '/models/embedding',
      providesTags: ['Settings'],
    }),
    getHealth: builder.query<HealthResponse, void>({
      query: () => '/health',
    }),
  }),
})

export const {
  useGetSettingsQuery,
  useUpdateSettingsMutation,
  useListLlmModelsQuery,
  useListEmbeddingModelsQuery,
  useGetHealthQuery,
} = settingsApi
