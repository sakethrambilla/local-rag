import type { DocumentType } from '@/types/documents'

const GENERATION_PATTERNS = [
  /\bgenerate\b.{0,30}\b(brd|sow|prd|document|doc|report|plan|brief)\b/i,
  /\bcreate\b.{0,30}\b(brd|sow|prd|document|report)\b.{0,30}\b(for|about|based on)\b/i,
  /\bwrite\b.{0,30}\b(brd|sow|prd|document|report)\b/i,
  /\bdraft\b.{0,30}\b(brd|sow|prd|document)\b/i,
  /\b(business requirements|statement of work|product requirements)\b/i,
]

const BRD_PATTERNS = [/\bbrd\b/i, /\bbusiness requirements?\b/i]
const SOW_PATTERNS = [/\bsow\b/i, /\bstatement of work\b/i]
const PRD_PATTERNS = [/\bprd\b/i, /\bproduct requirements?\b/i]

function detectDocumentType(text: string): DocumentType {
  if (BRD_PATTERNS.some((p) => p.test(text))) return 'brd'
  if (SOW_PATTERNS.some((p) => p.test(text))) return 'sow'
  if (PRD_PATTERNS.some((p) => p.test(text))) return 'prd'
  return 'custom'
}

export interface DocIntentResult {
  isGeneration: boolean
  documentType: DocumentType
}

export function detectDocumentIntent(text: string): DocIntentResult {
  const isGeneration = GENERATION_PATTERNS.some((p) => p.test(text))
  const documentType = isGeneration ? detectDocumentType(text) : 'custom'
  return { isGeneration, documentType }
}
