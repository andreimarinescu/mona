import { RouterProvider, createMemoryHistory, createRootRoute, createRoute, createRouter } from '@tanstack/react-router';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { DocumentSummary, Reason } from '../../data/dto';
import i18n from '../../i18n';
import { ReviewListItem } from './ReviewListItem';

const NOW = Date.parse('2026-10-01T12:00:00Z');

function doc(reasons: Reason[], over: Partial<DocumentSummary> = {}): DocumentSummary {
  return { id: 'doc_a', title: 'Nordtel invoice', reasons, confidence: 64, arrivedAt: '2026-10-01T06:14:00Z', source: 'drop', thumbnailUrl: null, ...over } as DocumentSummary;
}

function renderItem(d: DocumentSummary, corrected = false) {
  const root = createRootRoute({ component: () => <ul><ReviewListItem doc={d} selected={false} checked={false} correctedByYou={corrected} now={NOW} onCheck={() => {}} /></ul> });
  const review = createRoute({ getParentRoute: () => root, path: '/review/$documentId', component: () => null });
  const router = createRouter({ routeTree: root.addChildren([review]), history: createMemoryHistory({ initialEntries: ['/'] }) });
  return render(<RouterProvider router={router} />);
}

describe('ReviewListItem: one ReasonChip per reason', () => {
  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it.each([
    ['low', 'Low confidence · 64%'],
    ['entity', 'Unknown entity'],
    ['conflict', 'Conflicting rule'],
    ['unreadable', 'Unreadable'],
  ] as const)('%s is an icon, a word and its own outline class', async (reason, word) => {
    const { container } = renderItem(doc([reason], reason === 'unreadable' ? { confidence: null } : {}));
    expect(await screen.findByText(word)).toBeInTheDocument();
    expect(container.querySelector(`.mona-reason--${reason}`)).not.toBeNull();
    expect(container.querySelectorAll('.mona-reason')).toHaveLength(1);
  });

  it('shows every reason a document carries', async () => {
    const { container } = renderItem(doc(['low', 'conflict']));
    await screen.findByText('Conflicting rule');
    expect(container.querySelectorAll('.mona-reason')).toHaveLength(2);
  });

  it('words follow the interface language', async () => {
    await i18n.changeLanguage('fr');
    renderItem(doc(['entity']));
    expect(await screen.findByText('Entité inconnue')).toBeInTheDocument();
  });

  it('a document corrected this session shows "Corrected by you" instead of its reason', async () => {
    const { container } = renderItem(doc(['low']), true);
    expect(await screen.findByText('Corrected by you')).toBeInTheDocument();
    expect(container.querySelector('.mona-reason')).toBeNull();
    expect(screen.getByRole('checkbox')).toBeDisabled();
  });

  it('links its title to /review/:id', async () => {
    renderItem(doc(['low']));
    expect(await screen.findByRole('link', { name: 'Nordtel invoice' })).toHaveAttribute('href', '/review/doc_a');
  });
});
