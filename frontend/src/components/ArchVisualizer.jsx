import React, { useState, useEffect, useRef } from 'react';
import { GitBranch, RefreshCw, Loader2 } from 'lucide-react';
import mermaid from 'mermaid';
import axios from 'axios';

const API = 'http://localhost:8000';

mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  themeVariables: {
    primaryColor: '#1c2035',
    primaryTextColor: '#f1f5f9',
    primaryBorderColor: '#6366f1',
    lineColor: '#4b5563',
    secondaryColor: '#161929',
    tertiaryColor: '#0f1220',
    background: '#0a0c14',
    mainBkg: '#1c2035',
    nodeBorder: '#6366f1',
  },
});

function MermaidRenderer({ diagram }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!diagram || !ref.current) return;
    const id = `mermaid-${Date.now()}`;
    ref.current.innerHTML = '';
    mermaid.render(id, diagram).then(({ svg }) => {
      if (ref.current) ref.current.innerHTML = svg;
    }).catch(() => {
      if (ref.current) ref.current.innerHTML = `<pre style="color:var(--danger);font-size:0.8rem">${diagram}</pre>`;
    });
  }, [diagram]);

  return <div ref={ref} style={{ minHeight: 200 }} />;
}

export default function ArchVisualizer({ repo }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const generate = async () => {
    if (!repo) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await axios.post(`${API}/api/agents/architecture`, { repo_path: repo });
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
        <div className="empty-icon">🏗️</div>
        <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>No repository loaded</h3>
        <p>Load a repository first to generate architecture diagrams.</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }} className="animate-fade">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 4 }}>Architecture Diagram</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.84rem' }}>
            AI-enhanced dependency graph rendered as an interactive Mermaid diagram.
          </p>
        </div>
        <button id="btn-gen-arch" className="btn btn-primary" onClick={generate} disabled={loading}>
          {loading ? <Loader2 size={15} style={{ animation: 'spin 0.7s linear infinite' }} /> : <GitBranch size={15} />}
          {loading ? 'Generating…' : 'Generate Architecture'}
        </button>
      </div>

      {loading && (
        <div className="loading-spinner">
          <div className="spinner" />
          Building dependency graph and enhancing with Gemini…
        </div>
      )}

      {error && (
        <div className="card" style={{ borderColor: 'rgba(239,68,68,0.3)', color: 'var(--danger)', fontSize: '0.875rem' }}>
          ❌ {error}
        </div>
      )}

      {result && (
        <>
          <div className="mermaid-container animate-fade">
            <MermaidRenderer diagram={result.mermaid} />
          </div>

          {result.summary && (
            <div className="card">
              <div className="card-title">Architecture Summary</div>
              <div className="prose" style={{ whiteSpace: 'pre-wrap' }}>{result.summary}</div>
            </div>
          )}

          {result.steps?.length > 0 && (
            <div className="card">
              <div className="card-title">Agent Steps</div>
              <div className="steps-list">
                {result.steps.map((s, i) => <div key={i} className="step-item">{s}</div>)}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
