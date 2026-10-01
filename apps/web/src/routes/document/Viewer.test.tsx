import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PdfFrameHandle, PdfFrameProps } from '../../pdfjs/PdfFrame';
import { queryWrapper, useMockApi } from '../../test/mockApi';
import { Viewer } from './DocumentPage';

const frame = vi.hoisted(() => ({ find: vi.fn(async () => undefined), props: [] as unknown[] }));

vi.mock('../../pdfjs/PdfFrame', async () => {
  const React = await import('react');
  return {
    PdfFrame: (props: PdfFrameProps) => {
      frame.props.push({ file: props.file, page: props.page, query: props.query });
      React.useImperativeHandle(props.handle, () => ({ find: frame.find }) as PdfFrameHandle);
      return React.createElement('div', { 'data-testid': 'pdf-frame' });
    },
  };
});

describe('the viewer', () => {
  const api = useMockApi();

  beforeEach(() => {
    frame.find.mockClear();
    frame.props.length = 0;
  });

  async function open(title: string, search: Parameters<typeof Viewer>[0]['search'] = {}) {
    const world = api.world();
    const summary = [...world.docs.values()].find((d) => d.summary.title === title)!.summary;
    const doc = world.document(summary.id);
    const { Wrapper } = queryWrapper();
    render(<Viewer doc={doc} search={search} />, { wrapper: Wrapper });
    return doc;
  }

  const field = (key: string) => screen.getByTestId('side-panel').querySelector<HTMLElement>(`[data-field="${key}"]`)!;

  it('Show on page sends the findQuery with the evidence page, never the quote', async () => {
    await open('Call for contributions, Q3 2026');
    const amount = field('amount');
    expect(amount.querySelector('q')).toHaveTextContent('Montant à payer 1 284,00 €');
    await userEvent.click(within(amount).getByRole('button', { name: 'Show on page: Amount' }));
    expect(frame.find).toHaveBeenCalledTimes(1);
    expect(frame.find).toHaveBeenCalledWith('1 284,00', 1);
    expect(frame.find).not.toHaveBeenCalledWith('Montant à payer 1 284,00 €', expect.anything());
  });

  it('falls back to the value when the field has no findQuery', async () => {
    await open('Call for contributions, Q3 2026');
    await userEvent.click(within(field('addressee')).getByRole('button', { name: /Show on page/ }));
    expect(frame.find).toHaveBeenCalledWith('Cabinet dentaire Exemple', 1);
  });

  it('marks the active field, and the quote language when it differs from the interface', async () => {
    await open('Call for contributions, Q3 2026');
    await userEvent.click(within(field('issuer')).getByRole('button', { name: /Show on page: Issuer/ }));
    expect(within(field('issuer')).getByRole('button', { name: /Show on page: Issuer/ })).toHaveTextContent('Showing');
    expect(within(field('issuer')).getByRole('button', { name: /Show on page: Issuer/ })).toHaveAttribute('aria-pressed', 'true');
    expect(within(field('amount')).getByRole('button', { name: /Show on page: Amount/ })).toHaveTextContent('Show on page');
    expect(field('amount').querySelector('q')).toHaveAttribute('lang', 'fr');
  });

  it('hands the deep link to the PDF: page, the file and q', async () => {
    const doc = await open('Call for contributions, Q3 2026', { page: 9, q: '1 284,00', field: 'amount' });
    expect(frame.props.at(-1)).toEqual({ file: doc.pdfUrl, page: 1, query: '1 284,00' });
    expect(document.activeElement).toBe(field('amount'));
  });

  it('shows no PDF while a document is processing, and no PDF for an unreadable one', async () => {
    const world = api.world();
    const processing = [...world.docs.values()][0]!;
    const detail = { ...world.document(processing.summary.id), status: 'processing' as const, pipelineStage: 'ocr' as const };
    const { Wrapper } = queryWrapper();
    render(<Viewer doc={detail} search={{}} />, { wrapper: Wrapper });
    expect(screen.getByTestId('viewer-processing')).toHaveTextContent('still reading');
    expect(screen.queryByTestId('pdf-frame')).not.toBeInTheDocument();
    expect(screen.queryByTestId('side-panel')).not.toBeInTheDocument();
  });

  it('an unreadable document links to the review queue', async () => {
    await open('IMG_2231.jpg');
    expect(screen.getByTestId('viewer-unreadable')).toHaveTextContent("couldn't read");
    expect(screen.queryByTestId('pdf-frame')).not.toBeInTheDocument();
  });

  it('lists the Filed section with the rule, and the history with Undo', async () => {
    await open('Call for contributions, Q3 2026');
    const filed = screen.getByTestId('filed-section');
    expect(within(filed).getByTestId('filed-name')).toHaveTextContent('2026-09-22_URSSAF_Appel_T3.pdf');
    expect(within(filed).getByRole('link', { name: 'URSSAF calls' })).toHaveAttribute('href', expect.stringMatching(/^\/rules\/rul_/));
    const history = screen.getByRole('list', { name: 'History of this document' });
    expect(within(history).getAllByRole('button', { name: 'Undo' }).length).toBeGreaterThan(0);
  });
});
