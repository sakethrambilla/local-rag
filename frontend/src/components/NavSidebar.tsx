'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import Image from 'next/image'
import { usePathname } from 'next/navigation'
import { FolderOpen, Settings, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { ThemeToggle } from '@/components/ThemeToggle'

const NAV_ITEMS = [
  { href: '/projects', icon: FolderOpen, label: 'Projects' },
  { href: '/settings', icon: Settings,   label: 'Settings' },
]

export function NavSidebar() {
  const pathname = usePathname()
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    const saved = localStorage.getItem('sidebar-expanded')
    if (saved !== null) setExpanded(saved === 'true')
  }, [])

  const toggle = () => {
    setExpanded(prev => {
      localStorage.setItem('sidebar-expanded', String(!prev))
      return !prev
    })
  }

  return (
    <nav
      className={`flex h-full shrink-0 flex-col border-r border-border/60 bg-sidebar py-3 transition-[width] duration-200 ease-in-out overflow-hidden ${
        expanded ? 'w-52' : 'w-14'
      }`}
    >
      {/* Logo + toggle */}
      <div className={`mb-3 flex h-10 shrink-0 items-center ${expanded ? 'px-3 justify-between' : 'flex-col gap-1 justify-center'}`}>
        {expanded ? (
          <>
            <Image
              src="/images/logo-fullname.gif"
              alt="LocalRAG"
              width={120}
              height={32}
              unoptimized
              className="h-8 w-auto object-contain"
            />
            <button
              onClick={toggle}
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-foreground/5 hover:text-foreground transition-colors"
            >
              <PanelLeftClose className="h-4 w-4" />
            </button>
          </>
        ) : (
          <button onClick={toggle} className="flex flex-col items-center gap-0.5 group">
            <Image
              src="/images/logo.gif"
              alt="LocalRAG"
              width={28}
              height={28}
              unoptimized
              className="h-7 w-7 object-contain"
            />
            <PanelLeftOpen className="h-3 w-3 text-muted-foreground group-hover:text-foreground transition-colors" />
          </button>
        )}
      </div>

      {/* Nav items */}
      <div className={`flex flex-1 flex-col gap-0.5 ${expanded ? 'px-2' : 'items-center px-2'}`}>
        {NAV_ITEMS.map(({ href, icon: Icon, label }) => {
          const isActive = pathname.startsWith(href)
          const linkEl = (
            <Link
              href={href}
              className={`flex h-9 items-center rounded-xl transition-all whitespace-nowrap ${
                expanded ? 'w-full gap-2.5 px-2.5' : 'w-10 justify-center'
              } ${
                isActive
                  ? 'text-white shadow-sm'
                  : 'text-muted-foreground hover:bg-foreground/5 hover:text-foreground'
              }`}
              style={isActive ? { background: 'var(--brand-gradient)' } : undefined}
            >
              <Icon className="h-[18px] w-[18px] shrink-0" />
              {expanded && <span className="text-sm font-medium">{label}</span>}
            </Link>
          )

          return expanded ? (
            <div key={href}>{linkEl}</div>
          ) : (
            <Tooltip key={href}>
              <TooltipTrigger render={<span />}>
                {linkEl}
              </TooltipTrigger>
              <TooltipContent side="right">{label}</TooltipContent>
            </Tooltip>
          )
        })}
      </div>

      {/* Theme toggle */}
      <div className={`${expanded ? 'px-2' : 'flex justify-center'}`}>
        <ThemeToggle />
      </div>
    </nav>
  )
}
