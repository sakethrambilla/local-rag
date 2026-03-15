import { api } from './api'
import type {
  GeneratedDocumentMeta,
  GeneratedDocumentFull,
  DocumentVersion,
  EditPlan,
  EditPlanRequest,
  ChatWithDocumentRequest,
  ChatWithDocumentResponse,
} from '@/types/documents'

export const generatedDocumentsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    listGeneratedDocuments: builder.query<GeneratedDocumentMeta[], string | null>({
      query: (projectId) =>
        projectId
          ? `/generated-documents/?project_id=${projectId}`
          : '/generated-documents/',
      providesTags: ['GeneratedDocument' as 'GeneratedDocument'],
    }),
    getGeneratedDocument: builder.query<GeneratedDocumentFull, string>({
      query: (id) => `/generated-documents/${id}`,
      providesTags: (_r, _e, id) => [{ type: 'GeneratedDocument' as 'GeneratedDocument', id }],
    }),
    updateDocument: builder.mutation<
      void,
      { id: string; content: string; label?: string }
    >({
      query: ({ id, content, label }) => ({
        url: `/generated-documents/${id}`,
        method: 'PUT',
        body: { content, label },
      }),
      invalidatesTags: (_r, _e, { id }) => [
        { type: 'GeneratedDocument' as 'GeneratedDocument', id },
        'GeneratedDocument' as 'GeneratedDocument',
      ],
    }),
    deleteDocument: builder.mutation<void, string>({
      query: (id) => ({
        url: `/generated-documents/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['GeneratedDocument' as 'GeneratedDocument'],
    }),
    requestEditPlan: builder.mutation<
      EditPlan,
      { id: string } & EditPlanRequest
    >({
      query: ({ id, ...body }) => ({
        url: `/generated-documents/${id}/edit/plan`,
        method: 'POST',
        body,
      }),
    }),
    chatWithDocument: builder.mutation<
      ChatWithDocumentResponse,
      { id: string } & ChatWithDocumentRequest
    >({
      query: ({ id, ...body }) => ({
        url: `/generated-documents/${id}/chat`,
        method: 'POST',
        body,
      }),
    }),
    listVersions: builder.query<DocumentVersion[], string>({
      query: (docId) => `/generated-documents/${docId}/versions`,
      providesTags: (_r, _e, docId) => [
        { type: 'GeneratedDocumentVersion' as 'GeneratedDocumentVersion', id: docId },
      ],
    }),
    getVersion: builder.query<
      { content: string },
      { docId: string; versionId: string }
    >({
      query: ({ docId, versionId }) =>
        `/generated-documents/${docId}/versions/${versionId}`,
    }),
  }),
})

export const {
  useListGeneratedDocumentsQuery,
  useGetGeneratedDocumentQuery,
  useUpdateDocumentMutation,
  useDeleteDocumentMutation,
  useRequestEditPlanMutation,
  useChatWithDocumentMutation,
  useListVersionsQuery,
  useGetVersionQuery,
} = generatedDocumentsApi
