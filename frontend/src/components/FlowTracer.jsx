import React, { useState } from 'react';
import { Zap, Loader2, ArrowDown } from 'lucide-react';
import axios from 'axios';

const API = 'http://localhost:8000';

const PRESETS = [
  'Trace authentication flow',
  'Trace payment processing',
  'Trace user registration flow',
  'Trace API request lifecycle',
];

function parseFlowSteps(text) {
  const lines = text.split('\n').filter(l => l.trim());
  const steps = [];
  for (const line of lines) {
    const match = line.match(/^(\d+)\.\s+(.+)/);
    if (match) steps.push(match[2]);
  }
  return steps.length > 0 ? steps : null;
}

export default function FlowTracer({ repo, indexName }) {
  const [feature, setFeature] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const trace = async (f) => {
    const q = f || feature;
    if (!q.trim() || !repo) return;
    setFeature(q);
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await axios.post(`${API}/api/agents/flow`, {
        feature: q,
        repo_path: repo,
        index_name: indexName,
      });
      setResult(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  const flowSteps = result ? parseFlowSteps(result.explanation) : null;

  if (!repo) {
    return (
      <div className="empty-state animate-fade">
        <div className="empty-icon">⚡</div>
        <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>No repository loaded</h3>
        <p>Load a repository to trace feature flows.</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }} className="animate-fade">
      <div>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 4 }}>Feature Flow Tracer</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.84rem' }}>
          Trace any feature from frontend entry point to database through the call stack.
        </p>
      </div>

      {/* Presets */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {PRESETS.map((p, i) => (
          <button key={i} className="btn btn-secondary" style={{ fontSize: '0.78rem', padding: '6px 12px' }} onClick={() => trace(p)}>
            {p}
          </button>
        ))}
      </div>

      {/* Input */}
      <div style={{ display: 'flex', gap: 10 }}>
        <input
          id="flow-input"
          className="input"
          placeholder="e.g. Trace the payment flow, authentication, user signup…"
          value={feature}
          onChange={e => setFeature(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && trace()}
        />
        <button id="btn-trace" className="btn btn-primary" onClick={() => trace()} disabled={loading || !feature.trim()}>
          {loading ? <Loader2 size={15} style={{ animation: 'spin 0.7s linear infinite' }} /> : <Zap size={15} />}
          {loading ? 'Tracing…' : 'Trace'}
        </button>
      </div>

      {loading && (
        <div className="loading-spinner">
          <div className="spinner" />
          Searching code references and tracing flow…
        </div>
      )}

      {error && (
        <div className="card" style={{ borderColor: 'rgba(239,68,68,0.3)', color: 'var(--danger)', fontSize: '0.875rem' }}>❌ {error}</div>
      )}

      {result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }} className="animate-fade">
          {/* Visual flow steps */}
          {flowSteps ? (
            <div className="card">
              <div className="card-title">Flow Trace</div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 0 }}>
                {flowSteps.map((step, i) => (
                  <React.Fragment key={i}>
                    <div style={{
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border-active)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '10px 16px',
                      fontSize: '0.84rem',
                      color: 'var(--text-primary)',
                      width: '100%',
                    }}>
                      <span style={{ color: 'var(--accent)', fontWeight: 700, marginRight: 8 }}>{i + 1}.</span>
                      {step}
                    </div>
                    {i < flowSteps.length - 1 && (
                      <div style={{ display: 'flex', justifyContent: 'center', width: '100%', padding: '4px 0' }}>
                        <ArrowDown size={16} style={{ color: 'var(--text-muted)' }} />
                      </div>
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          ) : (
            <div className="card">
              <div className="card-title">Analysis</div>
              <div className="prose" style={{ whiteSpace: 'pre-wrap' }}>{result.explanation}</div>
            </div>
          )}

          {/* Code matches */}
          {result.search_results?.length > 0 && (
            <div className="card">
              <div className="card-title">Code References Found ({result.search_results.length})</div>
              <div className="file-list">
                {result.search_results.slice(0, 10).map((m, i) => (
                  <div key={i} className="file-item">
                    <span className="file-path">{m.file}:{m.line}</span>
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {m.snippet}
                    </span>
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
