import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import { queryWrapper, useMockApi } from '../../test/mockApi';
import { AccountantExportDialog } from './AccountantExportDialog';

describe('AccountantExportDialog', () => {
  const api = useMockApi({ exportMs: 0 });

  async function open(onClose = vi.fn()) {
    const { Wrapper } = queryWrapper();
    render(<AccountantExportDialog open onClose={onClose} />, { wrapper: Wrapper });
    const dialog = await screen.findByRole('dialog', { name: 'Export for your accountant' });
    await within(dialog).findByTestId('export-count');
    return { dialog, onClose };
  }

  it('renders nothing while closed', () => {
    const { Wrapper } = queryWrapper();
    render(<AccountantExportDialog open={false} onClose={vi.fn()} />, { wrapper: Wrapper });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('offers company entities only: no personal entity, no Visitors', async () => {
    const { dialog } = await open();
    const options = within(within(dialog).getByLabelText('Entity')).getAllByRole('option').map((o) => o.textContent);
    expect(options).toEqual(['Cabinet Marchand', 'SCI Les Tilleuls', 'Atelier Numérique']);
  });

  it('picks the newest fiscal year that has documents and says what is included and what is left out', async () => {
    const { dialog } = await open();
    expect(within(within(dialog).getByLabelText('Fiscal year')).getAllByRole('option').map((o) => o.textContent)).toEqual(['2026', '2025']);
    expect(within(dialog).getByTestId('export-count')).toHaveTextContent('7 documents, as filed, in their folders');
    expect(within(dialog).getByText('CSV index')).toBeInTheDocument();
    expect(within(dialog).getByTestId('export-in-review')).toHaveTextContent('2 documents are left out');
    expect(within(dialog).getByRole('button', { name: 'Export 7 documents' })).toBeEnabled();
    expect(within(dialog).getByText(/Personal entities and Visitors are never included/)).toBeInTheDocument();
  });

  it('switching the year or the entity refreshes the counts', async () => {
    const { dialog } = await open();
    await userEvent.selectOptions(within(dialog).getByLabelText('Fiscal year'), '2025');
    await waitFor(() => expect(within(dialog).queryByTestId('export-in-review')).not.toBeInTheDocument());
    await userEvent.selectOptions(within(dialog).getByLabelText('Entity'), 'Atelier Numérique');
    await waitFor(() => expect(within(dialog).getByTestId('export-count')).toHaveTextContent('3 documents, as filed'));
  });

  it('an entity with nothing filed cannot be built', async () => {
    const { dialog } = await open();
    await userEvent.selectOptions(within(dialog).getByLabelText('Entity'), 'SCI Les Tilleuls');
    expect(await within(dialog).findByText('Nothing is filed for this entity and year yet.')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /^Export/ })).toBeDisabled();
  });

  it('builds, polls while building, and offers the zip and the CSV when ready', async () => {
    const { dialog } = await open();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Export 7 documents' }));
    expect(await within(dialog).findByTestId('export-building')).toHaveTextContent('Building the pack');
    expect(within(dialog).getByLabelText('Entity')).toBeDisabled();
    const ready = await within(dialog).findByTestId('export-ready', undefined, { timeout: 6_000 });
    expect(within(ready).getByRole('link', { name: 'Download the zip' })).toHaveAttribute('href', expect.stringMatching(/^\/api\/exports\/exp_\w+\/zip$/));
    expect(within(ready).getByRole('link', { name: 'Download the CSV index' })).toHaveAttribute('href', expect.stringMatching(/\/csv$/));
    expect(within(ready).getByText('7 documents from Cabinet Marchand, fiscal year 2026.')).toBeInTheDocument();
    expect(api.world().exports.control.failNext).toBe(false);
  }, 10_000);

  it('a build that fails says so and can be tried again', async () => {
    api.world().exports.control.failNext = true;
    const { dialog } = await open();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Export 7 documents' }));
    expect(await within(dialog).findByText("The export didn't finish", undefined, { timeout: 6_000 })).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Try again' }));
    await userEvent.click(await within(dialog).findByRole('button', { name: 'Export 7 documents' }));
    expect(await within(dialog).findByTestId('export-ready', undefined, { timeout: 6_000 })).toBeInTheDocument();
  }, 20_000);

  it('a refused build stays on the choice with the reason', async () => {
    api.server.use(http.post('/api/exports', () => HttpResponse.json({ error: { code: 'not_allowed', message: 'No.' } }, { status: 403 })));
    const { dialog } = await open();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Export 7 documents' }));
    expect(await within(dialog).findByText("That can't be done here.")).toBeInTheDocument();
    expect(within(dialog).queryByTestId('export-building')).not.toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Export 7 documents' })).toBeEnabled();
  });

  it('Cancel closes without building anything', async () => {
    const { dialog, onClose } = await open();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(api.world().exports.control.failNext).toBe(false);
  });
});
