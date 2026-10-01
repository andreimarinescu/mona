import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { useAppState } from '../../state/context';
import i18n from '../../i18n';
import { useMockApi } from '../../test/mockApi';
import { renderRoute } from '../../test/renderRoute';
import { HomePage } from './HomePage';
import { ingestionFigures } from './ingestion';
import { DateTile } from './DateTile';
import { render } from '@testing-library/react';

function Askers() {
  const { askMona } = useAppState();
  return (
    <button type="button" onClick={() => askMona({ home: true })}>
      ask
    </button>
  );
}

describe('HomePage', () => {
  const api = useMockApi();
  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('writes the brief from the facts, with the caption and the two actions', async () => {
    await renderRoute(<HomePage />);
    const brief = await screen.findByTestId('mona-brief');
    expect(within(brief).getByRole('heading', { level: 1 })).toHaveTextContent(/^(Good morning|Good afternoon|Good evening), Léa Marchand\./);
    expect(brief).toHaveTextContent('I filed 23 documents');
    expect(brief).toHaveTextContent('6 need your eye.');
    expect(brief).toHaveTextContent('URSSAF, quarterly contributions, €1,284.00, is due in 2 days.');
    expect(within(brief).getByRole('button', { name: 'Review 6 documents' })).toBeInTheDocument();
    expect(within(brief).getByRole('button', { name: 'Open URSSAF, quarterly contributions' })).toBeInTheDocument();
    expect(screen.getByTestId('brief-caption')).toHaveTextContent(/^Written at \d\d:\d\d from 23 journal entries$/);
  });

  it('links each sentence to its source', async () => {
    await renderRoute(<HomePage />);
    const brief = await screen.findByTestId('mona-brief');
    expect(within(brief).getByText('6 need your eye.')).toHaveAttribute('href', '/review');
    expect(within(brief).getByText(/I filed 23 documents/)).toHaveAttribute('href', '/activity');
    expect(within(brief).getByText(/is due in 2 days/)).toHaveAttribute('href', expect.stringMatching(/^\/documents\/doc_/));
  });

  it('shows the four cards: review queue, what is due, recent activity, ingestion', async () => {
    await renderRoute(<HomePage />);
    const review = await screen.findByTestId('home-review');
    expect(within(review).getAllByRole('listitem')).toHaveLength(3);
    expect(within(review).getByText('Open queue')).toHaveAttribute('href', '/review');
    expect(review).toHaveTextContent('3 more are waiting.');
    const due = screen.getByTestId('home-due');
    expect(within(due).getAllByRole('listitem')).toHaveLength(3);
    expect(due).toHaveTextContent('€1,284.00');
    const activity = screen.getByTestId('home-activity');
    expect(within(activity).getByText('Full journal')).toHaveAttribute('href', '/activity');
    expect(within(activity).getByRole('button', { name: 'Undo' })).toBeEnabled();
    const ingestion = screen.getByTestId('home-ingestion');
    expect(within(ingestion).getByText('Activity log')).toHaveAttribute('href', '/activity');
    expect(within(ingestion).getByRole('img', { name: /^Documents per day, last 14 days\. Peak: \d+ on / })).toBeInTheDocument();
  });

  it('Undo on the activity card undoes the move and refreshes the card', async () => {
    await renderRoute(<HomePage />);
    const activity = await screen.findByTestId('home-activity');
    await userEvent.click(within(activity).getByRole('button', { name: 'Undo' }));
    await waitFor(() => expect(api.world().entries.some((e) => e.action === 'undo')).toBe(true));
  });

  it('registers the chat entry so the / key can focus it', async () => {
    await renderRoute(
      <>
        <HomePage />
        <Askers />
      </>,
    );
    const entry = await screen.findByRole('textbox', { name: 'Ask Mona' });
    await userEvent.click(screen.getByRole('button', { name: 'ask' }));
    expect(entry).toHaveFocus();
  });

  it('is in French when the profile is', async () => {
    api.world().account.patch({ locale: 'fr' });
    await i18n.changeLanguage('fr');
    await renderRoute(<HomePage />);
    const brief = await screen.findByTestId('mona-brief');
    expect(brief).toHaveTextContent(/J’ai classé 23 documents/);
    expect(brief).toHaveTextContent('6 documents attendent votre avis.');
  });
});

describe('HomePage states', () => {
  const api = useMockApi({ seed: false });

  it('shows the first-run checklist when nothing has ever arrived', async () => {
    await renderRoute(<HomePage />);
    const list = await screen.findByTestId('first-run');
    expect(within(list).getAllByRole('listitem')).toHaveLength(5);
    expect(within(list).getByText('Your first documents').closest('li')).not.toHaveAttribute('data-done');
    await waitFor(() => expect(list).toHaveTextContent('Mona’s Telegram bot is linked.'));
    expect(screen.queryByTestId('home-review')).toBeNull();
    await userEvent.click(within(list).getByRole('radio', { name: 'Français' }));
    await waitFor(() => expect(api.world().account.settings().locale).toBe('fr'));
  });

  it('marks the brain offline and disables the chat entry', async () => {
    api.world().account.setMona('offline');
    await renderRoute(<HomePage />);
    expect(await screen.findByText('Mona’s brain is offline')).toBeInTheDocument();
    expect(screen.getByTestId('chat-entry').querySelector('input')).toBeDisabled();
  });
});

describe('home helpers', () => {
  it('sums the last 7 of 14 days and finds the busiest', () => {
    const days = Array.from({ length: 14 }, (_, i) => ({ date: `2026-09-${String(18 + i).padStart(2, '0')}`, count: i === 3 ? 31 : i }));
    expect(ingestionFigures(days)).toEqual({ week: 7 + 8 + 9 + 10 + 11 + 12 + 13, today: 13, peak: 31, peakDate: '2026-09-21' });
  });

  it('DateTile is urgent at 3 days or fewer, and shows weekday and day', () => {
    const { container, rerender } = render(<DateTile date="2026-10-02" daysLeft={1} />);
    expect(container.firstElementChild).toHaveAttribute('data-urgent');
    expect(container).toHaveTextContent(/Fri.*2/);
    rerender(<DateTile date="2026-10-19" daysLeft={19} />);
    expect(container.firstElementChild).not.toHaveAttribute('data-urgent');
  });
});
