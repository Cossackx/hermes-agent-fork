import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { MarkdownTextContent } from './markdown-text'

describe('Markdown Obsidian links', () => {
  afterEach(cleanup)

  it('renders a validated Obsidian open link and hands it to external open on click', async () => {
    const openExternal = vi.fn()

    Object.assign(window, { hermesDesktop: { openExternal } })
    render(
      <MarkdownTextContent isRunning={false} text="[Open note](obsidian://open?vault=Example&file=notes%2Fhello.md)" />
    )

    const link = await screen.findByRole('link', { name: 'Open note' })
    expect(link.getAttribute('href')).toBe('obsidian://open?vault=Example&file=notes%2Fhello.md')
    expect(screen.queryByText(/blocked/)).toBeNull()

    fireEvent.click(link)
    expect(openExternal).toHaveBeenCalledWith('obsidian://open?vault=Example&file=notes%2Fhello.md')
  })

  it.each([
    'obsidian://open?vault=Example&file=%ZZ',
    'obsidian://open?vault=Example&file=%',
    'obsidian://open?vault=Example&file=%2',
    'obsidian://new?vault=Example',
    'obsidian://open?file=notes%2Fhello.md',
    'obsidian://open?vault=Example&file=notes.md&evil=1',
    'obsidian://open?vault=Example&file=notes.md&file=other.md',
    'obsidian://open?vault=Example&file=notes.md%0A',
    'obsidian://open@attacker.example?vault=Example&file=notes.md',
    'obsidian://open?vault=Example&file=notes.md#fragment',
    'vscode://file/notes.md',
    'javascript:alert(1)'
  ])('does not authorize malformed or unsupported links: %s', async href => {
    const { container } = render(<MarkdownTextContent isRunning={false} text={`[link](${href})`} />)
    await new Promise(resolve => setTimeout(resolve, 100))
    expect(container.querySelector('a')).toBeNull()
  })

  const md = '[Open note](obsidian://open?vault=Example&file=notes%2Fhello.md)'

  it('leaves inline code untouched', async () => {
    const { container } = render(<MarkdownTextContent isRunning={false} text={`\`${md}\``} />)
    await waitFor(() => expect(container.querySelector('code')?.textContent).toBe(md))
  })

  it('leaves fenced code untouched', async () => {
    const { container } = render(<MarkdownTextContent isRunning={false} text={'```text\n' + md + '\n```'} />)
    await waitFor(() => expect(container.textContent).toContain(md))
    expect(container.textContent).not.toContain('#hermes-obsidian/')
  })
})
