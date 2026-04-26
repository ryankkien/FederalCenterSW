import { FormEvent, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  BarChart3,
  BookOpen,
  CheckCircle2,
  Download,
  FileText,
  Filter,
  Layers3,
  Link2,
  LockKeyhole,
  LogOut,
  RefreshCw,
  Search,
  ShieldCheck,
  TrendingDown,
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
  detected_kind: string;
  matched_contract_id: string | null;
  match_status: string;
  processing_status: string;
  created_at: string;
};

type TimelineSignal = {
  id: string;
  category: string;
  label: string;
  summary: string;
  polarity: string;
  severity?: string | null;
  confidence?: number | null;
  document_id?: string | null;
  quote?: string | null;
  responsible_party?: string | null;
  recurrence_key: string;
};

type TimelineReport = {
  document_id: string;
  title: string;
  document_kind: string;
  period_label: string;
  report_period_start?: string | null;
  report_period_end?: string | null;
  created_at: string;
  processing_status: string;
  signals: TimelineSignal[];
};

type ContractPattern = {
  key: string;
  title: string;
  count: number;
  document_count: number;
  first_period_label?: string | null;
  last_period_label?: string | null;
  examples: string[];
};

type CparsRating = {
  label: string;
  rating: string;
  period_label?: string | null;
  summary?: string | null;
  source: string;
};

type PrimitiveCitation = {
  primitive_id: string;
  primitive_type: string;
  document_id?: string | null;
  label?: string | null;
  excerpt?: string | null;
};

type AnalystClaim = {
  title: string;
  finding: string;
  citations: PrimitiveCitation[];
  confidence?: number | null;
};

type PerformanceAxis = {
  axis: string;
  status: string;
  target_value: Record<string, unknown>;
  cohort_distribution?: Record<string, number | null> | null;
  target_percentile?: number | null;
  low_confidence: boolean;
  rationale: string;
  citations: PrimitiveCitation[];
};

type PredictedCparsFactor = {
  factor: string;
  rating?: string | null;
  not_extractable: boolean;
  rationale: string;
  citations: PrimitiveCitation[];
};

type AnalysisRun = {
  id: string;
  run_type: string;
  status: string;
  target_contract_id?: string | null;
  cohort_N?: number | null;
  result?: Record<string, unknown> | null;
  created_at?: string | null;
  completed_at?: string | null;
  model?: string | null;
};

type ContractAnalystBrief = {
  problem_statement: string;
  summary: string;
  outcome_context: AnalystClaim[];
  recurring_vs_one_off: AnalystClaim[];
  pre_degradation_signals: AnalystClaim[];
  success_or_recovery_signals: AnalystClaim[];
  execution_assessment: AnalystClaim[];
  government_vs_contractor: AnalystClaim[];
  limitations: string[];
};

type ContractTimelineAnalysis = {
  contract_id: string;
  contract_title: string;
  timeline: TimelineReport[];
  recurring_issues: ContractPattern[];
  one_off_issues: ContractPattern[];
  early_warning_signals: TimelineSignal[];
  positive_signals: TimelineSignal[];
  execution_patterns: TimelineSignal[];
  cpars_ratings: CparsRating[];
  analyst_brief?: ContractAnalystBrief | null;
  ai_analysis?: AnalysisRun | null;
  axes: PerformanceAxis[];
  cpars_predicted: Record<string, PredictedCparsFactor>;
  limitations: string[];
};

type CohortContractBrief = {
  contract_id: string;
  contract_title: string;
  performance_band: string;
  document_count: number;
  recurring_issue_count: number;
  positive_signal_count: number;
  execution_pattern_count: number;
  cpars_rating_count: number;
};

type CohortAnalysis = {
  contract_count: number;
  contracts: CohortContractBrief[];
  poor_contract_common_patterns: ContractPattern[];
  well_performing_common_patterns: ContractPattern[];
  delta_lessons: string[];
  qualitative_quantitative_correlations: string[];
  execution_correlations: string[];
  limitations: string[];
};

type SimilarContractInsight = {
  contract_id: string;
  contract_title: string;
  similarity_score?: number | null;
  match_basis: string[];
  failure_points: ContractPattern[];
  early_warnings: TimelineSignal[];
  recommendations: string[];
};

type ContractSimilarityInsights = {
  contract_id: string;
  target_contract_title: string;
  similar_contracts: SimilarContractInsight[];
  shared_failure_points: ContractPattern[];
  recommendations: string[];
  methodology: string[];
  limitations: string[];
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
          <h1>{user.role === 'official' ? 'Contract Analysis Workspace' : 'Contractor Document Portal'}</h1>
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
        <OfficialWorkspace token={token} setError={setError} />
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

function OfficialWorkspace({ token, setError }: { token: string; setError: (message: string) => void }) {
  const [indexOpen, setIndexOpen] = useState(false);

  return (
    <div className="official-stack">
      <OfficialAnalysisWorkspace token={token} setError={setError} />
      <details className="secondary-knowledge-index" onToggle={(event) => setIndexOpen(event.currentTarget.open)}>
        <summary>Evidence index</summary>
        {indexOpen ? <WikiWorkspace token={token} setError={setError} /> : null}
      </details>
    </div>
  );
}

function OfficialAnalysisWorkspace({ token, setError }: { token: string; setError: (message: string) => void }) {
  const [contracts, setContracts] = useState<ContractRecord[]>([]);
  const [selectedContractId, setSelectedContractId] = useState('');
  const [analysis, setAnalysis] = useState<ContractTimelineAnalysis | null>(null);
  const [cohort, setCohort] = useState<CohortAnalysis | null>(null);
  const [similarityInsights, setSimilarityInsights] = useState<ContractSimilarityInsights | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRunningAi, setIsRunningAi] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    try {
      const nextContracts = await api<ContractRecord[]>('/api/contracts', token);
      setContracts(nextContracts);
      const nextSelectedId = selectedContractId || nextContracts[0]?.id || '';
      setSelectedContractId(nextSelectedId);
      const [nextAnalysis, nextCohort, nextSimilarityInsights] = await Promise.all([
        nextSelectedId ? api<ContractTimelineAnalysis>(`/api/analysis/contracts/${nextSelectedId}`, token) : Promise.resolve(null),
        api<CohortAnalysis>('/api/analysis/cohort', token),
        nextSelectedId ? api<ContractSimilarityInsights>(`/api/contracts/${nextSelectedId}/similarity-insights`, token) : Promise.resolve(null),
      ]);
      setAnalysis(nextAnalysis);
      setCohort(nextCohort);
      setSimilarityInsights(nextSimilarityInsights);
    } catch (currentError) {
      setError(currentError instanceof Error ? currentError.message : 'Could not load contract analysis');
    } finally {
      setIsLoading(false);
    }
  }, [selectedContractId, setError, token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function selectContract(contractId: string) {
    setSelectedContractId(contractId);
    setIsLoading(true);
    try {
      const [nextAnalysis, nextSimilarityInsights] = await Promise.all([
        api<ContractTimelineAnalysis>(`/api/analysis/contracts/${contractId}`, token),
        api<ContractSimilarityInsights>(`/api/contracts/${contractId}/similarity-insights`, token),
      ]);
      setAnalysis(nextAnalysis);
      setSimilarityInsights(nextSimilarityInsights);
    } catch (currentError) {
      setError(currentError instanceof Error ? currentError.message : 'Could not load contract analysis');
    } finally {
      setIsLoading(false);
    }
  }

  async function runAiAnalysis() {
    if (!selectedContractId) {
      return;
    }
    setIsRunningAi(true);
    setError('');
    try {
      await api<AnalysisRun>(`/api/contracts/${selectedContractId}/performance-analysis`, token, {
        method: 'POST',
      });
      const nextAnalysis = await api<ContractTimelineAnalysis>(`/api/analysis/contracts/${selectedContractId}`, token);
      setAnalysis(nextAnalysis);
    } catch (currentError) {
      setError(currentError instanceof Error ? currentError.message : 'Could not run OpenAI analysis');
    } finally {
      setIsRunningAi(false);
    }
  }

  const latestSignals = analysis?.timeline.flatMap((report) => report.signals.slice(0, 3)).slice(0, 8) ?? [];
  const selectedContract = contracts.find((contract) => contract.id === selectedContractId);
  const hasCpars = Boolean(analysis?.cpars_ratings.length);
  const topRecurring = analysis?.recurring_issues.slice(0, 2).map((issue) => issue.title).join(', ');

  return (
    <section className="analysis-workspace" aria-labelledby="analysis-title">
      <div className="analysis-header">
        <div>
          <p className="eyebrow">Government Analysis</p>
          <h2 id="analysis-title">Contract Timeline And Cohort Patterns</h2>
        </div>
        <div className="analysis-actions">
          <button className="secondary-button" type="button" onClick={() => void runAiAnalysis()} disabled={isRunningAi || isLoading || !selectedContractId}>
            <RefreshCw size={16} />
            {isRunningAi ? 'Running OpenAI' : 'Run OpenAI analysis'}
          </button>
          <label className="compact-field">
            <span>Contract</span>
            <select value={selectedContractId} onChange={(event) => void selectContract(event.target.value)}>
              {contracts.map((contract) => (
                <option key={contract.id} value={contract.id}>
                  {contract.id}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <section className="contract-brief">
        <div className="article-header">
          <div>
            <p className="eyebrow">Contract Brief</p>
            <h3>{analysis?.contract_title ?? selectedContract?.title ?? 'Contract'}</h3>
          </div>
          <span className="security-badge">
            <ShieldCheck size={14} /> Standard
          </span>
        </div>
        <p className="article-summary">
          {buildContractBriefSummary(selectedContract, analysis, cohort)}
        </p>
        <div className="brief-section-grid">
          <article className="brief-section">
            <strong>Current Read</strong>
            <p>{topRecurring ? `Recurring signals: ${topRecurring}.` : 'No recurring issue family has crossed the current threshold.'}</p>
          </article>
          <article className="brief-section">
            <strong>Outcome Context</strong>
            <p>{hasCpars ? 'Imported CPARS ratings are available for outcome comparison.' : 'No actual CPARS ratings are imported for this contract yet.'}</p>
          </article>
          <article className="brief-section">
            <strong>Child Records</strong>
            <p>{selectedContract?.document_count ?? analysis?.timeline.length ?? 0} linked document(s), {selectedContract?.open_regression_count ?? 0} open regression finding(s), {selectedContract?.active_hypothesis_count ?? 0} active hypothesis item(s).</p>
          </article>
          <article className="brief-section">
            <strong>Cohort</strong>
            <p>{cohort?.contract_count ? `${cohort.contract_count} visible contract(s) are available for pattern comparison.` : 'No comparable visible contracts are available yet.'}</p>
          </article>
        </div>
      </section>
      <OpenAiAnalysis run={analysis?.ai_analysis ?? null} isRunning={isRunningAi} />
      {analysis?.analyst_brief ? <AnalystBrief brief={analysis.analyst_brief} /> : null}
      <div className="metric-grid">
        <MetricCard label="Reports" value={analysis?.timeline.length ?? 0} icon={<FileText size={17} />} />
        <MetricCard label="Recurring Issues" value={analysis?.recurring_issues.length ?? 0} icon={<TrendingDown size={17} />} />
        <MetricCard label="Positive Signals" value={analysis?.positive_signals.length ?? 0} icon={<CheckCircle2 size={17} />} />
        <MetricCard label="Cohort Contracts" value={cohort?.contract_count ?? 0} icon={<Layers3 size={17} />} />
      </div>
      <div className="analysis-grid">
        <AnalysisPanel title="Similar Contracts" icon={<Link2 size={16} />}>
          <SimilarContractsList insights={similarityInsights} />
        </AnalysisPanel>
        <AnalysisPanel title="Future Contract Writing" icon={<BookOpen size={16} />}>
          <TextList items={similarityInsights?.recommendations ?? []} empty="No similar-contract drafting guidance is available yet." />
          <div className="rail-divider" />
          <PatternList patterns={similarityInsights?.shared_failure_points ?? []} empty="No shared failure points have crossed the current threshold." compact />
        </AnalysisPanel>
        <AnalysisPanel title="Chronological Report Signals" icon={<BarChart3 size={16} />}>
          {analysis?.timeline.length ? (
            <div className="timeline-list">
              {analysis.timeline.map((report) => (
                <article className="timeline-row" key={report.document_id}>
                  <div>
                    <strong>{report.period_label}</strong>
                    <span>{report.title}</span>
                  </div>
                  <small>{toTitle(report.document_kind)} · {report.signals.length} signal(s)</small>
                </article>
              ))}
            </div>
          ) : (
            <p className="empty">{isLoading ? 'Loading analysis.' : 'No child reports are linked to this contract.'}</p>
          )}
        </AnalysisPanel>
        <AnalysisPanel title="Recurring Vs One-Off" icon={<Filter size={16} />}>
          <PatternList patterns={analysis?.recurring_issues ?? []} empty="No recurring issues detected yet." />
          <div className="rail-divider" />
          <PatternList patterns={analysis?.one_off_issues ?? []} empty="No one-off issues detected yet." compact />
        </AnalysisPanel>
        <AnalysisPanel title="Early Warnings And Positives" icon={<CheckCircle2 size={16} />}>
          <SignalList signals={analysis?.early_warning_signals ?? []} empty="No pre-degradation warning signals found yet." />
          <div className="rail-divider" />
          <SignalList signals={analysis?.positive_signals ?? []} empty="No positive signals extracted yet." />
        </AnalysisPanel>
        <AnalysisPanel title="Execution Patterns" icon={<Layers3 size={16} />}>
          <SignalList signals={analysis?.execution_patterns ?? latestSignals} empty="No sequencing, subcontractor, QC, staffing, or PMP execution signals found yet." />
        </AnalysisPanel>
        <AnalysisPanel title="CPARS Outcome Context" icon={<TrendingDown size={16} />}>
          <CparsList ratings={analysis?.cpars_ratings ?? []} />
          <div className="rail-divider" />
          <PredictedCparsList factors={Object.values(analysis?.cpars_predicted ?? {})} />
          <div className="rail-divider" />
          <CohortBriefList contracts={cohort?.contracts ?? []} />
        </AnalysisPanel>
        <AnalysisPanel title="Measurement Axes" icon={<BarChart3 size={16} />}>
          <AxisList axes={analysis?.axes ?? []} />
        </AnalysisPanel>
        <AnalysisPanel title="Cohort Lessons" icon={<BookOpen size={16} />}>
          <TextList items={cohort?.delta_lessons ?? []} empty="No cohort deltas are available yet." />
          <div className="rail-divider" />
          <TextList items={cohort?.qualitative_quantitative_correlations ?? []} empty="Import CPARS ratings to test qualitative-to-quantitative correlations." />
        </AnalysisPanel>
        <AnalysisPanel title="Cohort Pattern Sets" icon={<Link2 size={16} />}>
          <PatternList patterns={cohort?.poor_contract_common_patterns ?? []} empty="No poor-performing cohort pattern set yet." compact />
          <div className="rail-divider" />
          <PatternList patterns={cohort?.well_performing_common_patterns ?? []} empty="No well-performing or recovered cohort pattern set yet." compact />
        </AnalysisPanel>
      </div>
      {analysis?.limitations.length || cohort?.limitations.length || similarityInsights?.limitations.length ? (
        <div className="limitations-row">
          {[...(analysis?.limitations ?? []), ...(cohort?.limitations ?? []), ...(similarityInsights?.limitations ?? [])].map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function MetricCard({ label, value, icon }: { label: string; value: number; icon: ReactNode }) {
  return (
    <div className="metric-card">
      <span>{icon}</span>
      <strong>{value}</strong>
      <small>{label}</small>
    </div>
  );
}

function AnalysisPanel({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section className="analysis-panel">
      <div className="section-heading">
        <h3>{title}</h3>
        {icon}
      </div>
      {children}
    </section>
  );
}

function OpenAiAnalysis({ run, isRunning }: { run: AnalysisRun | null; isRunning: boolean }) {
  const result = run?.result ?? null;
  const axes = Array.isArray(result?.axes) ? result.axes : [];
  const cpars = result?.cpars_predicted && typeof result.cpars_predicted === 'object'
    ? Object.entries(result.cpars_predicted as Record<string, unknown>)
    : [];
  const summary = textFromUnknown(result?.summary);

  return (
    <section className="openai-analysis">
      <div className="section-heading">
        <div>
          <p className="eyebrow">OpenAI Analyst Run</p>
          <h3>Contract Performance Explanation</h3>
        </div>
        <span className={`status ${run?.status ?? (isRunning ? 'pending' : 'neutral')}`}>
          {isRunning ? 'running' : run?.status ?? 'not run'}
        </span>
      </div>
      {run ? (
        <>
          <p className="analyst-summary">{summary || 'OpenAI returned structured analysis without a top-level summary.'}</p>
          <div className="run-metadata">
            <span>Model: {run.model ?? 'gpt-5.4-mini'}</span>
            {run.completed_at ? <span>Completed: {new Date(run.completed_at).toLocaleString()}</span> : null}
            <span>Run: {run.id.slice(0, 8)}</span>
          </div>
          <div className="analyst-claim-grid">
            <article className="claim-group">
              <strong>Measured Axes</strong>
              {axes.length ? (
                axes.slice(0, 3).map((axis, index) => (
                  <div className="claim-row" key={`ai-axis-${index}`}>
                    <span>{toTitle(textFromUnknown((axis as Record<string, unknown>).axis) || `axis ${index + 1}`)}</span>
                    <p>{aiAxisSummary(axis)}</p>
                  </div>
                ))
              ) : (
                <p className="empty">No extractable measured axes came back from OpenAI.</p>
              )}
            </article>
            <article className="claim-group">
              <strong>Predicted CPARS</strong>
              {cpars.length ? (
                cpars.slice(0, 3).map(([factor, value]) => (
                  <div className="claim-row" key={factor}>
                    <span>{factor}</span>
                    <p>{aiCparsSummary(value)}</p>
                  </div>
                ))
              ) : (
                <p className="empty">No predicted CPARS factors came back from OpenAI.</p>
              )}
            </article>
            <article className="claim-group">
              <strong>Citations</strong>
              <p className="empty">Claims in this run are constrained to primitive IDs from extracted contract records.</p>
            </article>
          </div>
        </>
      ) : (
        <p className="empty">
          {isRunning ? 'OpenAI is building a cited contract analysis.' : 'No OpenAI analyst run has been created for this contract yet.'}
        </p>
      )}
    </section>
  );
}

function AnalystBrief({ brief }: { brief: ContractAnalystBrief }) {
  return (
    <section className="analyst-brief">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Extracted Evidence Rollup</p>
          <h3>Source Signal Context</h3>
        </div>
        <ShieldCheck size={16} />
      </div>
      <p className="analyst-summary">{brief.summary}</p>
      <div className="analyst-claim-grid">
        <ClaimGroup title="Outcome To Explain" claims={brief.outcome_context} empty="No CPARS/EVM outcome primitive is imported yet." />
        <ClaimGroup title="Recurring Vs One-Off" claims={brief.recurring_vs_one_off} empty="No recurring issue explanation is available yet." />
        <ClaimGroup title="Before Degradation" claims={brief.pre_degradation_signals} empty="No cited pre-degradation warning signal has been found yet." />
        <ClaimGroup title="What Worked" claims={brief.success_or_recovery_signals} empty="No cited positive or recovery signal has been found yet." />
        <ClaimGroup title="Execution Pattern" claims={brief.execution_assessment} empty="No cited sequencing, subcontractor, QC, staffing, or PMP execution pattern is available yet." />
        <ClaimGroup title="Cause Bucket" claims={brief.government_vs_contractor} empty="No responsible-party pattern is strong enough yet." />
      </div>
      {brief.limitations.length ? (
        <div className="limitations-row">
          {brief.limitations.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function aiAxisSummary(axis: unknown) {
  if (!axis || typeof axis !== 'object') {
    return textFromUnknown(axis);
  }
  const value = axis as Record<string, unknown>;
  return textFromUnknown(value.rationale)
    || textFromUnknown(value.status)
    || textFromUnknown(value.target_value)
    || 'Axis returned without a readable rationale.';
}

function aiCparsSummary(value: unknown) {
  if (!value || typeof value !== 'object') {
    return textFromUnknown(value);
  }
  const record = value as Record<string, unknown>;
  const rating = textFromUnknown(record.rating);
  const rationale = textFromUnknown(record.rationale);
  if (rating && rationale) {
    return `${rating}: ${rationale}`;
  }
  return rating || rationale || 'No readable CPARS rationale returned.';
}

function ClaimGroup({ title, claims, empty }: { title: string; claims: AnalystClaim[]; empty: string }) {
  return (
    <article className="claim-group">
      <strong>{title}</strong>
      {claims.length ? (
        claims.slice(0, 2).map((claim) => (
          <div className="claim-row" key={`${title}-${claim.title}`}>
            <span>{claim.title}</span>
            <p>{claim.finding}</p>
            <CitationChips citations={claim.citations} />
          </div>
        ))
      ) : (
        <p className="empty">{empty}</p>
      )}
    </article>
  );
}

function CitationChips({ citations }: { citations: PrimitiveCitation[] }) {
  if (!citations.length) {
    return null;
  }
  return (
    <div className="citation-chips">
      {citations.slice(0, 3).map((citation) => (
        <span title={citation.excerpt ?? citation.label ?? citation.primitive_id} key={`${citation.primitive_type}-${citation.primitive_id}`}>
          {citation.primitive_type}: {citation.primitive_id.slice(0, 8)}
        </span>
      ))}
    </div>
  );
}

function SimilarContractsList({ insights }: { insights: ContractSimilarityInsights | null }) {
  const contracts = insights?.similar_contracts ?? [];
  if (!contracts.length) {
    return <p className="empty">No similar visible contracts have enough extracted evidence yet.</p>;
  }
  return (
    <div className="pattern-list">
      {contracts.slice(0, 4).map((contract) => (
        <article className="pattern-row" key={contract.contract_id}>
          <strong>{contract.contract_title}</strong>
          <small>
            {contract.similarity_score !== null && contract.similarity_score !== undefined
              ? `${Math.round(contract.similarity_score * 100)}% similarity`
              : 'Comparable contract'}
          </small>
          {contract.match_basis[0] ? <span>{contract.match_basis[0]}</span> : null}
          {contract.failure_points[0] ? <p>{contract.failure_points[0].title}: {contract.failure_points[0].examples[0]}</p> : null}
          {contract.recommendations[0] ? <p>{contract.recommendations[0]}</p> : null}
        </article>
      ))}
    </div>
  );
}

function PatternList({ patterns, empty, compact = false }: { patterns: ContractPattern[]; empty: string; compact?: boolean }) {
  if (!patterns.length) {
    return <p className="empty">{empty}</p>;
  }
  return (
    <div className="pattern-list">
      {patterns.slice(0, compact ? 4 : 6).map((pattern) => (
        <article className="pattern-row" key={pattern.key}>
          <strong>{pattern.title}</strong>
          <small>{pattern.document_count} contract/report item(s) · {pattern.count} signal(s)</small>
          {pattern.examples[0] ? <span>{pattern.examples[0]}</span> : null}
        </article>
      ))}
    </div>
  );
}

function SignalList({ signals, empty }: { signals: TimelineSignal[]; empty: string }) {
  if (!signals.length) {
    return <p className="empty">{empty}</p>;
  }
  return (
    <div className="signal-list">
      {signals.slice(0, 6).map((signal) => (
        <article className="signal-row" key={signal.id}>
          <span className={`status ${signal.severity ?? signal.polarity}`}>{signal.polarity}</span>
          <strong>{signal.label}</strong>
          {signal.responsible_party ? <small>{toTitle(signal.responsible_party)}</small> : null}
          <p>{signal.summary}</p>
        </article>
      ))}
    </div>
  );
}

function TextList({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length) {
    return <p className="empty">{empty}</p>;
  }
  return (
    <div className="text-list">
      {items.slice(0, 5).map((item) => (
        <p key={item}>{item}</p>
      ))}
    </div>
  );
}

function CparsList({ ratings }: { ratings: CparsRating[] }) {
  if (!ratings.length) {
    return <p className="empty">No actual CPARS ratings are imported for this contract.</p>;
  }
  return (
    <div className="pattern-list">
      {ratings.slice(0, 6).map((rating) => (
        <article className="pattern-row" key={`${rating.label}-${rating.rating}-${rating.period_label ?? rating.source}`}>
          <strong>{rating.label}: {rating.rating}</strong>
          <small>{rating.period_label || rating.source}</small>
          {rating.summary ? <span>{rating.summary}</span> : null}
        </article>
      ))}
    </div>
  );
}

function PredictedCparsList({ factors }: { factors: PredictedCparsFactor[] }) {
  const extractable = factors.filter((factor) => !factor.not_extractable && factor.rating);
  if (!extractable.length) {
    return <p className="empty">No predicted CPARS factor is extractable from measured primitives yet.</p>;
  }
  return (
    <div className="pattern-list">
      {extractable.slice(0, 6).map((factor) => (
        <article className="pattern-row" key={factor.factor}>
          <strong>Predicted {factor.factor}: {factor.rating}</strong>
          <span>{factor.rationale}</span>
          <CitationChips citations={factor.citations} />
        </article>
      ))}
    </div>
  );
}

function AxisList({ axes }: { axes: PerformanceAxis[] }) {
  if (!axes.length) {
    return <p className="empty">No measured axes are available yet.</p>;
  }
  return (
    <div className="axis-list">
      {axes.slice(0, 9).map((axis) => (
        <article className="axis-row" key={axis.axis}>
          <div>
            <strong>{toTitle(axis.axis)}</strong>
            <span className={`status ${axis.status === 'measured' ? 'positive' : 'neutral'}`}>{axis.status}</span>
          </div>
          <p>{axis.rationale}</p>
          {axis.status === 'measured' ? (
            <small>
              Target: {formatAxisValue(axis.target_value)}
              {axis.target_percentile !== null && axis.target_percentile !== undefined ? ` · Cohort percentile ${Math.round(axis.target_percentile)}` : ''}
              {axis.low_confidence ? ' · low confidence' : ''}
            </small>
          ) : null}
          <CitationChips citations={axis.citations} />
        </article>
      ))}
    </div>
  );
}

function formatAxisValue(value: Record<string, unknown>) {
  const entries = Object.entries(value).slice(0, 3);
  if (!entries.length) {
    return 'not recorded';
  }
  return entries
    .map(([key, currentValue]) => `${toTitle(key)} ${formatPrimitiveValue(currentValue)}`)
    .join(', ');
}

function formatPrimitiveValue(value: unknown): string {
  if (value === null || value === undefined) {
    return 'not recorded';
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
}

function textFromUnknown(value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(textFromUnknown).filter(Boolean).join(' ');
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return textFromUnknown(record.text ?? record.summary ?? record.rationale ?? JSON.stringify(record));
  }
  return '';
}

function CohortBriefList({ contracts }: { contracts: CohortContractBrief[] }) {
  if (!contracts.length) {
    return <p className="empty">No comparable visible contracts are available.</p>;
  }
  return (
    <div className="pattern-list">
      {contracts.slice(0, 5).map((contract) => (
        <article className="pattern-row" key={contract.contract_id}>
          <strong>{contract.contract_title}</strong>
          <small>{toTitle(contract.performance_band)} · {contract.document_count} report(s)</small>
        </article>
      ))}
    </div>
  );
}

function buildContractBriefSummary(
  contract: ContractRecord | undefined,
  analysis: ContractTimelineAnalysis | null,
  cohort: CohortAnalysis | null,
) {
  const title = analysis?.contract_title ?? contract?.title ?? 'This contract';
  const reportCount = analysis?.timeline.length ?? contract?.document_count ?? 0;
  const recurringCount = analysis?.recurring_issues.length ?? 0;
  const positiveCount = analysis?.positive_signals.length ?? 0;
  const cohortCount = cohort?.contract_count ?? 0;
  return `${title} has ${reportCount} linked report/document record(s), ${recurringCount} recurring issue pattern(s), ${positiveCount} positive signal(s), and ${cohortCount} visible contract(s) in the comparison set.`;
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
  const [contracts, setContracts] = useState<ContractRecord[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedContractId, setSelectedContractId] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const loadPortal = useCallback(async () => {
    const [nextContracts, nextDocuments] = await Promise.all([
      api<ContractRecord[]>('/api/contracts', token),
      api<DocumentRecord[]>('/api/documents', token),
    ]);
    setContracts(nextContracts);
    setDocuments(nextDocuments);
    setSelectedContractId((current) => current || nextContracts[0]?.id || '');
  }, [token]);

  useEffect(() => {
    loadPortal().catch((error) => setError(error instanceof Error ? error.message : 'Could not load documents'));
  }, [loadPortal, setError]);

  async function handleUpload(form: HTMLFormElement) {
    setIsLoading(true);
    setError('');
    try {
      await api('/api/documents/upload', token, { method: 'POST', body: new FormData(form) });
      form.reset();
      await loadPortal();
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
          <label className="field">
            <span>Contract</span>
            <select name="contract_id" required value={selectedContractId} onChange={(event) => setSelectedContractId(event.target.value)}>
              {contracts.map((contract) => (
                <option key={contract.id} value={contract.id}>
                  {contract.id} · {contract.title}
                </option>
              ))}
            </select>
          </label>
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
                  <td><strong>{document.title}</strong><span className="muted">{document.contract_id ?? 'Contract pending'} · {document.notes}</span></td>
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
