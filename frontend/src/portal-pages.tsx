// @ts-nocheck
// portal-pages.tsx — Login, Home, Contracts, ContractDetail
import React, { useState, useEffect, useRef } from 'react';
import {
  Sidebar, TopBar, Tag,
  BtnPrimary, BtnSecondary, BtnGhost,
  SectionHeader, MetricCard, Spinner, EmptyState,
  IcoArrow, IcoChevron, IcoClose, IcoSearch, IcoUpload, IcoStar,
  fmtBytes, fmtDate, fmtDateMil,
} from './portal-shell';
import {
  createContract,
  downloadDocumentBlob,
  getContractAnalysis,
  getContractDeliverables,
  getContractLifecycle,
  getDocument,
  getPortfolioThemes,
  listAllDocuments,
  listContractDocuments,
  listContracts,
  listRegressions,
  mockLogin,
  normalizeContract,
  normalizeDocument,
  normalizeFinding,
  uploadDocument,
} from './api';

// ─── MOCK DATA ────────────────────────────────────────────────────────────────
const MOCK_CONTRACTS = [
  { id:'c1', number:'N00024-23-C-4187', title:'Atlantic Logistics & Sustainment Services', psc:'R706', naics:'541614', component:'PMS 325', value:'$4,210,440', period:'15 MAR 2023 — 14 FEB 2027', start:'2023-03-15', end:'2027-02-14', elapsed:78, lastActivity:'24 APR 2026', docsCount:14, contractor:'Atlantic Logistics LLC', co:'LCDR Nicole Jacobs', classification:'CUI', authorized:[
    { name:'LCDR Nicole Jacobs',  role:'Contracting Officer',           email:'n.jacobs@navy.mil' },
    { name:'LT M. Reyes',    role:'Contracting Officer Rep (COR)', email:'m.reyes@navy.mil' },
    { name:'CDR A. Singh',   role:'Program Manager',               email:'a.singh@navy.mil' },
    { name:'Daniel Kim',      role:'Contractor PM (Atlantic)',      email:'daniel.kim@atlanticlogistics.com' },
  ]},
  { id:'c2', number:'N00024-22-C-3091', title:'Pacific Fleet Maintenance Support',         psc:'J998', naics:'336611', component:'PMS 408', value:'$7,820,100', period:'10 JAN 2022 — 09 DEC 2026', start:'2022-01-10', end:'2026-12-09', elapsed:91, lastActivity:'22 APR 2026', docsCount:22, contractor:'Pacific Marine Industries', co:'CDR R. Patel' },
  { id:'c3', number:'N00178-22-D-7741', title:'NAVWAR IT Infrastructure Services',         psc:'D316', naics:'541512', component:'NAVWAR', value:'$12,140,000',period:'01 JUL 2022 — 30 JUN 2027', start:'2022-07-01', end:'2027-06-30', elapsed:64, lastActivity:'20 APR 2026', docsCount:9,  contractor:'Coastal Cyber Group', co:'CIV K. Brown' },
  { id:'c4', number:'N00024-21-C-2204', title:'Ship Maintenance & Rebuilding',             psc:'J999', naics:'336611', component:'PMS 312', value:'$9,500,300', period:'01 OCT 2021 — 30 SEP 2026', start:'2021-10-01', end:'2026-09-30', elapsed:88, lastActivity:'18 APR 2026', docsCount:31, contractor:'Eastern Shipworks', co:'LCDR Nicole Jacobs' },
  { id:'c5', number:'N00024-23-C-4501', title:'Administrative & Management Support',       psc:'R408', naics:'561110', component:'PMS 325', value:'$2,340,000', period:'01 APR 2023 — 31 MAR 2027', start:'2023-04-01', end:'2027-03-31', elapsed:62, lastActivity:'17 APR 2026', docsCount:7,  contractor:'Cardinal Admin Svcs.', co:'CIV M. Diaz' },
  { id:'c6', number:'N00178-23-D-8812', title:'Cybersecurity Assessment & Testing',        psc:'D310', naics:'541512', component:'NAVWAR', value:'$3,110,000', period:'15 JUN 2023 — 14 MAY 2027', start:'2023-06-15', end:'2027-05-14', elapsed:58, lastActivity:'15 APR 2026', docsCount:11, contractor:'Coastal Cyber Group', co:'CIV K. Brown' },
  { id:'c7', number:'N00025-22-C-0041', title:'NAVFAC Facilities Sustainment',             psc:'Z2AA', naics:'238910', component:'NAVFAC', value:'$5,640,200', period:'15 MAR 2022 — 14 FEB 2026', start:'2022-03-15', end:'2026-02-14', elapsed:100,lastActivity:'01 MAR 2026', docsCount:44, contractor:'Tidewater Construction', co:'CDR R. Patel' },
  { id:'c8', number:'N00024-23-C-4802', title:'Architect & Engineering — Dry Dock',        psc:'C211', naics:'541330', component:'NAVFAC', value:'$1,820,000', period:'01 SEP 2023 — 31 AUG 2026', start:'2023-09-01', end:'2026-08-31', elapsed:83, lastActivity:'10 APR 2026', docsCount:6,  contractor:'Bayside Engineering', co:'CIV M. Diaz' },
];

// Default access roster used when a contract record doesn't carry one explicitly.
const DEFAULT_AUTHORIZED = [
  { name:'LCDR Nicole Jacobs',  role:'Contracting Officer',           email:'n.jacobs@navy.mil' },
  { name:'LT M. Reyes',    role:'Contracting Officer Rep (COR)', email:'m.reyes@navy.mil' },
  { name:'CDR A. Singh',   role:'Program Manager',               email:'a.singh@navy.mil' },
];

// ─── DELIVERABLES (CDRL CATALOG) ────────────────────────────────────────────
// Extracted from the contract's CDRL list — what the contractor owes and when.
// kind: 'recurring' | 'milestone' | 'window'
function buildDeliverables(c) {
  const start = new Date(c.start), end = new Date(c.end);
  const today = new Date();
  const items = [];

  // ── Weekly Performance / Status Reports — CDRL A001 ──
  const weekly = [];
  let cur = new Date(start);
  // align to nearest Friday
  cur.setDate(cur.getDate() + ((5 - cur.getDay() + 7) % 7));
  let n = 1;
  while (cur <= end) {
    const due = new Date(cur);
    const filed = due < new Date('2026-04-18') && Math.random() > 0.05; // most past ones filed
    weekly.push({
      id:`${c.id}-wk-${n}`, due, filed,
      title:`WK-${String(n).padStart(2,'0')} ${due.toLocaleString('en-US',{month:'short'}).toUpperCase()} ${due.getDate()}`,
      late: filed && Math.random() < 0.18,
    });
    cur.setDate(cur.getDate() + 7);
    n++;
  }
  items.push({ id:'a001', cdrl:'A001', title:'Weekly Performance / Status Report', kind:'recurring', cadence:'Weekly · Fridays 1700', recipient:'COR + PMO', items: weekly });

  // ── Monthly Progress Review — CDRL A002 ──
  const monthly = [];
  let m = new Date(start.getFullYear(), start.getMonth()+1, 5);
  let mn = 1;
  while (m <= end) {
    const due = new Date(m);
    const filed = due < today;
    monthly.push({ id:`${c.id}-mon-${mn}`, due, filed, title:`${due.toLocaleString('en-US',{month:'short'}).toUpperCase()} ${due.getFullYear()}` });
    m.setMonth(m.getMonth()+1);
    mn++;
  }
  items.push({ id:'a002', cdrl:'A002', title:'Monthly Progress Review', kind:'recurring', cadence:'Monthly · 5th of each month', recipient:'COR + Component PMO', items: monthly });

  // ── IPMDAR Performance Narrative — CDRL A003 (monthly XML) ──
  const pnr = [];
  let p = new Date(start.getFullYear(), start.getMonth()+1, 10);
  let pn = 1;
  while (p <= end) {
    const due = new Date(p);
    const filed = due < today;
    pnr.push({ id:`${c.id}-pnr-${pn}`, due, filed, title:`${due.toLocaleString('en-US',{month:'short'}).toUpperCase()} ${due.getFullYear()}` });
    p.setMonth(p.getMonth()+1);
    pn++;
  }
  items.push({ id:'a003', cdrl:'A003', title:'IPMDAR Performance Narrative', kind:'recurring', cadence:'Monthly · 10th', recipient:'IPMDAR Connector', source:'imported', items: pnr });

  // ── Quarterly Subcontractor Performance — CDRL A004 ──
  const sub = [];
  let q = new Date(start.getFullYear(), Math.floor(start.getMonth()/3)*3 + 4, 15);
  let qn = 1;
  while (q <= end) {
    const due = new Date(q);
    const filed = due < today;
    sub.push({ id:`${c.id}-sub-${qn}`, due, filed, title:`Q${Math.floor(due.getMonth()/3)+1} ${due.getFullYear()}` });
    q.setMonth(q.getMonth()+3);
    qn++;
  }
  items.push({ id:'a004', cdrl:'A004', title:'Subcontractor Performance Report', kind:'recurring', cadence:'Quarterly · 15th', recipient:'COR', items: sub });

  // ── CPARS — interim & annual ──
  const cpars = [];
  let yr = start.getFullYear();
  while (yr <= end.getFullYear()) {
    const interim = new Date(yr, 9, 15);   // OCT 15
    const annual  = new Date(yr+1, 1, 28); // FEB 28 next year
    if (interim >= start && interim <= end) cpars.push({ id:`${c.id}-cp-i-${yr}`, due:interim, filed: interim<today, title:`Interim FY${(yr+1).toString().slice(-2)}` });
    if (annual >= start && annual <= end)   cpars.push({ id:`${c.id}-cp-a-${yr}`, due:annual,  filed: annual<today,  title:`Annual FY${(yr+1).toString().slice(-2)}` });
    yr++;
  }
  items.push({ id:'cpars', cdrl:'—', title:'CPARS Evaluation', kind:'milestone', cadence:'Interim & Annual', recipient:'CPARS · cpars.gov', source:'imported', items: cpars });

  // ── Modifications already executed ──
  items.push({ id:'mods', cdrl:'—', title:'Modifications', kind:'milestone', cadence:'Ad hoc', recipient:'Contracting Office', items:[
    { id:`${c.id}-m05`, due:new Date('2025-08-22'), filed:true, title:'P00005 Funding ↑' },
    { id:`${c.id}-m06`, due:new Date('2025-11-04'), filed:true, title:'P00006 PoP ext.' },
    { id:`${c.id}-m07`, due:new Date('2026-02-12'), filed:true, title:'P00007 Cyber clause' },
  ]});

  return items;
}

// ─── DOCUMENT CORPUS ────────────────────────────────────────────────────────
// Generated weekly status reports + modifications + imported reports (CPARS, IPMDAR)
function buildDocs(contractOrId) {
  // Accept either a full contract record or just an id (back-compat).
  const contract = typeof contractOrId === 'string' ? null : contractOrId;
  const contractId = contract?.id || contractOrId;

  const docs = [];

  // ── Contract itself — pinned at the top of every Documents view ──
  // This is what program officers reach for first when reviewing a contract.
  docs.push({
    id: `${contractId}-contract`,
    title: contract
      ? `${contract.number} — Base Award (${contract.title})`
      : 'Contract — Base Award',
    doc_type: 'Contract',
    source: 'Contracting Office',
    filename: `${contract?.number || contractId}-base-award.pdf`,
    content_type: 'application/pdf',
    size_bytes: 1_842_500,
    uploader: 'Contracting Office',
    created_at: contract?.start ? `${contract.start}T08:00:00Z` : '2024-01-01T08:00:00Z',
    period: 'Award',
    pinned: true,
  });

  // 14 weekly status reports
  for (let wk = 14; wk >= 1; wk--) {
    const wkStr = String(wk).padStart(2,'0');
    const date = new Date(2026, 3, 24 - (14-wk)*7);
    docs.push({
      id:`${contractId}-wk${wk}`,
      title:`Weekly Status Report — WK-${wkStr}`,
      doc_type:'Weekly Status',
      source:'Contractor',
      filename:`WK${wkStr}-status.pdf`, content_type:'application/pdf',
      size_bytes: 240000 + Math.floor(Math.random()*120000),
      uploader:'Contractor', created_at: date.toISOString(),
      period:`WK ${wkStr} FY26`,
    });
  }
  // Modifications
  docs.push({ id:`${contractId}-m07`, title:'Modification P00007 — Cyber clause language',          doc_type:'Modification', source:'Contracting Office', filename:'P00007-mod.pdf', content_type:'application/pdf', size_bytes:412300, uploader:'Contracting Office', created_at:'2026-02-12T10:00:00Z', period:'P00007' });
  docs.push({ id:`${contractId}-m06`, title:'Modification P00006 — Period of performance ext.',     doc_type:'Modification', source:'Contracting Office', filename:'P00006-mod.pdf', content_type:'application/pdf', size_bytes:298100, uploader:'Contracting Office', created_at:'2025-11-04T10:00:00Z', period:'P00006' });
  docs.push({ id:`${contractId}-m05`, title:'Modification P00005 — Funding obligation increase',    doc_type:'Modification', source:'Contracting Office', filename:'P00005-mod.pdf', content_type:'application/pdf', size_bytes:331400, uploader:'Contracting Office', created_at:'2025-08-22T10:00:00Z', period:'P00005' });
  docs.push({ id:`${contractId}-kp`,  title:'Key Personnel Substitution Notice (PM)',                doc_type:'Modification', source:'Contractor',         filename:'kp-sub-pm.pdf',  content_type:'application/pdf', size_bytes: 42100, uploader:'Contractor', created_at:'2026-03-10T08:17:00Z', period:'H-12' });

  // CPARS — imported from CPARS.cpars.gov
  docs.push({ id:`${contractId}-cp1`, title:'CPARS Evaluation — Interim FY25',  doc_type:'CPARS Report', source:'Imported · CPARS', filename:'cpars-interim-fy25.pdf', content_type:'application/pdf', size_bytes:198400, uploader:'CPARS Connector', created_at:'2025-10-15T08:00:00Z', period:'FY25 Interim', importRef:'CPARS#88241' });
  docs.push({ id:`${contractId}-cp2`, title:'CPARS Evaluation — Annual FY24',   doc_type:'CPARS Report', source:'Imported · CPARS', filename:'cpars-annual-fy24.pdf', content_type:'application/pdf', size_bytes:212100, uploader:'CPARS Connector', created_at:'2024-11-30T08:00:00Z', period:'FY24 Annual',   importRef:'CPARS#76122' });

  // IPMDAR — Performance narrative reports
  docs.push({ id:`${contractId}-ip1`, title:'Performance Narrative Report — MAR 2026', doc_type:'IPMDAR Narrative', source:'Imported · IPMDAR', filename:'ipmdar-pnr-2026-03.xml', content_type:'application/xml', size_bytes:88400,  uploader:'IPMDAR Connector', created_at:'2026-04-10T08:00:00Z', period:'MAR 2026', importRef:'IPMDAR#PNR-3-2026' });
  docs.push({ id:`${contractId}-ip2`, title:'Performance Narrative Report — FEB 2026', doc_type:'IPMDAR Narrative', source:'Imported · IPMDAR', filename:'ipmdar-pnr-2026-02.xml', content_type:'application/xml', size_bytes:91200,  uploader:'IPMDAR Connector', created_at:'2026-03-10T08:00:00Z', period:'FEB 2026', importRef:'IPMDAR#PNR-2-2026' });
  docs.push({ id:`${contractId}-ip3`, title:'IPMDAR Format 6 — Time-Phased Forecast',    doc_type:'IPMDAR Format-6', source:'Imported · IPMDAR', filename:'ipmdar-fmt6-2026-03.xml', content_type:'application/xml', size_bytes:104800, uploader:'IPMDAR Connector', created_at:'2026-04-10T08:00:00Z', period:'MAR 2026', importRef:'IPMDAR#F6-3-2026' });
  docs.push({ id:`${contractId}-ip4`, title:'IPMDAR Format 5 — Variance Analysis',       doc_type:'IPMDAR Format-5', source:'Imported · IPMDAR', filename:'ipmdar-fmt5-2026-03.xml', content_type:'application/xml', size_bytes: 76200, uploader:'IPMDAR Connector', created_at:'2026-04-10T08:00:00Z', period:'MAR 2026', importRef:'IPMDAR#F5-3-2026' });

  // Misc deliverables / invoices
  docs.push({ id:`${contractId}-i1`,  title:'Invoice 2026-0041',                doc_type:'Invoice',     source:'Contractor', filename:'invoice-2026-0041.pdf', content_type:'application/pdf', size_bytes:156788, uploader:'Contractor', created_at:'2026-03-28T11:40:00Z', period:'Q2 FY26' });
  docs.push({ id:`${contractId}-i2`,  title:'Invoice 2026-0030',                doc_type:'Invoice',     source:'Contractor', filename:'invoice-2026-0030.pdf', content_type:'application/pdf', size_bytes:148120, uploader:'Contractor', created_at:'2026-02-28T11:40:00Z', period:'Q2 FY26' });
  docs.push({ id:`${contractId}-l1`,  title:'Labor Hours Summary — March 2026', doc_type:'Deliverable', source:'Contractor', filename:'labor-mar-2026.xlsx', content_type:'application/vnd.ms-excel', size_bytes:91340, uploader:'Contractor', created_at:'2026-04-01T14:05:00Z', period:'MAR 2026' });
  docs.push({ id:`${contractId}-s1`,  title:'Subcontractor Performance Report — Q1 FY26', doc_type:'Tech Report', source:'Contractor', filename:'sub-perf-q1.pdf', content_type:'application/pdf', size_bytes:341200, uploader:'Contractor', created_at:'2026-03-20T13:30:00Z', period:'Q1 FY26' });

  return docs.sort((a, b) => {
    if (a.pinned && !b.pinned) return -1;
    if (b.pinned && !a.pinned) return 1;
    return new Date(b.created_at) - new Date(a.created_at);
  });
}

// Map doc_type → tone/abbrev/source
const DOC_TYPE_META = {
  'Contract':          { abbr:'CTR',  tone:'ink',     },
  'Weekly Status':     { abbr:'WSR',  tone:'default', },
  'Modification':      { abbr:'MOD',  tone:'accent',  },
  'CPARS Report':      { abbr:'CPRS', tone:'ink',     },
  'IPMDAR Narrative':  { abbr:'PNR',  tone:'ink',     },
  'IPMDAR Format-5':   { abbr:'F-5',  tone:'ink',     },
  'IPMDAR Format-6':   { abbr:'F-6',  tone:'ink',     },
  'Invoice':           { abbr:'INV',  tone:'default', },
  'Deliverable':       { abbr:'DEL',  tone:'default', },
  'Tech Report':       { abbr:'TR',   tone:'default', },
  'Memo':              { abbr:'MEM',  tone:'default', },
};

// ─── THEMES (cross-contract clusters) ────────────────────────────────────────
const THEMES = [
  {
    id:'t1', title:'CDRL slip following key-personnel rotation',
    severity:'critical', psc:'R-codes', component:'Multi',
    flagged: 5, total: 12, valueFlagged:'$94M',
    insight:'Across R-coded service contracts, weekly reports slip 4.2 days on average within 90 days of a PM substitution.',
    contracts: ['c1','c2','c5','c4','c8'],
    metric:'Median slip', value:'5.1d', delta:'+1.4d vs portfolio',
  },
  {
    id:'t2', title:'Vendor export-license expiry on critical path',
    severity:'critical', psc:'D-310', component:'NAVWAR',
    flagged: 2, total: 8, valueFlagged:'$15M',
    insight:'Cyber assessment contracts show recurring single-points-of-failure on vendor export licenses near deliverable windows.',
    contracts: ['c3','c6'],
    metric:'License lead time', value:'<30d', delta:'vs 60d target',
  },
  {
    id:'t3', title:'Travel ODC drift outpacing peer baseline',
    severity:'watch', psc:'R-408', component:'PMS 325',
    flagged: 4, total: 22, valueFlagged:'$48M',
    insight:'Admin support contracts show ODC growth (+18%) running well ahead of labor (+3%) and peer median (+6%).',
    contracts: ['c5','c1','c4','c2'],
    metric:'ODC growth', value:'+18%', delta:'+12pp vs peer',
  },
  {
    id:'t4', title:'Sub-tier safety reporting gap — first 6 months',
    severity:'watch', psc:'Z-2AA', component:'NAVFAC',
    flagged: 3, total: 6, valueFlagged:'$31M',
    insight:'Facilities sustainment contracts under-report sub-tier incidents until H-19 reminders begin.',
    contracts: ['c7','c8','c4'],
    metric:'Reporting gap', value:'~6 mo', delta:'closes after H-19',
  },
  {
    id:'t5', title:'Mid-period SPI decline on long base periods',
    severity:'watch', psc:'J-998', component:'PMS 408',
    flagged: 2, total: 11, valueFlagged:'$48M',
    insight:'J-coded fleet maintenance trends late in months 22–24 of 36-month periods.',
    contracts: ['c2','c4'],
    metric:'SPI shift', value:'0.97 → 0.89', delta:'months 22–24',
  },
];

// ─── FINDINGS (per-contract specific issues that ladder up to themes) ───────
const FINDINGS = {
  c1: [
    { id:'f1', severity:'critical', themeId:'t1',
      claim:'WK-14 status report filed 5 days late — 3rd slip in last 4 weeks.',
      observed:'Mean slip across last 4 reports: 4.2 days. Pattern began WK-09, coincident with PM substitution (KP H-12 notice, 10 MAR 2026).',
      sourceDoc:'Weekly Status Report — WK-14',
      similar:[
        { id:'c2', label:'Pacific Fleet Maintenance Support', detail:'Same pattern after PM rotation Jan 2025 — 6 slips' },
        { id:'c5', label:'Administrative & Management Support', detail:'PM rotation Sep 2025 — 4 slips, recovered after H-19' },
        { id:'c4', label:'Ship Maintenance & Rebuilding', detail:'Same lens, no recovery yet' },
      ],
    },
    { id:'f2', severity:'watch', themeId:'t3',
      claim:'Travel ODCs +21% over baseline this fiscal year.',
      observed:'IPMDAR Format-5 variance reports show 6 unbudgeted CONUS trips Q1 FY26. Peer median ODC growth at +6%.',
      sourceDoc:'IPMDAR Format-5 — Variance Analysis · MAR 2026',
      similar:[
        { id:'c5', label:'Administrative & Management Support', detail:'Same drift pattern, +14%' },
        { id:'c2', label:'Pacific Fleet Maintenance Support', detail:'+9% — early signal' },
      ],
    },
    { id:'f3', severity:'healthy', themeId:null,
      claim:'CPARS interim FY25 score (4.1 / 5) above peer median.',
      observed:'Peer median for R-706 at PMS 325 is 3.8. Strongest dimension: cost control.',
      sourceDoc:'CPARS Evaluation — Interim FY25',
      similar:[],
    },
  ],
};

const SEVERITY_META = {
  critical: { label:'Critical', clr:'var(--flag)',  bg:'var(--flag-soft)',  border:'var(--flag-mid)' },
  watch:    { label:'Watch',    clr:'var(--warn)',  bg:'var(--warn-soft)',  border:'var(--warn-mid)' },
  healthy:  { label:'Healthy',  clr:'var(--good)',  bg:'var(--good-soft)',  border:'var(--good-mid)' },
};

// ─── PSC SERVICE-CONTRACT CATEGORIES ───────────────────────────────────────
// Federal PSC service-contract category letters. Lets analysts filter by an
// entire category (e.g. "all R-coded") instead of picking individual codes.
const PSC_CATEGORIES = [
  { letter:'B', label:'Special Studies & Analyses' },
  { letter:'C', label:'Architect & Engineering Services' },
  { letter:'D', label:'Information Technology / Telecom' },
  { letter:'F', label:'Natural Resources / Conservation' },
  { letter:'H', label:'Quality Control / Testing' },
  { letter:'J', label:'Maintenance / Repair of Equipment' },
  { letter:'K', label:'Modification of Equipment' },
  { letter:'L', label:'Technical Representative Services' },
  { letter:'M', label:'Operation of Government Facilities' },
  { letter:'N', label:'Installation of Equipment' },
  { letter:'P', label:'Salvage Services' },
  { letter:'Q', label:'Medical Services' },
  { letter:'R', label:'Professional / Administrative / Management' },
  { letter:'S', label:'Utilities & Housekeeping' },
  { letter:'T', label:'Photographic, Mapping, Printing' },
  { letter:'U', label:'Education & Training' },
  { letter:'V', label:'Transportation, Travel, Relocation' },
  { letter:'W', label:'Lease / Rental of Equipment' },
  { letter:'X', label:'Lease / Rental of Facilities' },
  { letter:'Y', label:'Construction of Structures' },
  { letter:'Z', label:'Maint/Repair/Alteration of Real Property' },
];

// ─── PSC CODE CATALOG ───────────────────────────────────────────────────────
// Representative set of Product/Service Codes used in DoD/Navy procurement.
// Not exhaustive (the real list has 4 figures of codes), but covers the
// categories an analyst typically filters on. UI greys-out codes with no
// contracts in the current portfolio.
const PSC_CODES = [
  // R — Professional / Administrative / Management Support Services
  { code:'R408', desc:'Program Management / Support Services' },
  { code:'R425', desc:'Engineering & Technical Services' },
  { code:'R499', desc:'Other Professional Services' },
  { code:'R701', desc:'Advertising Services' },
  { code:'R706', desc:'Logistics Support Services' },
  { code:'R707', desc:'Management Services / Contract & Procurement Support' },
  { code:'R713', desc:'Acquisition Support Services' },
  // D — Information Technology / Telecommunications
  { code:'D302', desc:'IT & Telecom — Systems Development' },
  { code:'D306', desc:'IT & Telecom — Systems Analysis' },
  { code:'D307', desc:'IT & Telecom — IT Strategy & Architecture' },
  { code:'D310', desc:'IT & Telecom — Cyber Security & Information Assurance' },
  { code:'D316', desc:'IT & Telecom — Telecommunications Network Management' },
  { code:'D399', desc:'IT & Telecom — Other IT and Telecom Services' },
  // J — Maintenance, Repair, and Rebuilding of Equipment
  { code:'J019', desc:'Maint/Repair — Ships, Small Craft & Pontoons' },
  { code:'J998', desc:'Maint/Repair — Non-Nuclear Ships' },
  { code:'J999', desc:'Maint/Repair — Other Equipment' },
  // C — Architect & Engineering Services
  { code:'C211', desc:'Architect & Engineering — Naval Construction' },
  { code:'C212', desc:'Architect & Engineering — Construction (Other)' },
  // Z — Maintenance, Repair & Alteration of Real Property
  { code:'Z1AA', desc:'Maint/Repair — Office Buildings' },
  { code:'Z2AA', desc:'Construction of Office Buildings' },
  { code:'Z2BB', desc:'Construction of Industrial Facilities' },
  // Y — Construction of Structures and Facilities
  { code:'Y1AA', desc:'Construction — Office Buildings' },
  { code:'Y1BZ', desc:'Construction — Other Administrative Facilities' },
  // S — Utilities and Housekeeping Services
  { code:'S206', desc:'Guard Services' },
  { code:'S214', desc:'Lawn & Landscaping Services' },
  // M — Operation of Government-Owned Facilities
  { code:'M1JB', desc:'Operation of Naval Facilities' },
  // F — Natural Resources and Conservation
  { code:'F108', desc:'Environmental Studies & Assessments' },
  // Q — Medical Services
  { code:'Q509', desc:'Medical — Other' },
  // U — Education and Training Services
  { code:'U009', desc:'Training/Curriculum Development' },
  // 70 — General-Purpose Information Technology Equipment
  { code:'7030', desc:'ADP Software' },
  { code:'7035', desc:'ADP Support Equipment' },
];

// ─── INSIGHTS LIBRARY (filterable by PSC, etc.) ─────────────────────────────
const INSIGHTS = [
  { id:'i1', psc:'R706', naics:'541614', tone:'flag', lens:'Pattern · Recurrence',     contracts:'12 of 47',
    claim:'In R-coded service contracts, weekly reports slip when key personnel rotate within 90 days of a deliverable.',
    why:'Across 47 contracts, 12 show this pattern. Mean slip 4.2 days following PM substitution, vs. 0.6 days otherwise.',
    so:'Worth flagging when a key-personnel sub notice precedes a deliverable window. Predictive value ≈ 0.74.',
    historical: [
      { source:'FPDS-NG · FY18–FY22 R-coded service awards', n:187, note:'Baseline schedule-slip rate post-PM-sub: 12.4%' },
      { source:'NAVAIR portfolio · FY22–FY24 (cross-command)', n:34, note:'Same pattern observed in 9 of 34 contracts' },
      { source:'CPARS historical · R-coded narratives FY15–FY24', n:1240, note:'Key-personnel sub flagged in 22% of "Marginal" Schedule ratings' },
    ] },
  { id:'i2', psc:'D310', naics:'541512', tone:'flag', lens:'Anomaly · External Dependency', contracts:'3 of 8',
    claim:'D-310 cyber assessment contracts show recurring single-points-of-failure on vendor export licenses.',
    why:'License renewal packages submitted within 30 days of expiry in 3 of 8 cases. Mitigations rarely captured in IMS.',
    so:'Suggests a contract-clause template change — pre-renewal milestone with a 60-day buffer.',
    historical: [
      { source:'NAVWAR portfolio · FY20–FY24 cyber awards', n:42, note:'Late-renewal pattern in 11 of 42 (26%)' },
      { source:'GAO report GAO-23-105 — DoD export licensing', n:null, note:'Cited 30-day buffer as systemic risk' },
      { source:'FPDS-NG · D-310 awards FY15–FY24', n:312, note:'Median renewal lead time 22 days; recommended ≥60' },
    ] },
  { id:'i3', psc:'R408', naics:'561110', tone:'warn', lens:'Drift · Cost Composition', contracts:'9 of 22',
    claim:'In R-408 admin support, travel ODCs are growing faster than labor — and faster than peer median.',
    why:'ODCs +18% over baseline vs. +3% labor. Peer median ODC growth +6%.',
    so:'Not yet an overrun. Worth understanding before EAC re-projection.',
    historical: [
      { source:'OSD CAPE peer cohort · R-408 FY21–FY24', n:64, note:'Median ODC growth +6%; this portfolio +18% (sig.)' },
      { source:'IPMDAR Format-5 archive · FY22–FY24', n:902, note:'ODC drift precedes EAC re-baseline by 2.7 quarters on avg' },
    ] },
  { id:'i4', psc:'D310', naics:'541512', tone:'good', lens:'Win · Replicable Practice', contracts:'2 of 8',
    claim:'Two NAVWAR cyber contracts closed POA&M items 11 days ahead of plan — same mechanism in both.',
    why:'Mechanism: SOC-2-tied clause language adopted in mod P00007. Same pattern present in 11 peer contracts.',
    so:'Transferable to D, J, R-code SOW templates.',
    historical: [
      { source:'NAVWAR FY23 lessons-learned register', n:11, note:'Same clause language used in 11 peer awards' },
      { source:'CPARS · D-310 narratives FY22–FY24', n:184, note:'POA&M closure ahead-of-plan in 14% of awards using this clause vs. 4% baseline' },
    ] },
  { id:'i5', psc:'J998', naics:'336611', tone:'warn', lens:'Drift · Schedule Health', contracts:'5 of 11',
    claim:'J-998 fleet-maintenance contracts trend toward late delivery in months 22–24 of 36-month base periods.',
    why:'Mean SPI declines from 0.97 to 0.89 in this band. Correlates with sub-tier supplier lead-time growth.',
    so:'Prompt for a mid-period IMS health check would have caught 4 of 5 prior cases.',
    historical: [
      { source:'NAVSEA portfolio · J-998 FY18–FY23', n:38, note:'M22–M24 SPI dip in 21 of 38 (55%)' },
      { source:'DLA sub-tier lead-time reports FY22–FY24', n:null, note:'Average lead-time +14 days vs. baseline' },
      { source:'FPDS-NG · J-998 awards FY10–FY24', n:541, note:'Closeouts >30 days late more likely with M-22 SPI < 0.92' },
    ] },
  { id:'i6', psc:'C211', naics:'541330', tone:'good', lens:'Benchmark · Outperform', contracts:'1 of 3',
    claim:'A&E dry-dock work has come in 6.2% under EAC across recent NAVFAC contracts.',
    why:'Driver: BIM-coordinated design reviews introduced FY24. Reduced rework hours ~12%.',
    so:'Strong case for adopting the same review cadence in upcoming PMS 312 mods.',
    historical: [
      { source:'NAVFAC FY23–FY24 BIM pilot retrospective', n:8, note:'Mean cost variance −5.4% vs. −0.1% pre-pilot' },
      { source:'FPDS-NG · C-211 NAVFAC awards FY18–FY22', n:74, note:'Pre-BIM baseline: median rework 8.3% of labor hours' },
    ] },
  { id:'i7', psc:'Z2AA', naics:'238910', tone:'flag', lens:'Pattern · Recurrence', contracts:'4 of 6',
    claim:'Facilities sustainment contracts under-report sub-tier safety incidents in the first 6 months.',
    why:'Cross-checking with NAVFAC injury logs shows a 0.31 correlation; first-6-month reporting gap closes after H-19 reminders.',
    so:'Worth requiring sub-tier reporting from Day 1 in next-cycle solicitations.',
    historical: [
      { source:'NAVFAC injury log archive · FY20–FY24', n:1820, note:'Sub-tier under-report rate 41% in first 6 months' },
      { source:'OSHA Form 300A · DoD-installation contractors', n:null, note:'Aggregate gap of 28% vs. self-reported figures' },
    ] },
];

// ─── LOGIN PAGE ─────────────────────────────────────────────────────────────
function LoginPage({ onLogin }) {
  const [role, setRole] = useState('contractor');
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setLoading(true);
    try {
      const session = await mockLogin(role);
      onLogin(session.access_token, session.user);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight:'100vh', display:'flex', background:'var(--ink)' }}>
      {/* Left: insignia panel */}
      <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', position:'relative', overflow:'hidden' }}>
        <div style={{ position:'absolute', inset:0, opacity:0.06,
          backgroundImage:'linear-gradient(var(--sidebar-text-a) 1px, transparent 1px), linear-gradient(90deg, var(--sidebar-text-a) 1px, transparent 1px)',
          backgroundSize:'24px 24px',
        }}/>
        <div style={{ textAlign:'center', position:'relative', color:'#E6EDF6' }}>
          <svg width="100" height="100" viewBox="0 0 100 100" fill="none" style={{marginBottom:24}}>
            <rect x="6" y="6" width="88" height="88" stroke="#E6EDF6" strokeWidth="1.5"/>
            <rect x="14" y="14" width="72" height="72" stroke="#E6EDF6" strokeWidth="1" opacity="0.5"/>
            <path d="M30 50h40M50 30v40" stroke="#E6EDF6" strokeWidth="1.5"/>
            <circle cx="50" cy="50" r="14" stroke="#E6EDF6" strokeWidth="1"/>
          </svg>
          <div style={{ fontFamily:'var(--mono)', fontSize:13, letterSpacing:'0.3em', textTransform:'uppercase', color:'rgba(212,222,236,0.55)' }}>Department of the Navy</div>
          <div style={{ fontFamily:'var(--mono)', fontSize:22, letterSpacing:'0.18em', textTransform:'uppercase', marginTop:12, fontWeight:700 }}>CPM-PORTAL</div>
          <div style={{ fontSize:12, marginTop:8, color:'rgba(212,222,236,0.55)' }}>Contract Performance Monitor</div>
        </div>
      </div>

      {/* Right: form */}
      <form onSubmit={submit} style={{
        width:440, background:'var(--surface)', padding:'56px 48px',
        display:'flex', flexDirection:'column', justifyContent:'center',
      }}>
        <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.20em', textTransform:'uppercase', color:'var(--accent)', marginBottom:14, fontFamily:'var(--mono)' }}>Authorized Personnel</div>
        <h1 style={{ fontSize:26, fontWeight:700, letterSpacing:'-0.02em', color:'var(--ink)', marginBottom:6 }}>Sign in</h1>
        <p style={{ fontSize:13, color:'var(--ink-mute)', lineHeight:1.6, marginBottom:32 }}>Select your role to enter the prototype. Azure Entra SSO will replace this in production.</p>

        <div style={{ display:'grid', gap:6, marginBottom:24 }}>
          <label style={{ fontSize:11, fontWeight:600, color:'var(--ink-soft)', letterSpacing:'0.06em', textTransform:'uppercase', fontFamily:'var(--mono)' }}>Role</label>
          <select value={role} onChange={e => setRole(e.target.value)} style={{
            width:'100%', border:'1px solid var(--border-md)', borderRadius:3,
            padding:'10px 12px', background:'var(--surface)', color:'var(--ink)',
            fontSize:13, appearance:'none',
            backgroundImage:`url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%234D5A72' stroke-width='1.4' fill='none' stroke-linecap='round'/%3E%3C/svg%3E")`,
            backgroundRepeat:'no-repeat', backgroundPosition:'right 12px center', paddingRight:32,
          }}>
            <option value="contractor">Contractor</option>
            <option value="official">Government Official</option>
          </select>
        </div>

        <BtnPrimary type="submit" disabled={loading} style={{ width:'100%', padding:'11px 0', fontSize:13 }}>
          {loading ? 'Signing in…' : 'Continue →'}
        </BtnPrimary>

        <div style={{
          marginTop:32, paddingTop:20, borderTop:'1px solid var(--border)',
          fontSize:10, color:'var(--ink-faint)', textAlign:'center', fontFamily:'var(--mono)', letterSpacing:'0.10em',
        }}>CUI // SP-PROCURE · Authorized use only</div>
      </form>
    </div>
  );
}

// ─── HOME PAGE — themes-driven overview ─────────────────────────────────────
function HomePage({ user, onNav, onSelectContract }) {
  const today = new Date().toLocaleDateString('en-US', { weekday:'long', month:'long', day:'numeric', year:'numeric' });
  const nameParts = (user?.name || 'User').split(' ');
  const RANKS = new Set(['LCDR','LT','CDR','CAPT','CIV','ENS','ADM','RDML','VADM','LTJG']);
  const firstName = RANKS.has(nameParts[0]) ? (nameParts[1] || nameParts[0]) : nameParts[0];
  const [portfolio, setPortfolio] = useState(null);
  const [portfolioError, setPortfolioError] = useState(false);

  const [serviceCode, setServiceCode] = useState('All codes');
  const [component, setComponent] = useState('All');
  const [severity, setSeverity] = useState('≥ watch');
  const [period, setPeriod] = useState('Last 30 days');
  const [view, setView] = useState('All flagged');

  useEffect(() => {
    let cancelled = false;
    getPortfolioThemes(periodParam(period))
      .then(data => {
        if (!cancelled) {
          setPortfolio(data);
          setPortfolioError(false);
        }
      })
      .catch(() => {
        if (!cancelled) setPortfolioError(true);
      });
    return () => { cancelled = true; };
  }, [period]);

  const sourceThemes = portfolio?.themes || [];
  const kpis = portfolio?.kpis || {};
  const flaggedCount = kpis.flagged ?? sourceThemes.reduce((sum, t) => sum + (t.flagged || 0), 0);
  const totalContracts = kpis.total_contracts ?? 0;
  const aggregateValue = kpis.aggregate_value_flagged != null
    ? compactCurrency(kpis.aggregate_value_flagged)
    : '—';
  const healthyCount = Math.max(0, totalContracts - flaggedCount);

  // Filter themes by view
  const visibleThemes = sourceThemes.filter(t => {
    if (serviceCode !== 'All codes' && !themeMatchesServiceCode(t, serviceCode)) return false;
    if (component !== 'All' && t.component !== component) return false;
    if (severity === 'Critical only' && t.severity !== 'critical') return false;
    if (severity === '≥ watch' && !['critical', 'watch'].includes(t.severity)) return false;
    if (view === 'All flagged') return true;
    if (view === 'Critical') return t.severity === 'critical';
    if (view === 'Watch') return t.severity === 'watch';
    if (view === 'Healthy') return false;
    return true;
  });

  return (
    <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
      <TopBar crumbs={['Home']} />
      <div style={{ flex:1, overflowY:'auto', padding:'24px 32px 48px' }}>

        {/* Masthead */}
        <div style={{
          display:'flex', alignItems:'flex-end', justifyContent:'space-between',
          paddingBottom:14, marginBottom:18, borderBottom:'1px solid var(--border-md)',
        }}>
          <div>
            <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.18em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:6 }}>{today}</div>
            <h1 style={{ fontSize:24, fontWeight:700, letterSpacing:'-0.02em', color:'var(--ink)' }}>Portfolio Overview</h1>
            <p style={{ fontSize:13, color:'var(--ink-mute)', marginTop:4 }}>{firstName} — themes and patterns across {totalContracts} active contracts</p>
          </div>
          <div style={{ textAlign:'right' }}>
            <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-faint)', fontFamily:'var(--mono)' }}>Reporting Period</div>
            <div style={{ fontSize:14, fontWeight:600, color:'var(--ink)', marginTop:4, fontFamily:'var(--mono)' }}>FY26 · Q3</div>
          </div>
        </div>

        {/* KPI strip */}
        <div style={{ display:'grid', gridTemplateColumns:'repeat(4, 1fr)', gap:0, marginBottom:18, border:'1px solid var(--border)', borderRadius:4, background:'var(--surface)' }}>
          <KpiCell label="Flagged"            value={<span><span style={{color:'var(--flag)'}}>{flaggedCount}</span><span style={{color:'var(--ink-faint)'}}> / {totalContracts}</span></span>} sub={portfolioError ? 'backend unavailable' : 'backend evidence'} />
          <KpiCell label="Evidence Items"     value={<span style={{color:'var(--warn)'}}>{kpis.evidence_count ?? '—'}</span>} sub="findings, signals, facts" border />
          <KpiCell label="Cross-contract themes" value={<span>{sourceThemes.length}</span>} sub="backend grouped" border />
          <KpiCell label="Aggregate value flagged" value={aggregateValue} sub={totalContracts ? 'visible portfolio' : 'no contracts'} border />
        </div>

        {/* Filter / view bar */}
        <div style={{
          display:'flex', alignItems:'center', gap:10, flexWrap:'wrap',
          padding:'10px 14px', background:'var(--surface)',
          border:'1px solid var(--border)', borderRadius:4, marginBottom:18,
        }}>
          <span style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.16em', textTransform:'uppercase', fontFamily:'var(--mono)' }}>Filters</span>
          <FilterChip label="Service code" value={serviceCode} onChange={setServiceCode} options={['All codes','R-codes','D-codes','J-codes','Z-codes','C-codes']}/>
          <FilterChip label="Component"    value={component}   onChange={setComponent}   options={['All','PMS 325','PMS 312','PMS 408','NAVWAR','NAVFAC']}/>
          <FilterChip label="Severity"     value={severity}    onChange={setSeverity}    options={['Any','≥ watch','Critical only']}/>
          <FilterChip label="Period"       value={period}      onChange={setPeriod}      options={['Last 7 days','Last 30 days','Last 90 days','FY26']}/>

          <div style={{ marginLeft:'auto', display:'flex', gap:4 }}>
            {[
              { id:'All flagged', count:flaggedCount, tone:'ink' },
              { id:'Critical',    count:sourceThemes.filter(t => t.severity === 'critical').length, tone:'flag' },
              { id:'Watch',       count:sourceThemes.filter(t => t.severity === 'watch').length, tone:'warn' },
              { id:'Healthy',     count:healthyCount, tone:'good' },
            ].map(v => {
              const active = v.id === view;
              const tones = { ink:'var(--ink)', flag:'var(--flag)', warn:'var(--warn)', good:'var(--good)' };
              return (
                <button key={v.id} onClick={() => setView(v.id)} style={{
                  padding:'5px 11px', borderRadius:99,
                  border:`1px solid ${active ? tones[v.tone] : 'var(--border-md)'}`,
                  background: active ? tones[v.tone] : 'transparent',
                  color: active ? '#fff' : tones[v.tone],
                  fontSize:11, fontWeight:600, fontFamily:'var(--mono)',
                  letterSpacing:'0.04em', display:'inline-flex', alignItems:'center', gap:6,
                }}>{v.id} <span style={{opacity:0.7}}>{v.count}</span></button>
              );
            })}
          </div>
        </div>

        {/* Themes — grouped contracts + problems */}
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:10 }}>
          <div style={{ fontSize:11, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)' }}>Themes ({visibleThemes.length})</div>
          <div style={{ fontSize:10, color:'var(--ink-faint)', fontFamily:'var(--mono)', letterSpacing:'0.08em' }}>SORT risk ↓ · GROUP by theme</div>
        </div>

        <div style={{ display:'grid', gap:10 }}>
          {!portfolio && !portfolioError && <Spinner label="Loading portfolio evidence…" />}
          {visibleThemes.map(theme => (
            <ThemeCard key={theme.id} theme={theme} onSelectContract={onSelectContract} />
          ))}
          {portfolio && visibleThemes.length === 0 && <EmptyState title="No backend themes yet" sub={(portfolio.limitations || [])[0] || 'Upload and process documents to generate cross-contract themes.'}/>}
          {portfolioError && <EmptyState title="Portfolio evidence unavailable" sub="Backend portfolio evidence could not be loaded."/>}
        </div>
      </div>
    </div>
  );
}

function KpiCell({ label, value, sub, border }) {
  return (
    <div style={{
      padding:'14px 18px',
      borderLeft: border ? '1px solid var(--border)' : 'none',
    }}>
      <div style={{ fontSize:9.5, fontWeight:700, letterSpacing:'0.16em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:8 }}>{label}</div>
      <div style={{ fontSize:30, fontWeight:700, lineHeight:1, letterSpacing:'-0.02em', fontFamily:'var(--mono)' }}>{value}</div>
      {sub && <div style={{ fontSize:11, color:'var(--ink-mute)', marginTop:6 }}>{sub}</div>}
    </div>
  );
}

function FilterChip({ label, value, onChange, options }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position:'relative' }}>
      <button onClick={() => setOpen(o => !o)} style={{
        padding:'5px 10px', borderRadius:3,
        border:'1px solid var(--border-md)', background:'var(--surface-alt)',
        fontSize:11, fontFamily:'var(--mono)', color:'var(--ink-soft)', display:'inline-flex', alignItems:'center', gap:6,
      }}>
        <span style={{ color:'var(--ink-faint)', letterSpacing:'0.08em', textTransform:'uppercase' }}>{label}</span>
        <span style={{ color:'var(--ink)', fontWeight:600 }}>{value}</span>
        <IcoChevron dir="down" size={10}/>
      </button>
      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position:'fixed', inset:0, zIndex:5 }}/>
          <div style={{
            position:'absolute', top:'calc(100% + 4px)', left:0, zIndex:6,
            background:'var(--surface)', border:'1px solid var(--border-md)',
            borderRadius:3, boxShadow:'var(--shadow)', minWidth:160,
          }}>
            {options.map(o => (
              <div key={o} onClick={() => { onChange(o); setOpen(false); }} style={{
                padding:'7px 12px', fontSize:12, fontFamily:'var(--mono)',
                cursor:'pointer', background: o === value ? 'var(--surface-alt)' : 'transparent',
                color: o === value ? 'var(--ink)' : 'var(--ink-soft)',
                fontWeight: o === value ? 600 : 500,
              }}
                onMouseEnter={e => e.currentTarget.style.background='var(--surface-alt)'}
                onMouseLeave={e => e.currentTarget.style.background = o === value ? 'var(--surface-alt)' : 'transparent'}
              >{o}</div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function ThemeCard({ theme, onSelectContract }) {
  const [expanded, setExpanded] = useState(false);
  const sev = SEVERITY_META[theme.severity];
  const contracts = (theme.contracts || []).map(item => (
    typeof item === 'string'
      ? { id:item, number:item, title:'Contract details unavailable', component:'—', value:'—', unavailable:true }
      : normalizeThemeContract(item)
  )).filter(Boolean);

  return (
    <div style={{
      background:'var(--surface)', border:'1px solid var(--border)',
      borderLeft:`3px solid ${sev.clr}`,
      borderRadius:3,
    }}>
      <div onClick={() => setExpanded(e => !e)} style={{
        padding:'16px 20px', cursor:'pointer',
        display:'grid', gridTemplateColumns:'1fr auto auto auto auto', gap:24, alignItems:'center',
      }}>
        <div style={{ minWidth:0 }}>
          <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:6 }}>
            <span style={{
              fontSize:9.5, fontWeight:700, letterSpacing:'0.10em', textTransform:'uppercase',
              color:sev.clr, background:sev.bg, border:`1px solid ${sev.border}`,
              padding:'2px 7px', borderRadius:2, fontFamily:'var(--mono)',
            }}>{sev.label}</span>
            <Tag>{theme.psc}</Tag>
            <Tag>{theme.component}</Tag>
          </div>
          <div style={{ fontSize:14.5, fontWeight:600, color:'var(--ink)', lineHeight:1.4, marginBottom:4 }}>{theme.title}</div>
          <div style={{ fontSize:12, color:'var(--ink-mute)', lineHeight:1.5 }}>{theme.insight}</div>
        </div>

        <div style={{ textAlign:'right', minWidth:90 }}>
          <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase', color:'var(--ink-faint)', fontFamily:'var(--mono)', marginBottom:4 }}>{theme.metric}</div>
          <div style={{ fontSize:18, fontWeight:700, color:'var(--ink)', fontFamily:'var(--mono)', lineHeight:1 }}>{theme.value}</div>
          <div style={{ fontSize:10, color:'var(--ink-mute)', marginTop:4, fontFamily:'var(--mono)' }}>{theme.delta}</div>
        </div>

        <div style={{ textAlign:'right', minWidth:80 }}>
          <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase', color:'var(--ink-faint)', fontFamily:'var(--mono)', marginBottom:4 }}>Contracts</div>
          <div style={{ fontSize:18, fontWeight:700, color:'var(--ink)', fontFamily:'var(--mono)', lineHeight:1 }}>
            <span style={{color:sev.clr}}>{theme.flagged}</span><span style={{color:'var(--ink-faint)'}}> / {theme.total}</span>
          </div>
          <div style={{ fontSize:10, color:'var(--ink-mute)', marginTop:4, fontFamily:'var(--mono)' }}>flagged</div>
        </div>

        <div style={{ textAlign:'right', minWidth:80 }}>
          <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase', color:'var(--ink-faint)', fontFamily:'var(--mono)', marginBottom:4 }}>Value</div>
          <div style={{ fontSize:18, fontWeight:700, color:'var(--ink)', fontFamily:'var(--mono)', lineHeight:1 }}>{theme.valueFlagged}</div>
        </div>

        <div style={{ color:'var(--ink-mute)', transform: expanded ? 'rotate(90deg)' : 'none', transition:'transform 0.15s' }}>
          <IcoChevron dir="right"/>
        </div>
      </div>

      {expanded && (
        <div style={{ borderTop:'1px solid var(--border)', background:'var(--surface-alt)', padding:'12px 20px 14px' }}>
          <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:10 }}>Contracts in this theme</div>
          {contracts.length === 0 && (
            <div style={{ fontSize:11.5, color:'var(--ink-mute)' }}>
              No contract records were returned for this theme.
            </div>
          )}
          {contracts.map((c, i) => (
            <div key={c.id} onClick={() => !c.unavailable && onSelectContract(c)} style={{
              display:'grid', gridTemplateColumns:'160px 1fr 100px 100px 16px', gap:14, alignItems:'center',
              padding:'9px 0', borderBottom: i < contracts.length-1 ? '1px solid var(--border)' : 'none',
              cursor: c.unavailable ? 'default' : 'pointer',
            }}>
              <span style={{ fontFamily:'var(--mono)', fontSize:11.5, fontWeight:600, color:'var(--accent)' }}>{c.number}</span>
              <span style={{ fontSize:13, color:'var(--ink)', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{c.title}</span>
              <span style={{ fontSize:11, color:'var(--ink-mute)', fontFamily:'var(--mono)', textAlign:'right' }}>{c.component}</span>
              <span style={{ fontSize:11, color:'var(--ink-mute)', fontFamily:'var(--mono)', textAlign:'right' }}>{c.value}</span>
              <IcoChevron/>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── CONTRACTS LIST PAGE ────────────────────────────────────────────────────
function ContractsPage({ onSelectContract }) {
  const [search, setSearch] = useState('');
  const [pscFilter, setPscFilter] = useState('all');
  const [componentFilter, setComponentFilter] = useState('all');
  const [userContracts, setUserContracts] = useState([]);
  const [backendContracts, setBackendContracts] = useState(null);
  const [showLog, setShowLog] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listContracts()
      .then(rows => {
        if (!cancelled) setBackendContracts(rows.map(normalizeContract));
      })
      .catch(() => {
        if (!cancelled) setBackendContracts([]);
      });
    return () => { cancelled = true; };
  }, []);

  const baseContracts = backendContracts || [];
  const allContracts = [...userContracts, ...baseContracts];
  const presentPscs = new Set(allContracts.map(c => c.psc));
  const pscOptions = PSC_CODES.map(p => ({
    id: p.code, label: p.code, desc: p.desc,
    disabled: !presentPscs.has(p.code),
  }));
  // Make sure any PSC actually used by a contract appears in the dropdown,
  // even if it isn't in PSC_CODES.
  for (const c of allContracts) {
    if (!pscOptions.some(o => o.id === c.psc)) {
      pscOptions.push({ id:c.psc, label:c.psc, desc:'(from contract record)', disabled:false });
    }
  }
  pscOptions.sort((a, b) => a.id.localeCompare(b.id));

  const components = [...new Set(allContracts.map(c => c.component))];

  const filtered = allContracts.filter(c => {
    if (pscFilter !== 'all' && c.psc !== pscFilter) return false;
    if (componentFilter !== 'all' && c.component !== componentFilter) return false;
    if (search && !`${c.number} ${c.title} ${c.contractor}`.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
      <TopBar crumbs={['Contracts']} />

      <div style={{
        background:'var(--surface)', borderBottom:'1px solid var(--border)',
        padding:'18px 24px',
        display:'flex', alignItems:'flex-end', justifyContent:'space-between', gap:16,
      }}>
        <div>
          <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.18em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:6 }}>Workspace</div>
          <h1 style={{ fontSize:22, fontWeight:700, letterSpacing:'-0.02em', color:'var(--ink)' }}>Contracts</h1>
          <p style={{ fontSize:12, color:'var(--ink-mute)', marginTop:4 }}>{allContracts.length} contracts indexed · FY22 — FY27 spans</p>
        </div>
        <div style={{ display:'flex', gap:8 }}>
          <BtnSecondary>Export CSV</BtnSecondary>
          <BtnPrimary onClick={() => setShowLog(true)}>+ Log Contract</BtnPrimary>
        </div>
      </div>

      {/* Filter bar */}
      <div style={{
        background:'var(--surface)', borderBottom:'1px solid var(--border)',
        padding:'10px 24px',
        display:'flex', alignItems:'center', gap:14, flexWrap:'wrap',
      }}>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <span style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.12em', textTransform:'uppercase', fontFamily:'var(--mono)' }}>PSC</span>
          <SearchableSelect value={pscFilter} onChange={setPscFilter} options={pscOptions} placeholder="Search PSC code or description…" />
        </div>
        <div style={{ height:18, width:1, background:'var(--border)' }}/>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <span style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.12em', textTransform:'uppercase', fontFamily:'var(--mono)' }}>Component</span>
          <FilterPills options={[{id:'all', label:'All'}, ...components.map(c=>({id:c, label:c}))]} value={componentFilter} onChange={setComponentFilter} />
        </div>
        <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:8,
          border:'1px solid var(--border-md)', borderRadius:3,
          padding:'5px 10px', background:'var(--surface-alt)', color:'var(--ink-mute)' }}>
          <IcoSearch/>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Filter contracts…" style={{ border:'none', background:'transparent', outline:'none', width:200, fontSize:12 }}/>
        </div>
      </div>

      {/* Table */}
      <div style={{ flex:1, overflowY:'auto', background:'var(--bg)' }}>
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead>
            <tr style={{ background:'var(--surface-alt)' }}>
              {['Contract #', 'Title / Contractor', 'PSC', 'Component', 'Value', 'Period of Performance', 'Elapsed', 'Last Activity', ''].map((h,i) => (
                <th key={i} style={{
                  padding:'9px 16px', textAlign:'left',
                  fontSize:10, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase',
                  color:'var(--ink-mute)', whiteSpace:'nowrap', fontFamily:'var(--mono)',
                  position:'sticky', top:0, background:'var(--surface-alt)',
                  borderBottom:'1px solid var(--border-md)', borderTop:'1px solid var(--border)',
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((c) => (
              <tr key={c.id} onClick={() => onSelectContract(c)} style={{
                borderBottom:'1px solid var(--border)', cursor:'pointer',
                background:'var(--surface)', transition:'background 0.1s',
              }}
                onMouseEnter={e => e.currentTarget.style.background='var(--surface-alt)'}
                onMouseLeave={e => e.currentTarget.style.background='var(--surface)'}
              >
                <td style={{ padding:'13px 16px', whiteSpace:'nowrap' }}>
                  <span style={{ fontFamily:'var(--mono)', fontSize:12, fontWeight:600, color:'var(--accent)' }}>{c.number}</span>
                </td>
                <td style={{ padding:'13px 16px', maxWidth:300 }}>
                  <div style={{ fontSize:13, fontWeight:500, color:'var(--ink)', lineHeight:1.3 }}>{c.title}</div>
                  <div style={{ fontSize:11, color:'var(--ink-mute)', marginTop:2 }}>{c.contractor}</div>
                </td>
                <td style={{ padding:'13px 16px', whiteSpace:'nowrap' }}><Tag>{c.psc}</Tag></td>
                <td style={{ padding:'13px 16px', fontSize:12, color:'var(--ink-soft)', whiteSpace:'nowrap', fontFamily:'var(--mono)' }}>{c.component}</td>
                <td style={{ padding:'13px 16px', fontSize:12, fontWeight:600, color:'var(--ink)', fontFamily:'var(--mono)', whiteSpace:'nowrap', textAlign:'right' }}>{c.value}</td>
                <td style={{ padding:'13px 16px', fontSize:11, color:'var(--ink-mute)', whiteSpace:'nowrap', fontFamily:'var(--mono)' }}>{c.period}</td>
                <td style={{ padding:'13px 16px', whiteSpace:'nowrap' }}>
                  <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                    <div style={{ width:60, height:3, background:'var(--surface-alt)', borderRadius:2, overflow:'hidden', flexShrink:0, border:'1px solid var(--border)' }}>
                      <div style={{ height:'100%', width:`${c.elapsed}%`, background:'var(--ink-mute)' }}/>
                    </div>
                    <span style={{ fontSize:11, color:'var(--ink-mute)', fontFamily:'var(--mono)' }}>{c.elapsed}%</span>
                  </div>
                </td>
                <td style={{ padding:'13px 16px', fontSize:11, color:'var(--ink-mute)', whiteSpace:'nowrap', fontFamily:'var(--mono)' }}>{c.lastActivity}</td>
                <td style={{ padding:'13px 16px', color:'var(--ink-faint)' }}><IcoChevron/></td>
              </tr>
            ))}
          </tbody>
        </table>
        {backendContracts === null && <Spinner label="Loading contract records…" />}
        {backendContracts !== null && filtered.length === 0 && (
          <EmptyState
            title={allContracts.length === 0 ? "No contract records visible" : "No contracts match"}
            sub={allContracts.length === 0 ? "Create a contract record or request access to an existing record." : "Try adjusting your filters or search term."}
          />
        )}
      </div>

      {showLog && (
        <NewContractModal
          onClose={() => setShowLog(false)}
          onCreated={(c) => { setUserContracts(prev => [c, ...prev]); setShowLog(false); }}
        />
      )}
    </div>
  );
}

function FilterPills({ options, value, onChange }) {
  return (
    <div style={{ display:'flex', gap:4 }}>
      {options.map(o => {
        const active = o.id === value;
        return (
          <button key={o.id} onClick={() => onChange(o.id)} style={{
            padding:'4px 10px', borderRadius:3,
            border:`1px solid ${active ? 'var(--ink)' : 'var(--border-md)'}`,
            background: active ? 'var(--ink)' : 'transparent',
            color: active ? '#fff' : 'var(--ink-soft)',
            fontSize:11, fontWeight:active ? 600 : 500,
            fontFamily:'var(--mono)', letterSpacing:'0.04em',
          }}>{o.label}</button>
        );
      })}
    </div>
  );
}

// ─── CONTRACT DETAIL PAGE ───────────────────────────────────────────────────
const DETAIL_TABS = ['Overview', 'Lifecycle', 'Insights', 'Benchmarks', 'Documents'];

function ContractDetailPage({ contract, onBack, onSelectContract }) {
  const [tab, setTab] = useState('Overview');
  const [docs, setDocs] = useState([]);
  const [findings, setFindings] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [deliverables, setDeliverables] = useState(null);
  const [lifecycle, setLifecycle] = useState(null);
  const [lifecycleError, setLifecycleError] = useState(false);
  const [showUpload, setShowUpload] = useState(false);

  const c = contract;

  function refreshLifecycle() {
    setLifecycle(null);
    setLifecycleError(false);
    return getContractLifecycle(c.id)
      .then(row => {
        setLifecycle(row);
        setLifecycleError(false);
      })
      .catch(() => {
        setLifecycleError(true);
      });
  }

  useEffect(() => {
    setDocs([]);
    setFindings([]);
    setAnalysis(null);
    setDeliverables(null);
    setLifecycle(null);
    setLifecycleError(false);
    let cancelled = false;
    listContractDocuments(c.id)
      .then(rows => {
        if (!cancelled) setDocs(rows.map(row => normalizeDocument(row, c)));
      })
      .catch(() => { if (!cancelled) setDocs([]); });
    listRegressions(c.id)
      .then(rows => {
        if (!cancelled) setFindings(rows.map(normalizeFinding));
      })
      .catch(() => { if (!cancelled) setFindings([]); });
    getContractAnalysis(c.id)
      .then(row => {
        if (!cancelled) setAnalysis(row);
      })
      .catch(() => {});
    getContractDeliverables(c.id)
      .then(row => {
        if (!cancelled) setDeliverables(row);
      })
      .catch(() => {
        if (!cancelled) setDeliverables({ availability:'error', groups:[], limitations:['Deliverable evidence could not be loaded.'] });
      });
    getContractLifecycle(c.id)
      .then(row => {
        if (!cancelled) setLifecycle(row);
      })
      .catch(() => {
        if (!cancelled) setLifecycleError(true);
      });
    return () => { cancelled = true; };
  }, [c.id]);

  return (
    <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
      <TopBar crumbs={[{ label:'Contracts', onClick: onBack }, { label: c.number }]} />

      {/* Sub-header */}
      <div style={{
        background:'var(--surface)', borderBottom:'1px solid var(--border)',
        padding:'18px 24px 0',
      }}>
        <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', gap:16, marginBottom:14 }}>
          <div style={{ minWidth:0 }}>
            <div style={{ display:'flex', alignItems:'center', gap:10, flexWrap:'wrap', marginBottom:6 }}>
              <span style={{ fontFamily:'var(--mono)', fontSize:18, fontWeight:700, color:'var(--ink)' }}>{c.number}</span>
              <Tag>{c.psc}</Tag>
              <Tag>{c.component}</Tag>
              <Tag tone="default">NAICS {c.naics}</Tag>
            </div>
            <div style={{ fontSize:14, fontWeight:600, color:'var(--ink-soft)', marginBottom:4 }}>{c.title}</div>
            <div style={{ fontSize:11.5, color:'var(--ink-mute)', fontFamily:'var(--mono)' }}>
              {c.period} · {c.elapsed}% elapsed · {c.value} · CO {c.co}
            </div>
          </div>
          <div style={{ display:'flex', gap:8, flexShrink:0 }}>
            <BtnSecondary>Export</BtnSecondary>
          </div>
        </div>

        <div style={{ display:'flex', gap:0, marginLeft:-4 }}>
          {DETAIL_TABS.map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              padding:'8px 14px 9px',
              border:'none', borderBottom: t === tab ? '2px solid var(--ink)' : '2px solid transparent',
              background:'transparent',
              fontSize:13, fontWeight: t === tab ? 600 : 400,
              color: t === tab ? 'var(--ink)' : 'var(--ink-mute)',
              cursor:'pointer', marginBottom:-1,
            }}>{t}</button>
          ))}
        </div>
      </div>

      {/* Body */}
      <div style={{ flex:1, overflowY:'auto' }}>
        {tab === 'Overview'   && <OverviewTab contract={c} docs={docs} deliverables={deliverables} lifecycle={lifecycle} lifecycleError={lifecycleError} />}
        {tab === 'Lifecycle'  && <LifecycleTab contract={c} lifecycle={lifecycle} error={lifecycleError} />}
        {tab === 'Insights'   && <ContractInsightsTab contract={c} findings={findings} lifecycle={lifecycle} onSelectContract={onSelectContract} />}
        {tab === 'Benchmarks' && <BenchmarksTab contract={c} analysis={analysis} />}
        {tab === 'Documents'  && <DocumentsTab docs={docs} contract={c} onUpload={() => setShowUpload(true)} />}
      </div>

      {showUpload && <UploadModal contract={c} onClose={() => setShowUpload(false)} onUploaded={(d) => { setDocs(prev => [d, ...prev]); refreshLifecycle(); setShowUpload(false); }}/>}
    </div>
  );
}

// ─── OVERVIEW TAB ───────────────────────────────────────────────────────────
function OverviewTab({ contract: c, docs, deliverables, lifecycle, lifecycleError }) {
  const classification = c.classification || 'CUI';
  const header = lifecycle?.contract || {};
  const sources = lifecycle?.source_packet || [];
  const lifecycleDeliverables = lifecycle?.deliverables || [];
  const monthly = lifecycle?.monthly_reports || [];
  const issues = lifecycle?.issue_register || [];
  const financial = lifecycle?.financial_summary || {};
  const deliverableGroups = normalizeBackendDeliverables(deliverables);
  const deliverableAvailability = lifecycle
    ? lifecycle.availability
    : lifecycleError
      ? 'error'
      : (deliverables?.availability || 'loading');
  const allItems = lifecycleDeliverables.length
    ? lifecycleDeliverables
    : deliverableGroups.flatMap(d => d.items);
  const latestSource = docs[0] || null;
  const latestPeriod = monthly.length ? (monthly[monthly.length - 1].period || `Month ${monthly[monthly.length - 1].month_number}`) : 'No monthly row';
  const value = fmtLifecycleMoney(header.obligated_value || header.funded_amount || header.awarded_contract_value);
  const period = header.current_period || header.base_period || c.period;
  const contractRows = [
    ['Contract Number', header.contract_number || c.number, true],
    ['Contractor', header.contractor || c.contractor || 'Not extracted', false],
    ['Contracting Officer', header.contracting_officer || c.co || 'Not extracted', false],
    ['Agency / Office', [header.agency || c.component, header.office].filter(Boolean).join(' · ') || 'Not extracted', false],
    ['PSC / NAICS', `${c.psc || 'Not extracted'} · ${c.naics || 'Not extracted'}`, true],
    ['Period', period || 'Not extracted', true],
    ['Total Value', value === '—' ? (c.value || 'Not extracted') : value, true],
    ['Classification', classification, true],
  ];

  return (
    <div style={{ padding:'24px 24px 48px' }}>
      {/* Top metrics */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4, 1fr)', gap:12, marginBottom:24 }}>
        <MetricCard label="Contract Value" value={value === '—' ? c.value : value} sub="Lifecycle header" mono />
        <MetricCard label="Latest CPI / SPI" value={`${fmtLifecycleNumber(financial.latest_cpi)} / ${fmtLifecycleNumber(financial.latest_spi)}`} sub="IPMDAR lifecycle" mono />
        <MetricCard label="Deliverables" value={deliverableAvailability === 'available' ? String(allItems.length) : '—'} sub={availabilityLabel(deliverableAvailability)} mono />
        <MetricCard label="Latest Report" value={latestPeriod} sub={latestSource ? fmtDateMil(latestSource.created_at) : 'No filing'} mono />
      </div>

      {/* Two-column: details + activity */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:20, marginBottom:20 }}>
        <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4, padding:'18px 22px' }}>
          <div style={{ fontSize:11, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', marginBottom:14, fontFamily:'var(--mono)' }}>Contract Particulars</div>
          {contractRows.map(([k, v, mono]) => (
            <div key={k} style={{
              display:'flex', justifyContent:'space-between', gap:24,
              padding:'8px 0', borderBottom:'1px solid var(--border)',
            }}>
              <span style={{ fontSize:11.5, color:'var(--ink-mute)', whiteSpace:'nowrap', fontFamily:'var(--mono)', letterSpacing:'0.04em', textTransform:'uppercase' }}>{k}</span>
              <span style={{
                fontSize:12, fontWeight:600, color:'var(--ink)', textAlign:'right',
                fontFamily: mono ? 'var(--mono)' : 'inherit',
              }}>{v}</span>
            </div>
          ))}

          <div style={{ marginTop:14, paddingTop:14, borderTop:'1px solid var(--border-md)' }}>
            <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:10 }}>Lifecycle Readiness</div>
            {[
              ['Source packet', sources.length],
              ['Monthly rows', monthly.length],
              ['Issue rows', issues.length],
              ['Evidence gaps', (lifecycle?.limitations || []).length + (lifecycle?.not_proven || []).length],
            ].map(([label, count]) => (
              <div key={label} style={{ display:'flex', justifyContent:'space-between', gap:12, padding:'7px 0', borderBottom:'1px solid var(--border)' }}>
                <span style={{ fontSize:11.5, color:'var(--ink-mute)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'0.04em' }}>{label}</span>
                <span style={{ fontSize:12, color:'var(--ink)', fontWeight:700, fontFamily:'var(--mono)' }}>{count}</span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4, padding:'18px 22px' }}>
          <div style={{ fontSize:11, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', marginBottom:14, fontFamily:'var(--mono)' }}>Source Packet</div>
          {!lifecycle && !lifecycleError && <Spinner label="Loading lifecycle evidence…" />}
          {lifecycleError && <EmptyState title="Lifecycle unavailable" sub="Backend lifecycle evidence could not be loaded." />}
          {lifecycle && sources.length === 0 && <EmptyState title="No linked source packet" sub="Upload and process contract artifacts to populate the lifecycle packet." />}
          {sources.slice(0, 8).map((source, i) => {
            const d = docs.find(item => item.id === source.document_id) || source;
            const meta = DOC_TYPE_META[d.doc_type] || { abbr:'DOC', tone:'default' };
            return (
              <div key={source.document_id || d.id} style={{
                display:'flex', gap:12, padding:'8px 0',
                borderBottom: i < Math.min(sources.length, 8) - 1 ? '1px solid var(--border)' : 'none',
                alignItems:'center',
              }}>
                <div style={{
                  fontSize:9, fontWeight:700, fontFamily:'var(--mono)',
                  color: meta.tone === 'ink' ? '#fff' : 'var(--ink-mute)',
                  background: meta.tone === 'ink' ? 'var(--ink)' : 'var(--surface-alt)',
                  border: '1px solid ' + (meta.tone === 'ink' ? 'var(--ink)' : 'var(--border-md)'),
                  padding:'3px 6px', borderRadius:2, letterSpacing:'0.06em', minWidth:42, textAlign:'center',
                }}>{meta.abbr}</div>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontSize:12.5, color:'var(--ink)', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{source.title || d.title || source.filename}</div>
                  <div style={{ fontSize:10, color:'var(--ink-faint)', marginTop:2, fontFamily:'var(--mono)', letterSpacing:'0.04em', textTransform:'uppercase' }}>{source.lifecycle_role || source.document_kind || d.source}</div>
                </div>
                <div style={{ fontSize:10, color:source.has_extracted_text ? 'var(--good)' : 'var(--warn)', fontFamily:'var(--mono)', whiteSpace:'nowrap' }}>{source.has_extracted_text ? 'TEXT' : 'NO TEXT'}</div>
              </div>
            );
          })}
        </div>
      </div>

      <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4, padding:'18px 22px 22px' }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:18 }}>
          <div>
            <div style={{ fontSize:11, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)' }}>Deliverables Evidence</div>
            <div style={{ fontSize:11, color:'var(--ink-faint)', fontFamily:'var(--mono)', marginTop:4 }}>{period} · lifecycle CDRL/deliverable extraction</div>
          </div>
        </div>
        {!lifecycle && !lifecycleError && <Spinner label="Loading lifecycle deliverables…" />}
        {lifecycle && lifecycleDeliverables.length > 0 && (
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead>
              <tr style={{ background:'var(--surface-alt)' }}>
                {['CDRL', 'Deliverable', 'Status', 'Evidence'].map(h => (
                  <th key={h} style={{ padding:'9px 12px', textAlign:'left', fontSize:10, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', borderBottom:'1px solid var(--border-md)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lifecycleDeliverables.map((item, i) => (
                <tr key={`${item.cdrl_item || 'cdrl'}-${item.title}-${i}`} style={{ borderBottom:'1px solid var(--border)' }}>
                  <td style={{ padding:'10px 12px', fontSize:12, fontFamily:'var(--mono)', color:'var(--accent)', fontWeight:700 }}>{item.cdrl_item || '—'}</td>
                  <td style={{ padding:'10px 12px', fontSize:12.5, color:'var(--ink)' }}>{item.title || item.description || 'Deliverable'}</td>
                  <td style={{ padding:'10px 12px', fontSize:11, fontFamily:'var(--mono)', color:'var(--ink-soft)' }}>{item.status || item.acceptance_status || 'requirement'}</td>
                  <td style={{ padding:'10px 12px', fontSize:11, fontFamily:'var(--mono)', color:'var(--ink-mute)' }}>{(item.document_ids || []).join(', ') || item.source || 'lifecycle'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {lifecycle && lifecycleDeliverables.length === 0 && (
          <EmptyState title="No lifecycle deliverables available" sub={(lifecycle.limitations || deliverables?.limitations || [])[0] || availabilityLabel(deliverableAvailability)} />
        )}
        {lifecycleError && <EmptyState title="Deliverable evidence unavailable" sub="Backend lifecycle evidence could not be loaded." />}
      </div>
    </div>
  );
}

// ─── GANTT — schedule of CDRL deliverables across the period of performance ─
function ContractGantt({ contract: c, deliverables }) {
  const start = new Date(c.start).getTime();
  const end = new Date(c.end).getTime();
  const span = end - start;
  const today = Date.now();
  const todayPct = Math.max(0, Math.min(100, (today - start) / span * 100));

  // Year tick marks
  const startYear = new Date(c.start).getFullYear();
  const endYear = new Date(c.end).getFullYear();
  const ticks = [];
  for (let y = startYear; y <= endYear + 1; y++) {
    const t = new Date(y, 0, 1).getTime();
    if (t >= start && t <= end) ticks.push({ year:y, pct:(t-start)/span*100 });
  }

  return (
    <div>
      {/* Year axis */}
      <div style={{
        display:'grid', gridTemplateColumns:'260px 1fr', gap:0, marginBottom:8,
      }}>
        <div/>
        <div style={{ position:'relative', height:18 }}>
          {ticks.map(t => (
            <div key={t.year} style={{ position:'absolute', left:`${t.pct}%`, transform:'translateX(-50%)' }}>
              <div style={{ fontSize:10, color:'var(--ink-faint)', fontFamily:'var(--mono)', letterSpacing:'0.04em' }}>{t.year}</div>
            </div>
          ))}
          {/* Today label */}
          <div style={{ position:'absolute', left:`${todayPct}%`, top:0, transform:'translateX(-50%)', fontSize:9, fontWeight:700, color:'var(--flag)', fontFamily:'var(--mono)', letterSpacing:'0.06em', whiteSpace:'nowrap' }}>TODAY</div>
        </div>
      </div>

      {/* Period of performance row (header bar) */}
      <GanttRow
        label="Period of Performance" sublabel={c.period}
        renderTrack={(span, todayPct) => (
          <div style={{ position:'absolute', left:0, right:0, top:'50%', transform:'translateY(-50%)', height:14 }}>
            <div style={{ position:'absolute', inset:0, background:'var(--surface-alt)', border:'1px solid var(--border-md)', borderRadius:2 }}/>
            <div style={{ position:'absolute', left:0, top:0, bottom:0, width:`${c.elapsed}%`, background:'var(--ink)', opacity:0.85, borderRadius:2 }}/>
          </div>
        )}
        ticks={ticks} todayPct={todayPct}
      />

      {/* Deliverable rows */}
      {deliverables.map(d => (
        <GanttRow
          key={d.id}
          label={
            <span>
              {d.cdrl !== '—' && <span style={{ color:'var(--accent)', fontFamily:'var(--mono)', fontSize:9.5, fontWeight:700, marginRight:6, letterSpacing:'0.04em' }}>CDRL {d.cdrl}</span>}
              {d.title}
            </span>
          }
          sublabel={`${d.cadence} · ${d.recipient}${d.source === 'imported' ? ' · imported' : ''}`}
          renderTrack={() => (
            <div style={{ position:'absolute', inset:0 }}>
              {d.items.map(it => {
                const t = new Date(it.due).getTime();
                if (!Number.isFinite(t)) return null;
                if (t < start || t > end) return null;
                const pct = (t - start) / span * 100;
                const isLate = it.late;
                const isImported = d.source === 'imported';
                const isFiled = it.filed;
                const fill = isLate
                  ? 'var(--warn)'
                  : isFiled
                    ? (isImported ? 'var(--accent)' : 'var(--ink)')
                    : 'var(--surface)';
                const stroke = isLate
                  ? 'var(--warn)'
                  : isFiled
                    ? (isImported ? 'var(--accent)' : 'var(--ink)')
                    : 'var(--border-str)';
                return (
                  <div key={it.id} title={`${it.title} · due ${new Date(it.due).toLocaleDateString('en-US',{day:'2-digit',month:'short',year:'numeric'})}${isFiled ? ' · filed' : ''}${isLate ? ' (late)' : ''}`}
                    style={{
                      position:'absolute', left:`${pct}%`, transform:'translateX(-50%)',
                      top:'50%', marginTop:-5, width:8, height:10,
                      background: fill, border:`1.5px solid ${stroke}`,
                      borderRadius:1, cursor:'pointer',
                    }}/>
                );
              })}
            </div>
          )}
          ticks={ticks} todayPct={todayPct}
        />
      ))}
    </div>
  );
}

function GanttRow({ label, sublabel, renderTrack, ticks, todayPct }) {
  return (
    <div style={{
      display:'grid', gridTemplateColumns:'260px 1fr', gap:0,
      borderTop:'1px solid var(--border)', minHeight:38,
    }}>
      <div style={{ padding:'8px 14px 8px 0', borderRight:'1px solid var(--border)' }}>
        <div style={{ fontSize:12, color:'var(--ink)', fontWeight:500, lineHeight:1.3 }}>{label}</div>
        {sublabel && <div style={{ fontSize:9.5, color:'var(--ink-faint)', fontFamily:'var(--mono)', marginTop:3, letterSpacing:'0.04em', textTransform:'uppercase' }}>{sublabel}</div>}
      </div>
      <div style={{ position:'relative', padding:'8px 0' }}>
        {/* gridlines */}
        {ticks.map(t => (
          <div key={t.year} style={{ position:'absolute', left:`${t.pct}%`, top:0, bottom:0, width:1, background:'var(--border)' }}/>
        ))}
        {/* today line */}
        <div style={{ position:'absolute', left:`${todayPct}%`, top:0, bottom:0, width:1, background:'var(--flag)', opacity:0.7 }}/>
        {renderTrack()}
      </div>
    </div>
  );
}

function LegendDot({ color, border, label }) {
  return (
    <div style={{ display:'flex', alignItems:'center', gap:6 }}>
      <div style={{ width:8, height:8, background:color, border: border ? `1px solid ${border}` : 'none', borderRadius:1 }}/>
      <span>{label}</span>
    </div>
  );
}

function availabilityLabel(value) {
  const map = {
    loading: 'Loading evidence',
    available: 'backend evidence',
    not_extracted: 'not extracted',
    processing_pending: 'processing pending',
    source_absent: 'source absent',
    provider_unavailable: 'provider unavailable',
    not_applicable: 'not applicable',
    error: 'unavailable',
  };
  return map[value] || String(value || 'unavailable').replace(/_/g, ' ');
}

function normalizeBackendDeliverables(payload) {
  if (!payload?.groups) return [];
  return payload.groups.map(group => ({
    id: group.key,
    cdrl: group.cdrl_item || '—',
    title: group.title || 'Deliverable',
    kind: 'recurring',
    cadence: 'Extracted evidence',
    recipient: 'Contract file',
    items: (group.items || []).map(item => {
      const due = item.planned_due_date || item.actual_delivery_date || null;
      return {
        id: item.id,
        due,
        filed: Boolean(item.actual_delivery_date || item.status === 'reported' || item.status === 'on_time' || item.status === 'late'),
        late: item.status === 'late' || Number(item.days_late || 0) > 0,
        title: item.period_label || item.deliverable_name || group.title || 'Deliverable',
      };
    }),
  })).filter(group => group.items.length > 0);
}

function LifecycleTab({ contract: c, lifecycle, error }) {
  if (error) {
    return (
      <div style={{ padding:'24px' }}>
        <EmptyState title="Lifecycle packet unavailable" sub="The backend lifecycle endpoint could not be loaded for this contract." />
      </div>
    );
  }
  if (!lifecycle) {
    return (
      <div style={{ padding:'24px' }}>
        <Spinner label="Loading lifecycle evidence…" />
      </div>
    );
  }

  const monthly = lifecycle.monthly_reports || [];
  const ipmdar = lifecycle.ipmdar_metrics || [];
  const issues = lifecycle.issue_register || [];
  const ratings = lifecycle.cpars_ratings || [];
  const events = lifecycle.lifecycle_events || [];
  const sources = lifecycle.source_packet || [];
  const limitations = lifecycle.limitations || [];
  const notProven = lifecycle.not_proven || [];
  const financial = lifecycle.financial_summary || {};

  return (
    <div style={{ padding:'24px 24px 48px' }}>
      <SectionHeader
        title={`Lifecycle evidence for ${c.number}`}
        subtitle="Backend extracted packet from linked contract documents, reports, IPMDAR, CPARS, and CDRLs"
      />

      <div style={{ display:'grid', gridTemplateColumns:'repeat(4, 1fr)', gap:12, marginBottom:20 }}>
        <MetricCard label="Sources" value={String(sources.length)} sub={availabilityLabel(lifecycle.availability)} mono />
        <MetricCard label="Monthly Reports" value={String(monthly.length)} sub="status rows" mono />
        <MetricCard label="Latest CPI / SPI" value={`${fmtLifecycleNumber(financial.latest_cpi)} / ${fmtLifecycleNumber(financial.latest_spi)}`} sub="IPMDAR" mono />
        <MetricCard label="Latest Invoiced" value={fmtLifecycleMoney(financial.latest_invoiced_to_date)} sub="monthly report" mono />
      </div>

      {(limitations.length > 0 || notProven.length > 0) && (
        <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderLeft:'3px solid var(--warn)', borderRadius:4, padding:'14px 18px', marginBottom:20 }}>
          <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:8 }}>Evidence Limits</div>
          {[...limitations, ...notProven].slice(0, 8).map((item, i) => (
            <div key={`${item}-${i}`} style={{ fontSize:12, color:'var(--ink-mute)', lineHeight:1.55, padding:'3px 0' }}>{item}</div>
          ))}
        </div>
      )}

      <div style={{ display:'grid', gridTemplateColumns:'1.15fr 0.85fr', gap:18, marginBottom:18 }}>
        <LifecyclePanel title="Lifecycle Events" emptyTitle="No lifecycle events extracted" emptySub="Upload and process baseline reports, mods, and IPMDAR/CPARS evidence.">
          {events.map((event, i) => (
            <div key={`${event.date || 'event'}-${i}`} style={{ display:'grid', gridTemplateColumns:'112px 150px 1fr', gap:12, padding:'8px 0', borderBottom: i < events.length - 1 ? '1px solid var(--border)' : 'none' }}>
              <div style={{ fontSize:11, color:'var(--ink-soft)', fontFamily:'var(--mono)' }}>{fmtLifecycleDate(event.date)}</div>
              <div style={{ fontSize:10, color:'var(--accent)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'0.08em' }}>{event.type || 'event'}</div>
              <div style={{ fontSize:12.5, color:'var(--ink)', lineHeight:1.45 }}>{event.summary || 'Lifecycle event'}</div>
            </div>
          ))}
        </LifecyclePanel>

        <LifecyclePanel title="CPARS Ratings" emptyTitle="No CPARS ratings extracted" emptySub="Import an authorized CPARS export or process a CPARS narrative.">
          {ratings.map((rating, i) => (
            <div key={`${rating.label}-${i}`} style={{ display:'grid', gridTemplateColumns:'1fr auto', gap:12, padding:'8px 0', borderBottom: i < ratings.length - 1 ? '1px solid var(--border)' : 'none' }}>
              <div>
                <div style={{ fontSize:12.5, color:'var(--ink)', fontWeight:600 }}>{rating.label}</div>
                <div style={{ fontSize:10.5, color:'var(--ink-faint)', marginTop:2, fontFamily:'var(--mono)' }}>{rating.period_label || rating.source_document_id || 'CPARS evidence'}</div>
              </div>
              <div style={{ alignSelf:'center', fontSize:11, color:'var(--ink)', fontWeight:700, fontFamily:'var(--mono)', whiteSpace:'nowrap' }}>{rating.rating}</div>
            </div>
          ))}
        </LifecyclePanel>
      </div>

      <LifecycleTable
        title="Monthly Status Reports"
        emptyTitle="No monthly status rows extracted"
        emptySub="Upload processed monthly reports linked to this contract."
        columns={['Month', 'Period', 'Invoiced To Date', 'This Period', 'ETC', 'Schedule']}
        rows={monthly}
        renderRow={(row, i) => (
          <tr key={`${row.document_id}-${i}`} style={{ borderBottom:'1px solid var(--border)' }}>
            <LifecycleCell mono>{row.month_number || '—'}</LifecycleCell>
            <LifecycleCell>{row.period || row.source || '—'}</LifecycleCell>
            <LifecycleCell mono align="right">{fmtLifecycleMoney(row.invoiced_to_date)}</LifecycleCell>
            <LifecycleCell mono align="right">{fmtLifecycleMoney(row.invoiced_this_period)}</LifecycleCell>
            <LifecycleCell mono align="right">{fmtLifecycleMoney(row.estimated_cost_to_complete)}</LifecycleCell>
            <LifecycleCell>{row.schedule_status || row.problem_signal || '—'}</LifecycleCell>
          </tr>
        )}
      />

      <LifecycleTable
        title="IPMDAR Metrics"
        emptyTitle="No IPMDAR metrics extracted"
        emptySub="Process IPMDAR PNR/CPD/SPD evidence linked to this contract."
        columns={['Date', 'BCWS', 'BCWP', 'ACWP', 'CV', 'SV', 'CPI', 'SPI', 'Driver']}
        rows={ipmdar}
        renderRow={(row, i) => (
          <tr key={`${row.document_id}-${i}`} style={{ borderBottom:'1px solid var(--border)' }}>
            <LifecycleCell mono>{fmtLifecycleDate(row.data_date) || row.reporting_period || '—'}</LifecycleCell>
            <LifecycleCell mono align="right">{fmtLifecycleMoney(row.bcws)}</LifecycleCell>
            <LifecycleCell mono align="right">{fmtLifecycleMoney(row.bcwp)}</LifecycleCell>
            <LifecycleCell mono align="right">{fmtLifecycleMoney(row.acwp)}</LifecycleCell>
            <LifecycleCell mono align="right">{fmtLifecycleMoney(row.cost_variance)}</LifecycleCell>
            <LifecycleCell mono align="right">{fmtLifecycleMoney(row.schedule_variance)}</LifecycleCell>
            <LifecycleCell mono align="right">{fmtLifecycleNumber(row.cpi)}</LifecycleCell>
            <LifecycleCell mono align="right">{fmtLifecycleNumber(row.spi)}</LifecycleCell>
            <LifecycleCell>{row.primary_driver || '—'}</LifecycleCell>
          </tr>
        )}
      />

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:18 }}>
        <LifecycleTable
          title="Issue Register"
          emptyTitle="No lifecycle issues extracted"
          emptySub="Process reports with issue, variance, staffing, or delay evidence."
          columns={['Issue', 'Owner', 'Severity', 'Status']}
          rows={issues}
          compact
          renderRow={(row, i) => (
            <tr key={`${row.issue_id}-${i}`} style={{ borderBottom:'1px solid var(--border)' }}>
              <LifecycleCell>
                <div style={{ fontWeight:600, color:'var(--ink)' }}>{row.title || row.category || row.issue_id}</div>
                <div style={{ fontSize:11, color:'var(--ink-mute)', marginTop:3, lineHeight:1.45 }}>{row.summary || '—'}</div>
              </LifecycleCell>
              <LifecycleCell mono>{row.responsible_party || '—'}</LifecycleCell>
              <LifecycleCell mono>{row.severity || '—'}</LifecycleCell>
              <LifecycleCell mono>{row.status || '—'}</LifecycleCell>
            </tr>
          )}
        />

        <LifecycleTable
          title="Source Packet"
          emptyTitle="No source packet"
          emptySub="No linked contract documents are visible yet."
          columns={['Document', 'Kind', 'Status', 'Text']}
          rows={sources}
          compact
          renderRow={(row, i) => (
            <tr key={`${row.document_id}-${i}`} style={{ borderBottom:'1px solid var(--border)' }}>
              <LifecycleCell>{row.title || row.filename || row.document_id}</LifecycleCell>
              <LifecycleCell mono>{row.document_kind || row.lifecycle_role || '—'}</LifecycleCell>
              <LifecycleCell mono>{row.processing_status || '—'}</LifecycleCell>
              <LifecycleCell mono>{row.has_extracted_text ? 'yes' : 'no'}</LifecycleCell>
            </tr>
          )}
        />
      </div>
    </div>
  );
}

function LifecyclePanel({ title, emptyTitle, emptySub, children }) {
  const hasChildren = React.Children.count(children) > 0;
  return (
    <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4, padding:'16px 18px' }}>
      <div style={{ fontSize:11, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:12 }}>{title}</div>
      {hasChildren ? children : <EmptyState title={emptyTitle} sub={emptySub} />}
    </div>
  );
}

function LifecycleTable({ title, emptyTitle, emptySub, columns, rows, renderRow, compact }) {
  return (
    <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4, overflow:'hidden', marginBottom:18 }}>
      <div style={{ padding:'13px 16px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', justifyContent:'space-between', gap:12 }}>
        <div style={{ fontSize:11, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)' }}>{title}</div>
        <div style={{ fontSize:10, color:'var(--ink-faint)', fontFamily:'var(--mono)' }}>{rows.length} rows</div>
      </div>
      {rows.length === 0 ? (
        <EmptyState title={emptyTitle} sub={emptySub} />
      ) : (
        <div style={{ overflowX:'auto' }}>
          <table style={{ width:'100%', borderCollapse:'collapse', minWidth: compact ? 520 : 900 }}>
            <thead>
              <tr style={{ background:'var(--surface-alt)' }}>
                {columns.map((h, i) => (
                  <th key={i} style={{
                    padding:'9px 12px', textAlign:i > 1 && !compact ? 'right' : 'left',
                    fontSize:10, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase',
                    color:'var(--ink-mute)', whiteSpace:'nowrap', fontFamily:'var(--mono)',
                    borderBottom:'1px solid var(--border-md)',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>{rows.map(renderRow)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function LifecycleCell({ children, mono, align }) {
  return (
    <td style={{
      padding:'10px 12px',
      fontSize:12,
      color:'var(--ink-soft)',
      lineHeight:1.45,
      verticalAlign:'top',
      textAlign: align || 'left',
      fontFamily: mono ? 'var(--mono)' : 'inherit',
      whiteSpace: align === 'right' ? 'nowrap' : 'normal',
    }}>{children}</td>
  );
}

function fmtLifecycleMoney(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '—';
  return new Intl.NumberFormat('en-US', { style:'currency', currency:'USD', maximumFractionDigits:0 }).format(num);
}

function fmtLifecycleNumber(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '—';
  return String(Math.round(num * 1000) / 1000);
}

function fmtLifecycleDate(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return fmtDateMil(value);
}

// ─── DOCUMENTS TAB ──────────────────────────────────────────────────────────
function DocumentsTab({ docs, contract, onUpload }) {
  const [typeFilter, setTypeFilter] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [viewing, setViewing] = useState(null);

  const pinnedDocs = docs.filter(d => d.pinned);
  const otherDocs = docs.filter(d => !d.pinned);

  const types = [...new Set(otherDocs.map(d => d.doc_type))];
  const sources = [...new Set(otherDocs.map(d => d.source))];

  const filtered = otherDocs.filter(d => {
    if (typeFilter !== 'all' && d.doc_type !== typeFilter) return false;
    if (sourceFilter !== 'all' && d.source !== sourceFilter) return false;
    return true;
  });

  return (
    <div>
      {pinnedDocs.length > 0 && (
        <div style={{ padding:'18px 24px 6px', background:'var(--surface)' }}>
          <div style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.14em', textTransform:'uppercase', fontFamily:'var(--mono)', marginBottom:10, display:'flex', alignItems:'center', gap:8 }}>
            <span style={{ fontSize:11 }}>📌</span> Pinned · contract document
          </div>
          {pinnedDocs.map(doc => {
            const meta = DOC_TYPE_META[doc.doc_type] || { abbr:'DOC', tone:'default' };
            return (
              <div key={doc.id} style={{
                background:'var(--surface)',
                border:'1px solid var(--ink)',
                borderLeft:'3px solid var(--ink)',
                borderRadius:3,
                padding:'14px 18px',
                display:'flex', alignItems:'center', gap:16,
                boxShadow:'var(--shadow-sm)',
              }}>
                <span style={{
                  fontSize:10, fontWeight:700, fontFamily:'var(--mono)',
                  color:'#fff', background:'var(--ink)', border:'1px solid var(--ink)',
                  padding:'4px 9px', borderRadius:2, letterSpacing:'0.10em', flexShrink:0,
                }}>{meta.abbr}</span>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontSize:14, fontWeight:600, color:'var(--ink)', lineHeight:1.3, marginBottom:3 }}>{doc.title}</div>
                  <div style={{ fontSize:11, color:'var(--ink-mute)', fontFamily:'var(--mono)', letterSpacing:'0.04em' }}>
                    {doc.filename} · {fmtBytes(doc.size_bytes)} · Awarded {fmtDateMil(doc.created_at)}
                  </div>
                </div>
                <BtnSecondary style={{ padding:'5px 12px', fontSize:12, marginRight:6 }} onClick={() => setViewing(doc)}>View</BtnSecondary>
                <BtnSecondary style={{ padding:'5px 12px', fontSize:12 }} onClick={() => downloadDocAsText(doc)}>Download</BtnSecondary>
              </div>
            );
          })}
        </div>
      )}

      <div style={{
        padding:'14px 24px', display:'flex', alignItems:'center', gap:14,
        borderBottom:'1px solid var(--border)', background:'var(--surface)',
        flexWrap:'wrap',
      }}>
        <div style={{ fontSize:13, fontWeight:600, color:'var(--ink)' }}>{filtered.length} of {otherDocs.length} documents</div>
        <div style={{ height:18, width:1, background:'var(--border)' }}/>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <span style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.12em', textTransform:'uppercase', fontFamily:'var(--mono)' }}>Type</span>
          <FilterPills options={[{id:'all', label:'All'}, ...types.map(t=>({id:t, label:t}))]} value={typeFilter} onChange={setTypeFilter}/>
        </div>
        <div style={{ height:18, width:1, background:'var(--border)' }}/>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <span style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.12em', textTransform:'uppercase', fontFamily:'var(--mono)' }}>Source</span>
          <FilterPills options={[{id:'all', label:'All'}, ...sources.map(s=>({id:s, label:s}))]} value={sourceFilter} onChange={setSourceFilter}/>
        </div>
        <div style={{ marginLeft:'auto', display:'flex', gap:8 }}>
          <BtnPrimary onClick={onUpload}>+ Upload</BtnPrimary>
        </div>
      </div>

      <table style={{ width:'100%', borderCollapse:'collapse' }}>
        <thead>
          <tr style={{ background:'var(--surface-alt)' }}>
            {['Type', 'Title', 'Period', 'Source', 'File', 'Filed', ''].map((h,i) => (
              <th key={i} style={{
                padding:'9px 16px', textAlign:'left',
                fontSize:10, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase',
                color:'var(--ink-mute)', whiteSpace:'nowrap', fontFamily:'var(--mono)',
                borderBottom:'1px solid var(--border-md)',
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filtered.map((doc) => {
            const meta = DOC_TYPE_META[doc.doc_type] || { abbr:'DOC', tone:'default' };
            const isImport = doc.source.startsWith('Imported');
            return (
              <tr key={doc.id} style={{ borderBottom:'1px solid var(--border)', background:'var(--surface)', transition:'background 0.1s' }}
                onMouseEnter={e => e.currentTarget.style.background='var(--surface-alt)'}
                onMouseLeave={e => e.currentTarget.style.background='var(--surface)'}
              >
                <td style={{ padding:'12px 16px', whiteSpace:'nowrap' }}>
                  <span style={{
                    fontSize:9.5, fontWeight:700, fontFamily:'var(--mono)',
                    color: meta.tone === 'ink' ? '#fff' : meta.tone === 'accent' ? '#fff' : 'var(--ink-mute)',
                    background: meta.tone === 'ink' ? 'var(--ink)' : meta.tone === 'accent' ? 'var(--accent)' : 'var(--surface-alt)',
                    border: '1px solid ' + (meta.tone === 'ink' ? 'var(--ink)' : meta.tone === 'accent' ? 'var(--accent)' : 'var(--border-md)'),
                    padding:'3px 7px', borderRadius:2, letterSpacing:'0.08em',
                  }}>{meta.abbr}</span>
                  <div style={{ fontSize:10, color:'var(--ink-faint)', marginTop:4, fontFamily:'var(--mono)' }}>{doc.doc_type}</div>
                </td>
                <td style={{ padding:'12px 16px', maxWidth:300 }}>
                  <div style={{ fontSize:13, fontWeight:500, color:'var(--ink)', lineHeight:1.3 }}>{doc.title}</div>
                  {doc.importRef && <div style={{ fontSize:10, color:'var(--accent)', marginTop:3, fontFamily:'var(--mono)' }}>↳ {doc.importRef}</div>}
                </td>
                <td style={{ padding:'12px 16px', fontSize:11, fontFamily:'var(--mono)', color:'var(--ink-soft)', whiteSpace:'nowrap' }}>{doc.period}</td>
                <td style={{ padding:'12px 16px', fontSize:11, color: isImport ? 'var(--accent)' : 'var(--ink-mute)', fontFamily:'var(--mono)', whiteSpace:'nowrap', letterSpacing:'0.04em' }}>{doc.source}</td>
                <td style={{ padding:'12px 16px' }}>
                  <div style={{ fontSize:11.5, color:'var(--ink-soft)', fontFamily:'var(--mono)' }}>{doc.filename}</div>
                  <div style={{ fontSize:10, color:'var(--ink-faint)', marginTop:2, fontFamily:'var(--mono)' }}>{fmtBytes(doc.size_bytes)}</div>
                </td>
                <td style={{ padding:'12px 16px', fontSize:11, color:'var(--ink-mute)', whiteSpace:'nowrap', fontFamily:'var(--mono)' }}>{fmtDateMil(doc.created_at)}</td>
                <td style={{ padding:'12px 16px', whiteSpace:'nowrap' }}>
                  <BtnSecondary style={{ padding:'4px 10px', fontSize:11, marginRight:6 }} onClick={() => setViewing(doc)}>View</BtnSecondary>
                  <BtnSecondary style={{ padding:'4px 10px', fontSize:11 }} onClick={() => downloadDocAsText(doc)}>Download</BtnSecondary>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {filtered.length === 0 && <EmptyState title="No documents match" sub="Try a different filter combination."/>}
      {viewing && <DocumentViewerModal doc={viewing} onClose={() => setViewing(null)} />}
    </div>
  );
}

// ─── CONTRACT INSIGHTS TAB — findings → patterns → similar contracts ────────
function ContractInsightsTab({ contract: c, findings, lifecycle, onSelectContract }) {
  const lifecycleIssues = (lifecycle?.issue_register || []).map(issue => ({
    id: `lifecycle-${issue.issue_id || issue.title}`,
    severity: issue.severity === 'high' ? 'critical' : issue.severity === 'low' ? 'healthy' : 'watch',
    claim: issue.title || issue.category || 'Lifecycle issue',
    observed: issue.summary || issue.description || 'No lifecycle summary is available.',
    sourceDoc: issue.source_document_id || issue.source || 'Lifecycle packet',
    similar: [],
  }));
  const rowsById = new Map();
  for (const row of [...findings, ...lifecycleIssues]) {
    rowsById.set(row.id, row);
  }
  const rows = [...rowsById.values()];
  return (
    <div style={{ padding:'24px 24px 48px' }}>
      <SectionHeader
        title="Findings on this contract"
        subtitle={`${rows.length} backend issue rows from regressions and lifecycle extraction`}
      />
      <div style={{ display:'grid', gap:14 }}>
        {rows.length === 0 && (
          <EmptyState title="No extracted findings" sub="Run document processing or upload reports with extractable performance issues; no demo findings are shown here." />
        )}
        {rows.map(f => {
          const sev = SEVERITY_META[f.severity];
          return (
            <div key={f.id} style={{
              background:'var(--surface)', border:'1px solid var(--border)',
              borderLeft:`3px solid ${sev.clr}`, borderRadius:3,
            }}>
              {/* Finding header */}
              <div style={{ padding:'18px 22px 14px' }}>
                <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
                  <span style={{
                    fontSize:9.5, fontWeight:700, letterSpacing:'0.10em', textTransform:'uppercase',
                    color:sev.clr, background:sev.bg, border:`1px solid ${sev.border}`,
                    padding:'2px 7px', borderRadius:2, fontFamily:'var(--mono)',
                  }}>{sev.label}</span>
                  <span style={{ fontSize:10, color:'var(--ink-faint)', fontFamily:'var(--mono)', letterSpacing:'0.06em' }}>
                    SOURCE → {f.sourceDoc}
                  </span>
                </div>
                <div style={{ fontSize:15, fontWeight:600, color:'var(--ink)', lineHeight:1.4, marginBottom:8 }}>{f.claim}</div>
                <div style={{ fontSize:12, color:'var(--ink-mute)', lineHeight:1.6 }}>
                  <strong style={{color:'var(--ink-soft)', fontWeight:600}}>Observed: </strong>{f.observed}
                </div>
              </div>

              {/* Pattern link */}
              {/* Similar contracts */}
              {f.similar && f.similar.length > 0 && (
                <div style={{ borderTop:'1px solid var(--border)', padding:'12px 22px 14px' }}>
                  <div style={{ fontSize:9.5, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:8 }}>Other contracts informing this analysis</div>
                  {f.similar.map((s, i) => {
                    return (
                      <div key={s.id} style={{
                        display:'grid', gridTemplateColumns:'160px 1fr 16px', gap:14, alignItems:'center',
                        padding:'8px 0',
                        borderBottom: i < f.similar.length-1 ? '1px solid var(--border)' : 'none',
                      }}>
                        <span style={{ fontFamily:'var(--mono)', fontSize:11.5, fontWeight:600, color:'var(--accent)' }}>{s.number || s.id}</span>
                        <div style={{ minWidth:0 }}>
                          <div style={{ fontSize:12.5, color:'var(--ink)', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{s.label}</div>
                          <div style={{ fontSize:11, color:'var(--ink-mute)', marginTop:1 }}>{s.detail}</div>
                        </div>
                        <IcoChevron/>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── INSIGHTS LIBRARY (cross-portfolio) ─────────────────────────────────────
function InsightsTab({ psc, naics, embedded, onSelectContract, customInsights = [], onUnpin }) {
  // Embedded mode (inside a contract page) seeds with that contract's specific code.
  const [pscSelection, setPscSelection] = useState(() => ({
    categories: new Set(),
    codes: embedded && psc ? new Set([psc]) : new Set(),
  }));
  const [toneFilter, setToneFilter] = useState('all');
  const [openInsight, setOpenInsight] = useState(null);
  const [flagged, setFlagged] = useState(() => loadFlaggedInsights());

  // Custom insights from the user are shown ahead of built-ins.
  const ALL_INSIGHTS = [...customInsights, ...INSIGHTS];
  const presentInsightPscs = new Set(ALL_INSIGHTS.map(i => i.psc));
  const pscOptions = PSC_CODES.map(p => ({
    id: p.code, label: p.code, desc: p.desc,
    disabled: !presentInsightPscs.has(p.code),
  }));
  for (const ins of ALL_INSIGHTS) {
    if (!pscOptions.some(o => o.id === ins.psc)) {
      pscOptions.push({ id:ins.psc, label:ins.psc, desc:'(insight code)', disabled:false });
    }
  }
  pscOptions.sort((a, b) => a.id.localeCompare(b.id));

  function toggleFlag(id) {
    setFlagged(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      saveFlaggedInsights(next);
      return next;
    });
  }

  const noPscFilter = pscSelection.categories.size === 0 && pscSelection.codes.size === 0;
  const filtered = ALL_INSIGHTS.filter(i => {
    if (!noPscFilter) {
      const matchesCategory = pscSelection.categories.has(i.psc[0]);
      const matchesCode = pscSelection.codes.has(i.psc);
      if (!matchesCategory && !matchesCode) return false;
    }
    if (toneFilter !== 'all' && i.tone !== toneFilter) return false;
    return true;
  });

  const toneMap = {
    flag: { border:'var(--flag)', bg:'var(--flag-soft)', text:'var(--flag)' },
    warn: { border:'var(--warn)', bg:'var(--warn-soft)', text:'var(--warn)' },
    good: { border:'var(--good)', bg:'var(--good-soft)', text:'var(--good)' },
  };

  return (
    <div style={{ padding: embedded ? '24px 24px 48px' : '0' }}>
      {!embedded && (
        <div style={{
          padding:'14px 24px', display:'flex', alignItems:'center', gap:14,
          borderBottom:'1px solid var(--border)', background:'var(--surface)',
          flexWrap:'wrap',
        }}>
          <div style={{ display:'flex', alignItems:'center', gap:8 }}>
            <span style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.12em', textTransform:'uppercase', fontFamily:'var(--mono)' }}>PSC</span>
            <PSCMultiSelect
              categories={pscSelection.categories}
              codes={pscSelection.codes}
              codeOptions={pscOptions}
              onChange={setPscSelection}
            />
          </div>
          <div style={{ height:18, width:1, background:'var(--border)' }}/>
          <div style={{ display:'flex', alignItems:'center', gap:8 }}>
            <span style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.12em', textTransform:'uppercase', fontFamily:'var(--mono)' }}>Lens</span>
            <FilterPills options={[
              {id:'all', label:'All'},
              {id:'flag', label:'Patterns'},
              {id:'warn', label:'Drift'},
              {id:'good', label:'Wins'},
            ]} value={toneFilter} onChange={setToneFilter}/>
          </div>
        </div>
      )}

      <div style={{ padding: embedded ? 0 : '20px 24px' }}>
        {embedded && (
          <SectionHeader
            title={`Insights for ${psc}-coded contracts`}
            subtitle={`${filtered.length} cross-portfolio findings · NAICS ${naics}`}
          />
        )}
        <div style={{ display:'grid', gap:10 }}>
          {filtered.map((ins) => {
            const t = toneMap[ins.tone];
            const isFlagged = flagged.has(ins.id);
            return (
              <div key={ins.id}
                onClick={() => setOpenInsight(ins)}
                style={{
                  background:'var(--surface)', border:'1px solid var(--border)',
                  borderLeft:`3px solid ${t.border}`,
                  borderRadius:3, padding:'18px 20px',
                  cursor:'pointer', transition:'background 0.1s, border-color 0.1s',
                }}
                onMouseEnter={e => e.currentTarget.style.background='var(--surface-alt)'}
                onMouseLeave={e => e.currentTarget.style.background='var(--surface)'}
              >
                <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10, flexWrap:'wrap' }}>
                  <span style={{
                    fontSize:9.5, fontWeight:700, letterSpacing:'0.10em', textTransform:'uppercase',
                    color:t.text, background:t.bg, border:`1px solid ${t.border}`,
                    padding:'2px 7px', borderRadius:2, fontFamily:'var(--mono)',
                  }}>{ins.lens}</span>
                  <Tag>{ins.psc}</Tag>
                  <Tag>NAICS {ins.naics}</Tag>
                  {ins.custom && <Tag tone="accent">⚑ Pinned by you</Tag>}
                  {isFlagged && <Tag tone="flag">⚑ Flagged</Tag>}
                  <span style={{ marginLeft:'auto', fontSize:10, color:'var(--ink-faint)', fontFamily:'var(--mono)', letterSpacing:'0.06em' }}>Observed in {ins.contracts} contracts</span>
                </div>
                <div style={{ fontSize:14.5, fontWeight:600, color:'var(--ink)', lineHeight:1.45, marginBottom:10 }}>{ins.claim}</div>
                <div style={{ fontSize:12, color:'var(--ink-mute)', lineHeight:1.6, marginBottom:8 }}>
                  <strong style={{color:'var(--ink-soft)', fontWeight:600}}>Why: </strong>{ins.why}
                </div>
                <div style={{
                  fontSize:12, color:'var(--ink-soft)', lineHeight:1.6,
                  background:'var(--surface-alt)', borderLeft:`2px solid ${t.border}`,
                  padding:'9px 12px',
                }}>
                  <strong style={{ fontWeight:600 }}>So what: </strong>{ins.so}
                </div>
              </div>
            );
          })}
        </div>
        {filtered.length === 0 && <EmptyState title="No insights match" sub="Adjust your filters to see related findings."/>}
      </div>
      {openInsight && (
        <InsightDetailModal
          insight={openInsight}
          onClose={() => setOpenInsight(null)}
          onSelectContract={onSelectContract}
          isFlagged={flagged.has(openInsight.id)}
          onToggleFlag={toggleFlag}
          onUnpin={onUnpin}
        />
      )}
    </div>
  );
}

function InsightsPage({ onSelectContract }) {
  const [portfolio, setPortfolio] = useState(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let cancelled = false;
    getPortfolioThemes('fy26')
      .then(data => { if (!cancelled) { setPortfolio(data); setError(false); } })
      .catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, []);
  const themes = portfolio?.themes || [];
  return (
    <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
      <TopBar crumbs={['Insights']} />
      <div style={{
        background:'var(--surface)', borderBottom:'1px solid var(--border)',
        padding:'18px 24px',
        display:'flex', alignItems:'flex-end', justifyContent:'space-between', gap:16,
      }}>
        <div>
          <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.18em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:6 }}>Cross-portfolio</div>
          <h1 style={{ fontSize:22, fontWeight:700, letterSpacing:'-0.02em', color:'var(--ink)' }}>Insights Library</h1>
          <p style={{ fontSize:12, color:'var(--ink-mute)', marginTop:4 }}>
            {themes.length} backend evidence themes · generated from processed findings, facts, signals, and hypotheses
          </p>
        </div>
      </div>
      <div style={{ flex:1, overflowY:'auto', background:'var(--bg)', padding:'20px 24px' }}>
        {!portfolio && !error && <Spinner label="Loading backend insights…" />}
        {themes.map(theme => <ThemeCard key={theme.id} theme={theme} onSelectContract={onSelectContract} />)}
        {portfolio && themes.length === 0 && (
          <EmptyState title="No backend insights yet" sub={(portfolio.limitations || [])[0] || 'Process contract documents to create evidence-backed themes.'} />
        )}
        {error && <EmptyState title="Insights unavailable" sub="Backend portfolio evidence could not be loaded." />}
      </div>
    </div>
  );
}

// ─── BENCHMARKS TAB (within contract) ───────────────────────────────────────
const BENCHMARK_AXIS_META = {
  cost_performance:    { label: 'Cost Issue Signals',           primaryKey: 'cost_signal_count',            lowerBetter: true },
  schedule_performance:{ label: 'Schedule Issue Signals',       primaryKey: 'schedule_signal_count',        lowerBetter: true },
  scope_stability:     { label: 'Scope / Mod Signals',          primaryKey: 'scope_or_mod_signal_count',    lowerBetter: true },
  execution_and_risk:  { label: 'Execution Risk Signals',       primaryKey: 'issue_signal_count',           lowerBetter: true },
  quality:             { label: 'Quality Issue Signals',         primaryKey: 'defect_or_rework_signal_count',lowerBetter: true },
  regulatory_compliance:{ label: 'Compliance Signals',          primaryKey: 'compliance_signal_count',      lowerBetter: true },
  forecasting_accuracy:{ label: 'EAC Drift (× BAC)',            primaryKey: 'eac_drift',                    lowerBetter: true },
};

function _benchmarkRows(analysis) {
  if (!analysis) return null;
  const rows = [];

  for (const axis of (analysis.axes || [])) {
    if (axis.status !== 'measured') continue;
    const meta = BENCHMARK_AXIS_META[axis.axis];
    if (!meta) continue;
    const rawValue = axis.target_value?.[meta.primaryKey];
    if (rawValue === null || rawValue === undefined) continue;
    const numValue = Number(rawValue);
    const peerP50 = axis.cohort_distribution?.p50;
    const percentile = axis.target_percentile;

    let tone;
    if (percentile !== null && percentile !== undefined) {
      tone = meta.lowerBetter
        ? (percentile < 35 ? 'good' : percentile < 75 ? 'warn' : 'flag')
        : (percentile > 65 ? 'good' : percentile > 25 ? 'warn' : 'flag');
    } else {
      tone = 'warn';
    }

    const peerDisplay = peerP50 !== null && peerP50 !== undefined ? _fmt1(peerP50) : '—';
    const delta = peerP50 !== null && peerP50 !== undefined ? numValue - peerP50 : null;
    const deltaDisplay = delta !== null ? (delta >= 0 ? '+' : '') + _fmt1(delta) : '—';
    const label = meta.label + (axis.low_confidence ? ' †' : '');

    rows.push({ metric: label, value: _fmt1(numValue), peer: peerDisplay, delta: deltaDisplay, tone });
  }

  for (const cr of (analysis.cpars_ratings || []).slice(0, 2)) {
    const label = `CPARS ${cr.label}${cr.period_label ? ' · ' + cr.period_label : ''}`;
    rows.push({ metric: label, value: cr.rating, peer: '—', delta: '—', tone: _cparsRatingTone(cr.rating) });
  }

  return rows.length > 0 ? rows : null;
}

function _fmt1(n) {
  if (!Number.isFinite(n)) return String(n);
  const rounded = Math.round(n * 10) / 10;
  return rounded === Math.round(rounded) ? String(Math.round(rounded)) : rounded.toFixed(1);
}

function _cparsRatingTone(rating) {
  const r = (rating || '').toLowerCase();
  if (['exceptional', 'very good'].includes(r)) return 'good';
  if (r === 'satisfactory') return 'warn';
  return 'flag';
}

function BenchmarksTab({ contract: c, analysis }) {
  const realRows = _benchmarkRows(analysis);
  const rows = realRows || [];
  const toneClr = { good:'var(--good)', warn:'var(--warn)', flag:'var(--flag)' };

  return (
    <div style={{ padding:'24px 24px 48px' }}>
      <SectionHeader
        title={`Benchmarks for ${c.psc} · ${c.component}`}
        subtitle="Measured only from extracted backend primitives and visible cohort evidence"
      />
      {!analysis && <Spinner label="Loading benchmark evidence…" />}
      {analysis && rows.length === 0 && <EmptyState title="No benchmark axes available" sub="Run contract analysis after extracting report primitives." />}
      {rows.length > 0 && (
      <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4, overflow:'hidden' }}>
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead>
            <tr style={{ background:'var(--surface-alt)' }}>
              {['Metric', 'This Contract', 'Peer Median', 'Δ vs. Peer', 'Visual'].map((h,i) => (
                <th key={i} style={{
                  padding:'10px 16px', textAlign:i===0?'left':i<4?'right':'left',
                  fontSize:10, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase',
                  color:'var(--ink-mute)', whiteSpace:'nowrap', fontFamily:'var(--mono)',
                  borderBottom:'1px solid var(--border-md)',
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const num = parseFloat(r.value);
              const peer = parseFloat(r.peer);
              const max = Math.max(num, peer) * 1.1 || 1;
              return (
                <tr key={i} style={{ borderBottom: i < rows.length-1 ? '1px solid var(--border)' : 'none' }}>
                  <td style={{ padding:'12px 16px', fontSize:13, color:'var(--ink)', fontWeight:500 }}>{r.metric}</td>
                  <td style={{ padding:'12px 16px', fontSize:13, fontFamily:'var(--mono)', fontWeight:600, color:'var(--ink)', textAlign:'right' }}>{r.value}</td>
                  <td style={{ padding:'12px 16px', fontSize:12, fontFamily:'var(--mono)', color:'var(--ink-mute)', textAlign:'right' }}>{r.peer}</td>
                  <td style={{ padding:'12px 16px', fontSize:12, fontFamily:'var(--mono)', fontWeight:600, color:toneClr[r.tone], textAlign:'right' }}>{r.delta}</td>
                  <td style={{ padding:'12px 16px', minWidth:160 }}>
                    {Number.isFinite(num) && Number.isFinite(peer) ? <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                      <div style={{ flex:1, height:8, background:'var(--surface-alt)', borderRadius:1, position:'relative', border:'1px solid var(--border)' }}>
                        <div style={{ position:'absolute', left:0, top:0, bottom:0, width:`${(num/max)*100}%`, background:toneClr[r.tone] }}/>
                        <div style={{ position:'absolute', left:`${(peer/max)*100}%`, top:-2, bottom:-2, width:1.5, background:'var(--ink)' }}/>
                      </div>
                    </div> : <span style={{ fontSize:11, color:'var(--ink-mute)' }}>{r.rationale}</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      )}
      {rows.some(r => r.metric.endsWith('†')) && (
        <div style={{ marginTop:8, fontSize:11, color:'var(--ink-faint)', fontFamily:'var(--mono)' }}>
          † Low confidence — fewer than 20 peer contracts in cohort.
        </div>
      )}
      <div style={{ marginTop:14, fontSize:11, color:'var(--ink-faint)', fontFamily:'var(--mono)', letterSpacing:'0.04em', display:'flex', gap:18 }}>
        <span><span style={{display:'inline-block', width:10, height:6, background:'var(--ink)', verticalAlign:'middle', marginRight:4}}/>Peer median</span>
        <span>{analysis?.limitations?.[0] || 'Cohort values come from visible backend contract records.'}</span>
      </div>
    </div>
  );
}

function summarizeAxisValue(value) {
  const entries = Object.entries(value || {});
  if (!entries.length) return 'measured';
  const [key, val] = entries[0];
  return `${key.replace(/_/g, ' ')}: ${String(val)}`;
}

// ─── DOCUMENTS PAGE (cross-contract) ────────────────────────────────────────
function DocumentsPage({ onSelectContract }) {
  const [backendGroups, setBackendGroups] = useState(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listContracts(), listAllDocuments()])
      .then(([contractRows, documentRows]) => {
        if (cancelled) return;
        const contracts = contractRows.map(normalizeContract);
        const byId = new Map(contracts.map(c => [c.id, { contract: c, docs: [] }]));
        for (const row of documentRows) {
          const contractId = row.contract_id || row.matched_contract_id || row.id;
          const group = byId.get(contractId);
          if (group) group.docs.push(normalizeDocument(row, group.contract));
        }
        setBackendGroups([...byId.values()].filter(g => g.docs.length > 0));
      })
      .catch(() => {
        if (!cancelled) setBackendGroups([]);
      });
    return () => { cancelled = true; };
  }, []);

  const docsByContract = backendGroups || [];
  const totalDocs = docsByContract.reduce((n, g) => n + g.docs.length, 0);

  const [typeFilter, setTypeFilter] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [viewing, setViewing] = useState(null);
  const [collapsed, setCollapsed] = useState(() => new Set());

  const allDocs = docsByContract.flatMap(g => g.docs);
  const types = [...new Set(allDocs.map(d => d.doc_type))];
  const sources = [...new Set(allDocs.map(d => d.source))];

  function passesFilter(d) {
    if (typeFilter !== 'all' && d.doc_type !== typeFilter) return false;
    if (sourceFilter !== 'all' && d.source !== sourceFilter) return false;
    return true;
  }

  function toggle(id) {
    setCollapsed(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  const visibleGroups = docsByContract
    .map(g => ({ ...g, filteredDocs: g.docs.filter(passesFilter) }))
    .filter(g => g.filteredDocs.length > 0);
  const visibleDocsTotal = visibleGroups.reduce((n, g) => n + g.filteredDocs.length, 0);

  return (
    <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
      <TopBar crumbs={['Documents']} />
      <div style={{ background:'var(--surface)', borderBottom:'1px solid var(--border)', padding:'18px 24px' }}>
        <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.18em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:6 }}>Portfolio</div>
        <h1 style={{ fontSize:22, fontWeight:700, letterSpacing:'-0.02em', color:'var(--ink)' }}>All Documents</h1>
        <p style={{ fontSize:12, color:'var(--ink-mute)', marginTop:4 }}>{totalDocs} documents across {docsByContract.length} contracts · grouped by contract</p>
      </div>

      <div style={{ padding:'12px 24px', display:'flex', alignItems:'center', gap:14, borderBottom:'1px solid var(--border)', background:'var(--surface)', flexWrap:'wrap' }}>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <span style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.12em', textTransform:'uppercase', fontFamily:'var(--mono)' }}>Type</span>
          <FilterPills options={[{id:'all', label:'All'}, ...types.map(t=>({id:t, label:t}))]} value={typeFilter} onChange={setTypeFilter}/>
        </div>
        <div style={{ height:18, width:1, background:'var(--border)' }}/>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <span style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.12em', textTransform:'uppercase', fontFamily:'var(--mono)' }}>Source</span>
          <FilterPills options={[{id:'all', label:'All'}, ...sources.map(s=>({id:s, label:s}))]} value={sourceFilter} onChange={setSourceFilter}/>
        </div>
        <div style={{ marginLeft:'auto', fontSize:11, color:'var(--ink-faint)', fontFamily:'var(--mono)', letterSpacing:'0.04em' }}>
          {visibleDocsTotal} of {totalDocs} matching
        </div>
      </div>

      <div style={{ flex:1, overflowY:'auto', background:'var(--bg)', padding:'18px 24px 32px' }}>
        {backendGroups === null && <Spinner label="Loading document records…" />}
        {backendGroups !== null && visibleGroups.length === 0 && (
          <EmptyState
            title={totalDocs === 0 ? "No backend documents available" : "No documents match"}
            sub={totalDocs === 0 ? "Upload or process documents to populate this view." : "Try a different filter combination."}
          />
        )}
        <div style={{ display:'grid', gap:14 }}>
          {visibleGroups.map(({ contract: c, filteredDocs }) => {
            const isCollapsed = collapsed.has(c.id);
            return (
              <div key={c.id} style={{
                background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4, overflow:'hidden',
              }}>
                <div style={{
                  padding:'14px 18px', display:'flex', alignItems:'center', gap:14,
                  borderBottom: isCollapsed ? 'none' : '1px solid var(--border)',
                  background:'var(--surface-alt)',
                }}>
                  <button
                    type="button"
                    onClick={() => toggle(c.id)}
                    style={{
                      background:'none', border:'none', cursor:'pointer', color:'var(--ink-mute)',
                      transform: isCollapsed ? 'rotate(0)' : 'rotate(90deg)',
                      transition:'transform 0.12s', display:'flex', alignItems:'center',
                    }}
                  ><IcoChevron dir="right" /></button>
                  <div style={{ flex:1, minWidth:0, cursor:'pointer' }} onClick={() => onSelectContract(c)}>
                    <div style={{ display:'flex', alignItems:'baseline', gap:10, flexWrap:'wrap' }}>
                      <span style={{ fontFamily:'var(--mono)', fontSize:13, fontWeight:700, color:'var(--accent)' }}>{c.number}</span>
                      <span style={{ fontSize:13, fontWeight:600, color:'var(--ink)' }}>{c.title}</span>
                    </div>
                    <div style={{ fontSize:11, color:'var(--ink-mute)', marginTop:3, fontFamily:'var(--mono)', letterSpacing:'0.04em' }}>
                      {c.psc} · {c.component} · CO {c.co}
                    </div>
                  </div>
                  <div style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', fontFamily:'var(--mono)', letterSpacing:'0.10em', textTransform:'uppercase', whiteSpace:'nowrap' }}>
                    {filteredDocs.length} {filteredDocs.length === 1 ? 'doc' : 'docs'}
                  </div>
                </div>

                {!isCollapsed && (
                  <table style={{ width:'100%', borderCollapse:'collapse' }}>
                    <thead>
                      <tr style={{ background:'var(--surface)' }}>
                        {['Type', 'Title', 'Source', 'Filed', ''].map((h, i) => (
                          <th key={i} style={{
                            padding:'8px 16px', textAlign:'left',
                            fontSize:9.5, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase',
                            color:'var(--ink-faint)', whiteSpace:'nowrap', fontFamily:'var(--mono)',
                            borderBottom:'1px solid var(--border)',
                          }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filteredDocs.map((doc, i) => {
                        const meta = DOC_TYPE_META[doc.doc_type] || { abbr:'DOC', tone:'default' };
                        return (
                          <tr key={doc.id} style={{
                            borderBottom: i < filteredDocs.length - 1 ? '1px solid var(--border)' : 'none',
                            background:'var(--surface)',
                          }}>
                            <td style={{ padding:'11px 16px', whiteSpace:'nowrap' }}>
                              <span style={{
                                fontSize:9.5, fontWeight:700, fontFamily:'var(--mono)',
                                color: meta.tone === 'ink' ? '#fff' : meta.tone === 'accent' ? '#fff' : 'var(--ink-mute)',
                                background: meta.tone === 'ink' ? 'var(--ink)' : meta.tone === 'accent' ? 'var(--accent)' : 'var(--surface-alt)',
                                border: '1px solid ' + (meta.tone === 'ink' ? 'var(--ink)' : meta.tone === 'accent' ? 'var(--accent)' : 'var(--border-md)'),
                                padding:'3px 7px', borderRadius:2, letterSpacing:'0.08em',
                              }}>{meta.abbr}</span>
                            </td>
                            <td style={{ padding:'11px 16px' }}>
                              <div style={{ fontSize:13, color:'var(--ink)' }}>{doc.title}</div>
                              <div style={{ fontSize:10, color:'var(--ink-faint)', marginTop:2, fontFamily:'var(--mono)' }}>{doc.doc_type}</div>
                            </td>
                            <td style={{ padding:'11px 16px', fontSize:11, color:doc.source.startsWith('Imported')?'var(--accent)':'var(--ink-mute)', fontFamily:'var(--mono)', whiteSpace:'nowrap', letterSpacing:'0.04em' }}>{doc.source}</td>
                            <td style={{ padding:'11px 16px', fontSize:11, color:'var(--ink-mute)', fontFamily:'var(--mono)', whiteSpace:'nowrap' }}>{fmtDateMil(doc.created_at)}</td>
                            <td style={{ padding:'11px 16px', whiteSpace:'nowrap', textAlign:'right' }}>
                              <BtnSecondary style={{ padding:'4px 10px', fontSize:11, marginRight:6 }} onClick={() => setViewing(doc)}>View</BtnSecondary>
                              <BtnSecondary style={{ padding:'4px 10px', fontSize:11 }} onClick={() => downloadDocAsText(doc)}>Download</BtnSecondary>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            );
          })}
        </div>
      </div>
      {viewing && <DocumentViewerModal doc={viewing} onClose={() => setViewing(null)} />}
    </div>
  );
}

// ─── DOCUMENT VIEWER ────────────────────────────────────────────────────────
async function downloadDocAsText(doc) {
  let blob;
  let filename = doc.filename || `${doc.id}.txt`;
  try {
    blob = await downloadDocumentBlob(doc.id);
  } catch {
    const content = `${doc.title}\n${'-'.repeat(64)}\n\nThe original file could not be downloaded from backend storage.\n`;
    blob = new Blob([content], { type: 'text/plain' });
    filename = filename.replace(/\.(pdf|docx?|xlsx?|xml)$/i, '.txt');
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function DocumentViewerModal({ doc, onClose }) {
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState(false);
  useEffect(() => {
    if (!doc?.id) return undefined;
    let cancelled = false;
    getDocument(doc.id)
      .then(row => { if (!cancelled) { setDetail(row); setDetailError(false); } })
      .catch(() => { if (!cancelled) setDetailError(true); });
    return () => { cancelled = true; };
  }, [doc?.id]);
  if (!doc) return null;
  const meta = DOC_TYPE_META[doc.doc_type] || { abbr:'DOC', tone:'default' };
  const pageText = detail?.pages?.map(p => p.text).filter(Boolean).join('\n\n');
  const preview = pageText || (detailError ? 'Extracted text is not available for this document.' : 'Loading extracted text…');
  return (
    <div onClick={onClose} style={{
      position:'fixed', inset:0, background:'rgba(10,25,41,0.55)',
      display:'flex', alignItems:'center', justifyContent:'center', zIndex:50,
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background:'var(--surface)', borderRadius:4, width:880, maxWidth:'94vw',
        height:'82vh', display:'flex', flexDirection:'column',
        boxShadow:'var(--shadow)', border:'1px solid var(--border-md)',
      }}>
        <div style={{ padding:'16px 22px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', justifyContent:'space-between', gap:14 }}>
          <div style={{ display:'flex', alignItems:'center', gap:12, minWidth:0 }}>
            <span style={{
              fontSize:10, fontWeight:700, fontFamily:'var(--mono)',
              color: meta.tone === 'ink' ? '#fff' : meta.tone === 'accent' ? '#fff' : 'var(--ink-mute)',
              background: meta.tone === 'ink' ? 'var(--ink)' : meta.tone === 'accent' ? 'var(--accent)' : 'var(--surface-alt)',
              border: '1px solid ' + (meta.tone === 'ink' ? 'var(--ink)' : meta.tone === 'accent' ? 'var(--accent)' : 'var(--border-md)'),
              padding:'3px 8px', borderRadius:2, letterSpacing:'0.08em', flexShrink:0,
            }}>{meta.abbr}</span>
            <div style={{ minWidth:0 }}>
              <div style={{ fontSize:14, fontWeight:600, color:'var(--ink)', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{doc.title}</div>
              <div style={{ fontSize:11, color:'var(--ink-mute)', fontFamily:'var(--mono)', marginTop:2 }}>{doc.filename} · {fmtBytes(doc.size_bytes)} · {fmtDateMil(doc.created_at)}</div>
            </div>
          </div>
          <button type="button" onClick={onClose} style={{ background:'none', border:'none', color:'var(--ink-mute)', cursor:'pointer' }}><IcoClose/></button>
        </div>

        <div style={{ flex:1, display:'grid', gridTemplateColumns:'1fr 220px', minHeight:0 }}>
          <div style={{ overflowY:'auto', background:'#fafafa', padding:'24px 32px' }}>
            <div style={{
              background:'#fff', border:'1px solid var(--border-md)', borderRadius:3,
              padding:'32px 36px', maxWidth:680, margin:'0 auto',
              fontFamily:'var(--mono)', fontSize:12, lineHeight:1.65,
              color:'var(--ink)', whiteSpace:'pre-wrap',
              boxShadow:'var(--shadow-sm)', minHeight:'100%',
            }}>{preview}</div>
          </div>
          <div style={{ borderLeft:'1px solid var(--border)', background:'var(--surface-alt)', padding:'18px 18px', overflowY:'auto' }}>
            <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:10 }}>Details</div>
            {[
              ['Type', doc.doc_type],
              ['Period', doc.period || '—'],
              ['Source', doc.source],
              ['Uploader', doc.uploader],
              ['Filed', fmtDateMil(doc.created_at)],
              ['Size', fmtBytes(doc.size_bytes)],
              ['File', doc.filename],
              doc.importRef && ['Import ref', doc.importRef],
            ].filter(Boolean).map(([k, v]) => (
              <div key={k} style={{ marginBottom:10 }}>
                <div style={{ fontSize:9, fontWeight:700, color:'var(--ink-faint)', letterSpacing:'0.10em', textTransform:'uppercase', fontFamily:'var(--mono)', marginBottom:3 }}>{k}</div>
                <div style={{ fontSize:11.5, color:'var(--ink)', wordBreak:'break-word', fontFamily: k === 'File' || k === 'Filed' || k === 'Size' ? 'var(--mono)' : 'inherit' }}>{v}</div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ padding:'12px 22px', borderTop:'1px solid var(--border)', display:'flex', justifyContent:'flex-end', gap:10 }}>
          <BtnSecondary onClick={onClose}>Close</BtnSecondary>
          <BtnPrimary onClick={() => downloadDocAsText(doc)}>Download</BtnPrimary>
        </div>
      </div>
    </div>
  );
}

// ─── UPLOAD MODAL ───────────────────────────────────────────────────────────
function UploadModal({ contract, onClose, onUploaded, presetTitle = '', presetType = '' }) {
  const [title, setTitle] = useState(presetTitle);
  const [docType, setDocType] = useState(presetType);
  const [notes, setNotes] = useState('');
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const fileRef = useRef();

  async function handleSubmit(e) {
    e.preventDefault();
    if (!title || !docType || !file) return;
    setLoading(true);
    try {
      const uploaded = await uploadDocument({
        contractId: contract?.id,
        title,
        documentType: docType,
        notes,
        file,
      });
      onUploaded(normalizeDocument(uploaded, contract));
    } finally {
      setLoading(false);
    }
  }

  const fieldSt = { display:'grid', gap:6, marginBottom:16 };
  const labelSt = { fontSize:10, fontWeight:700, color:'var(--ink-soft)', letterSpacing:'0.12em', textTransform:'uppercase', fontFamily:'var(--mono)' };
  const inputSt = { width:'100%', border:'1px solid var(--border-md)', borderRadius:3, padding:'9px 12px', background:'var(--surface)', color:'var(--ink)', fontSize:13, outline:'none' };
  const DOC_TYPES = ['Weekly Status', 'Modification', 'Invoice', 'Deliverable', 'Tech Report', 'Memo'];

  return (
    <div onClick={onClose} style={{
      position:'fixed', inset:0, background:'rgba(10,25,41,0.55)',
      display:'flex', alignItems:'center', justifyContent:'center', zIndex:50,
    }}>
      <form onClick={e => e.stopPropagation()} onSubmit={handleSubmit} style={{
        background:'var(--surface)', borderRadius:4, width:520, maxWidth:'92vw',
        boxShadow:'var(--shadow)', border:'1px solid var(--border-md)',
      }}>
        <div style={{ padding:'18px 22px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
          <div>
            <div style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.14em', textTransform:'uppercase', fontFamily:'var(--mono)' }}>Upload Document</div>
            <div style={{ fontSize:14, fontWeight:600, color:'var(--ink)', marginTop:2, fontFamily:'var(--mono)' }}>{contract.number}</div>
          </div>
          <button type="button" onClick={onClose} style={{ background:'none', border:'none', color:'var(--ink-mute)' }}><IcoClose/></button>
        </div>

        <div style={{ padding:'22px' }}>
          <div
            onClick={() => fileRef.current?.click()}
            onDragOver={e => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={e => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) setFile(f); }}
            style={{
              border: `1.5px dashed ${dragging ? 'var(--accent)' : 'var(--border-md)'}`,
              borderRadius:3, padding:'24px 18px', textAlign:'center', cursor:'pointer',
              background: dragging ? 'var(--accent-soft)' : 'var(--surface-alt)',
              marginBottom:18,
            }}
          >
            <input ref={fileRef} type="file" style={{ display:'none' }} onChange={e => e.target.files[0] && setFile(e.target.files[0])}/>
            <div style={{ marginBottom:8, color:'var(--ink-faint)' }}><IcoUpload/></div>
            {file ? (
              <>
                <div style={{ fontSize:13, fontWeight:600, color:'var(--ink)' }}>{file.name}</div>
                <div style={{ fontSize:11, color:'var(--ink-mute)', marginTop:3, fontFamily:'var(--mono)' }}>{fmtBytes(file.size)} · click to change</div>
              </>
            ) : (
              <>
                <div style={{ fontSize:13, fontWeight:600, color:'var(--ink)' }}>Drop file here or click to browse</div>
                <div style={{ fontSize:11, color:'var(--ink-mute)', marginTop:3, fontFamily:'var(--mono)' }}>PDF · DOCX · XLSX · XML · max 50 MB</div>
              </>
            )}
          </div>

          <div style={fieldSt}>
            <label style={labelSt}>Title *</label>
            <input style={inputSt} value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Weekly Status Report — WK-15" required/>
          </div>

          <div style={fieldSt}>
            <label style={labelSt}>Document Type *</label>
            <select style={{ ...inputSt, appearance:'none',
              backgroundImage:`url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%234D5A72' stroke-width='1.4' fill='none' stroke-linecap='round'/%3E%3C/svg%3E")`,
              backgroundRepeat:'no-repeat', backgroundPosition:'right 12px center', paddingRight:32,
            }} value={docType} onChange={e => setDocType(e.target.value)} required>
              <option value="">Select type…</option>
              {DOC_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <div style={fieldSt}>
            <label style={labelSt}>Period / Notes</label>
            <input style={inputSt} value={notes} onChange={e => setNotes(e.target.value)} placeholder="e.g. WK 15 FY26"/>
          </div>
        </div>

        <div style={{ padding:'14px 22px', borderTop:'1px solid var(--border)', display:'flex', gap:10, justifyContent:'flex-end' }}>
          <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          <BtnPrimary type="submit" disabled={loading}>{loading ? 'Uploading…' : 'Upload Document'}</BtnPrimary>
        </div>
      </form>
    </div>
  );
}

// ─── CONTRACTOR VIEW ────────────────────────────────────────────────────────
// Limited workspace: only contracts they're on, focused on uploading
// extracted deliverables (especially weekly performance reports).

// Map a logged-in contractor's email to their contracts.
function contractsForContractor(user) {
  const map = {
    'daniel.kim@atlanticlogistics.com': ['c1'],
  };
  const ids = map[user?.email] || ['c1']; // demo fallback
  return MOCK_CONTRACTS.filter(c => ids.includes(c.id));
}

// Helpers shared by contractor pages
function deliverableStatus(item) {
  const today = Date.now();
  const due = new Date(item.due).getTime();
  if (item.filed) return item.late ? 'filed-late' : 'filed';
  if (due < today) return 'overdue';
  if (due < today + 7 * 24 * 60 * 60 * 1000) return 'due-soon';
  return 'upcoming';
}
const STATUS_META = {
  'filed':       { label:'Filed',       color:'var(--good)', bg:'var(--good-soft)', border:'var(--good-mid)' },
  'filed-late':  { label:'Filed (late)',color:'var(--warn)', bg:'var(--warn-soft)', border:'var(--warn-mid)' },
  'overdue':     { label:'Overdue',     color:'var(--flag)', bg:'var(--flag-soft)', border:'var(--flag-mid)' },
  'due-soon':    { label:'Due soon',    color:'var(--warn)', bg:'var(--warn-soft)', border:'var(--warn-mid)' },
  'upcoming':    { label:'Upcoming',    color:'var(--ink-mute)', bg:'var(--surface-alt)', border:'var(--border-md)' },
};

function ContractorHome({ user, onSelectContract }) {
  const [backendContracts, setBackendContracts] = useState(null);
  useEffect(() => {
    let cancelled = false;
    listContracts()
      .then(rows => {
        if (!cancelled) setBackendContracts(rows.map(normalizeContract));
      })
      .catch(() => {
        if (!cancelled) setBackendContracts([]);
      });
    return () => { cancelled = true; };
  }, []);
  const myContracts = backendContracts || [];
  const today = new Date().toLocaleDateString('en-US', { weekday:'long', month:'long', day:'numeric', year:'numeric' });
  const firstName = (user?.name || 'Contractor').split(' ')[0];
  const [uploadTarget, setUploadTarget] = useState(null);

  return (
    <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
      <TopBar crumbs={['Workspace']} />
      <div style={{ flex:1, overflowY:'auto', padding:'24px 32px 48px' }}>

        {/* Masthead */}
        <div style={{
          display:'flex', alignItems:'flex-end', justifyContent:'space-between',
          paddingBottom:14, marginBottom:22, borderBottom:'1px solid var(--border-md)',
        }}>
          <div>
            <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.18em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:6 }}>{today}</div>
            <h1 style={{ fontSize:24, fontWeight:700, letterSpacing:'-0.02em', color:'var(--ink)' }}>{firstName} — your workspace</h1>
            <p style={{ fontSize:13, color:'var(--ink-mute)', marginTop:4 }}>Submit deliverables for your active contracts.</p>
          </div>
          <div style={{ textAlign:'right' }}>
            <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-faint)', fontFamily:'var(--mono)' }}>Active Contracts</div>
            <div style={{ fontSize:22, fontWeight:700, color:'var(--ink)', marginTop:2, fontFamily:'var(--mono)' }}>{myContracts.length}</div>
          </div>
        </div>

        {/* My contracts */}
        <div style={{ fontSize:11, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:10 }}>My contracts</div>
        <div style={{ display:'grid', gap:14 }}>
          {backendContracts === null && <Spinner label="Loading your contracts…" />}
          {backendContracts !== null && myContracts.length === 0 && (
            <EmptyState title="No visible contract records" sub="Your account does not currently have access to any contract records." />
          )}
          {myContracts.map(c => {
            return (
              <div key={c.id} style={{
                background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4,
              }}>
                {/* Card header — clickable to drill in */}
                <div onClick={() => onSelectContract(c)} style={{
                  padding:'16px 22px', cursor:'pointer',
                  display:'grid', gridTemplateColumns:'1fr auto auto auto auto', gap:24, alignItems:'center',
                  borderBottom:'1px solid var(--border)',
                }}
                  onMouseEnter={e => e.currentTarget.style.background='var(--surface-alt)'}
                  onMouseLeave={e => e.currentTarget.style.background='transparent'}
                >
                  <div>
                    <div style={{ fontFamily:'var(--mono)', fontSize:11.5, fontWeight:600, color:'var(--accent)', marginBottom:4 }}>{c.number}</div>
                    <div style={{ fontSize:14, fontWeight:600, color:'var(--ink)' }}>{c.title}</div>
                    <div style={{ fontSize:11, color:'var(--ink-mute)', marginTop:3, fontFamily:'var(--mono)' }}>{c.period} · CO {c.co}</div>
                  </div>
                  <KpiMini label="Docs"    value={c.docsCount || 0} />
                  <KpiMini label="Elapsed" value={`${c.elapsed}%`} />
                  <BtnPrimary
                    style={{ padding:'5px 12px', fontSize:11.5, justifySelf:'end' }}
                    onClick={(e) => { e.stopPropagation(); setUploadTarget({ contract: c }); }}
                  >Upload</BtnPrimary>
                  <IcoChevron/>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {uploadTarget && (
        <UploadModal
          contract={uploadTarget.contract}
          onClose={() => setUploadTarget(null)}
          onUploaded={() => setUploadTarget(null)}
        />
      )}
    </div>
  );
}

function KpiMini({ label, value, flag }) {
  return (
    <div style={{ textAlign:'right', minWidth:70 }}>
      <div style={{ fontSize:9.5, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase', color:'var(--ink-faint)', fontFamily:'var(--mono)', marginBottom:4 }}>{label}</div>
      <div style={{ fontSize:18, fontWeight:700, color: flag ? 'var(--flag)' : 'var(--ink)', fontFamily:'var(--mono)', lineHeight:1 }}>{value}</div>
    </div>
  );
}

// ─── CONTRACTOR CONTRACT DETAIL ─────────────────────────────────────────────
function _normalizeDeliverableGroups(rows) {
  const groups = new Map();
  for (const row of rows) {
    const key = `${row.cdrl_item || ''}__${row.deliverable_name || ''}`;
    if (!groups.has(key)) {
      groups.set(key, {
        id: key,
        cdrl: row.cdrl_item || '—',
        title: row.deliverable_name || 'Deliverable',
        kind: 'recurring',
        cadence: '—',
        recipient: '—',
        items: [],
      });
    }
    const g = groups.get(key);
    const filed = !!(row.actual_delivery_date || row.status === 'on_time' || row.status === 'late');
    g.items.push({
      id: row.id,
      due: row.planned_due_date ? new Date(row.planned_due_date) : null,
      filed,
      late: filed && row.days_late > 0,
      title: row.period_label || row.planned_due_date || 'Period',
    });
  }
  return [...groups.values()];
}

// Two columns: contract particulars (left) + deliverables-as-upload-targets (right)
function ContractorContractPage({ contract, user, onBack }) {
  const c = contract;
  const [docs, setDocs] = useState([]);
  const [deliverables, setDeliverables] = useState(null);
  const [uploadTarget, setUploadTarget] = useState(null);
  const [freeUpload, setFreeUpload] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setDocs([]);
    setDeliverables(null);
    listContractDocuments(c.id)
      .then(rows => {
        if (!cancelled) setDocs(rows.map(row => normalizeDocument(row, c)));
      })
      .catch(() => { if (!cancelled) setDocs([]); });
    getContractDeliverables(c.id)
      .then(row => { if (!cancelled) setDeliverables(row); })
      .catch(() => { if (!cancelled) setDeliverables({ availability:'error', groups:[], limitations:['Deliverable evidence could not be loaded.'] }); });
    return () => { cancelled = true; };
  }, [c.id]);

  function handleFiled(groupId, itemId, doc) {
    setDocs(prev => [doc, ...prev]);
    setUploadTarget(null);
  }

  function handleFreeUploaded(doc) {
    setDocs(prev => [doc, ...prev]);
    setFreeUpload(false);
  }

  return (
    <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
      <TopBar crumbs={[{ label:'Workspace', onClick: onBack }, { label: c.number }]} />

      {/* Sub-header */}
      <div style={{ background:'var(--surface)', borderBottom:'1px solid var(--border)', padding:'18px 24px' }}>
        <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', gap:16 }}>
          <div style={{ minWidth:0 }}>
            <div style={{ display:'flex', alignItems:'center', gap:10, flexWrap:'wrap', marginBottom:6 }}>
              <span style={{ fontFamily:'var(--mono)', fontSize:18, fontWeight:700, color:'var(--ink)' }}>{c.number}</span>
              <Tag>{c.psc}</Tag>
              <Tag>{c.component}</Tag>
            </div>
            <div style={{ fontSize:14, fontWeight:600, color:'var(--ink-soft)', marginBottom:4 }}>{c.title}</div>
            <div style={{ fontSize:11.5, color:'var(--ink-mute)', fontFamily:'var(--mono)' }}>{c.period} · {c.elapsed}% elapsed · CO {c.co}</div>
          </div>
          <div style={{ flexShrink:0 }}>
            <BtnPrimary onClick={() => setFreeUpload(true)}>+ Upload Document</BtnPrimary>
          </div>
        </div>
      </div>

      {/* Body */}
      <div style={{ flex:1, overflowY:'auto', padding:'24px 24px 48px' }}>
        <div style={{ display:'grid', gridTemplateColumns:'320px 1fr', gap:20 }}>
          {/* Left: contract details */}
          <div>
            <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4, padding:'18px 20px', marginBottom:16 }}>
              <div style={{ fontSize:11, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', marginBottom:12, fontFamily:'var(--mono)' }}>Contract Details</div>
              {[
                ['Number',  c.number, true],
                ['Period',  c.period, true],
                ['Value',   c.value, true],
                ['CO',      c.co, false],
                ['COR',     'LT M. Reyes', false],
              ].map(([k, v, mono]) => (
                <div key={k} style={{ display:'flex', justifyContent:'space-between', gap:14, padding:'7px 0', borderBottom:'1px solid var(--border)' }}>
                  <span style={{ fontSize:10.5, color:'var(--ink-mute)', whiteSpace:'nowrap', fontFamily:'var(--mono)', letterSpacing:'0.04em', textTransform:'uppercase' }}>{k}</span>
                  <span style={{ fontSize:12, fontWeight:600, color:'var(--ink)', textAlign:'right', fontFamily: mono ? 'var(--mono)' : 'inherit' }}>{v}</span>
                </div>
              ))}
            </div>

            <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4, padding:'18px 20px' }}>
              <div style={{ fontSize:11, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', marginBottom:12, fontFamily:'var(--mono)' }}>Recent Filings</div>
              {docs.slice(0,5).map((d, i) => (
                <div key={d.id} style={{
                  fontSize:11.5, padding:'7px 0',
                  borderBottom: i < 4 ? '1px solid var(--border)' : 'none',
                }}>
                  <div style={{ color:'var(--ink)', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{d.title}</div>
                  <div style={{ fontSize:10, color:'var(--ink-faint)', fontFamily:'var(--mono)', marginTop:2, letterSpacing:'0.04em' }}>{fmtDateMil(d.created_at)} · {d.source}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Right: deliverables */}
          <div>
            <div style={{ marginBottom:6, display:'flex', alignItems:'center', justifyContent:'space-between' }}>
              <div>
                <div style={{ fontSize:14, fontWeight:700, color:'var(--ink)' }}>Deliverables Schedule</div>
                <div style={{ fontSize:11, color:'var(--ink-mute)', marginTop:2 }}>Extracted from your CDRL — click any open item to upload.</div>
              </div>
              <div style={{ fontSize:10, fontFamily:'var(--mono)', color:'var(--ink-faint)', letterSpacing:'0.06em' }}>
                CDRL · DD-1423
              </div>
            </div>

            <div style={{ marginTop:14, display:'grid', gap:14 }}>
              {deliverables === null && <Spinner label="Loading deliverable evidence…" />}
              {deliverables?.availability === 'available' && normalizeBackendDeliverables(deliverables).map(group => (
                <DeliverableGroupCard
                  key={group.id}
                  group={group}
                  onClickItem={(it) => !it.filed && setUploadTarget({ group, item: it })}
                />
              ))}
              {deliverables && deliverables.availability !== 'available' && (
                <EmptyState title="No deliverable schedule available" sub={(deliverables.limitations || [])[0] || availabilityLabel(deliverables.availability)} />
              )}
            </div>
          </div>
        </div>
      </div>

      {uploadTarget && (
        <UploadModal
          contract={c}
          presetTitle={`${uploadTarget.group.title} — ${uploadTarget.item.title}`}
          presetType={uploadTarget.group.title}
          onClose={() => setUploadTarget(null)}
          onUploaded={(d) => handleFiled(uploadTarget.group.id, uploadTarget.item.id, d)}
        />
      )}
      {freeUpload && (
        <UploadModal
          contract={c}
          onClose={() => setFreeUpload(false)}
          onUploaded={handleFreeUploaded}
        />
      )}
    </div>
  );
}

function DeliverableGroupCard({ group, onClickItem }) {
  const [expanded, setExpanded] = useState(group.kind === 'recurring');
  const items = group.items;
  const filedCount = items.filter(i => i.filed).length;
  const overdue = items.filter(i => !i.filed && new Date(i.due).getTime() < Date.now()).length;
  const next = items.find(i => !i.filed);
  const isImported = group.source === 'imported';

  // Show only items in a window around 'today' for recurring; show all milestones
  const today = Date.now();
  const window = 6;
  let visible = items;
  if (group.kind === 'recurring' && expanded) {
    const idx = items.findIndex(i => new Date(i.due).getTime() >= today);
    const start = Math.max(0, (idx === -1 ? items.length : idx) - window);
    const end = Math.min(items.length, (idx === -1 ? items.length : idx) + window);
    visible = items.slice(start, end);
  }

  return (
    <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4 }}>
      <div onClick={() => setExpanded(e => !e)} style={{
        padding:'14px 20px', cursor:'pointer',
        display:'grid', gridTemplateColumns:'1fr auto auto auto auto', gap:18, alignItems:'center',
      }}>
        <div>
          <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:4 }}>
            {group.cdrl !== '—' && <span style={{ fontSize:9.5, fontWeight:700, fontFamily:'var(--mono)', color:'var(--accent)', letterSpacing:'0.06em' }}>CDRL {group.cdrl}</span>}
            <span style={{ fontSize:13.5, fontWeight:600, color:'var(--ink)' }}>{group.title}</span>
            {isImported && <Tag tone="accent">Imported</Tag>}
          </div>
          <div style={{ fontSize:11, color:'var(--ink-mute)', fontFamily:'var(--mono)', letterSpacing:'0.04em' }}>{group.cadence} · {group.recipient}</div>
        </div>
        <KpiMini label="Filed" value={`${filedCount}/${items.length}`} />
        <KpiMini label="Overdue" value={overdue} flag={overdue > 0} />
        {next && !isImported ? (
          <BtnPrimary onClick={(e) => { e.stopPropagation(); onClickItem(next); }} style={{ padding:'6px 12px', fontSize:12 }}>
            Upload {next.title}
          </BtnPrimary>
        ) : isImported ? (
          <span style={{ fontSize:10.5, color:'var(--ink-mute)', fontFamily:'var(--mono)', letterSpacing:'0.04em' }}>Auto-imported</span>
        ) : (
          <span style={{ fontSize:11, color:'var(--good)', fontFamily:'var(--mono)' }}>✓ Complete</span>
        )}
        <div style={{ color:'var(--ink-mute)', transform: expanded ? 'rotate(90deg)' : 'none', transition:'transform 0.15s' }}>
          <IcoChevron dir="right"/>
        </div>
      </div>

      {expanded && (
        <div style={{ borderTop:'1px solid var(--border)', background:'var(--surface-alt)', padding:'10px 20px 14px' }}>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(180px, 1fr))', gap:8 }}>
            {visible.map(item => {
              const status = deliverableStatus(item);
              const meta = STATUS_META[status];
              const clickable = !item.filed && !isImported;
              return (
                <div key={item.id}
                  onClick={() => clickable && onClickItem(item)}
                  style={{
                    background:'var(--surface)', border:`1px solid ${meta.border}`,
                    borderRadius:3, padding:'8px 10px',
                    cursor: clickable ? 'pointer' : 'default',
                    transition:'border-color 0.12s',
                  }}
                  onMouseEnter={e => clickable && (e.currentTarget.style.borderColor='var(--ink)')}
                  onMouseLeave={e => clickable && (e.currentTarget.style.borderColor=meta.border)}
                >
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', gap:6 }}>
                    <span style={{ fontSize:11.5, fontWeight:600, color:'var(--ink)', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{item.title}</span>
                    <span style={{ fontSize:8.5, fontWeight:700, letterSpacing:'0.10em', textTransform:'uppercase', color:meta.color, fontFamily:'var(--mono)', whiteSpace:'nowrap' }}>{meta.label}</span>
                  </div>
                  <div style={{ fontSize:10, color:'var(--ink-faint)', marginTop:3, fontFamily:'var(--mono)', letterSpacing:'0.04em' }}>
                    DUE {new Date(item.due).toLocaleDateString('en-US',{day:'2-digit',month:'short',year:'2-digit'}).toUpperCase()}
                  </div>
                </div>
              );
            })}
          </div>
          {group.kind === 'recurring' && visible.length < items.length && (
            <div style={{ textAlign:'center', marginTop:10, fontSize:11, color:'var(--ink-mute)', fontFamily:'var(--mono)', letterSpacing:'0.04em' }}>
              Showing nearby items · {items.length} total
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── SEARCHABLE SELECT ──────────────────────────────────────────────────────
// A click-to-open dropdown with type-ahead search. Options can be flagged
// disabled (rendered muted but still clickable) — used for PSC where many
// codes exist but only some are present in the current portfolio.
function SearchableSelect({ value, onChange, options, placeholder = 'Select…', allLabel = 'All', width = 220 }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const ref = useRef(null);

  useEffect(() => {
    function onDocClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    if (open) document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const selected = value === 'all'
    ? null
    : options.find(o => o.id === value);

  const norm = q.trim().toLowerCase();
  const filtered = !norm
    ? options
    : options.filter(o => `${o.id} ${o.label} ${o.desc || ''}`.toLowerCase().includes(norm));

  return (
    <div ref={ref} style={{ position:'relative', display:'inline-block', width }}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        style={{
          width:'100%', display:'flex', alignItems:'center', justifyContent:'space-between',
          padding:'5px 10px', background:'var(--surface)',
          border:'1px solid var(--border-md)', borderRadius:3,
          fontSize:12, color: selected ? 'var(--ink)' : 'var(--ink-mute)',
          fontFamily:'inherit', cursor:'pointer', gap:8,
        }}
      >
        <span style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', textAlign:'left' }}>
          {selected ? (
            <>
              <span style={{ fontFamily:'var(--mono)', fontWeight:600 }}>{selected.id}</span>
              {selected.desc && <span style={{ color:'var(--ink-mute)', marginLeft:8 }}>{selected.desc}</span>}
            </>
          ) : (
            <span>{allLabel}</span>
          )}
        </span>
        <span style={{ color:'var(--ink-faint)', flexShrink:0 }}><IcoChevron dir="down" size={10} /></span>
      </button>
      {open && (
        <div style={{
          position:'absolute', top:'calc(100% + 4px)', left:0, zIndex:30,
          width:Math.max(width, 320), background:'var(--surface)',
          border:'1px solid var(--border-md)', borderRadius:3,
          boxShadow:'var(--shadow)',
        }}>
          <div style={{ padding:8, borderBottom:'1px solid var(--border)' }}>
            <input
              autoFocus
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder={placeholder}
              style={{
                width:'100%', border:'1px solid var(--border-md)', borderRadius:3,
                padding:'6px 9px', fontSize:12, outline:'none', background:'var(--surface-alt)',
              }}
            />
          </div>
          <div style={{ maxHeight:280, overflowY:'auto', padding:'4px 0' }}>
            <div
              onClick={() => { onChange('all'); setOpen(false); setQ(''); }}
              style={{
                padding:'7px 12px', fontSize:12, cursor:'pointer',
                background: value === 'all' ? 'var(--accent-soft)' : 'transparent',
                color: value === 'all' ? 'var(--accent)' : 'var(--ink)',
                fontWeight: value === 'all' ? 600 : 400,
              }}
              onMouseEnter={e => value !== 'all' && (e.currentTarget.style.background='var(--surface-alt)')}
              onMouseLeave={e => value !== 'all' && (e.currentTarget.style.background='transparent')}
            >{allLabel}</div>
            {filtered.length === 0 && (
              <div style={{ padding:'10px 12px', fontSize:11.5, color:'var(--ink-faint)' }}>No matches.</div>
            )}
            {filtered.map(opt => {
              const isActive = value === opt.id;
              return (
                <div key={opt.id}
                  onClick={() => { onChange(opt.id); setOpen(false); setQ(''); }}
                  style={{
                    padding:'7px 12px', fontSize:12, cursor:'pointer',
                    display:'flex', alignItems:'baseline', gap:10,
                    background: isActive ? 'var(--accent-soft)' : 'transparent',
                    opacity: opt.disabled ? 0.42 : 1,
                  }}
                  onMouseEnter={e => !isActive && (e.currentTarget.style.background='var(--surface-alt)')}
                  onMouseLeave={e => !isActive && (e.currentTarget.style.background='transparent')}
                >
                  <span style={{
                    fontFamily:'var(--mono)', fontWeight:600,
                    color: isActive ? 'var(--accent)' : 'var(--ink)', minWidth:54,
                  }}>{opt.id}</span>
                  {opt.desc && <span style={{ color:'var(--ink-mute)', flex:1 }}>{opt.desc}</span>}
                  {opt.disabled && <span style={{ fontSize:9.5, fontFamily:'var(--mono)', color:'var(--ink-faint)', letterSpacing:'0.08em', textTransform:'uppercase' }}>no examples</span>}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── PSC MULTI-SELECT (categories + specific codes) ─────────────────────────
// Lets the analyst pick whole letter-categories (e.g., "all R-codes") and/or
// individual PSC codes. An empty selection means no filter.
function PSCMultiSelect({ categories, codes, onChange, codeOptions, width = 260 }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const ref = useRef(null);

  useEffect(() => {
    function onDocClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    if (open) document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const norm = q.trim().toLowerCase();
  const filteredCats = !norm
    ? PSC_CATEGORIES
    : PSC_CATEGORIES.filter(c => `${c.letter} ${c.label}`.toLowerCase().includes(norm));
  const filteredCodes = !norm
    ? codeOptions
    : codeOptions.filter(o => `${o.id} ${o.label} ${o.desc || ''}`.toLowerCase().includes(norm));

  function toggleCategory(letter) {
    const next = new Set(categories);
    if (next.has(letter)) next.delete(letter); else next.add(letter);
    onChange({ categories: next, codes });
  }
  function toggleCode(code) {
    const next = new Set(codes);
    if (next.has(code)) next.delete(code); else next.add(code);
    onChange({ categories, codes: next });
  }
  function clearAll() {
    onChange({ categories: new Set(), codes: new Set() });
  }

  const totalSelected = categories.size + codes.size;
  const summary = totalSelected === 0
    ? 'All PSCs'
    : [
        ...[...categories].map(l => `${l}-codes`),
        ...[...codes],
      ].join(', ');

  return (
    <div ref={ref} style={{ position:'relative', display:'inline-block', width }}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        style={{
          width:'100%', display:'flex', alignItems:'center', justifyContent:'space-between',
          padding:'5px 10px', background:'var(--surface)',
          border:'1px solid var(--border-md)', borderRadius:3,
          fontSize:12, color: totalSelected > 0 ? 'var(--ink)' : 'var(--ink-mute)',
          cursor:'pointer', gap:8, fontFamily:'inherit',
        }}
      >
        <span style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', textAlign:'left' }}>
          {summary}
        </span>
        <span style={{ color:'var(--ink-faint)', flexShrink:0, display:'flex', alignItems:'center', gap:6 }}>
          {totalSelected > 0 && (
            <span style={{
              fontSize:10, fontFamily:'var(--mono)', fontWeight:700,
              background:'var(--ink)', color:'#fff', borderRadius:2, padding:'1px 5px',
            }}>{totalSelected}</span>
          )}
          <IcoChevron dir="down" size={10} />
        </span>
      </button>
      {open && (
        <div style={{
          position:'absolute', top:'calc(100% + 4px)', left:0, zIndex:30,
          width:Math.max(width, 360), background:'var(--surface)',
          border:'1px solid var(--border-md)', borderRadius:3,
          boxShadow:'var(--shadow)',
        }}>
          <div style={{ padding:8, borderBottom:'1px solid var(--border)', display:'flex', gap:6 }}>
            <input
              autoFocus
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Search category or PSC code…"
              style={{
                flex:1, border:'1px solid var(--border-md)', borderRadius:3,
                padding:'6px 9px', fontSize:12, outline:'none', background:'var(--surface-alt)',
              }}
            />
            {totalSelected > 0 && (
              <button
                type="button"
                onClick={clearAll}
                style={{
                  border:'1px solid var(--border-md)', borderRadius:3, padding:'0 10px',
                  background:'var(--surface-alt)', fontSize:11, color:'var(--ink-mute)',
                  cursor:'pointer', fontFamily:'var(--mono)', letterSpacing:'0.06em',
                }}
              >CLEAR</button>
            )}
          </div>
          <div style={{ maxHeight:340, overflowY:'auto' }}>
            {filteredCats.length > 0 && (
              <>
                <div style={{ padding:'8px 12px 4px', fontSize:9.5, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.14em', textTransform:'uppercase', fontFamily:'var(--mono)' }}>
                  Categories (broad)
                </div>
                {filteredCats.map(cat => {
                  const checked = categories.has(cat.letter);
                  return (
                    <label key={cat.letter} style={{
                      display:'flex', alignItems:'center', gap:10, padding:'6px 12px',
                      cursor:'pointer', fontSize:12,
                      background: checked ? 'var(--accent-soft)' : 'transparent',
                    }}
                      onMouseEnter={e => !checked && (e.currentTarget.style.background='var(--surface-alt)')}
                      onMouseLeave={e => !checked && (e.currentTarget.style.background='transparent')}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleCategory(cat.letter)}
                        style={{ accentColor:'var(--accent)' }}
                      />
                      <span style={{ fontFamily:'var(--mono)', fontWeight:700, color: checked ? 'var(--accent)' : 'var(--ink)', minWidth:38 }}>{cat.letter}-codes</span>
                      <span style={{ color:'var(--ink-mute)', flex:1 }}>{cat.label}</span>
                    </label>
                  );
                })}
              </>
            )}
            {filteredCodes.length > 0 && (
              <>
                <div style={{ padding:'10px 12px 4px', fontSize:9.5, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.14em', textTransform:'uppercase', fontFamily:'var(--mono)', borderTop: filteredCats.length > 0 ? '1px solid var(--border)' : 'none', marginTop: filteredCats.length > 0 ? 4 : 0 }}>
                  Specific codes
                </div>
                {filteredCodes.map(opt => {
                  const checked = codes.has(opt.id);
                  return (
                    <label key={opt.id} style={{
                      display:'flex', alignItems:'center', gap:10, padding:'6px 12px',
                      cursor:'pointer', fontSize:12,
                      background: checked ? 'var(--accent-soft)' : 'transparent',
                      opacity: opt.disabled ? 0.45 : 1,
                    }}
                      onMouseEnter={e => !checked && (e.currentTarget.style.background='var(--surface-alt)')}
                      onMouseLeave={e => !checked && (e.currentTarget.style.background='transparent')}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleCode(opt.id)}
                        style={{ accentColor:'var(--accent)' }}
                      />
                      <span style={{ fontFamily:'var(--mono)', fontWeight:600, color: checked ? 'var(--accent)' : 'var(--ink)', minWidth:54 }}>{opt.id}</span>
                      {opt.desc && <span style={{ color:'var(--ink-mute)', flex:1 }}>{opt.desc}</span>}
                      {opt.disabled && <span style={{ fontSize:9, fontFamily:'var(--mono)', color:'var(--ink-faint)', letterSpacing:'0.08em', textTransform:'uppercase' }}>no examples</span>}
                    </label>
                  );
                })}
              </>
            )}
            {filteredCats.length === 0 && filteredCodes.length === 0 && (
              <div style={{ padding:'12px', fontSize:11.5, color:'var(--ink-faint)' }}>No matches.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── NEW-CONTRACT (LOG) MODAL ───────────────────────────────────────────────
// Uses filename hints to prefill editable fields, then lets inline backend
// processing extract the real source-contract evidence after upload.
function NewContractModal({ onClose, onCreated }) {
  const [stage, setStage] = useState('drop'); // drop → extracting → review
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const fileRef = useRef(null);
  const [fields, setFields] = useState({
    number:'', title:'', psc:'', naics:'', component:'', value:'',
    start:'', end:'', contractor:'', co:'',
  });

  function pickFile(f) {
    if (!f) return;
    setFile(f);
    setStage('extracting');
    setTimeout(() => {
      setFields(extractFromFilename(f.name));
      setStage('review');
    }, 900);
  }

  async function commit(e) {
    e.preventDefault();
    if (!fields.number || !fields.title) return;
    try {
      setSubmitting(true);
      const created = await createContract({
        contract_number: fields.number,
        title: fields.title,
        vendor_name: fields.contractor || null,
        contracting_officer: fields.co || null,
        psc_code: fields.psc || 'R499',
        naics_code: fields.naics || '541611',
        office_name: fields.component || 'PMS 325',
        obligated_value: parseMoney(fields.value),
        period_start: fields.start || null,
        period_end: fields.end || null,
      });
      if (file) {
        await uploadDocument({
          contractId: created.id,
          title: `${fields.number} base contract`,
          documentType: 'Source Contract',
          notes: 'Uploaded during portal contract logging.',
          file,
          processInline: true,
        });
      }
      onCreated(normalizeContract(created));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div onClick={onClose} style={{
      position:'fixed', inset:0, background:'rgba(10,25,41,0.55)',
      display:'flex', alignItems:'center', justifyContent:'center', zIndex:50,
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background:'var(--surface)', borderRadius:4, width:580, maxWidth:'94vw',
        boxShadow:'var(--shadow)', border:'1px solid var(--border-md)',
      }}>
        <div style={{ padding:'16px 22px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
          <div>
            <div style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.14em', textTransform:'uppercase', fontFamily:'var(--mono)' }}>Log Contract</div>
            <div style={{ fontSize:14, fontWeight:600, color:'var(--ink)', marginTop:2 }}>Upload contract document — review filename hints</div>
          </div>
          <button type="button" onClick={onClose} style={{ background:'none', border:'none', color:'var(--ink-mute)', cursor:'pointer' }}><IcoClose/></button>
        </div>

        {stage === 'drop' && (
          <div style={{ padding:'22px' }}>
            <div
              onClick={() => fileRef.current?.click()}
              onDragOver={e => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={e => { e.preventDefault(); setDragging(false); pickFile(e.dataTransfer.files[0]); }}
              style={{
                border:`1.5px dashed ${dragging ? 'var(--accent)' : 'var(--border-md)'}`,
                borderRadius:3, padding:'34px 18px', textAlign:'center', cursor:'pointer',
                background: dragging ? 'var(--accent-soft)' : 'var(--surface-alt)',
              }}
            >
              <input ref={fileRef} type="file" style={{ display:'none' }} onChange={e => pickFile(e.target.files[0])}/>
              <div style={{ marginBottom:10, color:'var(--ink-faint)' }}><IcoUpload/></div>
              <div style={{ fontSize:13, fontWeight:600, color:'var(--ink)' }}>Drop the contract PDF or click to browse</div>
              <div style={{ fontSize:11, color:'var(--ink-mute)', marginTop:4, fontFamily:'var(--mono)' }}>Filename hints prefill the form; backend processing extracts source evidence after upload.</div>
            </div>
          </div>
        )}

        {stage === 'extracting' && (
          <div style={{ padding:'40px 22px', textAlign:'center' }}>
            <Spinner />
            <div style={{ fontSize:13, fontWeight:600, color:'var(--ink)', marginTop:14 }}>Preparing filename hints…</div>
            <div style={{ fontSize:11, color:'var(--ink-mute)', marginTop:6, fontFamily:'var(--mono)' }}>{file?.name}</div>
          </div>
        )}

        {stage === 'review' && (
          <form onSubmit={commit}>
            <div style={{ padding:'18px 22px' }}>
              <div style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.14em', textTransform:'uppercase', fontFamily:'var(--mono)', marginBottom:10 }}>Filename hints from {file?.name}</div>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
                {[
                  ['number',     'Contract Number *', false],
                  ['title',      'Title *',           true],
                  ['contractor', 'Contractor',        true],
                  ['co',         'Contracting Officer (CO)', true],
                  ['psc',        'PSC',               false],
                  ['naics',      'NAICS',             false],
                  ['component',  'Component',         true],
                  ['value',      'Obligated Value',   false],
                  ['start',      'Start Date',        false],
                  ['end',        'End Date',          false],
                ].map(([k, label, span]) => (
                  <label key={k} style={{ display:'grid', gap:5, gridColumn: span ? '1 / -1' : 'auto' }}>
                    <span style={{ fontSize:9.5, fontWeight:700, color:'var(--ink-soft)', letterSpacing:'0.10em', textTransform:'uppercase', fontFamily:'var(--mono)' }}>{label}</span>
                    <input
                      value={fields[k]}
                      onChange={e => setFields(f => ({ ...f, [k]: e.target.value }))}
                      style={{
                        width:'100%', border:'1px solid var(--border-md)', borderRadius:3,
                        padding:'7px 10px', background:'var(--surface)', color:'var(--ink)',
                        fontSize:12.5, outline:'none',
                        fontFamily: ['number','psc','naics','value','start','end'].includes(k) ? 'var(--mono)' : 'inherit',
                      }}
                      placeholder={k === 'start' || k === 'end' ? 'YYYY-MM-DD' : ''}
                      required={k === 'number' || k === 'title'}
                    />
                  </label>
                ))}
              </div>
            </div>
            <div style={{ padding:'12px 22px', borderTop:'1px solid var(--border)', display:'flex', justifyContent:'flex-end', gap:10 }}>
              <BtnSecondary type="button" onClick={onClose}>Cancel</BtnSecondary>
              <BtnPrimary type="submit" disabled={submitting}>{submitting ? 'Adding…' : 'Add to portfolio'}</BtnPrimary>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

function parseMoney(value) {
  const clean = String(value || '').replace(/[$,]/g, '').trim();
  if (!clean) return null;
  const parsed = Number(clean);
  return Number.isFinite(parsed) ? parsed : null;
}

function compactCurrency(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '$0';
  if (numeric >= 1_000_000_000) return `$${(numeric / 1_000_000_000).toFixed(1)}B`;
  if (numeric >= 1_000_000) return `$${Math.round(numeric / 1_000_000)}M`;
  if (numeric >= 1_000) return `$${Math.round(numeric / 1_000)}K`;
  return `$${Math.round(numeric)}`;
}

function normalizeThemeContract(row) {
  return {
    ...row,
    id: row.id,
    number: row.number || row.contract_number || row.id,
    title: row.title || row.number || row.id,
    psc: row.psc || row.psc_code || 'UNK',
    component: row.component || row.office_name || row.agency_name || 'Unassigned',
    value: row.value || compactCurrency(row.obligated_value || 0),
    start: row.start || row.period_start || '2026-01-01',
    end: row.end || row.period_end || '2027-12-31',
    docsCount: row.document_count || row.evidence_count || 0,
    contractor: row.vendor_name || row.contractor || 'TBD',
    co: row.contracting_officer || row.co || 'TBD',
    classification: row.security_level || row.classification || 'STANDARD',
  };
}

function themeMatchesServiceCode(theme, serviceCode) {
  if (!theme?.psc) return false;
  if (serviceCode.endsWith('-codes')) return String(theme.psc).startsWith(serviceCode[0]);
  return theme.psc === serviceCode;
}

function periodParam(period) {
  return String(period || '').toLowerCase().replace(/\s+/g, '_');
}

function extractFromFilename(name) {
  // Filename hinting only. The uploaded document is processed by the backend
  // after the contract record is created.
  const numMatch = name.match(/[Nn]\d{5}-\d{2}-[A-Z]-\d{4}/);
  const number = numMatch ? numMatch[0].toUpperCase() : 'N00024-26-C-' + Math.floor(1000 + Math.random() * 9000);
  return {
    number,
    title: 'Imported from ' + name.replace(/\.[^/.]+$/, ''),
    psc: 'R706',
    naics: '541614',
    component: 'PMS 325',
    value: '$0',
    start: new Date().toISOString().slice(0,10),
    end: new Date(Date.now() + 365 * 3 * 86400000).toISOString().slice(0,10),
    contractor: 'TBD',
    co: 'LCDR Nicole Jacobs',
  };
}

// ─── INSIGHT DETAIL + REPORT ────────────────────────────────────────────────
// Show contracts an insight is drawn from, allow flagging for follow-up,
// and let the analyst download a shareable report (Markdown).
function contractsForInsight(ins, contracts) {
  // Custom (pinned) insights carry the user's explicit selection.
  if (ins.pinnedContractIds && ins.pinnedContractIds.length > 0) {
    const set = new Set(ins.pinnedContractIds);
    return contracts.filter(c => set.has(c.id));
  }
  // Contracts whose PSC matches the insight's PSC. Falls back to a same-letter
  // bucket so analysts always see at least a couple of examples.
  const exact = contracts.filter(c => c.psc === ins.psc);
  if (exact.length >= 2) return exact;
  const bucket = contracts.filter(c => c.psc[0] === ins.psc[0]);
  return Array.from(new Set([...exact, ...bucket]));
}

// HTML escape for any user-supplied or model-supplied strings rendered into
// the report. Reports are loaded into an iframe and printed; we don't want
// stray angle brackets or quotes breaking the markup.
function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

const PDF_STYLES = `
  @page { size: Letter; margin: 0.75in; }
  * { box-sizing: border-box; }
  body {
    font-family: Georgia, 'Times New Roman', serif;
    color: #0A1929;
    font-size: 11pt;
    line-height: 1.55;
    margin: 0;
  }
  .doc-mast {
    border-bottom: 2px solid #0A1929;
    padding-bottom: 12px;
    margin-bottom: 18px;
  }
  .doc-mast .label {
    font-family: 'Courier New', monospace;
    font-size: 8.5pt;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #4D5A72;
    margin-bottom: 6px;
  }
  .doc-mast h1 {
    margin: 0 0 4px;
    font-size: 18pt;
    letter-spacing: -0.01em;
  }
  .doc-mast .meta {
    font-family: 'Courier New', monospace;
    font-size: 9pt;
    color: #4D5A72;
  }
  .insight {
    page-break-inside: avoid;
    margin-bottom: 28px;
    padding-bottom: 18px;
    border-bottom: 1px solid #ccd2dc;
  }
  .insight:last-child { border-bottom: none; }
  .insight h2 {
    font-size: 13pt;
    margin: 0 0 8px;
    color: #0A1929;
  }
  .pill {
    display: inline-block;
    font-family: 'Courier New', monospace;
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    padding: 2px 7px;
    border-radius: 2px;
    border: 1px solid #4D5A72;
    color: #4D5A72;
    background: #F4F6F9;
    margin-right: 6px;
  }
  .pill.flag { color: #9B3A1E; border-color: #9B3A1E; background: rgba(155,58,30,0.06); }
  .pill.warn { color: #7A5310; border-color: #7A5310; background: rgba(122,83,16,0.06); }
  .pill.good { color: #2F5D45; border-color: #2F5D45; background: rgba(47,93,69,0.06); }
  .pill.flagged { color: #fff; background: #9B3A1E; border-color: #9B3A1E; }
  .pill.pinned { color: #fff; background: #11447A; border-color: #11447A; }
  .claim {
    font-size: 12pt;
    font-weight: 600;
    margin: 6px 0 12px;
  }
  .section-label {
    font-family: 'Courier New', monospace;
    font-size: 8pt;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #4D5A72;
    margin: 14px 0 6px;
  }
  .body-text { margin: 0 0 8px; }
  .so-box {
    border-left: 2px solid #11447A;
    padding: 8px 12px;
    background: #F4F6F9;
    margin: 6px 0 14px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 4px;
    font-size: 9.5pt;
  }
  th {
    font-family: 'Courier New', monospace;
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    color: #4D5A72;
    text-align: left;
    padding: 6px 8px;
    border-bottom: 1.5px solid #0A1929;
  }
  td {
    padding: 5px 8px;
    border-bottom: 0.5px solid #ccd2dc;
    vertical-align: top;
  }
  td.mono, th.mono { font-family: 'Courier New', monospace; font-size: 9pt; }
  .historical-row {
    border-bottom: 0.5px solid #ccd2dc;
    padding: 8px 0;
  }
  .historical-row:last-child { border-bottom: none; }
  .historical-row .src { font-weight: 600; }
  .historical-row .n {
    font-family: 'Courier New', monospace;
    font-size: 8.5pt;
    color: #4D5A72;
    margin-left: 8px;
  }
  .historical-row .note {
    font-size: 10pt;
    color: #4D5A72;
    margin-top: 2px;
  }
  .footer {
    margin-top: 24px;
    padding-top: 10px;
    border-top: 1px solid #ccd2dc;
    font-family: 'Courier New', monospace;
    font-size: 8.5pt;
    color: #8492A6;
    letter-spacing: 0.06em;
  }
`;

function buildInsightReportHTML(ins, contracts, flagged) {
  const isCustom = !!ins.custom;
  const histRows = (ins.historical || []).map(h => `
    <div class="historical-row">
      <div><span class="src">${esc(h.source)}</span>${h.n != null ? `<span class="n">n = ${h.n.toLocaleString()}</span>` : ''}</div>
      <div class="note">${esc(h.note)}</div>
    </div>
  `).join('');
  const contractRows = contracts.length === 0
    ? `<tr><td colspan="5" style="text-align:center; color:#8492A6;">No matching contracts in your portfolio.</td></tr>`
    : contracts.map(c => `
      <tr>
        <td class="mono">${esc(c.number)}</td>
        <td>${esc(c.title)}</td>
        <td class="mono">${esc(c.psc)}</td>
        <td>${esc(c.component)}</td>
        <td class="mono" style="text-align:right;">${esc(c.value)}</td>
      </tr>
    `).join('');

  return `
    <div class="insight">
      <div>
        <span class="pill ${ins.tone}">${esc(ins.lens)}</span>
        <span class="pill">${esc(ins.psc)}</span>
        <span class="pill">NAICS ${esc(ins.naics)}</span>
        ${isCustom ? '<span class="pill pinned">⚑ Pinned</span>' : ''}
        ${flagged ? '<span class="pill flagged">⚑ Flagged</span>' : ''}
      </div>
      <h2 class="claim">${esc(ins.claim)}</h2>

      <div class="section-label">Why</div>
      <p class="body-text">${esc(ins.why || '—')}</p>

      <div class="section-label">So what</div>
      <div class="so-box">${esc(ins.so || '—')}</div>

      <div class="section-label">Your portfolio — source contracts (${contracts.length})</div>
      <table>
        <thead><tr><th>Contract #</th><th>Title</th><th>PSC</th><th>Component</th><th style="text-align:right;">Value</th></tr></thead>
        <tbody>${contractRows}</tbody>
      </table>

      ${histRows ? `
        <div class="section-label">Historical / cross-portfolio sources (${ins.historical.length})</div>
        ${histRows}
      ` : ''}
    </div>
  `;
}

function buildLibraryReportHTML(insights, flaggedSet) {
  const body = insights.map(ins => {
    const linked = contractsForInsight(ins, MOCK_CONTRACTS);
    return buildInsightReportHTML(ins, linked, flaggedSet?.has(ins.id));
  }).join('');
  return `
    <div class="doc-mast">
      <div class="label">FedCenter — Insights Library</div>
      <h1>Insights Library Export</h1>
      <div class="meta">
        Generated ${new Date().toLocaleString('en-US')} ·
        ${insights.length} insights${flaggedSet?.size ? ` · ${flaggedSet.size} flagged` : ''}
      </div>
    </div>
    ${body}
    <div class="footer">FedCenter Insights Library · ${new Date().toISOString().slice(0,10)}</div>
  `;
}

// Renders HTML into an offscreen iframe and triggers the browser's print
// dialog. Users get a real PDF via "Save as PDF" in the print destination.
// No external PDF dependency required.
function printHTMLAsPDF(html, title) {
  const iframe = document.createElement('iframe');
  iframe.style.position = 'fixed';
  iframe.style.right = '-9999px';
  iframe.style.bottom = '-9999px';
  iframe.style.width = '816px';
  iframe.style.height = '1056px';
  iframe.style.border = '0';
  document.body.appendChild(iframe);

  const doc = iframe.contentDocument || iframe.contentWindow.document;
  doc.open();
  doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title><style>${PDF_STYLES}</style></head><body>${html}</body></html>`);
  doc.close();

  // Give the iframe a tick to lay out before triggering print.
  setTimeout(() => {
    try {
      iframe.contentWindow.focus();
      iframe.contentWindow.print();
    } catch (err) {
      console.error('PDF print failed', err);
    }
    // Remove the iframe after the print dialog has had time to read it.
    setTimeout(() => {
      if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
    }, 1500);
  }, 200);
}

function downloadInsightReport(ins, contracts, flagged) {
  const html = `<div class="doc-mast">
    <div class="label">FedCenter · Insight Report</div>
    <h1>${esc(ins.lens)}</h1>
    <div class="meta">Generated ${new Date().toLocaleString('en-US')}</div>
  </div>
  ${buildInsightReportHTML(ins, contracts, flagged)}
  <div class="footer">FedCenter Insights Library</div>`;
  printHTMLAsPDF(html, `Insight ${ins.id} — ${ins.psc}`);
}

function downloadInsightLibrary(insights, flaggedSet) {
  printHTMLAsPDF(
    buildLibraryReportHTML(insights, flaggedSet),
    `FedCenter Insights Library — ${new Date().toISOString().slice(0,10)}`
  );
}

const INSIGHT_FLAGS_KEY = 'fcsw-insight-flags';
const CUSTOM_INSIGHTS_KEY = 'fcsw-custom-insights';

function loadFlaggedInsights() {
  try { return new Set(JSON.parse(localStorage.getItem(INSIGHT_FLAGS_KEY) || '[]')); }
  catch { return new Set(); }
}
function saveFlaggedInsights(set) {
  try { localStorage.setItem(INSIGHT_FLAGS_KEY, JSON.stringify([...set])); } catch {}
}

function loadCustomInsights() {
  try { return JSON.parse(localStorage.getItem(CUSTOM_INSIGHTS_KEY) || '[]'); }
  catch { return []; }
}
function saveCustomInsights(list) {
  try { localStorage.setItem(CUSTOM_INSIGHTS_KEY, JSON.stringify(list)); } catch {}
}

// Promote a per-contract finding into a library insight. Used when the
// analyst clicks "Pin to library" on a finding card.
function buildPinnedInsightFromFinding(contract, finding) {
  const toneFromSeverity = {
    critical: 'flag',
    watch:    'warn',
    healthy:  'good',
  };
  const theme = THEMES.find(t => t.id === finding.themeId);
  const similarIds = (finding.similar || []).map(s => s.id);
  const pinnedContractIds = Array.from(new Set([contract.id, ...similarIds]));
  return {
    id: `pinned-${contract.id}-${finding.id}`,
    custom: true,
    pinnedAt: new Date().toISOString(),
    sourceContractId: contract.id,
    sourceFindingId: finding.id,
    claim: finding.claim,
    why: finding.observed,
    so: theme
      ? theme.insight
      : 'Pinned from contract findings — track recurrence across the portfolio.',
    psc: contract.psc,
    naics: contract.naics,
    tone: toneFromSeverity[finding.severity] || 'flag',
    lens: theme
      ? `Pinned · ${theme.title.split(/[—:]/)[0].trim()}`
      : 'Pinned · From contract finding',
    contracts: `${pinnedContractIds.length} of ${MOCK_CONTRACTS.length}`,
    pinnedContractIds,
    historical: [
      { source: `Contract ${contract.number} · ${finding.sourceDoc}`, n: null, note: finding.observed },
      ...(theme ? [{ source: `Portfolio theme · ${theme.title}`, n: theme.flagged, note: theme.insight }] : []),
    ],
  };
}

// Add or remove a finding's library pin. Used directly from finding cards
// without an intermediate modal so analysts can pin in one click.
function pinFindingToLibrary(contract, finding) {
  const list = loadCustomInsights();
  const ins = buildPinnedInsightFromFinding(contract, finding);
  if (list.some(i => i.id === ins.id)) return list;
  const next = [ins, ...list];
  saveCustomInsights(next);
  return next;
}

function unpinFindingFromLibrary(contract, finding) {
  const id = `pinned-${contract.id}-${finding.id}`;
  const next = loadCustomInsights().filter(i => i.id !== id);
  saveCustomInsights(next);
  return next;
}

function InsightDetailModal({ insight, onClose, onSelectContract, isFlagged, onToggleFlag, onUnpin }) {
  if (!insight) return null;
  const linked = contractsForInsight(insight, MOCK_CONTRACTS);
  const toneMap = {
    flag: { border:'var(--flag)', bg:'var(--flag-soft)', text:'var(--flag)' },
    warn: { border:'var(--warn)', bg:'var(--warn-soft)', text:'var(--warn)' },
    good: { border:'var(--good)', bg:'var(--good-soft)', text:'var(--good)' },
  };
  const t = toneMap[insight.tone];

  return (
    <div onClick={onClose} style={{
      position:'fixed', inset:0, background:'rgba(10,25,41,0.55)',
      display:'flex', alignItems:'center', justifyContent:'center', zIndex:50,
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background:'var(--surface)', borderRadius:4, width:780, maxWidth:'94vw',
        maxHeight:'86vh', display:'flex', flexDirection:'column',
        boxShadow:'var(--shadow)', border:'1px solid var(--border-md)',
      }}>
        <div style={{ padding:'16px 22px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', justifyContent:'space-between', gap:14 }}>
          <div style={{ display:'flex', alignItems:'center', gap:10, flexWrap:'wrap' }}>
            <span style={{
              fontSize:9.5, fontWeight:700, letterSpacing:'0.10em', textTransform:'uppercase',
              color:t.text, background:t.bg, border:`1px solid ${t.border}`,
              padding:'2px 8px', borderRadius:2, fontFamily:'var(--mono)',
            }}>{insight.lens}</span>
            <Tag>{insight.psc}</Tag>
            <Tag>NAICS {insight.naics}</Tag>
            {insight.custom && <Tag tone="accent">⚑ Pinned by you</Tag>}
            {isFlagged && <Tag tone="flag">⚑ Flagged</Tag>}
          </div>
          <button type="button" onClick={onClose} style={{ background:'none', border:'none', color:'var(--ink-mute)', cursor:'pointer' }}><IcoClose/></button>
        </div>

        <div style={{ padding:'20px 22px', overflowY:'auto' }}>
          <div style={{ fontSize:15, fontWeight:600, color:'var(--ink)', lineHeight:1.45, marginBottom:14 }}>{insight.claim}</div>
          <div style={{ fontSize:12.5, color:'var(--ink-mute)', lineHeight:1.6, marginBottom:10 }}>
            <strong style={{ color:'var(--ink-soft)', fontWeight:600 }}>Why: </strong>{insight.why}
          </div>
          <div style={{
            fontSize:12.5, color:'var(--ink-soft)', lineHeight:1.6,
            background:'var(--surface-alt)', borderLeft:`2px solid ${t.border}`,
            padding:'10px 14px', marginBottom:18,
          }}>
            <strong style={{ fontWeight:600 }}>So what: </strong>{insight.so}
          </div>

          <div style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.14em', textTransform:'uppercase', fontFamily:'var(--mono)', marginBottom:8 }}>
            Your portfolio — source contracts ({linked.length})
          </div>
          <div style={{ border:'1px solid var(--border)', borderRadius:3, overflow:'hidden', marginBottom:18 }}>
            <table style={{ width:'100%', borderCollapse:'collapse' }}>
              <thead>
                <tr style={{ background:'var(--surface-alt)' }}>
                  {['Contract #','Title','PSC','Component','Value'].map((h,i) => (
                    <th key={i} style={{
                      padding:'8px 12px', textAlign:'left', fontSize:9.5, fontWeight:700,
                      letterSpacing:'0.12em', textTransform:'uppercase', color:'var(--ink-mute)',
                      fontFamily:'var(--mono)', borderBottom:'1px solid var(--border-md)',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {linked.map(c => (
                  <tr key={c.id}
                    onClick={() => { onSelectContract && onSelectContract(c); onClose(); }}
                    style={{ borderBottom:'1px solid var(--border)', cursor: onSelectContract ? 'pointer' : 'default', transition:'background 0.1s' }}
                    onMouseEnter={e => e.currentTarget.style.background='var(--surface-alt)'}
                    onMouseLeave={e => e.currentTarget.style.background='transparent'}
                  >
                    <td style={{ padding:'9px 12px', fontFamily:'var(--mono)', fontSize:11.5, color:'var(--accent)', fontWeight:600 }}>{c.number}</td>
                    <td style={{ padding:'9px 12px', fontSize:12, color:'var(--ink)' }}>{c.title}</td>
                    <td style={{ padding:'9px 12px', fontFamily:'var(--mono)', fontSize:11, color:'var(--ink-mute)' }}>{c.psc}</td>
                    <td style={{ padding:'9px 12px', fontSize:11, color:'var(--ink-mute)' }}>{c.component}</td>
                    <td style={{ padding:'9px 12px', fontFamily:'var(--mono)', fontSize:11.5, color:'var(--ink-soft)' }}>{c.value}</td>
                  </tr>
                ))}
                {linked.length === 0 && (
                  <tr><td colSpan={5} style={{ padding:'14px', textAlign:'center', fontSize:11.5, color:'var(--ink-faint)' }}>No matching contracts in your portfolio.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {insight.historical && insight.historical.length > 0 && (
            <>
              <div style={{ fontSize:10, fontWeight:700, color:'var(--ink-mute)', letterSpacing:'0.14em', textTransform:'uppercase', fontFamily:'var(--mono)', marginBottom:8 }}>
                Historical / cross-portfolio sources ({insight.historical.length})
              </div>
              <div style={{ border:'1px solid var(--border)', borderRadius:3, overflow:'hidden' }}>
                {insight.historical.map((h, i) => (
                  <div key={i} style={{
                    padding:'10px 14px',
                    borderBottom: i < insight.historical.length - 1 ? '1px solid var(--border)' : 'none',
                    background:'var(--surface)',
                  }}>
                    <div style={{ display:'flex', alignItems:'baseline', gap:10, flexWrap:'wrap', marginBottom:3 }}>
                      <span style={{ fontSize:12.5, fontWeight:600, color:'var(--ink)' }}>{h.source}</span>
                      {h.n != null && (
                        <span style={{
                          fontSize:9.5, fontWeight:700, fontFamily:'var(--mono)',
                          letterSpacing:'0.10em', color:'var(--ink-mute)',
                          background:'var(--surface-alt)', border:'1px solid var(--border-md)',
                          padding:'1px 6px', borderRadius:2,
                        }}>n = {h.n.toLocaleString()}</span>
                      )}
                    </div>
                    <div style={{ fontSize:11.5, color:'var(--ink-mute)', lineHeight:1.5 }}>{h.note}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div style={{ padding:'12px 22px', borderTop:'1px solid var(--border)', display:'flex', justifyContent:'space-between', gap:10 }}>
          <div style={{ display:'flex', gap:8 }}>
            <BtnSecondary onClick={() => onToggleFlag(insight.id)}>{isFlagged ? '⚑ Unflag' : '⚑ Flag for follow-up'}</BtnSecondary>
            {insight.custom && onUnpin && (
              <BtnSecondary onClick={() => { onUnpin(insight.id); onClose(); }}>Unpin from library</BtnSecondary>
            )}
          </div>
          <div style={{ display:'flex', gap:10 }}>
            <BtnSecondary onClick={onClose}>Close</BtnSecondary>
            <BtnPrimary onClick={() => downloadInsightReport(insight, linked, isFlagged)}>Download PDF</BtnPrimary>
          </div>
        </div>
      </div>
    </div>
  );
}

// Placeholder for any pages still wired in
function PlaceholderPage({ title, crumbs }) {
  return (
    <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
      <TopBar crumbs={crumbs || [title]} />
      <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center' }}>
        <EmptyState title={title} sub="This section is coming soon." />
      </div>
    </div>
  );
}

export {
  LoginPage, HomePage, ContractsPage, ContractDetailPage,
  InsightsPage, DocumentsPage, PlaceholderPage,
  ContractorHome, ContractorContractPage,
};
