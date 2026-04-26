import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { App } from './App';

describe('App', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders the sign-in screen when no session is stored', async () => {
    render(<App />);

    expect(await screen.findByRole('heading', { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByText(/authorized personnel/i)).toBeInTheDocument();
  });
});
