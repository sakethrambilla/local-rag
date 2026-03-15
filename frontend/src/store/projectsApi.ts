import { api } from './api'

export interface Project {
  id: string
  name: string
  description: string
  doc_count: number
  memory_doc_id: string | null
  created_at: string
  updated_at: string
}

export interface ProjectCreate {
  name: string
  description?: string
}

export interface ProjectUpdate {
  name?: string
  description?: string
}

export interface ProjectDocumentAssign {
  doc_id: string
}

export const projectsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    listProjects: builder.query<Project[], void>({
      query: () => '/projects/',
      transformResponse: (res: { projects: Project[] }) => res.projects,
      providesTags: ['Project'],
    }),
    getProject: builder.query<Project, string>({
      query: (id) => `/projects/${id}`,
      providesTags: (_r, _e, id) => [{ type: 'Project', id }],
    }),
    createProject: builder.mutation<Project, ProjectCreate>({
      query: (body) => ({ url: '/projects/', method: 'POST', body }),
      invalidatesTags: ['Project'],
    }),
    updateProject: builder.mutation<Project, { id: string } & ProjectUpdate>({
      query: ({ id, ...body }) => ({ url: `/projects/${id}`, method: 'PUT', body }),
      invalidatesTags: ['Project'],
    }),
    deleteProject: builder.mutation<void, string>({
      query: (id) => ({ url: `/projects/${id}`, method: 'DELETE' }),
      invalidatesTags: ['Project'],
    }),
    listProjectDocuments: builder.query<import('@/types').DocumentInfo[], string>({
      query: (projectId) => `/projects/${projectId}/documents`,
      providesTags: (_r, _e, projectId) => [{ type: 'Project', id: projectId }, 'Document'],
    }),
    assignDocumentToProject: builder.mutation<void, { projectId: string; docId: string }>({
      query: ({ projectId, docId }) => ({
        url: `/projects/${projectId}/documents`,
        method: 'POST',
        body: { doc_id: docId },
      }),
      invalidatesTags: ['Project', 'Document'],
    }),
    removeDocumentFromProject: builder.mutation<void, { projectId: string; docId: string }>({
      query: ({ projectId, docId }) => ({
        url: `/projects/${projectId}/documents/${docId}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Project', 'Document'],
    }),
  }),
})

export const {
  useListProjectsQuery,
  useGetProjectQuery,
  useCreateProjectMutation,
  useUpdateProjectMutation,
  useDeleteProjectMutation,
  useListProjectDocumentsQuery,
  useAssignDocumentToProjectMutation,
  useRemoveDocumentFromProjectMutation,
} = projectsApi
