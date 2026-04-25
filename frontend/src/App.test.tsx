import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ status: 'ok', service: 'api' }),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders backend health from the API', async () => {
    render(<App />);

    expect(screen.getByRole('heading', { name: /typescript frontend/i })).toBeInTheDocument();
    expect(await screen.findByText('api: ok')).toBeInTheDocument();
  });
});
