import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import {
  Search, GitBranch, Zap, AlertTriangle, Code2, BookOpen,
  FolderOpen, ChevronRight, Activity, Terminal
} from 'lucide-react';

import QAInterface from './components/QAInterface';
import ArchVisualizer from './components/ArchVisualizer';
import FlowTracer from './components/FlowTracer';
import ImpactDashboard from './components/ImpactDashboard';
import DeadCode from './components/DeadCode';
import OnboardingMode from './components/OnboardingMode';
import RepoSetup from './components/RepoSetup';

import './index.css';

const NAV = [
  { id: 'qa',       label: 'Repository Q&A',    icon: Search,       path: '/qa',       badge: 'Agent' },
  { id: 'arch',     label: 'Architecture',       icon: GitBranch,    path: '/arch',     badge: 'Agent' },
  { id: 'flow',     label: 'Flow Tracer',         icon: Zap,          path: '/flow',     badge: '' },
  { id: 'impact',   label: 'Impact Analysis',    icon: AlertTriangle, path: '/impact',  badge: 'Agent' },
  { id: 'dead',     label: 'Dead Code',          icon: Code2,        path: '/dead',     badge: '' },
  { id: 'onboard',  label: 'Onboarding Mode',    icon: BookOpen,     path: '/onboard',  badge: 'Agent' },
];

function Sidebar({ repo, onRepoClick }) {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-icon">🔍</div>
        <span className="logo-text">Code Detective</span>
      </div>

      <span className="sidebar-section-label">Features</span>

      {NAV.map(item => {
        const Icon = item.icon;
        const active = location.pathname === item.path || (location.pathname === '/' && item.path === '/qa');
        return (
          <div
            key={item.id}
            className={`nav-item ${active ? 'active' : ''}`}
            onClick={() => navigate(item.path)}
            id={`nav-${item.id}`}
          >
            <Icon size={16} className="nav-icon" />
            <span style={{ flex: 1 }}>{item.label}</span>
            {item.badge && (
              <span style={{
                fontSize: '0.62rem', fontWeight: 700,
                background: 'rgba(99,102,241,0.15)', color: '#818cf8',
                border: '1px solid rgba(99,102,241,0.3)',
                borderRadius: 4, padding: '1px 5px',
              }}>{item.badge}</span>
            )}
          </div>
        );
      })}

      <span className="sidebar-section-label">Repository</span>
      <div className="nav-item" onClick={onRepoClick} id="nav-repo">
        <FolderOpen size={16} className="nav-icon" />
        <span style={{ flex: 1 }}>Load Repository</span>
      </div>

      <div className="sidebar-repo">
        {repo ? (
          <div className="repo-badge">
            <strong>Active Repo</strong>
            <span style={{ wordBreak: 'break-all', fontSize: '0.75rem', color: '#6366f1' }}>
              {repo.split(/[\\/]/).pop()}
            </span>
          </div>
        ) : (
          <div className="repo-badge">
            <strong style={{ color: '#4b5563' }}>No repo loaded</strong>
            <span>Click "Load Repository" above</span>
          </div>
        )}
      </div>
    </nav>
  );
}

function TopBar({ title, badge }) {
  return (
    <header className="topbar">
      <Activity size={16} style={{ color: '#6366f1' }} />
      <span className="topbar-title">{title}</span>
      {badge && <span className="topbar-badge">{badge}</span>}
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981', boxShadow: '0 0 8px #10b981' }} />
        <span style={{ fontSize: '0.75rem', color: '#64748b' }}>API Connected</span>
      </div>
    </header>
  );
}

const PAGE_META = {
  '/qa':      { title: 'Repository Q&A',   badge: 'LangGraph Agent' },
  '/arch':    { title: 'Architecture Diagram', badge: 'LangGraph Agent' },
  '/flow':    { title: 'Feature Flow Tracer', badge: 'AST + Deps' },
  '/impact':  { title: 'Impact Analysis',  badge: 'LangGraph Agent' },
  '/dead':    { title: 'Dead Code Detector', badge: 'AST Static Analysis' },
  '/onboard': { title: 'Onboarding Mode',  badge: 'LangGraph Agent' },
  '/setup':   { title: 'Load Repository',  badge: '' },
};

function AppInner() {
  const [repo, setRepo] = useState(() => localStorage.getItem('cd_repo') || '');
  const [indexName, setIndexName] = useState(() => localStorage.getItem('cd_index') || '');
  const navigate = useNavigate();
  const location = useLocation();

  const handleRepoLoaded = (repoPath, idxName) => {
    setRepo(repoPath);
    setIndexName(idxName);
    localStorage.setItem('cd_repo', repoPath);
    localStorage.setItem('cd_index', idxName);
    navigate('/qa');
  };

  const meta = PAGE_META[location.pathname] || PAGE_META['/qa'];

  return (
    <div className="app-shell">
      <Sidebar repo={repo} onRepoClick={() => navigate('/setup')} />
      <div className="main-content">
        <TopBar title={meta.title} badge={meta.badge} />
        <div className="content-area">
          <Routes>
            <Route path="/"       element={<QAInterface repo={repo} indexName={indexName} />} />
            <Route path="/qa"     element={<QAInterface repo={repo} indexName={indexName} />} />
            <Route path="/arch"   element={<ArchVisualizer repo={repo} />} />
            <Route path="/flow"   element={<FlowTracer repo={repo} indexName={indexName} />} />
            <Route path="/impact" element={<ImpactDashboard repo={repo} />} />
            <Route path="/dead"   element={<DeadCode repo={repo} />} />
            <Route path="/onboard" element={<OnboardingMode repo={repo} />} />
            <Route path="/setup"  element={<RepoSetup onLoaded={handleRepoLoaded} />} />
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
