import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { DocumentFacets } from '../../data/dto';
import { queryWrapper, useMockApi } from '../../test/mockApi';
import { FacetPanel } from './FacetPanel';

const facets: DocumentFacets = {
  entities: [
    { id: 'ent_a', name: 'Cabinet Marchand', count: 9 },
    { id: 'ent_b', name: 'Atelier Numérique', count: 3 },
  ],
  years: [
    { year: 2026, count: 9 },
    { year: 2025, count: 5 },
  ],
  categories: [{ id: 'tax', label: 'Tax', count: 9 }],
  counterparties: [{ id: 'cpt_a', name: 'URSSAF', count: 9 }],
  statuses: [
    { status: 'filed', count: 10 },
    { status: 'review', count: 2 },
  ],
  amount: { min: 100, max: 5000 },
};

describe('FacetPanel', () => {
  useMockApi();

  function setup(filters = {}, scoped = false) {
    const onChange = vi.fn();
    const { Wrapper } = queryWrapper();
    render(<FacetPanel facets={facets} filters={filters} scoped={scoped} onChange={onChange} />, { wrapper: Wrapper });
    return onChange;
  }

  it('picks an entity, a year, a category and a counterparty', async () => {
    const onChange = setup();
    await userEvent.click(screen.getByRole('radio', { name: /Atelier Numérique/ }));
    expect(onChange).toHaveBeenLastCalledWith({ entityId: 'ent_b' });
    await userEvent.click(screen.getByRole('button', { name: '2025 · 5' }));
    expect(onChange).toHaveBeenLastCalledWith({ year: 2025 });
    await userEvent.selectOptions(screen.getByLabelText('Category'), 'tax');
    expect(onChange).toHaveBeenLastCalledWith({ categoryId: 'tax' });
    await userEvent.click(screen.getByRole('combobox', { name: 'Counterparty' }));
    await userEvent.click(screen.getByRole('option', { name: /URSSAF/ }));
    expect(onChange).toHaveBeenLastCalledWith({ counterpartyId: 'cpt_a' });
  });

  it('toggling the selected year clears it', async () => {
    const onChange = setup({ year: 2026 });
    const tag = screen.getByRole('button', { name: '2026 · 9' });
    expect(tag).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(tag);
    expect(onChange).toHaveBeenLastCalledWith({ year: undefined });
  });

  it('commits the amount range on blur, and ignores junk', async () => {
    const onChange = setup();
    await userEvent.type(screen.getByLabelText('Minimum amount'), '1000');
    await userEvent.tab();
    expect(onChange).toHaveBeenLastCalledWith({ amountMin: 1000, amountMax: undefined });
  });

  it('unchecking a status keeps the other two, and all three means no filter', async () => {
    const onChange = setup();
    await userEvent.click(screen.getByRole('checkbox', { name: /Unreadable/ }));
    expect(onChange).toHaveBeenLastCalledWith({ statuses: ['filed', 'review'] });
  });

  it('rechecking the last missing status clears the status filter', async () => {
    const onChange = setup({ statuses: ['filed', 'review'] });
    await userEvent.click(screen.getByRole('checkbox', { name: /Unreadable/ }));
    expect(onChange).toHaveBeenLastCalledWith({ statuses: undefined });
  });

  it('leaves out the entity facet when the shell scope is set', () => {
    setup({}, true);
    expect(screen.queryByRole('radio', { name: /Cabinet Marchand/ })).not.toBeInTheDocument();
    expect(within(screen.getByTestId('facet-panel')).getByLabelText('Category')).toBeInTheDocument();
  });
});
