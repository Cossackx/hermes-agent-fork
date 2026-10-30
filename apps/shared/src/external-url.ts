/**
 * Which URLs Desktop hands to a browser when asked to open something
 * externally. Electron's `openExternalUrl` (shell.openExternal) and the
 * browser-hosted bridge (window.open) share this one rule, so an agent- or
 * tool-supplied `javascript:` or custom-scheme link is refused on both hosts.
 *
 * `file:` is its own kind: only a host with a local file opener may act on it.
 */

const WEB_PROTOCOLS = new Set(['http:', 'https:', 'mailto:'])

/**
 * `obsidian://open?vault=<name>&file=<path>` is the one custom scheme Desktop
 * opens: a vault deep link an agent hands the user. Only that host and those two
 * query keys, no credentials/port/path/fragment, no control characters, no
 * malformed percent-escapes; anything else stays refused like any custom scheme.
 */
export function isSafeObsidianOpenUrl(rawUrl: string): boolean {
  if (/\p{Cc}/u.test(rawUrl) || /%(?![\da-f]{2})/i.test(rawUrl)) {
    return false
  }

  let url: URL

  try {
    url = new URL(rawUrl)
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

  const params = new URLSearchParams(url.search)
  const vault = params.get('vault')
  const file = params.get('file')
  const keys = [...params.keys()]

  return Boolean(
    vault?.trim() &&
      file?.trim() &&
      keys.every(key => key === 'vault' || key === 'file') &&
      new Set(keys).size === keys.length &&
      !/\p{Cc}/u.test(vault) &&
      !/\p{Cc}/u.test(file)
  )
}

export interface ExternalUrlTarget {
  kind: 'file' | 'web'
  /** `web`: the normalized URL. `file`: the trimmed input, left for the host's file opener to parse. */
  url: string
}

/** Classify an external URL; null for empty, malformed or unsupported-scheme input. */
export function externalUrlTarget(rawUrl: string): ExternalUrlTarget | null {
  const raw = String(rawUrl || '').trim()

  if (!raw) {
    return null
  }

  let parsed: URL

  try {
    parsed = new URL(raw)
  } catch {
    return null
  }

  if (parsed.protocol === 'file:') {
    return { kind: 'file', url: raw }
  }

  if (WEB_PROTOCOLS.has(parsed.protocol)) {
    return { kind: 'web', url: parsed.toString() }
  }

  return isSafeObsidianOpenUrl(raw) ? { kind: 'web', url: raw } : null
}
