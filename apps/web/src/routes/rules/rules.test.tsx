import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import i18n from '../../i18n';
import { useMockApi } from '../../test/mockApi';
import { renderRoute } from '../../test/renderRoute';
import { RulesPage } from './RulesPage';
import { lastFiredLabel, needsCheck } from './ruleView';

const rowOf = (name: string | RegExp) => screen.getByRole('link', { name }).closest('tr')!;

describe('RulesPage', () => {
  const api = useMockApi();

  it('lists every rule with its destination, source chip, counts and a switch, and counts the ones that are on', async () => {
    await renderRoute(<RulesPage />);
    const row = await screen.findByRole('link', { name: 'Martin Supplies invoices' });
    const tr = row.closest('tr')!;
    expect(within(tr).getByText('Built in')).toBeInTheDocument();
    expect(within(tr).getByText('148')).toBeInTheDocument();
    expect(tr).toHaveTextContent('Atelier Numérique / {year} Cabinet Marchand / Factures reçues / Fournitures');
    expect(within(tr).getByRole('switch', { name: 'Use the rule “Martin Supplies invoices”' })).toBeChecked();
    expect(screen.getByText(/^11 rules, 9 on\./)).toBeInTheDocument();
  });

  it('row states: a draft is off and labelled, a disabled rule is off, corrections above 2 say "check"', async () => {
    await renderRoute(<RulesPage />);
    await screen.findByRole('link', { name: 'Martin Supplies invoices' });
    const draft = rowOf('Banque Lumière: Atelier statements');
    expect(draft).toHaveAttribute('data-state', 'draft');
    expect(within(draft).getByText('Draft')).toBeInTheDocument();
    expect(within(draft).getByRole('switch')).not.toBeChecked();
    expect(within(draft).getByText('Never')).toBeInTheDocument();
    expect(within(rowOf('SIE Laval tax notices')).getByRole('switch')).not.toBeChecked();
    const checked = rowOf('Banque Lumière statements, personal');
    expect(within(checked).getByText('3 · check')).toBeInTheDocument();
    expect(within(rowOf('Martin Supplies invoices')).queryByText(/check/)).toBeNull();
  });

  it('turns a rule off and a draft on through PATCH, and keeps the switch in step', async () => {
    await renderRoute(<RulesPage />);
    await screen.findByRole('link', { name: 'Martin Supplies invoices' });
    await userEvent.click(within(rowOf('Martin Supplies invoices')).getByRole('switch'));
    await waitFor(() => expect(within(rowOf('Martin Supplies invoices')).getByRole('switch')).not.toBeChecked());
    expect(api.world().registry.rule(api.world().registry.listRules(new URLSearchParams({ q: 'Martin' })).items[0]!.rule.id).rule.state).toBe('disabled');
    await userEvent.click(within(rowOf('Banque Lumière: Atelier statements')).getByRole('switch'));
    await waitFor(() => expect(within(rowOf('Banque Lumière: Atelier statements')).getByRole('switch')).toBeChecked());
    expect(within(rowOf('Banque Lumière: Atelier statements')).queryByText('Draft')).toBeNull();
    expect(screen.getByText(/^11 rules, 9 on\./)).toBeInTheDocument();
  });

  it('shows what Mona learned today, from interviews and corrections', async () => {
    await renderRoute(<RulesPage />);
    const panel = await screen.findByTestId('learned-panel');
    await waitFor(() => expect(within(panel).getAllByRole('link')).toHaveLength(2));
    expect(panel).toHaveTextContent('What Mona learned today');
    expect(panel).toHaveTextContent('From your answer · today');
    expect(panel).toHaveTextContent('From your correction · today');
  });

  it('searches by name and says so when nothing matches', async () => {
    await renderRoute(<RulesPage />);
    await screen.findByRole('link', { name: 'Martin Supplies invoices' });
    await userEvent.type(screen.getByRole('searchbox', { name: 'Find a rule' }), 'laval');
    await waitFor(() => expect(screen.getAllByTestId('rule-row')).toHaveLength(1), { timeout: 2_000 });
    await userEvent.clear(screen.getByRole('searchbox', { name: 'Find a rule' }));
    await userEvent.type(screen.getByRole('searchbox', { name: 'Find a rule' }), 'zzzz');
    expect(await screen.findByText('No rule matches', undefined, { timeout: 2_000 })).toBeInTheDocument();
  });
});

describe('rule view helpers', () => {
  const t = i18n.getFixedT('en');
  const now = Date.parse('2026-10-01T15:00:00');

  it('flags corrections above 2 only', () => {
    expect([0, 2, 3].map((n) => needsCheck({ correctionsSince: n }))).toEqual([false, false, true]);
  });

  it('writes the last firing as a time, Yesterday, a weekday, a date, or Never', () => {
    expect(lastFiredLabel('2026-10-01T06:12:00', now, 'en', t)).toBe('06:12');
    expect(lastFiredLabel('2026-09-30T23:00:00', now, 'en', t)).toBe('Yesterday');
    expect(lastFiredLabel('2026-09-28T09:00:00', now, 'en', t)).toBe('Monday');
    expect(lastFiredLabel('2026-09-22T09:00:00', now, 'en', t)).toBe('22 September');
    expect(lastFiredLabel(undefined, now, 'en', t)).toBe('Never');
    expect(lastFiredLabel('2026-09-28T09:00:00', now, 'fr', i18n.getFixedT('fr'))).toBe('lundi');
  });
});
