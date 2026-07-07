import React, { useState } from 'react';
import { FolderOpen, GitBranch, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import axios from 'axios';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function RepoSetup({ onLoaded }) {
  const [tab, setTab] = useState('local');
  const [localPath, setLocalPath] = useState('');
  const [githubUrl, setGithubUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState(null); // {type: 'success'|'error', msg}
  const [scanResult, setScanResult] = useState(null);

  const MOCK_REPO_PATH = import.meta.env.VITE_MOCK_REPO_PATH || '../mock-repo';

  const handleLoad = async () => {
    setLoading(true);
    setStatus(null);
    setScanResult(null);

    try {
      let repoPath = localPath.trim();

      // If GitHub tab, clone first
      if (tab === 'github') {
        const cloneRes = await axios.post(`${API}/api/mcp/github/clone`, { github_url: githubUrl.trim() });
        repoPath = cloneRes.data.local_path;
        setStatus({ type: 'success', msg: `Repository ${cloneRes.data.action}: ${cloneRes.data.repo_name}` });
      }

      // Scan + build index
      const scanRes = await axios.post(`${API}/api/scan/`, {
        repo_path: repoPath,
        build_index: true,
      });

      setScanResult(scanRes.data);
      const idxName = scanRes.data.index_name || 'default';
      setStatus({ type: 'success', msg: `Scanned ${scanRes.data.total_files} files. Vector index built!` });

      setTimeout(() => onLoaded(repoPath, idxName), 1200);
    } catch (e) {
      setStatus({ type: 'error', msg: e.response?.data?.detail || e.message });
    } finally {
      setLoading(false);
    }
  };

  const loadMock = () => {
    setTab('local');
    setLocalPath(MOCK_REPO_PATH);
  };

  return (
    <div className="repo-panel animate-fade">
      <div>
        <h2>Load Repository</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginTop: 6 }}>
          Scan a local directory or clone from GitHub to power the intelligence engine.
        </p>
      </div>

      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: 8 }}>
        {['local', 'github'].map(t => (
          <button
            key={t}
            id={`tab-${t}`}
            className={`btn ${tab === t ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setTab(t)}
          >
            {t === 'local' ? <FolderOpen size={15} /> : <GitBranch size={15} />}
            {t === 'local' ? 'Local Path' : 'GitHub URL'}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {tab === 'local' ? (
          <>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 600 }}>
              Repository Path
            </label>
            <input
              id="input-local-path"
              className="input"
              placeholder="C:\Users\you\projects\my-repo"
              value={localPath}
              onChange={e => setLocalPath(e.target.value)}
            />
            <button
              className="btn btn-secondary"
              style={{ alignSelf: 'flex-start', fontSize: '0.8rem' }}
              onClick={loadMock}
            >
              Use Mock Repo (for testing)
            </button>
          </>
        ) : (
          <>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 600 }}>
              GitHub Repository URL
            </label>
            <input
              id="input-github-url"
              className="input"
              placeholder="https://github.com/org/repo"
              value={githubUrl}
              onChange={e => setGithubUrl(e.target.value)}
            />
          </>
        )}

        <button
          id="btn-load-repo"
          className="btn btn-primary"
          disabled={loading || (tab === 'local' ? !localPath.trim() : !githubUrl.trim())}
          onClick={handleLoad}
          style={{ alignSelf: 'flex-start' }}
        >
          {loading ? <Loader2 size={15} className="spin-icon" style={{ animation: 'spin 0.7s linear infinite' }} /> : null}
          {loading ? 'Scanning…' : 'Load & Scan Repository'}
        </button>
      </div>

      {/* Status */}
      {status && (
        <div className="card animate-fade" style={{
          borderColor: status.type === 'success' ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)',
          background: status.type === 'success' ? 'rgba(16,185,129,0.05)' : 'rgba(239,68,68,0.05)',
          display: 'flex', gap: 10, alignItems: 'flex-start',
        }}>
          {status.type === 'success'
            ? <CheckCircle2 size={18} style={{ color: 'var(--success)', flexShrink: 0, marginTop: 1 }} />
            : <AlertCircle size={18} style={{ color: 'var(--danger)', flexShrink: 0, marginTop: 1 }} />}
          <span style={{ fontSize: '0.875rem', color: status.type === 'success' ? 'var(--success)' : 'var(--danger)' }}>
            {status.msg}
          </span>
        </div>
      )}

      {/* Scan stats */}
      {scanResult && (
        <div className="stats-grid animate-fade">
          <div className="stat-card">
            <div className="stat-value">{scanResult.total_files}</div>
            <div className="stat-label">Files Scanned</div>
          </div>
          <div className="stat-card">
            <div className="stat-value" style={{ color: 'var(--accent-2)' }}>
              {scanResult.index?.chunks_indexed ?? '—'}
            </div>
            <div className="stat-label">Chunks Indexed</div>
          </div>
          <div className="stat-card">
            <div className="stat-value" style={{ color: 'var(--accent-3)' }}>
              {scanResult.index?.dimension ?? '—'}
            </div>
            <div className="stat-label">Dimensions</div>
          </div>
        </div>
      )}
    </div>
  );
}
