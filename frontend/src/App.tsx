import { FormEvent, useEffect, useMemo, useState } from 'react';

type Role = 'contractor' | 'official';

type User = {
  id: string;
  email: string;
  name: string;
  role: Role;
};

type LoginResponse = {
  access_token: string;
  token_type: string;
  user: User;
};

type DocumentRecord = {
  id: string;
  title: string;
  document_type: string;
  notes: string | null;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  uploader_id: string;
  uploader_role: string;
  created_at: string;
};

const storedTokenKey = 'fcsw-token';

export function App() {
  const [token, setToken] = useState(() => localStorage.getItem(storedTokenKey) ?? '');
  const [user, setUser] = useState<User | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!token || user) {
      return;
    }

    fetch('/api/auth/me', { headers: authHeaders(token) })
      .then(assertOk)
      .then((response) => response.json() as Promise<User>)
      .then(setUser)
      .catch(() => {
        localStorage.removeItem(storedTokenKey);
        setToken('');
      });
  }, [token, user]);

  useEffect(() => {
    if (!token || !user) {
      return;
    }
    void loadDocuments(token, setDocuments, setError);
  }, [token, user]);

  function handleLogin(nextToken: string, nextUser: User) {
    localStorage.setItem(storedTokenKey, nextToken);
    setToken(nextToken);
    setUser(nextUser);
    setError('');
  }

  function handleLogout() {
    localStorage.removeItem(storedTokenKey);
    setToken('');
    setUser(null);
    setDocuments([]);
    setError('');
  }

  async function handleUpload(form: HTMLFormElement) {
    if (!token) {
      return;
    }

    setIsLoading(true);
    setError('');
    try {
      const response = await fetch('/api/documents/upload', {
        method: 'POST',
        headers: authHeaders(token),
        body: new FormData(form),
      });
      await assertOk(response);
      form.reset();
      await loadDocuments(token, setDocuments, setError);
    } catch (currentError) {
      setError(currentError instanceof Error ? currentError.message : 'Upload failed');
    } finally {
      setIsLoading(false);
    }
  }

  async function handleDownload(document: DocumentRecord) {
    if (!token) {
      return;
    }

    setError('');
    try {
      const response = await fetch(`/api/documents/${document.id}/download`, {
        headers: authHeaders(token),
      });
      await assertOk(response);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement('a');
      link.href = url;
      link.download = document.original_filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (currentError) {
      setError(currentError instanceof Error ? currentError.message : 'Download failed');
    }
  }

  if (!user) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Federal Center SW</p>
          <h1>{user.role === 'contractor' ? 'Contractor Document Portal' : 'Official Review Portal'}</h1>
        </div>
        <div className="session">
          <span>{user.name}</span>
          <button className="secondary-button" type="button" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </header>

      {error ? <p className="alert">{error}</p> : null}

      {user.role === 'contractor' ? (
        <ContractorPortal
          documents={documents}
          isLoading={isLoading}
          onUpload={(event) => {
            event.preventDefault();
            void handleUpload(event.currentTarget);
          }}
          onDownload={(document) => void handleDownload(document)}
        />
      ) : (
        <OfficialPortal documents={documents} onDownload={(document) => void handleDownload(document)} />
      )}
    </main>
  );
}

function LoginScreen({ onLogin }: { onLogin: (token: string, user: User) => void }) {
  const [role, setRole] = useState<Role>('contractor');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError('');
    try {
      const response = await fetch('/api/auth/mock-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role }),
      });
      await assertOk(response);
      const login = (await response.json()) as LoginResponse;
      onLogin(login.access_token, login.user);
    } catch (currentError) {
      setError(currentError instanceof Error ? currentError.message : 'Login failed');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="login-shell">
      <form className="login-panel" onSubmit={submit}>
        <p className="eyebrow">Federal Center SW</p>
        <h1>Sign in</h1>
        <p className="lede">Choose a mock role for the prototype. This will be replaced by Azure Entra login later.</p>

        <label className="field">
          <span>Role</span>
          <select value={role} onChange={(event) => setRole(event.target.value as Role)}>
            <option value="contractor">Contractor</option>
            <option value="official">Government official</option>
          </select>
        </label>

        {error ? <p className="alert">{error}</p> : null}

        <button className="primary-button" type="submit" disabled={isLoading}>
          {isLoading ? 'Signing in...' : 'Continue'}
        </button>
      </form>
    </main>
  );
}

function ContractorPortal({
  documents,
  isLoading,
  onUpload,
  onDownload,
}: {
  documents: DocumentRecord[];
  isLoading: boolean;
  onUpload: (event: FormEvent<HTMLFormElement>) => void;
  onDownload: (document: DocumentRecord) => void;
}) {
  return (
    <div className="workspace">
      <section className="panel" aria-labelledby="upload-title">
        <h2 id="upload-title">Upload Document</h2>
        <form className="upload-form" onSubmit={onUpload}>
          <label className="field">
            <span>Title</span>
            <input name="title" required maxLength={200} />
          </label>
          <label className="field">
            <span>Document type</span>
            <input name="document_type" required maxLength={80} />
          </label>
          <label className="field">
            <span>Notes</span>
            <textarea name="notes" rows={4} />
          </label>
          <label className="field">
            <span>File</span>
            <input
              name="file"
              type="file"
              required
              accept=".pdf,.doc,.docx,.txt,.csv,.xlsx,.png,.jpg,.jpeg"
            />
          </label>
          <button className="primary-button" type="submit" disabled={isLoading}>
            {isLoading ? 'Uploading...' : 'Upload'}
          </button>
        </form>
      </section>

      <DocumentList title="My Uploads" documents={documents} onDownload={onDownload} emptyText="No documents uploaded yet." />
    </div>
  );
}

function OfficialPortal({
  documents,
  onDownload,
}: {
  documents: DocumentRecord[];
  onDownload: (document: DocumentRecord) => void;
}) {
  return (
    <div className="workspace single">
      <DocumentList
        title="Contractor Uploads"
        documents={documents}
        onDownload={onDownload}
        emptyText="No contractor uploads are available."
        showUploader
      />
    </div>
  );
}

function DocumentList({
  title,
  documents,
  emptyText,
  onDownload,
  showUploader = false,
}: {
  title: string;
  documents: DocumentRecord[];
  emptyText: string;
  onDownload: (document: DocumentRecord) => void;
  showUploader?: boolean;
}) {
  const countText = useMemo(() => `${documents.length} document${documents.length === 1 ? '' : 's'}`, [documents]);

  return (
    <section className="panel" aria-labelledby={`${title}-title`}>
      <div className="panel-heading">
        <h2 id={`${title}-title`}>{title}</h2>
        <span>{countText}</span>
      </div>

      {documents.length === 0 ? (
        <p className="empty">{emptyText}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                {showUploader ? <th>Uploader</th> : null}
                <th>File</th>
                <th>Uploaded</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((document) => (
                <tr key={document.id}>
                  <td>
                    <strong>{document.title}</strong>
                    {document.notes ? <span className="muted">{document.notes}</span> : null}
                  </td>
                  <td>{document.document_type}</td>
                  {showUploader ? <td>{document.uploader_id}</td> : null}
                  <td>
                    {document.original_filename}
                    <span className="muted">{formatBytes(document.size_bytes)}</span>
                  </td>
                  <td>{new Date(document.created_at).toLocaleDateString()}</td>
                  <td>
                    <button className="secondary-button" type="button" onClick={() => onDownload(document)}>
                      Download
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

async function loadDocuments(
  token: string,
  setDocuments: (documents: DocumentRecord[]) => void,
  setError: (message: string) => void,
) {
  try {
    const response = await fetch('/api/documents', { headers: authHeaders(token) });
    await assertOk(response);
    setDocuments((await response.json()) as DocumentRecord[]);
  } catch (currentError) {
    setError(currentError instanceof Error ? currentError.message : 'Could not load documents');
  }
}

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` };
}

async function assertOk(response: Response) {
  if (!response.ok) {
    let detail = `Request failed with ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Keep the status-based message when the response body is not JSON.
    }
    throw new Error(detail);
  }
  return response;
}

function formatBytes(value: number) {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
