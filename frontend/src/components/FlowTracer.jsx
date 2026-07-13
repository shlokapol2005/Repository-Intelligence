import React, { useState, useEffect, useRef } from 'react';
import { Zap, Loader2, ArrowDown, GitBranch, X, Maximize2 } from 'lucide-react';
import axios from 'axios';
import mermaid from 'mermaid';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Default presets shown before repo is loaded / graph has no routes
const DEFAULT_PRESETS = [
  'Trace authentication flow',
  'Trace API request lifecycle',
  'Trace data processing pipeline',
  'Trace error handling flow',
];

// Node type styling for the step cards
const TYPE_META = {
  api_route:  { icon: '🌐', label: 'API Route',   color: '#34d399' },
  middleware: { icon: '🔒', label: 'Middleware',   color: '#e0a458' },
  service:    { icon: '⚙️', label: 'Service',      color: '#2dd4bf' },
  database:   { icon: '🗄️', label: 'Database',     color: '#6ee7b7' },
  external:   { icon: '🔌', label: 'External API', color: '#f0c07a' },
  util:       { icon: '🔧', label: 'Utility',      color: '#5a6d64' },
};

/** Build a Mermaid flowchart string from structured steps */
function buildMermaid(steps) {
  if (!steps?.length) return '';
  const lines = ['flowchart TD'];
  const colors = {
    api_route: '#059669', middleware: '#b97e34', service: '#0d9488',
    database: '#047857', external: '#a37327', util: '#334b42',
  };

  steps.forEach((s, i) => {
    const id = `N${i}`;
    const file = (s.file || '').split('/').pop();          // basename only
    const fn   = s.function ? `\n${s.function}` : '';
    const label = `${s.file}${fn ? '\n' + s.function : ''}`.replace(/"/g, "'");
    lines.push(`    ${id}["${label}"]`);
    if (i > 0) lines.push(`    N${i - 1} --> ${id}`);
  });

  // Color classes
  steps.forEach((s, i) => {
    const c = colors[s.type] || '#374151';
    lines.push(`    style N${i} fill:${c},stroke:#fff,color:#fff`);
  });

  return lines.join('\n');
}

/** Full-screen Mermaid diagram modal */
function MermaidModal({ steps, onClose }) {
  const ref = useRef(null);

  useEffect(() => {
    mermaid.initialize({ startOnLoad: false, theme: 'dark', flowchart: { curve: 'basis' } });
    const code = buildMermaid(steps);
    if (code && ref.current) {
      ref.current.removeAttribute('data-processed');
      ref.current.textContent = code;
      mermaid.run({ nodes: [ref.current] }).catch(() => {});
    }
  }, [steps]);

  // Close on Escape
  useEffect(() => {
    const handler = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          position: 'relative',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-active)',
          borderRadius: 'var(--radius)',
          padding: 32,
          maxWidth: '90vw', maxHeight: '90vh',
          overflow: 'auto',
          minWidth: 500,
        }}
      >
        <button
          onClick={onClose}
          style={{
            position: 'absolute', top: 12, right: 12,
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-muted)',
          }}
        >
          <X size={20} />
        </button>
        <div style={{ fontWeight: 700, fontSize: '1rem', marginBottom: 20 }}>
          🗺️ Feature Flow Diagram
        </div>

        {/* Legend */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
          {Object.entries(TYPE_META).map(([k, v]) => (
            <span key={k} style={{
              background: v.color + '22', border: `1px solid ${v.color}55`,
              borderRadius: 6, padding: '2px 10px', fontSize: '0.75rem',
              color: v.color, fontWeight: 600,
            }}>
              {v.icon} {v.label}
            </span>
          ))}
        </div>

        <div className="mermaid" ref={ref} />
      </div>
    </div>
  );
}

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
  const [presets, setPresets] = useState(DEFAULT_PRESETS);
  const [showDiagram, setShowDiagram] = useState(false);

  // #16 — Dynamically build presets from actual API routes in the repo
  useEffect(() => {
    if (!repo) return;
    axios.post(`${API}/api/graph/full`, { repo_path: repo })
      .then(res => {
        const nodes = res.data?.nodes || [];
        const routes = [];
        for (const node of nodes) {
          for (const route of (node.api_routes || [])) {
            if (route.method && route.path) {
              routes.push(`Trace ${route.method} ${route.path}`);
            }
          }
          if (routes.length >= 6) break;
        }
        if (routes.length >= 2) setPresets(routes.slice(0, 6));
      })
      .catch(() => {}); // silently fall back to defaults
  }, [repo]);

  const trace = async (f) => {
    const q = f || feature;
    if (!q.trim() || !repo) return;
    setFeature(q);
    setLoading(true);
    setError('');
    setResult(null);
    setShowDiagram(false);
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

  const hasStructured = result?.steps_structured?.length > 0;
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
          Trace any feature through your codebase — from API route to database, following actual import chains.
        </p>
      </div>

      {/* #16 — Dynamic presets from actual repo routes */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {presets.map((p, i) => (
          <button
            key={i}
            className="btn btn-secondary"
            style={{ fontSize: '0.78rem', padding: '6px 12px' }}
            onClick={() => trace(p)}
          >
            {p}
          </button>
        ))}
      </div>

      {/* Input */}
      <div style={{ display: 'flex', gap: 10 }}>
        <input
          id="flow-input"
          className="input"
          placeholder="e.g. Trace the authentication flow, scan endpoint, user registration…"
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
          Searching codebase, expanding dependency graph, tracing flow…
        </div>
      )}

      {error && (
        <div className="card" style={{ borderColor: 'rgba(239,68,68,0.3)', color: 'var(--danger)', fontSize: '0.875rem' }}>❌ {error}</div>
      )}

      {result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }} className="animate-fade">

          {/* #12 — View as Diagram button (only when structured steps exist) */}
          {hasStructured && (
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setShowDiagram(true)}
                style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.82rem' }}
              >
                <Maximize2 size={14} />
                View as Diagram
              </button>
            </div>
          )}

          {/* Structured step cards */}
          {hasStructured ? (
            <div className="card">
              <div className="card-title">Flow Trace</div>

              {/* Disclaimer banner — shown when no literal keyword match was found */}
              {result.disclaimer && (
                <div style={{
                  background: 'rgba(245, 158, 11, 0.1)',
                  border: '1px solid rgba(245, 158, 11, 0.35)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '10px 14px',
                  fontSize: '0.82rem',
                  color: '#f59e0b',
                  marginBottom: 16,
                  lineHeight: 1.5,
                }}>
                  {result.disclaimer}
                </div>
              )}

              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 0 }}>
                {result.steps_structured.map((s, i) => {
                  const meta = TYPE_META[s.type] || TYPE_META.util;
                  return (
                    <React.Fragment key={i}>
                      <div style={{
                        background: 'var(--bg-elevated)',
                        border: `1px solid ${meta.color}55`,
                        borderRadius: 'var(--radius-sm)',
                        padding: '12px 16px',
                        width: '100%',
                      }}>
                        {/* Header row */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                          <span style={{
                            background: meta.color + '22',
                            border: `1px solid ${meta.color}55`,
                            borderRadius: 4, padding: '1px 8px',
                            fontSize: '0.7rem', fontWeight: 700, color: meta.color,
                          }}>
                            {meta.icon} {meta.label}
                          </span>
                          <span style={{ color: 'var(--accent)', fontWeight: 700, fontSize: '0.84rem' }}>
                            Step {s.step}
                          </span>
                        </div>
                        {/* File + function */}
                        <div style={{ fontFamily: 'monospace', fontSize: '0.82rem', color: 'var(--text-primary)', marginBottom: 4 }}>
                          {s.file}{s.function ? ` → ${s.function}` : ''}
                        </div>
                        {/* Action description */}
                        <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
                          {s.action}
                        </div>
                      </div>
                      {i < result.steps_structured.length - 1 && (
                        <div style={{ display: 'flex', justifyContent: 'center', width: '100%', padding: '4px 0' }}>
                          <ArrowDown size={16} style={{ color: 'var(--text-muted)' }} />
                        </div>
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
            </div>
          ) : flowSteps ? (
            /* Fallback: text steps from explanation */
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
            /* Raw text fallback */
            <div className="card">
              <div className="card-title">Analysis</div>
              <div className="prose" style={{ whiteSpace: 'pre-wrap' }}>{result.explanation}</div>
            </div>
          )}

          {/* Agent execution steps */}
          {result.steps?.length > 0 && (
            <div className="card">
              <div className="card-title" style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Agent Steps</div>
              <div className="steps-list">
                {result.steps.map((s, i) => (
                  <div key={i} className="step-item">{s}</div>
                ))}
              </div>
            </div>
          )}

          {/* Code references */}
          {result.search_results?.length > 0 && (
            <div className="card">
              <div className="card-title">
                <GitBranch size={14} style={{ display: 'inline', marginRight: 6 }} />
                Files Involved ({result.search_results.length})
              </div>
              <div className="file-list">
                {[...new Map(result.search_results.map(m => [m.file, m])).values()]
                  .slice(0, 12)
                  .map((m, i) => (
                    <div key={i} className="file-item">
                      <span className="file-path">{m.file}</span>
                      {m.snippet && (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {m.snippet}
                        </span>
                      )}
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* #12 — Full-screen Mermaid diagram modal */}
      {showDiagram && result?.steps_structured?.length > 0 && (
        <MermaidModal steps={result.steps_structured} onClose={() => setShowDiagram(false)} />
      )}
    </div>
  );
}
