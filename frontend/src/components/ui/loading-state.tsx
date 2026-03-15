'use client'

import Image from 'next/image'

interface LoadingStateProps {
  message?: string
  fullScreen?: boolean
}

export function LoadingState({
  message = 'Loading...',
  fullScreen = false,
}: LoadingStateProps) {
  const content = (
    <div className="flex flex-col items-center justify-center gap-4">
      <Image
        src="/images/logo.gif"
        alt="Loading"
        width={100}
        height={100}
        unoptimized
        className="object-contain"
      />
      <p
        className="font-semibold"
        style={{ color: '#009dd1', fontSize: '20px', fontFamily: 'Manrope, sans-serif' }}
      >
        {message}
      </p>
    </div>
  )

  if (fullScreen) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center backdrop-blur-sm bg-background/60">
        {content}
      </div>
    )
  }

  return (
    <div className="flex w-full items-center justify-center py-12">
      {content}
    </div>
  )
}
