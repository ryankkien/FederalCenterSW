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

const contractRecord = {
  id: 'N40080-24-D-1042',
  title: 'Environmental Compliance and Permitting Support Services',
  status: 'active',
  source: 'contract_record',
  category_code: 'R',
  document_count: 2,
  open_regression_count: 1,
  active_hypothesis_count: 1,
  pending_job_count: 1,
  unmatched_document_count: 0,
  has_knowledge_base: true,
};

const documentRecord = {
  id: 'doc-1',
  title: 'Monthly progress report',
  document_type: 'Progress Report',
  document_kind: 'monthly_report',
  notes: 'Submitted for review',
  original_filename: 'progress.pdf',
  stored_filename: 'main.pdf',
  content_type: 'application/pdf',
  size_bytes: 1280,
  uploader_id: 'contractor-demo',
  uploader_role: 'contractor',
  contract_id: 'N40080-24-D-1042',
  match_status: 'matched',
  processing_status: 'queued',
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

  it('routes contractors to upload and status after login', async () => {
    const fetchMock = contractorFetch();
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.submit(screen.getByRole('button', { name: 'Continue' }).closest('form')!);

    expect(await screen.findByRole('heading', { name: 'Contractor Document Portal' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Upload Document' })).toBeInTheDocument();
    expect(screen.getByLabelText('Contract')).toBeInTheDocument();

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

  it('routes officials to the wiki index workspace', async () => {
    vi.stubGlobal('fetch', officialFetch());

    render(<App />);
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'official' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Continue' }).closest('form')!);

    expect(await screen.findByRole('heading', { name: 'Contract Analysis Workspace' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Contract Timeline And Cohort Patterns' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Contract Performance Explanation' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run OpenAI analysis' })).toBeInTheDocument();
    expect(screen.getByText('Model: gpt-5.4-mini')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Source Signal Context' })).toBeInTheDocument();
    expect(screen.getByText('Measurement Axes')).toBeInTheDocument();
    expect(screen.getByText('Similar Contracts')).toBeInTheDocument();
    expect(screen.getAllByText('Include a GFE/GFI/access responsibility matrix with owner, due date, acceptance criteria, and schedule relief rules.').length).toBeGreaterThan(0);
    expect(screen.getByText('Evidence index')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Grokipedia Index' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Evidence index'));
    expect(await screen.findByRole('heading', { name: 'Grokipedia Index' })).toBeInTheDocument();
    expect(
      await screen.findByRole('button', { name: /contract result Environmental Compliance/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Citations' })).toBeInTheDocument();
  });

  it('filters and opens wiki search results', async () => {
    const fetchMock = officialFetch();
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'official' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Continue' }).closest('form')!);
    fireEvent.click(await screen.findByText('Evidence index'));

    fireEvent.change(await screen.findByLabelText('Search knowledge index'), { target: { value: 'Aging RFI' } });
    fireEvent.click(await screen.findByRole('button', { name: /regression result Aging RFI/ }));

    expect(await screen.findByRole('heading', { name: 'Aging RFI' })).toBeInTheDocument();
    expect(screen.getAllByText('RFI is 21 days open.').length).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledWith('/api/wiki/search?q=Aging+RFI', expect.any(Object));
  });
});

function contractorFetch() {
  return vi.fn((input: Parameters<typeof fetch>[0]) => {
    const url = String(input);
    if (url === '/api/auth/mock-login') {
      return Promise.resolve(jsonResponse({ access_token: 'contractor-token', user: contractorUser }));
    }
    if (url === '/api/contracts') {
      return Promise.resolve(jsonResponse([contractRecord]));
    }
    if (url === '/api/documents') {
      return Promise.resolve(jsonResponse([documentRecord]));
    }
    if (url === '/api/documents/upload') {
      return Promise.resolve(jsonResponse(documentRecord, 201));
    }
    return Promise.resolve(jsonResponse({}));
  });
}

function officialFetch() {
  return vi.fn((input: Parameters<typeof fetch>[0]) => {
    const url = String(input);
    if (url === '/api/auth/mock-login') {
      return Promise.resolve(jsonResponse({ access_token: 'official-token', user: officialUser }));
    }
    if (url === '/api/contracts') {
      return Promise.resolve(jsonResponse([contractRecord]));
    }
    if (url === '/api/analysis/contracts/N40080-24-D-1042') {
      return Promise.resolve(jsonResponse(contractAnalysis));
    }
    if (url === '/api/contracts/N40080-24-D-1042/performance-analysis') {
      return Promise.resolve(jsonResponse(contractAnalysis.ai_analysis, 202));
    }
    if (url === '/api/analysis/cohort') {
      return Promise.resolve(jsonResponse(cohortAnalysis));
    }
    if (url === '/api/contracts/N40080-24-D-1042/similarity-insights') {
      return Promise.resolve(jsonResponse(similarityInsights));
    }
    if (url.startsWith('/api/wiki/search')) {
      if (url.includes('Aging+RFI')) {
        return Promise.resolve(jsonResponse([wikiRegressionNode]));
      }
      return Promise.resolve(jsonResponse([wikiContractNode, wikiRegressionNode, wikiContractorNode]));
    }
    if (url === '/api/wiki/contracts/N40080-24-D-1042') {
      return Promise.resolve(jsonResponse(wikiContractArticle));
    }
    if (url === '/api/wiki/nodes/reg-node-1') {
      return Promise.resolve(jsonResponse(wikiRegressionArticle));
    }
    if (url === '/api/wiki/contractors/UEIATLANTIC1') {
      return Promise.resolve(jsonResponse(wikiContractorArticle));
    }
    if (url === '/api/knowledge/ingestion-runs') {
      return Promise.resolve(jsonResponse({ id: 'run-1', status: 'completed', source_record_count: 2, node_count: 3, citation_count: 4 }, 202));
    }
    return Promise.resolve(jsonResponse({}));
  });
}

const wikiContractNode = {
  id: 'contract:N40080-24-D-1042',
  node_type: 'contract',
  title: 'Environmental Compliance and Permitting Support Services',
  summary: 'Onboarding article for the contract.',
  contract_id: 'N40080-24-D-1042',
  vendor_uei: 'UEIATLANTIC1',
  security_level: 'standard',
  status: 'active',
  citation_count: 2,
};

const wikiRegressionNode = {
  id: 'reg-node-1',
  node_type: 'regression',
  title: 'Aging RFI',
  summary: 'RFI is 21 days open.',
  contract_id: 'N40080-24-D-1042',
  vendor_uei: 'UEIATLANTIC1',
  security_level: 'controlled',
  status: 'open',
  citation_count: 1,
};

const wikiContractorNode = {
  id: 'contractor-node-1',
  node_type: 'contractor',
  title: 'Atlantic Environmental',
  summary: 'Contractor evidence profile.',
  contract_id: null,
  vendor_uei: 'UEIATLANTIC1',
  security_level: 'controlled',
  status: 'active',
  citation_count: 1,
};

const wikiContractArticle = {
  ...wikiContractNode,
  body: 'Contract onboarding article body.',
  sections: [{ title: 'Onboarding Brief', body: 'All contract onboarding details are indexed.' }],
  citations: [{ id: 'cite-1', label: 'Monthly progress report', excerpt: 'RFI is 21 days open.', source_path: 'contracts/doc-1/main.pdf' }],
  related_nodes: [wikiRegressionNode, wikiContractorNode],
  limitations: [],
  metadata: {},
};

const wikiRegressionArticle = {
  ...wikiRegressionNode,
  body: 'RFI is 21 days open.',
  sections: [{ title: 'Indexed Text', body: 'RFI is 21 days open.' }],
  citations: [{ id: 'cite-2', label: 'Weekly report', excerpt: 'RFI is 21 days open.', source_path: 'contracts/doc-1/main.pdf' }],
  related_nodes: [wikiContractNode],
  limitations: [],
  metadata: {},
};

const wikiContractorArticle = {
  ...wikiContractorNode,
  body: 'Contractor evidence profile.',
  sections: [{ title: 'Evidence Labels', body: 'Unresolved issues: 1.' }],
  citations: [],
  related_nodes: [wikiContractNode],
  limitations: ['Labels are evidence counters.'],
  metadata: {},
};

const contractAnalysis = {
  contract_id: 'N40080-24-D-1042',
  contract_title: 'Environmental Compliance and Permitting Support Services',
  timeline: [
    {
      document_id: 'doc-1',
      title: 'Monthly progress report',
      document_kind: 'monthly_report',
      period_label: '2026-04-25',
      created_at: '2026-04-25T18:00:00Z',
      processing_status: 'processed',
      signals: [
        {
          id: 'sig-1',
          category: 'issue',
          label: 'Aging RFI',
          summary: 'RFI is 21 days open.',
          polarity: 'negative',
          severity: 'medium',
          document_id: 'doc-1',
          responsible_party: 'government',
          recurrence_key: 'issue-aging-rfi',
        },
      ],
    },
  ],
  recurring_issues: [],
  one_off_issues: [{ key: 'issue-aging-rfi', title: 'Aging RFI', count: 1, document_count: 1, examples: ['RFI is 21 days open.'] }],
  early_warning_signals: [],
  positive_signals: [],
  execution_patterns: [],
  cpars_ratings: [],
  ai_analysis: {
    id: 'ai-run-1',
    run_type: 'per_contract',
    status: 'complete',
    target_contract_id: 'N40080-24-D-1042',
    result: {
      summary: 'OpenAI identifies the RFI as an early execution risk. [sig-1]',
      axes: [
        {
          axis: 'execution_and_risk',
          status: 'measured',
          rationale: 'The target has one cited aging RFI issue primitive.',
        },
      ],
      cpars_predicted: {
        Management: {
          rating: 'Marginal',
          rationale: 'Open RFI aging creates management risk.',
        },
      },
    },
    completed_at: '2026-04-25T19:00:00Z',
    model: 'gpt-5.4-mini',
  },
  analyst_brief: {
    problem_statement: 'Explain the outcome with cited primitives.',
    summary: 'Aging RFI appears across the timeline. [sig-1]',
    outcome_context: [],
    recurring_vs_one_off: [
      {
        title: 'One-off issues',
        finding: 'Aging RFI appears once and should be treated as one-off until repeated.',
        citations: [{ primitive_id: 'sig-1', primitive_type: 'report_fact', document_id: 'doc-1', label: 'Aging RFI', excerpt: 'RFI is 21 days open.' }],
        confidence: 0.6,
      },
    ],
    pre_degradation_signals: [],
    success_or_recovery_signals: [],
    execution_assessment: [],
    government_vs_contractor: [],
    limitations: ['Actual CPARS ratings are absent.'],
  },
  axes: [
    {
      axis: 'execution_and_risk',
      status: 'measured',
      target_value: { issue_signal_count: 1 },
      cohort_distribution: { p10: 1, p25: 1, p50: 1, p75: 1, p90: 1 },
      target_percentile: 100,
      low_confidence: true,
      rationale: 'Execution and risk is measured from issue signals.',
      citations: [{ primitive_id: 'sig-1', primitive_type: 'report_fact', document_id: 'doc-1', label: 'Aging RFI', excerpt: 'RFI is 21 days open.' }],
    },
  ],
  cpars_predicted: {
    Management: {
      factor: 'Management',
      rating: 'Marginal',
      not_extractable: false,
      rationale: 'Target is high percentile for execution and risk.',
      citations: [{ primitive_id: 'sig-1', primitive_type: 'report_fact', document_id: 'doc-1', label: 'Aging RFI', excerpt: 'RFI is 21 days open.' }],
    },
  },
  limitations: ['No CPARS ratings are available unless authorized CPARS exports have been imported.'],
};

const cohortAnalysis = {
  contract_count: 1,
  contracts: [
    {
      contract_id: 'N40080-24-D-1042',
      contract_title: 'Environmental Compliance and Permitting Support Services',
      performance_band: 'mixed',
      document_count: 1,
      recurring_issue_count: 0,
      positive_signal_count: 0,
      execution_pattern_count: 0,
      cpars_rating_count: 0,
    },
  ],
  poor_contract_common_patterns: [],
  well_performing_common_patterns: [],
  delta_lessons: [],
  qualitative_quantitative_correlations: [],
  execution_correlations: [],
  limitations: ['Cohort analysis needs at least two visible contracts to compare patterns.'],
};

const similarityInsights = {
  contract_id: 'N40080-24-D-1042',
  target_contract_title: 'Environmental Compliance and Permitting Support Services',
  similar_contracts: [
    {
      contract_id: 'N40080-24-D-2042',
      contract_title: 'Base Operations Access Support',
      similarity_score: 0.82,
      match_basis: ['Shared extracted tags: gfe_delay, access.'],
      failure_points: [
        {
          key: 'schedule-regression-gfe',
          title: 'GFE availability delay',
          count: 2,
          document_count: 2,
          examples: ['Government-furnished access arrived late and delayed field work.'],
        },
      ],
      early_warnings: [],
      recommendations: [
        'Include a GFE/GFI/access responsibility matrix with owner, due date, acceptance criteria, and schedule relief rules.',
      ],
    },
  ],
  shared_failure_points: [
    {
      key: 'schedule-regression-gfe',
      title: 'GFE availability delay',
      count: 2,
      document_count: 2,
      examples: ['Government-furnished access arrived late and delayed field work.'],
    },
  ],
  recommendations: [
    'Include a GFE/GFI/access responsibility matrix with owner, due date, acceptance criteria, and schedule relief rules.',
  ],
  methodology: ['Use chunk-embedding similarity when indexed embeddings exist.'],
  limitations: [],
};

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  };
}
