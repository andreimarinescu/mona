import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { useMockApi } from '../../test/mockApi';
import { renderRoute } from '../../test/renderRoute';
import { PEOPLE, ENTITIES, VISITORS_ID } from '../../mocks/seed';
import { CategoryTree } from './CategoryTree';
import { EntityCard } from './EntityCard';
import { EntitiesPage } from './EntitiesPage';
import { fiscalYearEndText, formatSiren, monogram, sortEntities } from './entityView';

describe('EntityCard', () => {
  it('shows masked accounts, fiscal year end, sub-units, people and visibility', async () => {
    await renderRoute(<EntityCard entity={ENTITIES[3]!} documentCount={2} people={PEOPLE} />);
    const card = screen.getByTestId('entity-card');
    expect(card).toHaveTextContent('Banque Lumière •••• 3350');
    expect(card).toHaveTextContent('Crédit Mutuel •••• 7712');
    expect(card).not.toHaveTextContent(/FR76/);
    expect(card).toHaveTextContent('31 December');
    expect(card).toHaveTextContent('Léa · Thomas');
    expect(card).toHaveTextContent('Not applicable');
    expect(within(card).getByText('Personal')).toHaveAttribute('data-visibility', 'personal');
    expect(card).toHaveTextContent('Personal documents stay out of Telegram and accountant exports.');
  });

  it('shows a practice entity with SIREN, legal form and people with their roles', async () => {
    await renderRoute(<EntityCard entity={ENTITIES[0]!} documentCount={16} people={PEOPLE} />);
    const card = screen.getByTestId('entity-card');
    expect(card).toHaveTextContent('SELARL · 16 documents');
    expect(card).toHaveTextContent('000 000 001');
    expect(card).toHaveTextContent('Léa, manager · Camille, assistant');
    expect(within(card).getByText('Practice')).toHaveAttribute('data-visibility', 'practice');
  });

  it('shows Visitors as the visitors area, with its purge delay, and no SIREN or accounts', async () => {
    await renderRoute(<EntityCard entity={ENTITIES[4]!} documentCount={0} people={PEOPLE} visitors={{ purgeAfterHours: 24 }} />);
    const card = screen.getByTestId('entity-card');
    expect(card).toHaveAttribute('data-kind', 'visitors');
    expect(screen.getByTestId('visitors-note')).toHaveTextContent('deleted after 24 hours');
    expect(card).not.toHaveTextContent('SIREN');
    expect(within(card).getByText('Visitors', { selector: 'span' })).toBeInTheDocument();
  });

  it('helpers: monogram, SIREN grouping, fiscal year end, Visitors last', () => {
    expect([monogram('Cabinet Marchand'), monogram('Personnel'), monogram('SCI Les Tilleuls')]).toEqual(['CM', 'PE', 'SL']);
    expect(formatSiren('912408337')).toBe('912 408 337');
    expect(fiscalYearEndText('06-30', 'fr')).toBe('30 juin');
    expect(sortEntities([ENTITIES[4]!, ENTITIES[0]!], VISITORS_ID).map((e) => e.key)).toEqual(['cabinet-marchand', 'visitors']);
  });
});

describe('EntitiesPage', () => {
  useMockApi();

  it('lists the entities with Visitors last and the tab counts', async () => {
    await renderRoute(<EntitiesPage tab="entities" />);
    const cards = await screen.findAllByTestId('entity-card');
    expect(cards.map((c) => c.getAttribute('data-kind'))).toEqual(['practice', 'practice', 'practice', 'personal', 'visitors']);
    expect(screen.getByRole('tab', { name: /Entities/ })).toHaveTextContent('5');
    expect(await screen.findByRole('tab', { name: /Categories/ })).toHaveTextContent('4');
    expect(screen.getByTestId('visitors-note')).toBeInTheDocument();
  });

  it('shows the categories as an ARIA tree with counts, and the editor for the selected one', async () => {
    await renderRoute(<EntitiesPage tab="categories" />, '/entities/categories/tax');
    const tree = await screen.findByRole('tree', { name: 'Categories' });
    const items = within(tree).getAllByRole('treeitem');
    expect(items.length).toBeGreaterThanOrEqual(4);
    expect(items[0]).toHaveAttribute('aria-level', '1');
  });
});

describe('CategoryTree', () => {
  it('selects with Enter, moves with the arrows and opens a category with Right', async () => {
    const cats = ENTITIES.length ? (await import('../../mocks/seed')).CATEGORIES : [];
    const picked: string[] = [];
    await renderRoute(<CategoryTree categories={cats} counts={{ invoices: 8 }} selectedId="bank" onSelect={(id) => picked.push(id)} />);
    const tree = screen.getByRole('tree');
    const invoices = within(tree).getByRole('treeitem', { name: /Received invoices, 8 documents/ });
    expect(within(tree).getByRole('treeitem', { name: /Bank/ })).toHaveAttribute('aria-selected', 'true');
    invoices.focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(invoices).toHaveAttribute('aria-expanded', 'true');
    await userEvent.keyboard('{ArrowDown}');
    expect(within(tree).getByText('Telecom').closest('[role="treeitem"]')).toHaveFocus();
    await userEvent.keyboard('{ArrowLeft}');
    expect(invoices).toHaveFocus();
    await userEvent.keyboard('{Enter}');
    expect(picked).toEqual(['invoices']);
  });
});
