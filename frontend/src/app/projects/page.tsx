'use client'

import dynamic from 'next/dynamic'

const ProjectsView = dynamic(
  () => import('@/components/projects/ProjectsView').then((m) => ({ default: m.ProjectsView })),
  { ssr: false }
)

export default function ProjectsPage() {
  return <ProjectsView />
}
