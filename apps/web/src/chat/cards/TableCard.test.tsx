import { waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { TableView } from '../../data/dto';
import { useMockApi } from '../../test/mockApi';
import { renderInApp } from '../../test/renderInApp';
import type { MonaUIMessage } from '../types';
import { MonaMessage } from '../Messages';

const CNV = 'cnv_01j9zq3k8e6y4v2m7c5r1t0b9a';

const VIEW: TableView = {
  id: 'exp_01j9zq3k8e6y4v2m7c5r1t0b9c',
  title: 'Payables',
  columns: [
    { key: 'title', label: 'Title' },
    { key: 'due_date', label: 'Due date' },
    { key: 'payment_iban', label: 'Payment IBAN' },
    { key: 'amount', label: 'Amount' },
    { key: 'reference', label: 'Reference' },
  ],
  rows: [
    { title: 'Contributions, third quarter', due_date: '2026-10-14', payment_iban: 'FR7699999000010123456789012', amount: 1284, currency: 'EUR', reference: null },
    { title: 'Training levy', due_date: null, payment_iban: null, amount: null, currency: null, reference: null },
  ],
  rowsTotal: 2,
  truncated: false,
  emptyColumns: ['reference'],
  lang: 'en',
};

const message = (view: TableView): MonaUIMessage =>
  ({ id: 'msg_t', role: 'assistant', metadata: { conversationId: CNV }, parts: [{ type: 'data-table', id: view.id, data: view }] }) as MonaUIMessage;

const card = () => document.querySelector<HTMLElement>('[data-card="table"]')!;

describe('TableCard (A36)', () => {
  const api = useMockApi();

  it('the data-table part renders on the design system Table: labels, C8 amounts and dates, tabular amounts, blanks as a dash', async () => {
    await renderInApp(<MonaMessage message={message(VIEW)} streaming={false} newest />);
    const c = within(card());
    expect(c.getByRole('heading', { name: 'Payables' })).toBeInTheDocument();
    expect(c.getByTestId('table-meta')).toHaveTextContent('2 documents');
    const table = c.getByRole('table');
    expect(within(table).getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['Title', 'Due date', 'Payment IBAN', 'Amount', 'Reference']);
    const [first, second] = within(table).getAllByRole('row').slice(1);
    expect(within(first!).getAllByRole('cell').map((td) => td.textContent)).toEqual(['Contributions, third quarter', '14 Oct 2026', 'FR7699999000010123456789012', '€1,284.00', '—']);
    expect(within(second!).getAllByRole('cell').map((td) => td.textContent)).toEqual(['Training levy', '—', '—', '—', '—']);
    expect(within(first!).getAllByRole('cell')[3]).toHaveAttribute('data-numeric');
    expect(c.getByTestId('table-empty-columns')).toHaveTextContent('Blank for every document: Reference.');
    const group = c.getByRole('group', { name: 'Download as' });
    expect(within(group).getAllByRole('button').map((b) => b.textContent)).toEqual(['CSV', 'Excel', 'Word']);
  });

  it('"showing 50 of N" when there are more rows than the card holds, the 500 cut, and no blank-column note when every column has data', async () => {
    const rows = Array.from({ length: 50 }, (_, i) => ({ title: `Doc ${i}` }));
    await renderInApp(<MonaMessage message={message({ ...VIEW, columns: [VIEW.columns[0]!], rows, rowsTotal: 500, truncated: true, emptyColumns: [], lang: 'fr' })} streaming={false} newest />);
    const c = within(card());
    expect(c.getByTestId('table-meta')).toHaveTextContent('Showing 50 of 500');
    expect(c.getByText('Only the first 500 documents are in this table.')).toBeInTheDocument();
    expect(c.queryByTestId('table-empty-columns')).toBeNull();
    expect(c.getByTestId('table-rows')).toHaveAttribute('lang', 'fr');
  });

  it('Download as Excel makes the file from the table, downloads it, and notes it in the conversation', async () => {
    const world = api.world();
    const ids = [...world.docs.values()].filter((d) => d.summary.dueDate && !d.deleted).map((d) => d.summary.id);
    const view = world.exports.inline('Payables', ids, ['title', 'due_date']);
    const created = vi.fn(() => 'blob:xlsx');
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() }));
    await renderInApp(<MonaMessage message={message(view)} streaming={false} newest />, { conversationId: CNV });
    await userEvent.click(within(card()).getByRole('button', { name: 'Excel' }));
    await waitFor(() => expect(created).toHaveBeenCalledTimes(1));
    expect(world.notes).toEqual([expect.objectContaining({ conversationId: CNV, kind: 'table.download', text: `Downloaded the table "Payables" as XLSX (${ids.length} rows).` })]);
  });

  it('Refresh reads the table again; once none of its documents is left it says so and offers no download', async () => {
    const world = api.world();
    const [doc] = [...world.docs.values()].filter((d) => d.summary.dueDate && !d.deleted);
    const view = world.exports.inline('Payables', [doc!.summary.id], ['title']);
    await renderInApp(<MonaMessage message={message(view)} streaming={false} newest />);
    expect(within(card()).getByRole('table')).toHaveTextContent(doc!.summary.title);
    doc!.deleted = true;
    await userEvent.click(within(card()).getByRole('button', { name: 'Refresh' }));
    expect(await within(card()).findByRole('status')).toHaveTextContent('None of these documents is in the archive any more.');
    expect(within(card()).queryByRole('table')).toBeNull();
    expect(within(card()).queryByRole('group', { name: 'Download as' })).toBeNull();
  });
});
