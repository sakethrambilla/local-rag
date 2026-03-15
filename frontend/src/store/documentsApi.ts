import { api } from './api'
import type { DocumentInfo, DocumentUploadResponse } from '@/types'

export const documentsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    listDocuments: builder.query<DocumentInfo[], void>({
      query: () => '/documents/',        // trailing slash required
      providesTags: ['Document'],
    }),
    uploadDocument: builder.mutation<DocumentUploadResponse, FormData>({
      query: (formData) => ({
        url: '/documents/upload',        // backend path
        method: 'POST',
        body: formData,
      }),
      invalidatesTags: ['Document', 'Project'],
    }),
    deleteDocument: builder.mutation<void, string>({
      query: (id) => ({
        url: `/documents/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Document'],
    }),
  }),
})

export const {
  useListDocumentsQuery,
  useUploadDocumentMutation,
  useDeleteDocumentMutation,
} = documentsApi
