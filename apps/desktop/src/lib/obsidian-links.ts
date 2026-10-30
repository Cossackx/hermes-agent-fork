import { isSafeObsidianOpenUrl } from '@hermes/shared'

const OBSIDIAN_MARKDOWN_PREFIX = '#hermes-obsidian/'

export function obsidianMarkdownHref(target: string): string | null {
  return isSafeObsidianOpenUrl(target) ? `${OBSIDIAN_MARKDOWN_PREFIX}${encodeURIComponent(target)}` : null
}

export function obsidianTargetFromMarkdownHref(href?: string): string | null {
  if (!href?.startsWith(OBSIDIAN_MARKDOWN_PREFIX)) {
    return null
  }

  try {
    const target = decodeURIComponent(href.slice(OBSIDIAN_MARKDOWN_PREFIX.length))

    return isSafeObsidianOpenUrl(target) ? target : null
  } catch {
    return null
  }
}

export function rewriteObsidianMarkdownLinks(markdown: string): string {
  return markdown.replace(/(\]\()(<?)(obsidian:\/\/[^\s)>]+)(>?)(\))/gi, (raw, before, open, target, close, after) => {
    const href = obsidianMarkdownHref(target)

    return href ? `${before}${open}${href}${close}${after}` : raw
  })
}
