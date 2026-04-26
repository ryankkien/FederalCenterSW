// @ts-nocheck
// portal-shell.tsx — Sidebar, TopBar, and shared UI primitives
import React from 'react';

// ─── Icons (minimal inline SVG) ────────────────────────────────────────────
const IcoHome     = () => <svg width="14" height="14" viewBox="0 0 15 15" fill="none"><path d="M1.5 7L7.5 1.5 13.5 7v7H9.5v-4.5h-4V14H1.5V7z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/></svg>;
const IcoContracts= () => <svg width="14" height="14" viewBox="0 0 15 15" fill="none"><rect x="2" y="1.5" width="9" height="12" rx="0.5" stroke="currentColor" strokeWidth="1.3"/><path d="M4.5 5h4M4.5 7.5h4M4.5 10h2.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/><path d="M11 5.5v7.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>;
const IcoInsights = () => <svg width="14" height="14" viewBox="0 0 15 15" fill="none"><path d="M2 12h11M2 12V3M4 10l2.5-3 2 2 3-4.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>;
const IcoDocs     = () => <svg width="14" height="14" viewBox="0 0 15 15" fill="none"><path d="M3 1.5h6l3 3v9H3v-12z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/><path d="M9 1.5v3h3M5 7.5h5M5 10h5M5 12.5h3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>;
const IcoAdmin    = () => <svg width="14" height="14" viewBox="0 0 15 15" fill="none"><circle cx="7.5" cy="5.5" r="2.5" stroke="currentColor" strokeWidth="1.3"/><path d="M2 13c0-2.5 2.5-4 5.5-4s5.5 1.5 5.5 4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>;
const IcoSearch   = () => <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="6" cy="6" r="4" stroke="currentColor" strokeWidth="1.3"/><path d="M9.5 9.5L12.5 12.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>;
const IcoUpload   = () => <svg width="14" height="14" viewBox="0 0 15 15" fill="none"><path d="M7.5 10V2.5M4.5 5.5l3-3 3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/><path d="M2 11.5v1a1 1 0 001 1h9a1 1 0 001-1v-1" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>;
const IcoChevron  = ({ dir = 'right', size = 12 }) => {
  const d = { right: 'M4.5 3L8 6.5 4.5 10', left: 'M8 3L4.5 6.5 8 10', down: 'M3 5l3.5 3.5L10 5' }[dir];
  return <svg width={size} height={size} viewBox="0 0 12 12" fill="none"><path d={d} stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>;
};
const IcoClose    = () => <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>;
const IcoArrow    = () => <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 7h8M8 4l3 3-3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>;
const IcoStar     = () => <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1.5l1.85 3.55 3.9.55-2.85 2.7.7 3.85L7 10.4l-3.6 1.75.7-3.85L1.25 5.6l3.9-.55L7 1.5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/></svg>;

// ─── NAV CONFIG (removed statuses, queue, reports, benchmarks, lessons) ────
const NAV = [
  { id:'home',      label:'Home',     Icon: IcoHome },
  { id:'contracts', label:'Contracts',Icon: IcoContracts },
  { id:'insights',  label:'Insights', Icon: IcoInsights },
  { id:'documents', label:'Documents',Icon: IcoDocs },
];

const NAV_FOOTER = [
  { id:'admin',     label:'Admin',    Icon: IcoAdmin },
];

// ─── SIDEBAR ────────────────────────────────────────────────────────────────
function Sidebar({ active, onNav, user, onLogout }) {
  const isContractor = user?.role === 'contractor';
  // Contractors get a focused workspace: home only. Officials get the full nav.
  const navItems   = isContractor ? NAV.filter(n => n.id === 'home') : NAV;
  const footerItems = isContractor ? [] : NAV_FOOTER;
  return (
    <aside style={{
      width:228, flexShrink:0,
      background:'var(--sidebar-bg)',
      display:'flex', flexDirection:'column',
      borderRight:'1px solid rgba(0,0,0,0.3)',
    }}>
      {/* Wordmark — formal stencil-feel */}
      <div style={{
        padding:'18px 20px 16px',
        borderBottom:'1px solid var(--sidebar-rule)',
      }}>
        <div style={{ display:'flex', alignItems:'center', gap:9 }}>
          {/* Insignia mark */}
          <div style={{
            width:22, height:22, flexShrink:0, position:'relative',
          }}>
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
              <rect x="1" y="1" width="20" height="20" stroke="#E6EDF6" strokeWidth="1.2"/>
              <rect x="4.5" y="4.5" width="13" height="13" stroke="#E6EDF6" strokeWidth="0.8" opacity="0.5"/>
              <path d="M7 11h8M11 7v8" stroke="#E6EDF6" strokeWidth="1.2"/>
            </svg>
          </div>
          <div>
            <div style={{
              fontWeight:700, fontSize:13, letterSpacing:'0.06em',
              color:'var(--sidebar-text-a)', fontFamily:'var(--mono)', textTransform:'uppercase',
            }}>CPM-PORTAL</div>
            <div style={{
              fontSize:9, letterSpacing:'0.18em', textTransform:'uppercase',
              color:'var(--sidebar-text)', marginTop:1, fontFamily:'var(--mono)',
            }}>Perf · Monitor</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex:1, padding:'10px 8px', overflowY:'auto' }}>
        <div style={{
          fontSize:9, letterSpacing:'0.18em', textTransform:'uppercase',
          color:'var(--sidebar-text)', fontFamily:'var(--mono)',
          padding:'4px 12px 8px', opacity:0.65,
        }}>Workspace</div>
        {navItems.map(({ id, label, Icon }) => {
          const isActive = active === id;
          return (
            <div key={id}
              onClick={() => onNav(id)}
              style={{
                display:'flex', alignItems:'center', gap:10,
                padding:'8px 12px', borderRadius:3, margin:'1px 0',
                cursor:'pointer', position:'relative',
                background: isActive ? 'var(--sidebar-active)' : 'transparent',
                color: isActive ? 'var(--sidebar-text-a)' : 'var(--sidebar-text)',
                fontWeight: isActive ? 600 : 400,
                fontSize:13, transition:'background 0.12s',
              }}
              onMouseEnter={e => !isActive && (e.currentTarget.style.background='var(--sidebar-hover)')}
              onMouseLeave={e => !isActive && (e.currentTarget.style.background='transparent')}
            >
              {isActive && <div style={{ position:'absolute', left:0, top:6, bottom:6, width:2, background:'var(--sidebar-text-a)' }}/>}
              <span style={{ opacity: isActive ? 1 : 0.7, display:'flex', alignItems:'center' }}><Icon /></span>
              <span style={{ flex:1 }}>{label}</span>
            </div>
          );
        })}
      </nav>

      {/* Footer nav */}
      {footerItems.length > 0 && <div style={{ padding:'8px 8px 0', borderTop:'1px solid var(--sidebar-rule)' }}>
        {footerItems.map(({ id, label, Icon }) => {
          const isActive = active === id;
          return (
            <div key={id} onClick={() => onNav(id)} style={{
              display:'flex', alignItems:'center', gap:10,
              padding:'8px 12px', borderRadius:3,
              cursor:'pointer',
              background: isActive ? 'var(--sidebar-active)' : 'transparent',
              color: isActive ? 'var(--sidebar-text-a)' : 'var(--sidebar-text)',
              fontWeight: isActive ? 600 : 400, fontSize:13,
            }}
              onMouseEnter={e => !isActive && (e.currentTarget.style.background='var(--sidebar-hover)')}
              onMouseLeave={e => !isActive && (e.currentTarget.style.background='transparent')}
            ><Icon /><span>{label}</span></div>
          );
        })}
      </div>}

      {/* User */}
      <div style={{
        borderTop:'1px solid var(--sidebar-rule)',
        padding:'12px 16px', marginTop:8,
      }}>
        <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
          <div style={{
            width:28, height:28, borderRadius:2,
            background:'rgba(212,222,236,0.12)',
            border:'1px solid rgba(212,222,236,0.18)',
            display:'flex', alignItems:'center', justifyContent:'center',
            fontSize:11, fontWeight:700, color:'var(--sidebar-text-a)',
            fontFamily:'var(--mono)', flexShrink:0,
          }}>{(user?.name || 'U').split(' ').map(s=>s[0]).slice(0,2).join('').toUpperCase()}</div>
          <div style={{ minWidth:0 }}>
            <div style={{ fontSize:12, fontWeight:600, color:'var(--sidebar-text-a)', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>
              {user?.name || 'Unknown'}
            </div>
            <div style={{ fontSize:9, color:'var(--sidebar-text)', textTransform:'uppercase', letterSpacing:'0.12em', fontFamily:'var(--mono)' }}>
              {user?.role === 'contractor' ? 'Contractor' : 'Gov · Official'}
            </div>
          </div>
        </div>
        <button
          onClick={onLogout}
          style={{
            width:'100%', padding:'5px 0', borderRadius:2,
            border:'1px solid var(--sidebar-border)',
            background:'transparent', color:'var(--sidebar-text)',
            fontSize:11, fontWeight:500, letterSpacing:'0.06em', textTransform:'uppercase',
            fontFamily:'var(--mono)',
          }}
          onMouseEnter={e => e.currentTarget.style.background='var(--sidebar-hover)'}
          onMouseLeave={e => e.currentTarget.style.background='transparent'}
        >Sign out</button>
      </div>
    </aside>
  );
}

// ─── TOPBAR ──────────────────────────────────────────────────────────────────
function TopBar({ crumbs = [], onNav }) {
  return (
    <div style={{
      height:46, flexShrink:0,
      background:'var(--surface)',
      borderBottom:'1px solid var(--border)',
      display:'flex', alignItems:'center',
      padding:'0 24px', gap:16,
    }}>
      <div style={{ flex:1, display:'flex', alignItems:'center', gap:6, fontSize:12, color:'var(--ink-mute)' }}>
        {crumbs.map((c, i) => (
          <React.Fragment key={i}>
            <span
              style={{
                color: i === crumbs.length-1 ? 'var(--ink)' : 'var(--ink-mute)',
                fontWeight: i === crumbs.length-1 ? 600 : 400,
                cursor: i < crumbs.length-1 ? 'pointer' : 'default',
                fontFamily: i === crumbs.length-1 ? 'inherit' : 'inherit',
              }}
              onClick={() => c.onClick && c.onClick()}
            >{typeof c === 'string' ? c : c.label}</span>
            {i < crumbs.length-1 && <span style={{ opacity:0.35 }}>›</span>}
          </React.Fragment>
        ))}
      </div>

      <div style={{
        display:'flex', alignItems:'center', gap:8,
        border:'1px solid var(--border-md)',
        borderRadius:3, padding:'5px 10px',
        background:'var(--surface-alt)',
        color:'var(--ink-mute)', fontSize:12,
        width:280, cursor:'text',
      }}>
        <IcoSearch />
        <span>Search contracts, documents…</span>
        <span style={{
          marginLeft:'auto', fontSize:10, fontWeight:600,
          border:'1px solid var(--border-md)', borderRadius:2,
          padding:'1px 5px', color:'var(--ink-faint)',
          fontFamily:'var(--mono)',
        }}>⌘K</span>
      </div>

      <div style={{
        fontSize:10, letterSpacing:'0.14em', fontWeight:700,
        color:'var(--ink-faint)', fontFamily:'var(--mono)',
        whiteSpace:'nowrap', borderLeft:'1px solid var(--border)', paddingLeft:14,
      }}>CUI // SP-PROCURE</div>
    </div>
  );
}

// ─── SHARED UI PRIMITIVES ────────────────────────────────────────────────────

// Tag chip
function Tag({ children, tone = 'default' }) {
  const map = {
    default: { bg:'var(--surface-alt)', border:'var(--border-md)', text:'var(--ink-mute)' },
    accent:  { bg:'var(--accent-soft)', border:'var(--accent-mid)', text:'var(--accent)' },
    flag:    { bg:'var(--flag-soft)',   border:'var(--flag-mid)',   text:'var(--flag)' },
    good:    { bg:'var(--good-soft)',   border:'var(--good-mid)',   text:'var(--good)' },
    warn:    { bg:'var(--warn-soft)',   border:'var(--warn-mid)',   text:'var(--warn)' },
    ink:     { bg:'var(--ink)',         border:'var(--ink)',        text:'#fff' },
  };
  const s = map[tone] || map.default;
  return (
    <span style={{
      display:'inline-block',
      background:s.bg, border:`1px solid ${s.border}`,
      borderRadius:2, padding:'1px 6px',
      fontSize:10, fontWeight:600, letterSpacing:'0.08em',
      textTransform:'uppercase', color:s.text, whiteSpace:'nowrap',
      fontFamily:'var(--mono)',
    }}>{children}</span>
  );
}

// Buttons
function BtnPrimary({ children, onClick, disabled, type='button', style={} }) {
  return (
    <button type={type} onClick={onClick} disabled={disabled} style={{
      background: disabled ? 'var(--ink-faint)' : 'var(--ink)',
      color:'#fff', border:'1px solid var(--ink)',
      padding:'7px 14px', borderRadius:3,
      fontWeight:600, fontSize:12.5, letterSpacing:'0.01em',
      cursor: disabled ? 'not-allowed' : 'pointer',
      whiteSpace:'nowrap',
      ...style,
    }}>{children}</button>
  );
}

function BtnSecondary({ children, onClick, style={} }) {
  return (
    <button type="button" onClick={onClick} style={{
      background:'var(--surface)', color:'var(--ink-soft)',
      border:'1px solid var(--border-md)',
      padding:'6px 12px', borderRadius:3,
      fontWeight:500, fontSize:12.5,
      whiteSpace:'nowrap',
      ...style,
    }}>{children}</button>
  );
}

function BtnGhost({ children, onClick, tone='default', style={} }) {
  const colors = {
    default: 'var(--ink-mute)',
    accent:  'var(--accent)',
    flag:    'var(--flag)',
    good:    'var(--good)',
  };
  return (
    <button type="button" onClick={onClick} style={{
      background:'transparent', color: colors[tone] || colors.default,
      border:'none', padding:'6px 10px',
      fontWeight:500, fontSize:13,
      whiteSpace:'nowrap',
      ...style,
    }}>{children}</button>
  );
}

// Section header
function SectionHeader({ title, subtitle, right }) {
  return (
    <div style={{ display:'flex', alignItems:'flex-end', justifyContent:'space-between', gap:16, marginBottom:18 }}>
      <div>
        <h2 style={{ fontSize:16, fontWeight:700, color:'var(--ink)', letterSpacing:'-0.005em' }}>{title}</h2>
        {subtitle && <p style={{ fontSize:12, color:'var(--ink-mute)', marginTop:3 }}>{subtitle}</p>}
      </div>
      {right && <div style={{ display:'flex', gap:8 }}>{right}</div>}
    </div>
  );
}

// Metric card — formal, no top accent border by default
function MetricCard({ label, value, sub, mono, style={}, onClick }) {
  return (
    <div onClick={onClick} style={{
      background:'var(--surface)', border:`1px solid var(--border)`,
      borderRadius:4, padding:'14px 16px',
      cursor: onClick ? 'pointer' : 'default',
      flex:1, ...style,
    }}>
      <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.14em', textTransform:'uppercase', color:'var(--ink-mute)', marginBottom:8, fontFamily:'var(--mono)' }}>{label}</div>
      <div style={{ fontSize:24, fontWeight:700, letterSpacing:'-0.02em', color:'var(--ink)', lineHeight:1, fontFamily: mono ? 'var(--mono)' : 'inherit' }}>{value}</div>
      {sub && <div style={{ fontSize:11, color:'var(--ink-mute)', marginTop:6 }}>{sub}</div>}
    </div>
  );
}

// Spinner
function Spinner() {
  return (
    <div style={{ display:'flex', justifyContent:'center', padding:40 }}>
      <div style={{
        width:20, height:20, border:'2px solid var(--border-md)',
        borderTopColor:'var(--ink)', borderRadius:'50%',
        animation:'spin 0.7s linear infinite',
      }}/>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}

// Empty state
function EmptyState({ icon, title, sub, action }) {
  return (
    <div style={{ textAlign:'center', padding:'48px 24px', color:'var(--ink-mute)' }}>
      <div style={{ fontSize:14, fontWeight:600, color:'var(--ink-soft)', marginBottom:6 }}>{title}</div>
      {sub && <div style={{ fontSize:12, marginBottom:16 }}>{sub}</div>}
      {action}
    </div>
  );
}

// Format helpers
function fmtBytes(v) {
  if (v < 1024) return `${v} B`;
  if (v < 1048576) return `${(v/1024).toFixed(1)} KB`;
  return `${(v/1048576).toFixed(1)} MB`;
}
function fmtDate(s) {
  return new Date(s).toLocaleDateString('en-US', { month:'short', day:'2-digit', year:'numeric' });
}
function fmtDateMil(s) {
  const d = new Date(s);
  const day = String(d.getDate()).padStart(2,'0');
  const mon = d.toLocaleDateString('en-US',{month:'short'}).toUpperCase();
  return `${day} ${mon} ${d.getFullYear()}`;
}

export {
  Sidebar, TopBar,
  Tag, BtnPrimary, BtnSecondary, BtnGhost,
  SectionHeader, MetricCard, Spinner, EmptyState,
  IcoHome, IcoContracts, IcoInsights, IcoDocs, IcoAdmin,
  IcoArrow, IcoChevron, IcoClose, IcoSearch, IcoUpload, IcoStar,
  fmtBytes, fmtDate, fmtDateMil,
};
