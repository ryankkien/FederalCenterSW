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

// ─── MOCK DATA ────────────────────────────────────────────────────────────────
const MOCK_CONTRACTS = [
  { id:'c1', number:'N00024-23-C-4187', title:'Atlantic Logistics & Sustainment Services', psc:'R706', naics:'541614', component:'PMS 325', value:'$4,210,440', period:'15 MAR 2023 — 14 FEB 2027', start:'2023-03-15', end:'2027-02-14', elapsed:78, lastActivity:'24 APR 2026', docsCount:14, contractor:'Atlantic Logistics LLC', co:'LCDR J. Vance', classification:'CUI', authorized:[
    { name:'LCDR J. Vance',  role:'Contracting Officer',           email:'j.vance@navy.mil' },
    { name:'LT M. Reyes',    role:'Contracting Officer Rep (COR)', email:'m.reyes@navy.mil' },
    { name:'CDR A. Singh',   role:'Program Manager',               email:'a.singh@navy.mil' },
    { name:'Sarah Kim',      role:'Contractor PM (Atlantic)',      email:'sarah.kim@atlanticlogistics.com' },
  ]},
  { id:'c2', number:'N00024-22-C-3091', title:'Pacific Fleet Maintenance Support',         psc:'J998', naics:'336611', component:'PMS 408', value:'$7,820,100', period:'10 JAN 2022 — 09 DEC 2026', start:'2022-01-10', end:'2026-12-09', elapsed:91, lastActivity:'22 APR 2026', docsCount:22, contractor:'Pacific Marine Industries', co:'CDR R. Patel' },
  { id:'c3', number:'N00178-22-D-7741', title:'NAVWAR IT Infrastructure Services',         psc:'D316', naics:'541512', component:'NAVWAR', value:'$12,140,000',period:'01 JUL 2022 — 30 JUN 2027', start:'2022-07-01', end:'2027-06-30', elapsed:64, lastActivity:'20 APR 2026', docsCount:9,  contractor:'Coastal Cyber Group', co:'CIV K. Brown' },
  { id:'c4', number:'N00024-21-C-2204', title:'Ship Maintenance & Rebuilding',             psc:'J999', naics:'336611', component:'PMS 312', value:'$9,500,300', period:'01 OCT 2021 — 30 SEP 2026', start:'2021-10-01', end:'2026-09-30', elapsed:88, lastActivity:'18 APR 2026', docsCount:31, contractor:'Eastern Shipworks', co:'LCDR J. Vance' },
  { id:'c5', number:'N00024-23-C-4501', title:'Administrative & Management Support',       psc:'R408', naics:'561110', component:'PMS 325', value:'$2,340,000', period:'01 APR 2023 — 31 MAR 2027', start:'2023-04-01', end:'2027-03-31', elapsed:62, lastActivity:'17 APR 2026', docsCount:7,  contractor:'Cardinal Admin Svcs.', co:'CIV M. Diaz' },
  { id:'c6', number:'N00178-23-D-8812', title:'Cybersecurity Assessment & Testing',        psc:'D310', naics:'541512', component:'NAVWAR', value:'$3,110,000', period:'15 JUN 2023 — 14 MAY 2027', start:'2023-06-15', end:'2027-05-14', elapsed:58, lastActivity:'15 APR 2026', docsCount:11, contractor:'Coastal Cyber Group', co:'CIV K. Brown' },
  { id:'c7', number:'N00025-22-C-0041', title:'NAVFAC Facilities Sustainment',             psc:'Z2AA', naics:'238910', component:'NAVFAC', value:'$5,640,200', period:'15 MAR 2022 — 14 FEB 2026', start:'2022-03-15', end:'2026-02-14', elapsed:100,lastActivity:'01 MAR 2026', docsCount:44, contractor:'Tidewater Construction', co:'CDR R. Patel' },
  { id:'c8', number:'N00024-23-C-4802', title:'Architect & Engineering — Dry Dock',        psc:'C211', naics:'541330', component:'NAVFAC', value:'$1,820,000', period:'01 SEP 2023 — 31 AUG 2026', start:'2023-09-01', end:'2026-08-31', elapsed:83, lastActivity:'10 APR 2026', docsCount:6,  contractor:'Bayside Engineering', co:'CIV M. Diaz' },
];

// Default access roster used when a contract record doesn't carry one explicitly.
const DEFAULT_AUTHORIZED = [
  { name:'LCDR J. Vance',  role:'Contracting Officer',           email:'j.vance@navy.mil' },
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
function buildDocs(contractId) {
  const docs = [];
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

  return docs.sort((a,b)=> new Date(b.created_at) - new Date(a.created_at));
}

// Map doc_type → tone/abbrev/source
const DOC_TYPE_META = {
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

// ─── INSIGHTS LIBRARY (filterable by PSC, etc.) ─────────────────────────────
const INSIGHTS = [
  { id:'i1', psc:'R706', naics:'541614', tone:'flag', lens:'Pattern · Recurrence',     contracts:'12 of 47',
    claim:'In R-coded service contracts, weekly reports slip when key personnel rotate within 90 days of a deliverable.',
    why:'Across 47 contracts, 12 show this pattern. Mean slip 4.2 days following PM substitution, vs. 0.6 days otherwise.',
    so:'Worth flagging when a key-personnel sub notice precedes a deliverable window. Predictive value ≈ 0.74.' },
  { id:'i2', psc:'D310', naics:'541512', tone:'flag', lens:'Anomaly · External Dependency', contracts:'3 of 8',
    claim:'D-310 cyber assessment contracts show recurring single-points-of-failure on vendor export licenses.',
    why:'License renewal packages submitted within 30 days of expiry in 3 of 8 cases. Mitigations rarely captured in IMS.',
    so:'Suggests a contract-clause template change — pre-renewal milestone with a 60-day buffer.' },
  { id:'i3', psc:'R408', naics:'561110', tone:'warn', lens:'Drift · Cost Composition', contracts:'9 of 22',
    claim:'In R-408 admin support, travel ODCs are growing faster than labor — and faster than peer median.',
    why:'ODCs +18% over baseline vs. +3% labor. Peer median ODC growth +6%.',
    so:'Not yet an overrun. Worth understanding before EAC re-projection.' },
  { id:'i4', psc:'D310', naics:'541512', tone:'good', lens:'Win · Replicable Practice', contracts:'2 of 8',
    claim:'Two NAVWAR cyber contracts closed POA&M items 11 days ahead of plan — same mechanism in both.',
    why:'Mechanism: SOC-2-tied clause language adopted in mod P00007. Same pattern present in 11 peer contracts.',
    so:'Transferable to D, J, R-code SOW templates.' },
  { id:'i5', psc:'J998', naics:'336611', tone:'warn', lens:'Drift · Schedule Health', contracts:'5 of 11',
    claim:'J-998 fleet-maintenance contracts trend toward late delivery in months 22–24 of 36-month base periods.',
    why:'Mean SPI declines from 0.97 to 0.89 in this band. Correlates with sub-tier supplier lead-time growth.',
    so:'Prompt for a mid-period IMS health check would have caught 4 of 5 prior cases.' },
  { id:'i6', psc:'C211', naics:'541330', tone:'good', lens:'Benchmark · Outperform', contracts:'1 of 3',
    claim:'A&E dry-dock work has come in 6.2% under EAC across recent NAVFAC contracts.',
    why:'Driver: BIM-coordinated design reviews introduced FY24. Reduced rework hours ~12%.',
    so:'Strong case for adopting the same review cadence in upcoming PMS 312 mods.' },
  { id:'i7', psc:'Z2AA', naics:'238910', tone:'flag', lens:'Pattern · Recurrence', contracts:'4 of 6',
    claim:'Facilities sustainment contracts under-report sub-tier safety incidents in the first 6 months.',
    why:'Cross-checking with NAVFAC injury logs shows a 0.31 correlation; first-6-month reporting gap closes after H-19 reminders.',
    so:'Worth requiring sub-tier reporting from Day 1 in next-cycle solicitations.' },
];

// ─── LOGIN PAGE ─────────────────────────────────────────────────────────────
function LoginPage({ onLogin }) {
  const [role, setRole] = useState('contractor');
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setLoading(true);
    await new Promise(r => setTimeout(r, 400));
    const mockUser = role === 'contractor'
      ? { id:'u1', email:'sarah.kim@atlanticlogistics.com', name:'Sarah Kim',     role:'contractor' }
      : { id:'u2', email:'j.vance@navy.mil',                name:'LCDR J. Vance', role:'official'   };
    onLogin('mock-token-' + role, mockUser);
    setLoading(false);
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
  const firstName = (user?.name || 'User').split(' ').slice(-1)[0];

  const [serviceCode, setServiceCode] = useState('All codes');
  const [component, setComponent] = useState('All');
  const [severity, setSeverity] = useState('≥ watch');
  const [period, setPeriod] = useState('Last 30 days');
  const [view, setView] = useState('All flagged');

  // Filter themes by view
  const visibleThemes = THEMES.filter(t => {
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
            <p style={{ fontSize:13, color:'var(--ink-mute)', marginTop:4 }}>{firstName} — themes and patterns across 47 active contracts</p>
          </div>
          <div style={{ textAlign:'right' }}>
            <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-faint)', fontFamily:'var(--mono)' }}>Reporting Period</div>
            <div style={{ fontSize:14, fontWeight:600, color:'var(--ink)', marginTop:4, fontFamily:'var(--mono)' }}>FY26 · Q3</div>
          </div>
        </div>

        {/* KPI strip */}
        <div style={{ display:'grid', gridTemplateColumns:'repeat(4, 1fr)', gap:0, marginBottom:18, border:'1px solid var(--border)', borderRadius:4, background:'var(--surface)' }}>
          <KpiCell label="Flagged"            value={<span><span style={{color:'var(--flag)'}}>8</span><span style={{color:'var(--ink-faint)'}}> / 47</span></span>} sub="+3 vs prior week" />
          <KpiCell label="Median CDRL slip"   value={<span style={{color:'var(--warn)'}}>12<span style={{fontSize:18, marginLeft:2}}>d</span></span>} sub="stable across portfolio" border />
          <KpiCell label="Cross-contract themes" value={<span>{THEMES.length}</span>} sub="≥2 instances each" border />
          <KpiCell label="Aggregate value flagged" value="$236M" sub="15% of portfolio" border />
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
              { id:'All flagged', count:8, tone:'ink' },
              { id:'Critical',    count:3, tone:'flag' },
              { id:'Watch',       count:5, tone:'warn' },
              { id:'Healthy',     count:39, tone:'good' },
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
          {visibleThemes.map(theme => (
            <ThemeCard key={theme.id} theme={theme} onSelectContract={onSelectContract} />
          ))}
          {visibleThemes.length === 0 && <EmptyState title="No themes match" sub="Adjust filters to see related patterns."/>}
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
  const contracts = theme.contracts.map(id => MOCK_CONTRACTS.find(c => c.id === id)).filter(Boolean);

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
          {contracts.map((c, i) => (
            <div key={c.id} onClick={() => onSelectContract(c)} style={{
              display:'grid', gridTemplateColumns:'160px 1fr 100px 100px 16px', gap:14, alignItems:'center',
              padding:'9px 0', borderBottom: i < contracts.length-1 ? '1px solid var(--border)' : 'none',
              cursor:'pointer',
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

  const pscBuckets = [...new Set(MOCK_CONTRACTS.map(c => c.psc[0]))].sort();
  const components = [...new Set(MOCK_CONTRACTS.map(c => c.component))];

  const filtered = MOCK_CONTRACTS.filter(c => {
    if (pscFilter !== 'all' && c.psc[0] !== pscFilter) return false;
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
          <p style={{ fontSize:12, color:'var(--ink-mute)', marginTop:4 }}>{MOCK_CONTRACTS.length} contracts indexed · FY22 — FY27 spans</p>
        </div>
        <div style={{ display:'flex', gap:8 }}>
          <BtnSecondary>Export CSV</BtnSecondary>
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
          <FilterPills options={[{id:'all', label:'All'}, ...pscBuckets.map(p=>({id:p, label:p+'-codes'}))]} value={pscFilter} onChange={setPscFilter} />
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
        {filtered.length === 0 && <EmptyState title="No contracts match" sub="Try adjusting your filters or search term." />}
      </div>
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
const DETAIL_TABS = ['Overview', 'Insights', 'Benchmarks', 'Documents'];

function ContractDetailPage({ contract, onBack, onSelectContract }) {
  const [tab, setTab] = useState('Overview');
  const [docs, setDocs] = useState(() => buildDocs(contract.id));
  const [showUpload, setShowUpload] = useState(false);

  const c = contract;

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
        {tab === 'Overview'   && <OverviewTab contract={c} docs={docs} />}
        {tab === 'Insights'   && <ContractInsightsTab contract={c} onSelectContract={onSelectContract} />}
        {tab === 'Benchmarks' && <BenchmarksTab contract={c} />}
        {tab === 'Documents'  && <DocumentsTab docs={docs} contract={c} onUpload={() => setShowUpload(true)} />}
      </div>

      {showUpload && <UploadModal contract={c} onClose={() => setShowUpload(false)} onUploaded={(d) => { setDocs(prev => [d, ...prev]); setShowUpload(false); }}/>}
    </div>
  );
}

// ─── OVERVIEW TAB ───────────────────────────────────────────────────────────
function OverviewTab({ contract: c, docs }) {
  const authorized = c.authorized || DEFAULT_AUTHORIZED;
  const classification = c.classification || 'CUI';
  const deliverables = buildDeliverables(c);

  // Counts of upcoming vs filed
  const today = Date.now();
  const allItems = deliverables.flatMap(d => d.items);
  const filedCount = allItems.filter(i => i.filed).length;
  const upcomingCount = allItems.filter(i => !i.filed && new Date(i.due).getTime() > today).length;

  return (
    <div style={{ padding:'24px 24px 48px' }}>
      {/* Top metrics */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4, 1fr)', gap:12, marginBottom:24 }}>
        <MetricCard label="Contract Value" value={c.value}            sub="Total obligated"     mono />
        <MetricCard label="Period Elapsed" value={`${c.elapsed}%`}    sub={c.period}            mono />
        <MetricCard label="Deliverables Filed" value={`${filedCount} / ${allItems.length}`} sub={`${upcomingCount} upcoming`} mono />
        <MetricCard label="Last Activity"  value={c.lastActivity}     sub="Most recent filing"  mono />
      </div>

      {/* Two-column: details + activity */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:20, marginBottom:20 }}>
        <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4, padding:'18px 22px' }}>
          <div style={{ fontSize:11, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', marginBottom:14, fontFamily:'var(--mono)' }}>Contract Particulars</div>
          {[
            ['Contract Number',    c.number, true],
            ['Contractor',         c.contractor, false],
            ['Contracting Officer',c.co, false],
            ['Component',          c.component, false],
            ['PSC / NAICS',        `${c.psc} · ${c.naics}`, true],
            ['Period',             c.period, true],
            ['Total Obligated',    c.value, true],
            ['Classification',     classification, true],
          ].map(([k, v, mono]) => (
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

          {/* Authorized access block */}
          <div style={{ marginTop:14, paddingTop:14, borderTop:'1px solid var(--border-md)' }}>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:10 }}>
              <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)' }}>Authorized Access</div>
              <div style={{ display:'inline-flex', alignItems:'center', gap:6, fontSize:9.5, fontFamily:'var(--mono)', color:'var(--accent)', border:'1px solid var(--accent)', padding:'2px 7px', borderRadius:2, fontWeight:700, letterSpacing:'0.10em' }}>
                <svg width="9" height="9" viewBox="0 0 12 12" fill="none"><path d="M3 5V4a3 3 0 016 0v1m-7 0h8v6H2V5z" stroke="currentColor" strokeWidth="1.5"/></svg>
                {classification}
              </div>
            </div>
            {authorized.map((p, i) => (
              <div key={i} style={{
                display:'grid', gridTemplateColumns:'1fr auto', gap:8,
                padding:'7px 0', borderBottom: i < authorized.length-1 ? '1px solid var(--border)' : 'none',
              }}>
                <div style={{ minWidth:0 }}>
                  <div style={{ fontSize:12.5, color:'var(--ink)', fontWeight:500 }}>{p.name}</div>
                  <div style={{ fontSize:10.5, color:'var(--ink-faint)', fontFamily:'var(--mono)', marginTop:1 }}>{p.email}</div>
                </div>
                <div style={{ fontSize:10.5, color:'var(--ink-mute)', fontFamily:'var(--mono)', letterSpacing:'0.04em', textTransform:'uppercase', whiteSpace:'nowrap', alignSelf:'center' }}>{p.role}</div>
              </div>
            ))}
            <button style={{
              marginTop:10, padding:'5px 10px', fontSize:11, fontFamily:'var(--mono)',
              background:'transparent', border:'1px dashed var(--border-str)', borderRadius:2,
              color:'var(--ink-mute)', letterSpacing:'0.04em', cursor:'pointer',
            }}>+ Manage access</button>
          </div>
        </div>

        <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4, padding:'18px 22px' }}>
          <div style={{ fontSize:11, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', marginBottom:14, fontFamily:'var(--mono)' }}>Recent Filings</div>
          {docs.slice(0, 8).map((d, i) => {
            const meta = DOC_TYPE_META[d.doc_type] || { abbr:'DOC', tone:'default' };
            return (
              <div key={d.id} style={{
                display:'flex', gap:12, padding:'8px 0',
                borderBottom: i < 7 ? '1px solid var(--border)' : 'none',
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
                  <div style={{ fontSize:12.5, color:'var(--ink)', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{d.title}</div>
                  <div style={{ fontSize:10, color:'var(--ink-faint)', marginTop:2, fontFamily:'var(--mono)', letterSpacing:'0.04em', textTransform:'uppercase' }}>{d.source}</div>
                </div>
                <div style={{ fontSize:10, color:'var(--ink-faint)', fontFamily:'var(--mono)', whiteSpace:'nowrap' }}>{fmtDateMil(d.created_at)}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Gantt — at the bottom */}
      <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4, padding:'18px 22px 22px' }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:18 }}>
          <div>
            <div style={{ fontSize:11, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)' }}>Deliverables Schedule</div>
            <div style={{ fontSize:11, color:'var(--ink-faint)', fontFamily:'var(--mono)', marginTop:4 }}>{c.period} · extracted from CDRL</div>
          </div>
          <div style={{ display:'flex', gap:14, fontSize:10, color:'var(--ink-mute)', fontFamily:'var(--mono)', letterSpacing:'0.04em' }}>
            <LegendDot color="var(--ink)"       label="Filed"/>
            <LegendDot color="var(--surface-alt)" border="var(--border-str)" label="Upcoming"/>
            <LegendDot color="var(--warn)"      label="Late"/>
            <LegendDot color="var(--accent)"    label="Imported"/>
          </div>
        </div>
        <ContractGantt contract={c} deliverables={deliverables} />
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

// ─── DOCUMENTS TAB ──────────────────────────────────────────────────────────
function DocumentsTab({ docs, contract, onUpload }) {
  const [typeFilter, setTypeFilter] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');

  const types = [...new Set(docs.map(d => d.doc_type))];
  const sources = [...new Set(docs.map(d => d.source))];

  const filtered = docs.filter(d => {
    if (typeFilter !== 'all' && d.doc_type !== typeFilter) return false;
    if (sourceFilter !== 'all' && d.source !== sourceFilter) return false;
    return true;
  });

  return (
    <div>
      <div style={{
        padding:'14px 24px', display:'flex', alignItems:'center', gap:14,
        borderBottom:'1px solid var(--border)', background:'var(--surface)',
        flexWrap:'wrap',
      }}>
        <div style={{ fontSize:13, fontWeight:600, color:'var(--ink)' }}>{filtered.length} of {docs.length} documents</div>
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
          <BtnSecondary>Import from CPARS</BtnSecondary>
          <BtnSecondary>Import from IPMDAR</BtnSecondary>
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
                <td style={{ padding:'12px 16px' }}>
                  <BtnSecondary style={{ padding:'4px 10px', fontSize:11 }}>Download</BtnSecondary>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {filtered.length === 0 && <EmptyState title="No documents match" sub="Try a different filter combination."/>}
    </div>
  );
}

// ─── CONTRACT INSIGHTS TAB — findings → patterns → similar contracts ────────
function ContractInsightsTab({ contract: c, onSelectContract }) {
  const findings = FINDINGS[c.id] || FINDINGS.c1; // fall back to demo set

  return (
    <div style={{ padding:'24px 24px 48px' }}>
      <SectionHeader
        title="Findings on this contract"
        subtitle={`${findings.length} specific issues flagged from filed documents — each linked to a portfolio-wide pattern`}
      />
      <div style={{ display:'grid', gap:14 }}>
        {findings.map(f => {
          const sev = SEVERITY_META[f.severity];
          const theme = THEMES.find(t => t.id === f.themeId);
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
              {theme && (
                <div style={{
                  borderTop:'1px dashed var(--border-md)',
                  background:'var(--surface-alt)',
                  padding:'12px 22px',
                }}>
                  <div style={{ fontSize:9.5, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:6 }}>↳ Matches portfolio theme</div>
                  <div style={{ fontSize:13, fontWeight:600, color:'var(--ink)', marginBottom:4 }}>{theme.title}</div>
                  <div style={{ fontSize:11.5, color:'var(--ink-mute)', lineHeight:1.5 }}>
                    {theme.flagged} of {theme.total} {theme.psc} contracts show this pattern. {theme.insight}
                  </div>
                </div>
              )}

              {/* Similar contracts */}
              {f.similar && f.similar.length > 0 && (
                <div style={{ borderTop:'1px solid var(--border)', padding:'12px 22px 14px' }}>
                  <div style={{ fontSize:9.5, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:8 }}>Other contracts informing this analysis</div>
                  {f.similar.map((s, i) => {
                    const ctr = MOCK_CONTRACTS.find(c2 => c2.id === s.id);
                    return (
                      <div key={s.id} onClick={() => ctr && onSelectContract && onSelectContract(ctr)} style={{
                        display:'grid', gridTemplateColumns:'160px 1fr 16px', gap:14, alignItems:'center',
                        padding:'8px 0',
                        borderBottom: i < f.similar.length-1 ? '1px solid var(--border)' : 'none',
                        cursor:'pointer',
                      }}>
                        <span style={{ fontFamily:'var(--mono)', fontSize:11.5, fontWeight:600, color:'var(--accent)' }}>{ctr?.number || s.id}</span>
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
function InsightsTab({ psc, naics, embedded }) {
  const [pscFilter, setPscFilter] = useState(embedded ? psc : 'all');
  const [toneFilter, setToneFilter] = useState('all');

  const pscBuckets = [...new Set(INSIGHTS.map(i => i.psc))].sort();

  const filtered = INSIGHTS.filter(i => {
    if (pscFilter !== 'all' && i.psc !== pscFilter) return false;
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
            <FilterPills options={[{id:'all', label:'All'}, ...pscBuckets.map(p=>({id:p, label:p}))]} value={pscFilter} onChange={setPscFilter}/>
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
            return (
              <div key={ins.id} style={{
                background:'var(--surface)', border:'1px solid var(--border)',
                borderLeft:`3px solid ${t.border}`,
                borderRadius:3, padding:'18px 20px',
              }}>
                <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10, flexWrap:'wrap' }}>
                  <span style={{
                    fontSize:9.5, fontWeight:700, letterSpacing:'0.10em', textTransform:'uppercase',
                    color:t.text, background:t.bg, border:`1px solid ${t.border}`,
                    padding:'2px 7px', borderRadius:2, fontFamily:'var(--mono)',
                  }}>{ins.lens}</span>
                  <Tag>{ins.psc}</Tag>
                  <Tag>NAICS {ins.naics}</Tag>
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
    </div>
  );
}

function InsightsPage() {
  return (
    <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
      <TopBar crumbs={['Insights']} />
      <div style={{
        background:'var(--surface)', borderBottom:'1px solid var(--border)',
        padding:'18px 24px',
      }}>
        <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.18em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:6 }}>Cross-portfolio</div>
        <h1 style={{ fontSize:22, fontWeight:700, letterSpacing:'-0.02em', color:'var(--ink)' }}>Insights Library</h1>
        <p style={{ fontSize:12, color:'var(--ink-mute)', marginTop:4 }}>{INSIGHTS.length} findings across the portfolio · filter by PSC, NAICS, or lens</p>
      </div>
      <div style={{ flex:1, overflowY:'auto', background:'var(--bg)' }}>
        <InsightsTab />
      </div>
    </div>
  );
}

// ─── BENCHMARKS TAB (within contract) ───────────────────────────────────────
function BenchmarksTab({ contract: c }) {
  const rows = [
    { metric:'Cost Performance Index (CPI)', value:'0.96', peer:'0.94', delta:'+0.02', tone:'good' },
    { metric:'Schedule Performance Index (SPI)', value:'0.91', peer:'0.93', delta:'-0.02', tone:'warn' },
    { metric:'Weekly Report On-Time Rate', value:'78%', peer:'85%', delta:'-7pp', tone:'flag' },
    { metric:'Modification Cycle Time (days)', value:'38', peer:'31', delta:'+7', tone:'warn' },
    { metric:'Invoice → Payment (days)', value:'19', peer:'24', delta:'-5', tone:'good' },
    { metric:'CPARS Score (most recent)', value:'4.1 / 5', peer:'3.8 / 5', delta:'+0.3', tone:'good' },
    { metric:'Sub-tier Reporting Compliance', value:'92%', peer:'88%', delta:'+4pp', tone:'good' },
  ];
  const toneClr = { good:'var(--good)', warn:'var(--warn)', flag:'var(--flag)' };

  return (
    <div style={{ padding:'24px 24px 48px' }}>
      <SectionHeader
        title={`Benchmarks for ${c.psc} · ${c.component}`}
        subtitle={`Comparing against peer cohort of contracts with the same PSC and component`}
      />
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
                    <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                      <div style={{ flex:1, height:8, background:'var(--surface-alt)', borderRadius:1, position:'relative', border:'1px solid var(--border)' }}>
                        <div style={{ position:'absolute', left:0, top:0, bottom:0, width:`${(num/max)*100}%`, background:toneClr[r.tone] }}/>
                        <div style={{ position:'absolute', left:`${(peer/max)*100}%`, top:-2, bottom:-2, width:1.5, background:'var(--ink)' }}/>
                      </div>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div style={{ marginTop:14, fontSize:11, color:'var(--ink-faint)', fontFamily:'var(--mono)', letterSpacing:'0.04em', display:'flex', gap:18 }}>
        <span><span style={{display:'inline-block', width:10, height:6, background:'var(--ink)', verticalAlign:'middle', marginRight:4}}/>Peer median</span>
        <span>Cohort: 22 contracts · same PSC + component · last 36 months</span>
      </div>
    </div>
  );
}

// ─── DOCUMENTS PAGE (cross-contract) ────────────────────────────────────────
function DocumentsPage({ onSelectContract }) {
  const allDocs = MOCK_CONTRACTS.flatMap(c =>
    buildDocs(c.id).slice(0, 4).map(d => ({ ...d, contractNumber:c.number, contractId:c.id, contract:c }))
  ).sort((a,b) => new Date(b.created_at) - new Date(a.created_at));

  const [typeFilter, setTypeFilter] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const types = [...new Set(allDocs.map(d => d.doc_type))];
  const sources = [...new Set(allDocs.map(d => d.source))];

  const filtered = allDocs.filter(d => {
    if (typeFilter !== 'all' && d.doc_type !== typeFilter) return false;
    if (sourceFilter !== 'all' && d.source !== sourceFilter) return false;
    return true;
  });

  return (
    <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
      <TopBar crumbs={['Documents']} />
      <div style={{ background:'var(--surface)', borderBottom:'1px solid var(--border)', padding:'18px 24px' }}>
        <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.18em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:6 }}>Portfolio</div>
        <h1 style={{ fontSize:22, fontWeight:700, letterSpacing:'-0.02em', color:'var(--ink)' }}>All Documents</h1>
        <p style={{ fontSize:12, color:'var(--ink-mute)', marginTop:4 }}>{allDocs.length} documents across {MOCK_CONTRACTS.length} contracts</p>
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
      </div>

      <div style={{ flex:1, overflowY:'auto', background:'var(--bg)' }}>
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead>
            <tr style={{ background:'var(--surface-alt)' }}>
              {['Type', 'Title', 'Contract', 'Source', 'Filed', ''].map((h,i) => (
                <th key={i} style={{
                  padding:'9px 16px', textAlign:'left',
                  fontSize:10, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase',
                  color:'var(--ink-mute)', whiteSpace:'nowrap', fontFamily:'var(--mono)',
                  position:'sticky', top:0, background:'var(--surface-alt)',
                  borderBottom:'1px solid var(--border-md)',
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map(doc => {
              const meta = DOC_TYPE_META[doc.doc_type] || { abbr:'DOC', tone:'default' };
              return (
                <tr key={doc.id} onClick={() => onSelectContract(doc.contract)} style={{
                  borderBottom:'1px solid var(--border)', cursor:'pointer',
                  background:'var(--surface)', transition:'background 0.1s',
                }}
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
                  </td>
                  <td style={{ padding:'12px 16px' }}>
                    <div style={{ fontSize:13, color:'var(--ink)' }}>{doc.title}</div>
                    <div style={{ fontSize:10, color:'var(--ink-faint)', marginTop:2, fontFamily:'var(--mono)' }}>{doc.doc_type}</div>
                  </td>
                  <td style={{ padding:'12px 16px', fontFamily:'var(--mono)', fontSize:11.5, color:'var(--accent)', whiteSpace:'nowrap' }}>{doc.contractNumber}</td>
                  <td style={{ padding:'12px 16px', fontSize:11, color:doc.source.startsWith('Imported')?'var(--accent)':'var(--ink-mute)', fontFamily:'var(--mono)', whiteSpace:'nowrap', letterSpacing:'0.04em' }}>{doc.source}</td>
                  <td style={{ padding:'12px 16px', fontSize:11, color:'var(--ink-mute)', fontFamily:'var(--mono)', whiteSpace:'nowrap' }}>{fmtDateMil(doc.created_at)}</td>
                  <td style={{ padding:'12px 16px', color:'var(--ink-faint)' }}><IcoChevron/></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── UPLOAD MODAL ───────────────────────────────────────────────────────────
function UploadModal({ contract, onClose, onUploaded }) {
  const [title, setTitle] = useState('');
  const [docType, setDocType] = useState('');
  const [notes, setNotes] = useState('');
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const fileRef = useRef();

  async function handleSubmit(e) {
    e.preventDefault();
    if (!title || !docType || !file) return;
    setLoading(true);
    await new Promise(r => setTimeout(r, 600));
    onUploaded({
      id:'new-' + Date.now(), title, doc_type:docType, source:'Contractor',
      filename: file.name, content_type: file.type, size_bytes: file.size,
      uploader: 'Contractor', created_at: new Date().toISOString(),
      period: notes || '—',
    });
    setLoading(false);
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
    'sarah.kim@atlanticlogistics.com': ['c1'],
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
  const myContracts = contractsForContractor(user);
  const today = new Date().toLocaleDateString('en-US', { weekday:'long', month:'long', day:'numeric', year:'numeric' });
  const firstName = (user?.name || 'Contractor').split(' ')[0];

  // Aggregate next deliverables across all contracts
  const upNext = myContracts.flatMap(c => {
    const dels = buildDeliverables(c);
    return dels.flatMap(group => group.items
      .filter(i => !i.filed)
      .slice(0, 4)
      .map(i => ({ contract:c, group, item:i, status:deliverableStatus(i) })));
  })
  .sort((a,b) => new Date(a.item.due) - new Date(b.item.due))
  .slice(0, 6);

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

        {/* Up next */}
        <div style={{ marginBottom:28 }}>
          <div style={{ fontSize:11, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:10 }}>
            Up next — your deliverables
          </div>
          <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4 }}>
            {upNext.map((row, i) => {
              const meta = STATUS_META[row.status];
              return (
                <div key={`${row.contract.id}-${row.item.id}`} onClick={() => onSelectContract(row.contract)} style={{
                  display:'grid', gridTemplateColumns:'120px 1fr 220px 110px 110px 16px',
                  gap:16, alignItems:'center',
                  padding:'12px 18px', cursor:'pointer',
                  borderBottom: i < upNext.length-1 ? '1px solid var(--border)' : 'none',
                  transition:'background 0.1s',
                }}
                  onMouseEnter={e => e.currentTarget.style.background='var(--surface-alt)'}
                  onMouseLeave={e => e.currentTarget.style.background='transparent'}
                >
                  <div style={{ fontFamily:'var(--mono)', fontSize:11.5, fontWeight:600, color:'var(--accent)' }}>
                    {row.group.cdrl !== '—' ? `CDRL ${row.group.cdrl}` : row.group.title.split(' ')[0]}
                  </div>
                  <div>
                    <div style={{ fontSize:13, fontWeight:600, color:'var(--ink)' }}>{row.group.title}</div>
                    <div style={{ fontSize:11, color:'var(--ink-mute)', marginTop:2, fontFamily:'var(--mono)' }}>{row.item.title}</div>
                  </div>
                  <div style={{ fontSize:11, color:'var(--ink-mute)', fontFamily:'var(--mono)', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{row.contract.number} · {row.contract.title}</div>
                  <div style={{ fontSize:11, fontFamily:'var(--mono)', color:'var(--ink-soft)' }}>
                    DUE {new Date(row.item.due).toLocaleDateString('en-US',{day:'2-digit', month:'short'}).toUpperCase()}
                  </div>
                  <div style={{ display:'flex', justifyContent:'flex-end' }}>
                    <span style={{
                      fontSize:9.5, fontWeight:700, letterSpacing:'0.10em', textTransform:'uppercase',
                      color:meta.color, background:meta.bg, border:`1px solid ${meta.border}`,
                      padding:'2px 7px', borderRadius:2, fontFamily:'var(--mono)',
                    }}>{meta.label}</span>
                  </div>
                  <IcoChevron/>
                </div>
              );
            })}
            {upNext.length === 0 && <EmptyState title="All caught up" sub="No outstanding deliverables right now."/>}
          </div>
        </div>

        {/* My contracts */}
        <div style={{ fontSize:11, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', fontFamily:'var(--mono)', marginBottom:10 }}>My contracts</div>
        <div style={{ display:'grid', gap:10 }}>
          {myContracts.map(c => {
            const dels = buildDeliverables(c);
            const all = dels.flatMap(d => d.items);
            const filed = all.filter(i => i.filed).length;
            const overdue = all.filter(i => !i.filed && new Date(i.due).getTime() < Date.now()).length;
            return (
              <div key={c.id} onClick={() => onSelectContract(c)} style={{
                background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4,
                padding:'18px 22px', cursor:'pointer',
                display:'grid', gridTemplateColumns:'1fr auto auto auto auto', gap:24, alignItems:'center',
                transition:'border-color 0.12s',
              }}
                onMouseEnter={e => e.currentTarget.style.borderColor='var(--border-str)'}
                onMouseLeave={e => e.currentTarget.style.borderColor='var(--border)'}
              >
                <div>
                  <div style={{ fontFamily:'var(--mono)', fontSize:11.5, fontWeight:600, color:'var(--accent)', marginBottom:4 }}>{c.number}</div>
                  <div style={{ fontSize:14, fontWeight:600, color:'var(--ink)' }}>{c.title}</div>
                  <div style={{ fontSize:11, color:'var(--ink-mute)', marginTop:3, fontFamily:'var(--mono)' }}>{c.period} · CO {c.co}</div>
                </div>
                <KpiMini label="Filed"    value={`${filed}/${all.length}`} />
                <KpiMini label="Overdue"  value={overdue} flag={overdue > 0} />
                <KpiMini label="Elapsed"  value={`${c.elapsed}%`} />
                <IcoChevron/>
              </div>
            );
          })}
        </div>
      </div>
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
// Two columns: contract particulars (left) + deliverables-as-upload-targets (right)
function ContractorContractPage({ contract, user, onBack }) {
  const c = contract;
  const [docs, setDocs] = useState(() => buildDocs(c.id));
  const [deliverables, setDeliverables] = useState(() => buildDeliverables(c));
  const [uploadTarget, setUploadTarget] = useState(null);

  function handleFiled(groupId, itemId, doc) {
    setDeliverables(ds => ds.map(g => g.id === groupId
      ? { ...g, items: g.items.map(i => i.id === itemId ? { ...i, filed:true, late:false } : i) }
      : g
    ));
    setDocs(prev => [doc, ...prev]);
    setUploadTarget(null);
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
              {deliverables.map(group => (
                <DeliverableGroupCard
                  key={group.id}
                  group={group}
                  onClickItem={(it) => !it.filed && setUploadTarget({ group, item: it })}
                />
              ))}
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
