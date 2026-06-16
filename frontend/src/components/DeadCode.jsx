import React, { useState } from 'react';
import { Code2, Loader2, RefreshCw } from 'lucide-react';
import axios from 'axios';

const API = 'http://localhost:8000';

export default function DeadCode({ repo }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const detect = async () => {
    if (!repo) return;
    setLoading(true); setError(''); setResult(null);
    try {
      const res = await axios.post(`${API}/api/graph/dead-code`, { repo_path: repo });
      setResult(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  if (!repo) {
    return (
      <div className="empty-state animate-fade">
        <div className="empty-icon">🧹</div>
        <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>No repository loaded</h3>
        <p>Load a repository to detect dead code.</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }} className="animate-fade">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 4 }}>Dead Code Detector</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.84rem' }}>
            Finds files with zero in-degree in the dependency graph — nothing imports them.
          </p>
        </div>
        <button id="btn-detect-dead" className="btn btn-primary" onClick={detect} disabled={loading}>
          {loading ? <Loader2 size={15} style={{ animation: 'spin 0.7s linear infinite' }} /> : <Code2 size={15} />}
          {loading ? 'Scanning…' : 'Detect Dead Code'}
        </button>
      </div>

      {loading && (
        <div className="loading-spinner"><div className="spinner" />Analyzing dependency graph…</div>
      )}
      {error && (
        <div className="card" style={{ borderColor: 'rgba(239,68,68,0.3)', color: 'var(--danger)', fontSize: '0.875rem' }}>❌ {error}</div>
      )}

      {result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }} className="animate-fade">
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-value" style={{ color: result.count > 0 ? 'var(--warning)' : 'var(--success)' }}>
                {result.count}
              </div>
              <div className="stat-label">Unused Files</div>
            </div>
          </div>

          {result.count === 0 ? (
            <div className="card" style={{ textAlign: 'center', padding: '32px', color: 'var(--success)' }}>
              <div style={{ fontSize: '2rem', marginBottom: 8 }}>✅</div>
              <strong>No dead code found!</strong>
              <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginTop: 6 }}>
                All files appear to be imported or referenced somewhere.
              </p>
            </div>
          ) : (
            <div className="card">
              <div className="card-title">Unused Files ({result.count})</div>
              <div className="file-list">
                {result.unused_files.map((item, i) => (
                  <div key={i} className="file-item" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 6 }}>
                    <span className="file-path">{item.file}</span>
                    <div className="file-tags">
                      {item.language && <span className="tag">{item.language}</span>}
                      {item.functions?.map((f, fi) => (
                        <span key={fi} className="tag" style={{ color: 'var(--accent)' }}>fn: {f}</span>
                      ))}
                      {item.classes?.map((c, ci) => (
                        <span key={ci} className="tag" style={{ color: 'var(--accent-2)' }}>class: {c}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
