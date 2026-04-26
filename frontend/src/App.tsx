// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { Sidebar } from './portal-shell';
import {
  LoginPage,
  HomePage,
  ContractsPage,
  ContractDetailPage,
  InsightsPage,
  DocumentsPage,
  PlaceholderPage,
  ContractorHome,
  ContractorContractPage,
} from './portal-pages';

const TOKEN_KEY = 'fcsw-token';

export function App() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) ?? '');
  const [user, setUser] = useState(null);
  const [page, setPage] = useState('home');
  const [contract, setContract] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    if (!token) {
      setAuthChecked(true);
      return;
    }
    fetch('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((u) => {
        setUser(u);
        setAuthChecked(true);
      })
      .catch(() => {
        const stored = localStorage.getItem('fcsw-user');
        if (stored) {
          try {
            setUser(JSON.parse(stored));
          } catch {}
        }
        setAuthChecked(true);
      });
  }, []);

  // Sync state ↔ browser history so the browser back/forward buttons
  // navigate between pages within the app.
  function pushHistory(nextPage, nextContract) {
    const state = { page: nextPage, contract: nextContract || null };
    window.history.pushState(state, '', '');
  }

  useEffect(() => {
    // Seed history state on first load so popstate has something to restore to.
    if (!window.history.state || !window.history.state.page) {
      window.history.replaceState({ page, contract }, '', '');
    }
    function onPop(e) {
      const s = e.state;
      if (s && s.page) {
        setPage(s.page);
        setContract(s.contract || null);
      } else {
        setPage('home');
        setContract(null);
      }
    }
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  function handleLogin(tok, usr) {
    localStorage.setItem(TOKEN_KEY, tok);
    localStorage.setItem('fcsw-user', JSON.stringify(usr));
    setToken(tok);
    setUser(usr);
    setPage('home');
    setContract(null);
    pushHistory('home', null);
  }

  function handleLogout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem('fcsw-user');
    setToken('');
    setUser(null);
    setPage('home');
    setContract(null);
    pushHistory('home', null);
  }

  function handleNav(dest) {
    if (dest === 'logout') {
      handleLogout();
      return;
    }
    const nextContract = dest === 'contract-detail' ? contract : null;
    setPage(dest);
    if (dest !== 'contract-detail') setContract(null);
    pushHistory(dest, nextContract);
  }

  function handleSelectContract(c) {
    setContract(c);
    setPage('contract-detail');
    pushHistory('contract-detail', c);
  }

  if (!authChecked) return null;
  if (!user) return <LoginPage onLogin={handleLogin} />;

  const isContractor = user.role === 'contractor';

  const officialPages = {
    home: <HomePage user={user} onNav={handleNav} onSelectContract={handleSelectContract} />,
    contracts: <ContractsPage onSelectContract={handleSelectContract} />,
    'contract-detail': contract ? (
      <ContractDetailPage
        contract={contract}
        onBack={() => window.history.back()}
        onNav={handleNav}
        onSelectContract={handleSelectContract}
      />
    ) : (
      <ContractsPage onSelectContract={handleSelectContract} />
    ),
    insights: <InsightsPage onSelectContract={handleSelectContract} />,
    documents: <DocumentsPage onSelectContract={handleSelectContract} />,
    admin: <PlaceholderPage title="Admin" crumbs={['Admin']} />,
  };

  const contractorPages = {
    home: <ContractorHome user={user} onSelectContract={handleSelectContract} />,
    'contract-detail': contract ? (
      <ContractorContractPage contract={contract} user={user} onBack={() => window.history.back()} />
    ) : (
      <ContractorHome user={user} onSelectContract={handleSelectContract} />
    ),
  };

  const pageMap = isContractor ? contractorPages : officialPages;
  const currentPage = pageMap[page] || pageMap['home'];

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar
        active={page === 'contract-detail' ? 'contracts' : page}
        onNav={handleNav}
        user={user}
        onLogout={handleLogout}
      />
      <div className="app-main" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
        {currentPage}
      </div>
    </div>
  );
}
