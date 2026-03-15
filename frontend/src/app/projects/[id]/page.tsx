'use client'

import { use } from 'react'
import dynamic from 'next/dynamic'

const ProjectDetailPage = dynamic(
  () => import('@/components/projects/ProjectDetailPage').then((m) => ({ default: m.ProjectDetailPage })),
  { ssr: false }
)

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return <ProjectDetailPage projectId={id} />
}
