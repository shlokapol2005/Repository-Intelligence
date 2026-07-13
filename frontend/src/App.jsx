import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import {
  MessageCircle, GitBranch, Code2, BookOpen,
  FolderOpen, Aperture,
} from 'lucide-react';

import LandingPage from './components/LandingPage';
import ChatAssistant from './components/ChatAssistant';
import GraphExplorer from './components/GraphExplorer';
import DeadCode from './components/DeadCode';
import OnboardingMode from './components/OnboardingMode';
import RepoSetup from './components/RepoSetup';

import './index.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/** Polls the backend /health endpoint so the header status is real, not decorative. */
function useApiStatus() {
  const [status, setStatus] = useState('checking'); // 'checking' | 'online' | 'offline'

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        await axios.get(`${API}/health`, { timeout: 4000 });
        if (!cancelled) setStatus('online');
      } catch {
        if (!cancelled) setStatus('offline');
      }
    };
    check();
    const id = setInterval(check, 15000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return status;
}

const NAV = [
  { id: 'qa',      label: 'Assistant',  icon: MessageCircle, path: '/qa',      badge: '' },
  { id: 'arch',    label: 'Code Graph', icon: GitBranch,     path: '/arch',    badge: '' },
  { id: 'dead',    label: 'Dead Code',  icon: Code2,         path: '/dead',    badge: '' },
  { id: 'onboard', label: 'Onboarding', icon: BookOpen,      path: '/onboard', badge: '' },
];

function HeaderBar({ repo, onRepoClick }) {
  const navigate = useNavigate();
  const location = useLocation();
  const isLanding = location.pathname === '/';
  const apiStatus = useApiStatus();

  const statusMeta = {
    online:   { label: 'Backend online',    title: 'FastAPI backend at ' + API + ' responded to /health — live features (Q&A, graph, impact) will work.' },
    offline:  { label: 'Backend unreachable', title: 'Could not reach ' + API + '. Start it with "python run_all.py" or check your backend URL.' },
    checking: { label: 'Checking backend…', title: 'Pinging ' + API + '/health…' },
  }[apiStatus];

  return (
    <header className="header-bar">
      <div className="header-brand" onClick={() => navigate('/')}>
        <div className="header-logo"><Aperture size={18} strokeWidth={2.2} /></div>
        <span className="header-brand-text">Repo<b>Lens</b></span>
      </div>

      {!isLanding && (
        <nav className="header-nav">
          {NAV.map(item => {
            const Icon = item.icon;
            const active = location.pathname === item.path
              || (item.id === 'qa' && ['/flow', '/impact'].includes(location.pathname));
            return (
              <div
                key={item.id}
                className={`header-tab ${active ? 'active' : ''}`}
                onClick={() => navigate(item.path)}
                id={`nav-${item.id}`}
              >
                <Icon size={15} className="tab-icon" />
                <span>{item.label}</span>
                {item.badge && <span className="header-tab-badge">{item.badge}</span>}
              </div>
            );
          })}
        </nav>
      )}

      {!isLanding && (
        <div className="header-right">
          <div className={`header-status header-status--${apiStatus}`} title={statusMeta.title}>
            <span className="dot" /> {statusMeta.label}
          </div>
          <div className="header-repo-chip" onClick={onRepoClick} title={repo || 'Load a repository'}>
            <FolderOpen size={13} style={{ color: 'var(--accent)', flexShrink: 0 }} />
            {repo
              ? <span className="repo-name">{repo.split(/[\\/]/).pop()}</span>
              : <span style={{ color: 'var(--text-muted)' }}>No repo</span>}
          </div>
        </div>
      )}
    </header>
  );
}

function AppInner() {
  const [repo, setRepo] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const urlRepo = params.get('repo');
    if (urlRepo) {
      localStorage.setItem('cd_repo', urlRepo);
      return urlRepo;
    }
    return localStorage.getItem('cd_repo') || '';
  });
  const [indexName, setIndexName] = useState(() => localStorage.getItem('cd_index') || '');
  const navigate = useNavigate();
  const location = useLocation();

  const handleRepoLoaded = (repoPath, idxName) => {
    setRepo(repoPath);
    setIndexName(idxName);
    localStorage.setItem('cd_repo', repoPath);
    localStorage.setItem('cd_index', idxName);
    navigate('/arch');
  };

  const isGraph = location.pathname === '/arch';
  const isLanding = location.pathname === '/';

  let areaClass = 'content-area';
  if (isGraph) areaClass += ' content-area--graph';
  if (isLanding) areaClass += ' content-area--full';

  return (
    <div className="app-shell">
      <HeaderBar repo={repo} onRepoClick={() => navigate('/setup')} />
      <div className="main-content">
        <div className={areaClass}>
          <Routes>
            <Route path="/"        element={<LandingPage onGetStarted={() => navigate('/setup')} />} />
            <Route path="/qa"      element={<ChatAssistant repo={repo} indexName={indexName} initialMode="qa" />} />
            <Route path="/arch"    element={<GraphExplorer repo={repo} />} />
            <Route path="/flow"    element={<ChatAssistant repo={repo} indexName={indexName} initialMode="flow" />} />
            <Route path="/impact"  element={<ChatAssistant repo={repo} indexName={indexName} initialMode="impact" />} />
            <Route path="/dead"    element={<DeadCode repo={repo} />} />
            <Route path="/onboard" element={<OnboardingMode repo={repo} />} />
            <Route path="/setup"   element={<RepoSetup onLoaded={handleRepoLoaded} />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppInner />
    </BrowserRouter>
  );
}
