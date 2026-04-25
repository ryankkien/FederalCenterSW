import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';

const contractorUser = {
  id: 'contractor-demo',
  email: 'contractor@example.com',
  name: 'Contractor Demo',
  role: 'contractor',
};

const officialUser = {
  id: 'official-demo',
  email: 'official@example.gov',
  name: 'Government Official Demo',
  role: 'official',
};

const documentRecord = {
  id: 'doc-1',
  title: 'Monthly progress report',
  document_type: 'Progress Report',
  notes: 'Submitted for review',
  original_filename: 'progress.pdf',
  content_type: 'application/pdf',
  size_bytes: 1280,
  uploader_id: 'contractor-demo',
  uploader_role: 'contractor',
  created_at: '2026-04-25T18:00:00Z',
};

describe('App', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('shows the mock login page first', () => {
    vi.stubGlobal('fetch', vi.fn());

    render(<App />);

    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.getByLabelText('Role')).toBeInTheDocument();
  });

  it('routes contractors to upload and my uploads after login', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ access_token: 'contractor-token', user: contractorUser }))
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(documentRecord, 201))
      .mockResolvedValueOnce(jsonResponse([documentRecord]));
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.submit(screen.getByRole('button', { name: 'Continue' }).closest('form')!);

    expect(await screen.findByRole('heading', { name: 'Contractor Document Portal' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Upload Document' })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Monthly progress report' } });
    fireEvent.change(screen.getByLabelText('Document type'), { target: { value: 'Progress Report' } });
    fireEvent.change(screen.getByLabelText('Notes'), { target: { value: 'Submitted for review' } });
    fireEvent.change(screen.getByLabelText('File'), {
      target: { files: [new File(['report'], 'progress.pdf', { type: 'application/pdf' })] },
    });
    fireEvent.submit(screen.getByRole('button', { name: 'Upload' }).closest('form')!);

    expect(await screen.findByText('Monthly progress report')).toBeInTheDocument();
    expect(screen.getByText('progress.pdf')).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/documents/upload', expect.any(Object)));
  });

  it('routes officials to the read-only review portal', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ access_token: 'official-token', user: officialUser }))
      .mockResolvedValueOnce(jsonResponse([documentRecord]));
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'official' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Continue' }).closest('form')!);

    expect(await screen.findByRole('heading', { name: 'Official Review Portal' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Contractor Uploads' })).toBeInTheDocument();
    expect(await screen.findByText('Monthly progress report')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Upload Document' })).not.toBeInTheDocument();
  });
});

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  };
}
