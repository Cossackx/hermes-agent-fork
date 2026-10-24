const OBSIDIAN_MARKDOWN_PREFIX = '#hermes-obsidian/'

function isSafeObsidianOpenUrl(value: string): boolean {
  if (/[\u0000-\u001f\u007f]/.test(value)) {
    return false
  }

  let url: URL

  try {
    url = new URL(value)
  } catch {
    return false
  }

  if (
    url.protocol !== 'obsidian:' ||
    url.hostname.toLowerCase() !== 'open' ||
    url.username ||
    url.password ||
    url.port ||
    (url.pathname !== '' && url.pathname !== '/') ||
    url.hash
  ) {
    return false
  }

  try {
    const params = new URLSearchParams(url.search)
    const vault = params.get('vault')
    const file = params.get('file')

    return Boolean(
      vault?.trim() &&
        file?.trim() &&
        [...params.keys()].every(key => key === 'vault' || key === 'file') &&
        new Set(params.keys()).size === [...params.keys()].length &&
        !/[\u0000-\u001f\u007f]/.test(vault) &&
        !/[\u0000-\u001f\u007f]/.test(file)
    )
  } catch {
    return false
  }
}

type MarkdownNode = {
  children?: MarkdownNode[]
  type?: string
  url?: unknown
}

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
