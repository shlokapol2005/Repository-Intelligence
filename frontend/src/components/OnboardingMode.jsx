import React, { useState } from 'react';
import { BookOpen, Loader2 } from 'lucide-react';
import axios from 'axios';

const API = 'http://localhost:8000';

function parseModules(text) {
  if (!text) return [];
  const sections = text.split(/\n##\s+/).filter(Boolean);
  return sections.map((section, i) => {
    const lines = section.split('\n');
    const title = lines[0].trim();
    const body = lines.slice(1).join('\n').trim();
    return { id: i, title, body };
  });
}

export default function OnboardingMode({ repo }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [openModule, setOpenModule] = useState(0);

  const generate = async () => {
    if (!repo) return;
    setLoading(true); setError(''); setResult(null);
    try {
      const res = await axios.post(`${API}/api/agents/onboard`, { repo_path: repo });
      setResult(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  const modules = result ? parseModules(result.learning_path) : [];

  if (!repo) {
    return (
      <div className="empty-state animate-fade">
        <div className="empty-icon">📚</div>
        <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>No repository loaded</h3>
        <p>Load a repository to generate an onboarding guide.</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }} className="animate-fade">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 4 }}>Onboarding Mode</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.84rem' }}>
            AI-generated learning path based on the repository's core modules and architecture.
          </p>
        </div>
        <button id="btn-gen-onboard" className="btn btn-primary" onClick={generate} disabled={loading}>
          {loading ? <Loader2 size={15} style={{ animation: 'spin 0.7s linear infinite' }} /> : <BookOpen size={15} />}
          {loading ? 'Generating…' : 'Generate Learning Path'}
        </button>
      </div>

      {loading && (
        <div className="loading-spinner"><div className="spinner" />Analyzing modules and building learning path with Gemini…</div>
      )}
      {error && (
        <div className="card" style={{ borderColor: 'rgba(239,68,68,0.3)', color: 'var(--danger)', fontSize: '0.875rem' }}>❌ {error}</div>
      )}

      {modules.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }} className="animate-fade">
          {modules.map((mod, i) => (
            <div
              key={mod.id}
              className="onboard-module"
              style={{ cursor: 'pointer' }}
              onClick={() => setOpenModule(openModule === i ? -1 : i)}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <h3>
                  <span style={{ marginRight: 8, opacity: 0.6, fontSize: '0.8rem' }}>Module {i + 1}</span>
                  {mod.title}
                </h3>
                <span style={{ color: 'var(--text-muted)', fontSize: '1.2rem' }}>
                  {openModule === i ? '−' : '+'}
                </span>
              </div>
              {openModule === i && (
                <div className="prose" style={{ marginTop: 12, whiteSpace: 'pre-wrap', borderTop: '1px solid var(--border)', paddingTop: 12 }}>
                  {mod.body}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {result && modules.length === 0 && (
        <div className="card">
          <div className="card-title">Learning Path</div>
          <div className="prose" style={{ whiteSpace: 'pre-wrap' }}>{result.learning_path}</div>
        </div>
      )}
    </div>
  );
}
