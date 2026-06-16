import React, { useState } from 'react';
import { AlertTriangle, Loader2, FileWarning } from 'lucide-react';
import axios from 'axios';

const API = 'http://localhost:8000';

export default function ImpactDashboard({ repo }) {
  const [targetFile, setTargetFile] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const analyze = async () => {
    if (!targetFile.trim() || !repo) return;
    setLoading(true); setError(''); setResult(null);
    try {
      const res = await axios.post(`${API}/api/agents/impact`, {
        target_file: targetFile.trim(),
        repo_path: repo,
      });
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
        <div className="empty-icon">⚠️</div>
        <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>No repository loaded</h3>
        <p>Load a repository to run impact analysis.</p>
      </div>
    );
  }

  const impact = result?.impact;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }} className="animate-fade">
      <div>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 4 }}>Impact Analysis</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.84rem' }}>
          Enter a file path to see what breaks if you modify it.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 10 }}>
        <input
          id="impact-input"
          className="input"
          placeholder="e.g. backend/auth.py"
          value={targetFile}
          onChange={e => setTargetFile(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && analyze()}
        />
        <button id="btn-analyze" className="btn btn-primary" onClick={analyze} disabled={loading || !targetFile.trim()}>
          {loading ? <Loader2 size={15} style={{ animation: 'spin 0.7s linear infinite' }} /> : <AlertTriangle size={15} />}
          {loading ? 'Analyzing…' : 'Analyze Impact'}
        </button>
      </div>

      {loading && (
        <div className="loading-spinner"><div className="spinner" />Traversing dependency graph…</div>
      )}

      {error && (
        <div className="card" style={{ borderColor: 'rgba(239,68,68,0.3)', color: 'var(--danger)', fontSize: '0.875rem' }}>❌ {error}</div>
      )}

      {impact && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }} className="animate-fade">
          {/* Risk header */}
          <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <FileWarning size={28} style={{ color: 'var(--warning)', flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 4 }}>Modifying</div>
              <div className="file-path" style={{ fontSize: '0.95rem', marginBottom: 8 }}>{impact.target}</div>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <span className={`risk-badge risk-${impact.risk}`}>{impact.risk} Risk</span>
                <span style={{ fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
                  {impact.affected_count} file(s) affected
                </span>
              </div>
            </div>
          </div>

          {/* Stats */}
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-value">{impact.affected_count}</div>
              <div className="stat-label">Affected Files</div>
            </div>
            <div className="stat-card">
              <div className="stat-value" style={{ color: 'var(--warning)' }}>{impact.affected_routes?.length ?? 0}</div>
              <div className="stat-label">Affected Routes</div>
            </div>
            <div className="stat-card">
              <div className={`stat-value risk-${impact.risk}`} style={{ background: 'none', border: 'none', padding: 0 }}>
                {impact.risk}
              </div>
              <div className="stat-label">Risk Level</div>
            </div>
          </div>

          {/* Risk explanation */}
          {result.risk_explanation && (
            <div className="card">
              <div className="card-title">Risk Assessment</div>
              <div className="prose" style={{ whiteSpace: 'pre-wrap' }}>{result.risk_explanation}</div>
            </div>
          )}

          {/* Affected routes */}
          {impact.affected_routes?.length > 0 && (
            <div className="card">
              <div className="card-title">Affected API Routes</div>
              <div className="file-list">
                {impact.affected_routes.map((r, i) => (
                  <div key={i} className="file-item">
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <span style={{
                        padding: '2px 8px', borderRadius: 4, fontSize: '0.7rem', fontWeight: 700,
                        background: r.method === 'GET' ? 'rgba(16,185,129,0.15)' : 'rgba(99,102,241,0.15)',
                        color: r.method === 'GET' ? 'var(--success)' : 'var(--accent)',
                        border: `1px solid ${r.method === 'GET' ? 'rgba(16,185,129,0.3)' : 'rgba(99,102,241,0.3)'}`,
                      }}>{r.method}</span>
                      <span className="file-path">{r.path}</span>
                    </div>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{r.file}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Affected files */}
          {impact.affected_files?.length > 0 && (
            <div className="card">
              <div className="card-title">Affected Files ({impact.affected_files.length})</div>
              <div className="file-list">
                {impact.affected_files.map((f, i) => (
                  <div key={i} className="file-item">
                    <span className="file-path">{f}</span>
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
