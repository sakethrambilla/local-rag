'use client'

import dynamic from 'next/dynamic'

const DocumentsView = dynamic(
  () => import('@/components/upload/DocumentsView').then((m) => ({ default: m.DocumentsView })),
  { ssr: false }
)

export default function DocumentsPage() {
  return <DocumentsView />
}
