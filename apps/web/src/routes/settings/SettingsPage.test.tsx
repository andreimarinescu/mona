import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import i18n from '../../i18n';
import { useMockApi } from '../../test/mockApi';
import { renderRoute } from '../../test/renderRoute';
import { SettingsPage } from './SettingsPage';
import { statusTiles, diskTone } from './statusView';

const GB = 1024 ** 3;

describe('SettingsPage', () => {
  const api = useMockApi();
  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('saves the thresholds it changed and nothing else', async () => {
    await renderRoute(<SettingsPage />);
    const high = await screen.findByLabelText('Files on her own from (%)');
    const save = within(screen.getByTestId('settings-thresholds')).getByRole('button', { name: 'Save' });
    expect(save).toBeDisabled();
    await userEvent.clear(high);
    await userEvent.type(high, '90');
    await userEvent.click(save);
    await waitFor(() => expect(api.world().account.settings()).toMatchObject({ confidenceHigh: 90, confidenceLow: 60, badgeHours: 24 }));
    await waitFor(() => expect(save).toBeDisabled());
  });

  it('refuses bad values before any request, with the limit in words', async () => {
    await renderRoute(<SettingsPage />);
    const low = await screen.findByLabelText('Asks you below (%)');
    const save = within(screen.getByTestId('settings-thresholds')).getByRole('button', { name: 'Save' });
    await userEvent.clear(low);
    await userEvent.type(low, '85');
    expect(await screen.findByText('The low threshold must be under the high one.')).toBeInTheDocument();
    expect(save).toBeDisabled();
    const hours = screen.getByLabelText('Show “Filed by Mona” for (hours)');
    await userEvent.clear(hours);
    await userEvent.type(hours, '200');
    expect(screen.getByText('Enter a number from 1 to 168.')).toBeInTheDocument();
    await userEvent.clear(hours);
    await userEvent.type(hours, '2.5');
    expect(screen.getByText('Enter a whole number.')).toBeInTheDocument();
    expect(api.world().account.settings().confidenceLow).toBe(60);
  });

  it('saves the profile section: name, practice and auto-lock', async () => {
    await renderRoute(<SettingsPage />);
    const lock = await screen.findByLabelText('Lock after (minutes)');
    await userEvent.clear(lock);
    await userEvent.type(lock, '30');
    await userEvent.click(within(screen.getByTestId('settings-profile')).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.world().account.settings().autoLockMinutes).toBe(30));
  });

  it('changes the interface language at once', async () => {
    await renderRoute(<SettingsPage />);
    await userEvent.click(await screen.findByRole('radio', { name: 'Français' }));
    await waitFor(() => expect(api.world().account.settings().locale).toBe('fr'));
  });

  it.each(['en', 'fr', 'ro'] as const)('the filing language picker names each language in itself (%s)', async (lng) => {
    await i18n.changeLanguage(lng);
    await renderRoute(<SettingsPage />);
    const select = await screen.findByRole('combobox', { name: i18n.getFixedT(lng)('settings.language.filing') });
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual(['Français', 'English', 'Română']);
  });

  it('changes the password: mismatch and short values stay in the dialog, a wrong current password is reported', async () => {
    await renderRoute(<SettingsPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Change password' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText('Current password'), 'nope');
    await userEvent.type(within(dialog).getByLabelText('New password'), 'short');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Change password' }));
    expect(await within(dialog).findByText('The new password needs at least 8 characters.')).toBeInTheDocument();
    await userEvent.clear(within(dialog).getByLabelText('New password'));
    await userEvent.type(within(dialog).getByLabelText('New password'), 'long enough');
    await userEvent.type(within(dialog).getByLabelText('New password again'), 'different');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Change password' }));
    expect(await within(dialog).findByText('The two passwords differ.')).toBeInTheDocument();
    await userEvent.clear(within(dialog).getByLabelText('New password again'));
    await userEvent.type(within(dialog).getByLabelText('New password again'), 'long enough');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Change password' }));
    expect(await within(dialog).findByText("That password isn't right.")).toBeInTheDocument();
  });

  it('shows the system status tiles and the privacy diagram, with the version from the build', async () => {
    await renderRoute(<SettingsPage />);
    const tiles = await screen.findAllByTestId('status-tile');
    expect(tiles).toHaveLength(5);
    expect(screen.getByTestId('settings-status')).toHaveTextContent('qwen3.6-35b-a3b');
    expect(screen.getByTestId('settings-status')).toHaveTextContent('Q4_K_XL');
    expect(await screen.findByTestId('flow-telegram')).toHaveTextContent('Passes through Telegram');
    expect(screen.getByTestId('flow-stays')).toHaveTextContent('deleted after 24 hours');
    expect(screen.queryByTestId('flow-cloud')).toBeNull();
    expect(screen.getByTestId('about-web-version')).toHaveTextContent(/^Mona \d+\.\d+\.\d+/);
    expect(screen.queryByText(/recovery key/i)).toBeNull();
    expect(screen.queryByText(/theme/i)).toBeNull();
  });
});

describe('statusTiles', () => {
  const t = i18n.getFixedT('en');
  const base = {
    version: '0.1.0',
    build: null,
    env: 'dev' as const,
    mona: { status: 'offline' as const, hermesVersion: null },
    llm: { endpoint: 'openrouter' as const, model: null, quantization: null, contextPerSlot: null, slots: null, vramBytes: null },
    queues: { llm: { todo: 2, doing: 1 }, cpu: { todo: 0, doing: 3 } },
    database: 'error' as const,
    disk: { dataFreeBytes: 50 * GB, dataTotalBytes: 1000 * GB },
    privacy: { cloudAi: true, telegram: false },
  };

  it('says "not reported" for nulls and flags what needs attention in words, not colour alone', () => {
    const tiles = Object.fromEntries(statusTiles(base, t, 'en').map((x) => [x.id, x]));
    expect(tiles.model).toMatchObject({ value: 'Not reported', tone: 'unknown', status: 'Cloud model (development setup)' });
    expect(tiles.mona).toMatchObject({ value: 'Not answering', status: 'Needs attention', tone: 'bad' });
    expect(tiles.queue).toMatchObject({ value: '6 waiting', detail: 'Reading: 3 · Filing: 3' });
    expect(tiles.disk).toMatchObject({ value: '50\u00a0GB free', tone: 'warn', status: 'Running low' });
    expect(tiles.database).toMatchObject({ tone: 'bad', status: 'Needs attention' });
  });

  it('grades the disk by the free fraction', () => {
    expect([diskTone(500, 1000), diskTone(99, 1000), diskTone(29, 1000), diskTone(1, 0)]).toEqual(['ok', 'warn', 'bad', 'unknown']);
  });
});
