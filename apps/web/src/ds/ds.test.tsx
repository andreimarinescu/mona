import { render, screen } from '@testing-library/react';
import { version } from 'react';
import { describe, expect, it } from 'vitest';
import { Button, StatusPill, format } from './index';

describe('DS bundle shim', () => {
  it('runs the bundle on the app React 19', () => {
    expect(window.React.version).toBe(version);
    expect(version.startsWith('19.')).toBe(true);
    render(<Button variant="primary">Save</Button>);
    expect(screen.getByRole('button', { name: 'Save' })).toHaveClass('mona-btn--primary');
  });

  it('re-exports components and format from window.Mona', () => {
    render(<StatusPill status="review" lang="fr" />);
    expect(screen.getByText('À vérifier')).toBeInTheDocument();
    expect(format.money(1284, 'EUR', 'fr')).toBe('1\u00a0284,00\u00a0€');
  });
});
