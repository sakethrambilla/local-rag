import { Skeleton } from '@/components/ui/skeleton'

export default function EditorLoading() {
  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <div className="h-14 border-b flex items-center px-4 gap-4 shrink-0">
        <Skeleton className="h-8 w-24" />
        <Skeleton className="h-6 w-64" />
        <div className="flex-1" />
        <Skeleton className="h-8 w-16" />
        <Skeleton className="h-8 w-20" />
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Editor skeleton */}
        <div className="flex-1 p-8 space-y-4 overflow-hidden">
          <Skeleton className="h-8 w-3/4" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-6 w-1/2 mt-6" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-4/5" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/5" />
          <Skeleton className="h-6 w-2/3 mt-6" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
        </div>

        {/* Chat sidebar skeleton */}
        <div className="w-80 border-l p-4 space-y-3 shrink-0">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <div className="mt-auto pt-4 space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        </div>
      </div>
    </div>
  )
}
