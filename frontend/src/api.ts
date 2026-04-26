/* eslint-disable @typescript-eslint/no-explicit-any */
const TOKEN_KEY = 'fcsw-token';

type RequestOptions = NonNullable<Parameters<typeof fetch>[1]> & {
  form?: FormData;
};

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

async function request(path: string, options: RequestOptions = {}) {
  const headers = {
    ...authHeaders(),
    ...((options.headers as Record<string, string>) || {}),
  };
  const init: NonNullable<Parameters<typeof fetch>[1]> = {
    ...options,
    headers,
    body: options.form || options.body,
  };
  delete (init as RequestOptions).form;
  const response = await fetch(path, init);
  if (!response.ok) {
    let message = `Request failed with ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep the status-based message when the response is not JSON.
    }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

export async function mockLogin(role: string) {
  return request('/api/auth/mock-login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  });
}

export async function listContracts() {
  return request('/api/contracts');
}

export async function createContract(payload: Record<string, unknown>) {
  return request('/api/contracts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function listAllDocuments() {
  return request('/api/documents');
}

export async function listContractDocuments(contractId: string) {
  return request(`/api/contracts/${encodeURIComponent(contractId)}/documents`);
}

export async function getDocument(documentId: string) {
  return request(`/api/documents/${encodeURIComponent(documentId)}`);
}

export async function downloadDocumentBlob(documentId: string) {
  const response = await fetch(`/api/documents/${encodeURIComponent(documentId)}/download`, {
    headers: authHeaders(),
  });
  if (!response.ok) throw new Error(`Request failed with ${response.status}`);
  return response.blob();
}

export async function uploadDocument({
  contractId,
  title,
  documentType,
  notes,
  file,
  processInline = true,
}: {
  contractId?: string;
  title: string;
  documentType: string;
  notes?: string;
  file: File;
  processInline?: boolean;
}) {
  const form = new FormData();
  form.append('title', title);
  form.append('document_type', documentType);
  if (notes) form.append('notes', notes);
  if (contractId) form.append('contract_id', contractId);
  if (processInline) form.append('process_inline', 'true');
  form.append('file', file);
  return request('/api/documents/upload', { method: 'POST', form });
}

export async function listDeliverables(contractId: string) {
  return request(`/api/contracts/${encodeURIComponent(contractId)}/deliverables`);
}

export async function listRegressions(contractId: string) {
  return request(`/api/contracts/${encodeURIComponent(contractId)}/regressions`);
}

export async function listSimilarContracts(contractId: string) {
  return request(`/api/contracts/${encodeURIComponent(contractId)}/similar-contracts`);
}

export async function getContractAnalysis(contractId: string) {
  return request(`/api/analysis/contracts/${encodeURIComponent(contractId)}`);
}

export async function getContractLifecycle(contractId: string) {
  return request(`/api/contracts/${encodeURIComponent(contractId)}/lifecycle`);
}

export async function listProcessingJobs(contractId: string) {
  return request(`/api/contracts/${encodeURIComponent(contractId)}/processing-jobs`);
}

export async function getContractDeliverables(contractId: string) {
  return request(`/api/contracts/${encodeURIComponent(contractId)}/deliverables`);
}

export async function getContractCohort(contractId: string) {
  return request(`/api/contracts/${encodeURIComponent(contractId)}/cohort`);
}

export async function getContractSimilarityInsights(contractId: string) {
  return request(`/api/contracts/${encodeURIComponent(contractId)}/similarity-insights`);
}

export async function getPortfolioThemes(period?: string) {
  const params = new URLSearchParams();
  if (period) params.set('period', period);
  const suffix = params.toString() ? `?${params}` : '';
  return request(`/api/portfolio/themes${suffix}`);
}

export async function getPortfolioLessons(period?: string) {
  const params = new URLSearchParams();
  if (period) params.set('period', period);
  const suffix = params.toString() ? `?${params}` : '';
  return request(`/api/portfolio/lessons${suffix}`);
}

export async function getPortfolioGenerateStatus(): Promise<{
  new_doc_count: number;
  affected_contract_count: number;
}> {
  return request('/api/portfolio/generate-status');
}

export async function postGenerateInsights(): Promise<{ queued: number }> {
  return request('/api/portfolio/generate-insights', { method: 'POST' });
}

export async function getContractAnalysisLog(contractId: string): Promise<Array<{
  id: string;
  status: string;
  run_type?: string;
  created_at: string;
  completed_at?: string;
  analyzed_doc_count: number;
  summary?: string;
  prior_run_id?: string;
  changes?: Array<{ axis: string; change_type: string; description: string }>;
  investigated_contract_ids?: string[];
  insight_hypothesis_id?: string;
}>> {
  return request(`/api/contracts/${encodeURIComponent(contractId)}/analysis-log`);
}

export async function downloadContractInsightsPdf(contractId: string, contractNumber: string): Promise<void> {
  const response = await fetch(`/api/contracts/${encodeURIComponent(contractId)}/insights-pdf`, {
    headers: authHeaders(),
  });
  if (!response.ok) throw new Error(`Export failed with ${response.status}`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const safe = (contractNumber || contractId || 'contract').replace(/[^A-Za-z0-9._-]+/g, '_');
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${safe}_insights.pdf`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function normalizeContract(row: any) {
  const start = row.period_start || row.start || '2026-01-01';
  const end = row.period_end || row.end || '2027-12-31';
  const startMs = new Date(start).getTime();
  const endMs = new Date(end).getTime();
  const elapsed = Number.isFinite(startMs) && Number.isFinite(endMs) && endMs > startMs
    ? Math.max(0, Math.min(100, Math.round(((Date.now() - startMs) / (endMs - startMs)) * 100)))
    : 0;
  const number = row.contract_number || row.number || row.id;
  const psc = row.psc_code || row.psc || row.category_code || 'UNK';
  const naics = row.naics_code || row.naics || 'NA';
  const component = row.office_name || row.agency_name || row.component || 'Unassigned';
  return {
    ...row,
    id: row.id,
    number,
    title: row.title || number,
    psc,
    naics,
    component,
    value: row.obligated_value ? currency(row.obligated_value) : (row.value || 'TBD'),
    period: row.period || `${fmtDateMil(start)} — ${fmtDateMil(end)}`,
    start,
    end,
    elapsed,
    lastActivity: row.updated_at ? fmtDateMil(row.updated_at) : (row.created_at ? fmtDateMil(row.created_at) : 'No filings'),
    docsCount: row.document_count || 0,
    contractor: row.vendor_name || row.contractor_id || row.contractor || 'TBD',
    co: row.contracting_officer || row.co || 'TBD',
    classification: (row.security_level || 'standard').toUpperCase(),
  };
}

export function normalizeDocument(row: any, contract?: any) {
  const docType = row.document_type || row.document_kind || 'Document';
  const periodStart = row.report_period_start;
  const periodEnd = row.report_period_end;
  const period = periodStart && periodEnd
    ? `${fmtDateMil(periodStart)} — ${fmtDateMil(periodEnd)}`
    : periodStart || periodEnd || row.notes || '—';
  return {
    ...row,
    id: row.id,
    title: row.title || row.original_filename || 'Untitled document',
    doc_type: docType,
    source: sourceLabel(row),
    filename: row.original_filename || row.stored_filename || row.filename || `${row.id}.pdf`,
    content_type: row.content_type || 'application/octet-stream',
    size_bytes: row.size_bytes || 0,
    uploader: row.uploader_role || row.uploader_id || 'Unknown',
    created_at: row.created_at || new Date().toISOString(),
    period,
    contract_id: row.contract_id || contract?.id,
    pinned: docType.toLowerCase().includes('contract') || row.document_kind === 'source_contract',
    processing_status: row.processing_status,
    match_status: row.match_status,
  };
}

export function normalizeFinding(row: any) {
  return {
    id: row.id,
    severity: severityTone(row.severity),
    themeId: null,
    claim: row.title || row.finding_type || 'Contract finding',
    observed: row.summary || row.quote || 'No summary is available yet.',
    sourceDoc: row.document_title || row.document_id || row.document_upload_id || 'Analysis evidence',
    similar: [],
    raw: row,
  };
}

function sourceLabel(row: any) {
  if (row.intake_source === 'email') return 'Email intake';
  if (row.uploader_role === 'official') return 'Government';
  if (row.uploader_role === 'contractor') return 'Contractor';
  return row.source || 'Portal';
}

function severityTone(value: string) {
  const severity = String(value || '').toLowerCase();
  if (['critical', 'high'].includes(severity)) return 'critical';
  if (['medium', 'watch', 'warning'].includes(severity)) return 'watch';
  return 'watch';
}

function currency(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value || 'TBD');
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(numeric);
}

function fmtDateMil(s: string) {
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return 'TBD';
  const day = String(d.getDate()).padStart(2, '0');
  const mon = d.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
  return `${day} ${mon} ${d.getFullYear()}`;
}
