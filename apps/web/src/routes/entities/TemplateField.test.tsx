import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { CATEGORIES, ENTITIES } from '../../mocks/seed';
import { renderRoute } from '../../test/renderRoute';
import { useMockApi } from '../../test/mockApi';
import { CategoryEditor } from './CategoryEditor';
import { TemplateField } from './TemplateField';

function Harness({ initial = '{entity}/{fy} {entity}/Documents', error = null }: { initial?: string; error?: { offset: number; message?: string } | null }) {
  const [value, setValue] = useState(initial);
  return <TemplateField kind="path" label="Path template" value={value} onChange={setValue} error={error} />;
}

describe('TemplateField', () => {
  it('shows the template as literal text and token chips', () => {
    render(<Harness />);
    const chips = within(screen.getByTestId('template-chips'));
    expect(chips.getByText('{fy}')).toHaveAttribute('data-token', 'fy');
    expect(screen.getByTestId('template-chips').querySelectorAll('[data-token]')).toHaveLength(3);
    expect(screen.getByRole('textbox', { name: 'Path template' })).toHaveValue('{entity}/{fy} {entity}/Documents');
  });

  it('offers the nine tokens and inserts one where the caret is', async () => {
    render(<Harness initial="{entity}/" />);
    const group = screen.getByRole('group', { name: 'Tokens' });
    expect(within(group).getAllByRole('button')).toHaveLength(9);
    await userEvent.click(within(group).getByRole('button', { name: 'Insert {counterparty}' }));
    expect(screen.getByRole('textbox', { name: 'Path template' })).toHaveValue('{entity}/{counterparty}');
    expect(screen.getByTestId('template-chips').querySelectorAll('[data-token]')).toHaveLength(2);
  });

  it('says where a template is wrong, with the character offset', () => {
    render(<Harness error={{ offset: 5, message: 'Unknown token.' }} />);
    expect(screen.getByRole('textbox', { name: 'Path template' })).toBeInvalid();
    expect(screen.getByTestId('template-error')).toHaveTextContent('The template has a mistake at character 5.Unknown token.');
  });
});

describe('CategoryEditor preview and 422', () => {
  const api = useMockApi();
  const category = () => structuredClone(CATEGORIES[2]!);

  async function open() {
    return renderRoute(<CategoryEditor category={category()} entities={ENTITIES} documentCount={11} />);
  }

  it('previews the rendered path and file name, and follows an edit', async () => {
    await open();
    const preview = screen.getByTestId('template-preview');
    await waitFor(() => expect(preview).toHaveTextContent('Cabinet Marchand / Appels de paiement / 2026 / 2026-02-27_Example-Supplier_Contribution-annuelle.pdf'), { timeout: 3_000 });
    const path = screen.getByRole('textbox', { name: 'Path template' });
    await userEvent.clear(path);
    await userEvent.type(path, '{{entity}/{{fy} {{entity}/{{category}', { delay: 0 });
    await waitFor(() => expect(preview).toHaveTextContent('Cabinet Marchand / 2025 Cabinet Marchand / Appels de paiement'), { timeout: 3_000 });
  });

  it('shows the server error for a bad template before and after a save attempt', async () => {
    await open();
    const path = screen.getByRole('textbox', { name: 'Path template' });
    await userEvent.clear(path);
    await userEvent.type(path, '{{entity}/{{nope}', { delay: 0 });
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    const error = await screen.findByTestId('template-error');
    expect(error).toHaveTextContent('mistake at character');
    expect(api.world().registry.categoryList().items[2]!.template.pathTemplate).toBe('{entity}/{category}/{year}');
  });

  it('saves a good template, and Discard puts the saved one back', async () => {
    await open();
    const file = screen.getByRole('textbox', { name: 'File name template' });
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
    await userEvent.type(file, '_{{sub}', { delay: 0 });
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled();
    await userEvent.click(screen.getByRole('button', { name: 'Discard' }));
    expect(file).toHaveValue('{date:YYYY-MM-DD}_{issuer}_{sub}');
    await userEvent.type(file, '_{{reference}', { delay: 0 });
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(api.world().registry.categoryList().items[2]!.template.fileTemplate).toBe('{date:YYYY-MM-DD}_{issuer}_{sub}_{reference}'));
  });
});
