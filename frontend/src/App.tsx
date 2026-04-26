import { FormEvent, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  BookOpen,
  Download,
  FileText,
  Filter,
  Link2,
  LockKeyhole,
  LogOut,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
} from 'lucide-react';

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

type ContractRecord = {
  id: string;
  title: string;
  status: string;
  source: string;
  contractor_id?: string | null;
  category_code?: string | null;
  document_count: number;
  open_regression_count: number;
  active_hypothesis_count: number;
  pending_job_count: number;
  unmatched_document_count: number;
  has_knowledge_base: boolean;
};

type DocumentRecord = {
  id: string;
  title: string;
  document_type: string;
  document_kind: string;
  notes: string | null;
  original_filename: string;
  stored_filename: string;
  content_type: string;
  size_bytes: number;
  uploader_id: string;
  uploader_role: string;
  contract_id: string | null;
  match_status: string;
  processing_status: string;
  created_at: string;
};

type WikiNodeSummary = {
  id: string;
  node_type: string;
  title: string;
  summary: string;
  contract_id?: string | null;
  vendor_uei?: string | null;
  security_level: SecurityLevel;
  status: string;
  citation_count: number;
};

type WikiCitation = {
  id: string;
  label: string;
  excerpt: string;
  url?: string | null;
  source_path?: string | null;
  document_id?: string | null;
  source_record_id?: string | null;
  external_source_ref_id?: string | null;
};

type WikiSection = {
  title: string;
  body: string;
};

type WikiArticle = WikiNodeSummary & {
  body: string;
  sections: WikiSection[];
  citations: WikiCitation[];
  related_nodes: WikiNodeSummary[];
  limitations: string[];
  metadata: Record<string, unknown>;
};

type KnowledgeRunResponse = {
  id: string;
  status: string;
  source_record_count: number;
  node_count: number;
  citation_count: number;
};

type SasUrlResponse = {
  url: string;
  expires_in_minutes: number;
};

type SecurityLevel = 'standard' | 'controlled' | 'restricted' | 'privileged';
type FetchInit = NonNullable<Parameters<typeof fetch>[1]>;

const storedTokenKey = 'fcsw-token';
const entryTypes: Array<{ id: string; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'contract', label: 'Contracts' },
  { id: 'contractor', label: 'Contractors' },
  { id: 'topic', label: 'Topics' },
  { id: 'source', label: 'Official Sources' },
  { id: 'regression', label: 'Regressions' },
  { id: 'hypothesis', label: 'Hypotheses' },
  { id: 'document', label: 'Documents' },
];
const securityLevels: Array<SecurityLevel | 'all'> = ['all', 'standard', 'controlled', 'restricted', 'privileged'];

export function App() {
  const [token, setToken] = useState(() => localStorage.getItem(storedTokenKey) ?? '');
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token || user) {
      return;
    }
    api<User>('/api/auth/me', token)
      .then(setUser)
      .catch(() => {
        localStorage.removeItem(storedTokenKey);
        setToken('');
      });
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
    setError('');
  }

  if (!user) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Federal Center SW</p>
          <h1>{user.role === 'official' ? 'Grokipedia Workspace' : 'Contractor Document Portal'}</h1>
        </div>
        <div className="session">
          <span>{user.name}</span>
          <button className="icon-button" type="button" onClick={handleLogout} title="Sign out">
            <LogOut size={18} />
          </button>
        </div>
      </header>
      {error ? <p className="alert">{error}</p> : null}
      {user.role === 'official' ? (
        <WikiWorkspace token={token} setError={setError} />
      ) : (
        <ContractorPortal token={token} setError={setError} />
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
      const login = await api<LoginResponse>('/api/auth/mock-login', undefined, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role }),
      });
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
        <label className="field">
          <span>Role</span>
          <select value={role} onChange={(event) => setRole(event.target.value as Role)}>
            <option value="contractor">Contractor</option>
            <option value="official">Government official</option>
          </select>
        </label>
        {error ? <p className="alert inline">{error}</p> : null}
        <button className="primary-button" type="submit" disabled={isLoading}>
          {isLoading ? 'Signing in...' : 'Continue'}
        </button>
      </form>
    </main>
  );
}

function WikiWorkspace({ token, setError }: { token: string; setError: (message: string) => void }) {
  const [contracts, setContracts] = useState<ContractRecord[]>([]);
  const [entries, setEntries] = useState<WikiNodeSummary[]>([]);
  const [selectedArticle, setSelectedArticle] = useState<WikiArticle | null>(null);
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [contractFilter, setContractFilter] = useState('all');
  const [securityFilter, setSecurityFilter] = useState<SecurityLevel | 'all'>('all');
  const [selectedEntryId, setSelectedEntryId] = useState('');
  const [runSummary, setRunSummary] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams();
      if (query.trim()) {
        params.set('q', query.trim());
      }
      if (typeFilter !== 'all') {
        params.append('types', typeFilter);
      }
      if (contractFilter !== 'all') {
        params.set('contract_id', contractFilter);
      }
      const [nextContracts, nextEntries] = await Promise.all([
        api<ContractRecord[]>('/api/contracts', token),
        api<WikiNodeSummary[]>(`/api/wiki/search${params.toString() ? `?${params}` : ''}`, token),
      ]);
      setContracts(nextContracts);
      setEntries(nextEntries);
      const nextSelectedId = nextEntries.some((entry) => entry.id === selectedEntryId)
        ? selectedEntryId
        : nextEntries[0]?.id ?? '';
      setSelectedEntryId(nextSelectedId);
      const nextSelected = nextEntries.find((entry) => entry.id === nextSelectedId);
      if (nextSelected) {
        setSelectedArticle(await loadWikiArticle(nextSelected, token));
      } else {
        setSelectedArticle(null);
      }
    } catch (currentError) {
      setError(currentError instanceof Error ? currentError.message : 'Could not load knowledge index');
    } finally {
      setIsLoading(false);
    }
  }, [contractFilter, query, selectedEntryId, setError, token, typeFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  async function selectEntry(entry: WikiNodeSummary) {
    setSelectedEntryId(entry.id);
    setSelectedArticle(await loadWikiArticle(entry, token));
  }

  async function refreshKnowledgeIndex() {
    setIsLoading(true);
    setRunSummary('');
    try {
      const run = await api<KnowledgeRunResponse>('/api/knowledge/ingestion-runs', token, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope: 'visible', sources: ['open'], limit: 100 }),
      });
      setRunSummary(
        `Run ${run.status}: ${run.source_record_count} sources, ${run.node_count} nodes, ${run.citation_count} citations.`,
      );
      await load();
    } catch (currentError) {
      setError(currentError instanceof Error ? currentError.message : 'Could not refresh knowledge index');
    } finally {
      setIsLoading(false);
    }
  }

  const filteredEntries = useMemo(
    () =>
      entries
        .filter((entry) => securityFilter === 'all' || entry.security_level === securityFilter)
        .sort((left, right) => scoreEntry(right, query) - scoreEntry(left, query)),
    [entries, query, securityFilter],
  );
  const selectedEntry = entries.find((entry) => entry.id === selectedEntryId) ?? filteredEntries[0] ?? entries[0];
  const relatedEntries = selectedArticle?.related_nodes ?? [];

  return (
    <div className="wiki-layout">
      <section className="wiki-search">
        <div>
          <p className="eyebrow">Knowledge Index</p>
          <h2>Grokipedia Index</h2>
        </div>
        <form className="search-box" onSubmit={(event) => event.preventDefault()}>
          <Search size={18} />
          <input
            aria-label="Search knowledge index"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search contracts, topics, findings, clauses, RFIs"
          />
        </form>
        <button className="icon-button" type="button" onClick={() => void refreshKnowledgeIndex()} title="Refresh index">
          <RefreshCw size={17} />
        </button>
        {runSummary ? <span className="run-summary">{runSummary}</span> : null}
      </section>

      <aside className="index-sidebar">
        <FacetGroup title="Entry Type" icon={<Filter size={16} />}>
          {entryTypes.map((item) => (
            <FacetButton
              key={item.id}
              active={typeFilter === item.id}
              label={item.label}
              count={item.id === 'all' ? entries.length : entries.filter((entry) => entry.node_type === item.id).length}
              onClick={() => setTypeFilter(item.id)}
            />
          ))}
        </FacetGroup>
        <FacetGroup title="Contracts" icon={<BookOpen size={16} />}>
          <FacetButton
            active={contractFilter === 'all'}
            label="All Contracts"
            count={entries.length}
            onClick={() => setContractFilter('all')}
          />
          {contracts.map((contract) => (
            <FacetButton
              key={contract.id}
              active={contractFilter === contract.id}
              label={contract.id}
              count={entries.filter((entry) => entry.contract_id === contract.id).length}
              onClick={() => setContractFilter(contract.id)}
            />
          ))}
        </FacetGroup>
        <FacetGroup title="Visibility" icon={<LockKeyhole size={16} />}>
          {securityLevels.map((level) => (
            <FacetButton
              key={level}
              active={securityFilter === level}
              label={toTitle(level)}
              count={level === 'all' ? entries.length : entries.filter((entry) => entry.security_level === level).length}
              onClick={() => setSecurityFilter(level)}
            />
          ))}
        </FacetGroup>
      </aside>

      <section className="index-results">
        <div className="section-heading">
          <h2>Results</h2>
          <span className="result-count">{isLoading ? 'Indexing' : `${filteredEntries.length} entries`}</span>
        </div>
        {filteredEntries.length === 0 ? (
          <p className="empty">No visible entries match this search.</p>
        ) : (
          <div className="result-list">
            {filteredEntries.map((entry) => (
              <button
                aria-label={`${entry.node_type} result ${entry.title}`}
                className={`result-row ${entry.id === selectedEntry?.id ? 'selected' : ''}`}
                key={entry.id}
                type="button"
                onClick={() => void selectEntry(entry)}
              >
                <span className={`type-chip ${entry.node_type}`}>{entry.node_type}</span>
                <strong>{entry.title}</strong>
                <span>{entry.summary}</span>
                <small>
                  {entry.contract_id ?? entry.vendor_uei ?? 'global'} · {toTitle(entry.security_level)} · {entry.citation_count} citation(s)
                </small>
              </button>
            ))}
          </div>
        )}
      </section>

      <article className="wiki-article">
        {selectedArticle ? (
          <>
            <div className="article-header">
              <div>
                <p className="eyebrow">{selectedArticle.contract_id ?? selectedArticle.vendor_uei ?? 'Knowledge Node'}</p>
                <h2>{selectedArticle.title}</h2>
              </div>
              <div className="article-badges">
                <span className={`type-chip ${selectedArticle.node_type}`}>{selectedArticle.node_type}</span>
                <span className="security-badge">
                  <ShieldCheck size={14} /> {toTitle(selectedArticle.security_level)}
                </span>
              </div>
            </div>
            <p className="article-summary">{selectedArticle.summary}</p>
            {selectedArticle.sections.length ? (
              selectedArticle.sections.map((section) => (
                <div className="article-section" key={section.title}>
                  <h3>{section.title}</h3>
                  <p>{section.body}</p>
                </div>
              ))
            ) : (
              <div className="article-section">
                <h3>Indexed Text</h3>
                <p>{selectedArticle.body}</p>
              </div>
            )}
            {selectedArticle.limitations.length ? (
              <div className="article-section">
                <h3>Limitations</h3>
                <p>{selectedArticle.limitations.join(' ')}</p>
              </div>
            ) : null}
            {selectedArticle.status ? (
              <div className="article-section">
                <h3>Status</h3>
                <span className={`status ${selectedArticle.status}`}>{selectedArticle.status}</span>
              </div>
            ) : null}
          </>
        ) : (
          <EmptyState text="No index entry selected." />
        )}
      </article>

      <aside className="citation-rail">
        <div className="section-heading">
          <h2>Citations</h2>
          <FileText size={16} />
        </div>
        {selectedArticle?.citations.length ? (
          <div className="citation-list">
            {selectedArticle.citations.map((citation) => (
              <article className="citation" key={citation.id}>
                <strong>{citation.label}</strong>
                <p>{citation.excerpt}</p>
                {citation.source_path ? <small>{citation.source_path}</small> : null}
                {citation.url ? <small>{citation.url}</small> : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="empty">No citations attached.</p>
        )}
        <div className="rail-divider" />
        <div className="section-heading">
          <h2>Related</h2>
          <Link2 size={16} />
        </div>
        {relatedEntries.length ? (
          <div className="related-list">
            {relatedEntries.map((entry) => (
              <button
                aria-label={`Related ${entry.node_type} ${entry.title}`}
                key={entry.id}
                type="button"
                onClick={() => void selectEntry(entry)}
              >
                <span>{entry.node_type}</span>
                <strong>{entry.title}</strong>
              </button>
            ))}
          </div>
        ) : (
          <p className="empty">No related entries.</p>
        )}
      </aside>
    </div>
  );
}

function FacetGroup({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section className="facet-group">
      <div className="section-heading">
        <h2>{title}</h2>
        {icon}
      </div>
      <div className="facet-list">{children}</div>
    </section>
  );
}

function FacetButton({
  active,
  label,
  count,
  onClick,
}: {
  active: boolean;
  label: string;
  count: number;
  onClick: () => void;
}) {
  return (
    <button className={`facet-button ${active ? 'active' : ''}`} type="button" onClick={onClick}>
      <span>{label}</span>
      <small>{count}</small>
    </button>
  );
}

async function loadWikiArticle(entry: WikiNodeSummary, token: string): Promise<WikiArticle> {
  if (entry.node_type === 'contract' && entry.contract_id) {
    return api<WikiArticle>(`/api/wiki/contracts/${entry.contract_id}`, token);
  }
  if (entry.node_type === 'contractor' && entry.vendor_uei) {
    return api<WikiArticle>(`/api/wiki/contractors/${entry.vendor_uei}`, token);
  }
  return api<WikiArticle>(`/api/wiki/nodes/${entry.id}`, token);
}

function scoreEntry(entry: WikiNodeSummary, query: string) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return entry.citation_count;
  }
  let score = entry.citation_count;
  if (entry.title.toLowerCase().includes(normalized)) {
    score += 10;
  }
  if (entry.summary.toLowerCase().includes(normalized)) {
    score += 5;
  }
  if ((entry.contract_id ?? '').toLowerCase().includes(normalized)) {
    score += 4;
  }
  return score;
}

function ContractorPortal({ token, setError }: { token: string; setError: (message: string) => void }) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const loadDocuments = useCallback(async () => {
    setDocuments(await api<DocumentRecord[]>('/api/documents', token));
  }, [token]);

  useEffect(() => {
    loadDocuments().catch((error) => setError(error instanceof Error ? error.message : 'Could not load documents'));
  }, [loadDocuments, setError]);

  async function handleUpload(form: HTMLFormElement) {
    setIsLoading(true);
    setError('');
    try {
      await api('/api/documents/upload', token, { method: 'POST', body: new FormData(form) });
      form.reset();
      await loadDocuments();
    } catch (currentError) {
      setError(currentError instanceof Error ? currentError.message : 'Upload failed');
    } finally {
      setIsLoading(false);
    }
  }

  async function handleDownload(document: DocumentRecord) {
    try {
      const sas = await api<SasUrlResponse>(`/api/documents/${document.id}/sas-url`, token);
      window.open(sas.url, '_blank', 'noopener,noreferrer');
    } catch {
      const response = await fetch(`/api/documents/${document.id}/download`, { headers: authHeaders(token) });
      await assertOk(response);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement('a');
      link.href = url;
      link.download = document.stored_filename || document.original_filename;
      link.click();
      URL.revokeObjectURL(url);
    }
  }

  return (
    <div className="workspace">
      <section className="panel" aria-labelledby="upload-title">
        <div className="section-heading">
          <h2 id="upload-title">Upload Document</h2>
          <Upload size={18} />
        </div>
        <form className="upload-form" onSubmit={(event) => { event.preventDefault(); void handleUpload(event.currentTarget); }}>
          <label className="field"><span>Title</span><input name="title" required maxLength={200} /></label>
          <label className="field"><span>Document type</span><input name="document_type" required maxLength={80} /></label>
          <label className="field"><span>Notes</span><textarea name="notes" rows={4} /></label>
          <label className="field"><span>File</span><input name="file" type="file" required accept=".pdf,.doc,.docx,.txt,.csv,.xlsx,.png,.jpg,.jpeg" /></label>
          <button className="primary-button" type="submit" disabled={isLoading}>{isLoading ? 'Uploading...' : 'Upload'}</button>
        </form>
      </section>
      <section className="panel full">
        <h2>My Uploads</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Title</th><th>Status</th><th>File</th><th>Action</th></tr></thead>
            <tbody>
              {documents.map((document) => (
                <tr key={document.id}>
                  <td><strong>{document.title}</strong><span className="muted">{document.notes}</span></td>
                  <td>{document.processing_status}</td>
                  <td>{document.original_filename}<span className="muted">{formatBytes(document.size_bytes)}</span></td>
                  <td><button className="icon-button" type="button" onClick={() => void handleDownload(document)} title="Download"><Download size={16} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p className="empty">{text}</p>;
}

function authHeaders(token?: string): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function mergeHeaders(token?: string, headers?: FetchInit['headers']) {
  const merged = new globalThis.Headers(headers);
  if (token) {
    merged.set('Authorization', `Bearer ${token}`);
  }
  return merged;
}

async function api<T>(path: string, token?: string, init: FetchInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: mergeHeaders(token, init.headers),
  });
  await assertOk(response);
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
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

function toTitle(value: string) {
  return value
    .split(/[_-]/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}
