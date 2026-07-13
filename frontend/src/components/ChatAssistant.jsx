import React, { useState, useRef, useEffect } from 'react';
import {
  Send, Bot, User, FileCode, ChevronDown, ChevronUp,
  Search, Zap, AlertTriangle, Loader2, Maximize2, ArrowDown,
  GitBranch, X, FileWarning,
} from 'lucide-react';
import axios from 'axios';
import mermaid from 'mermaid';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/* ─────────────────────────────────────────────────────────────────
   MODES — Q&A, Flow, and Impact are all "type something, get an
   answer" interactions, unified here into one chat surface. Each
   mode keeps its own conversation thread and calls the exact same
   endpoint the original standalone page used — only the shell is
   shared, the logic per mode is untouched.
   ───────────────────────────────────────────────────────────────── */
const MODES = [
  {
    id: 'qa', label: 'Q&A', icon: Search,
    placeholder: 'Ask anything about this codebase…',
    introTitle: 'Ask anything about this codebase',
    introText: "Authentication flows, feature implementations, dependencies, architecture patterns — ask in plain English and I'll search the repo for the answer.",
  },
  {
    id: 'flow', label: 'Flow', icon: Zap,
    placeholder: 'e.g. Trace the authentication flow, scan endpoint, user registration…',
    introTitle: 'Trace a feature end-to-end',
    introText: "Tell me a feature or API route and I'll trace it through your codebase — from entrypoint to database.",
  },
  {
    id: 'impact', label: 'Impact', icon: AlertTriangle,
    placeholder: 'e.g. backend/auth.py',
    introTitle: 'See the blast radius before you touch it',
    introText: "Give me a file path and I'll show you exactly what breaks — risk level, affected files, affected routes.",
  },
];

const DEFAULT_FLOW_PRESETS = [
  'Trace authentication flow',
  'Trace API request lifecycle',
  'Trace data processing pipeline',
  'Trace error handling flow',
];

const QA_SUGGESTIONS = [
  'Explain the authentication flow',
  'Where is JWT validation implemented?',
  'How does payment processing work?',
  'What are the main API routes?',
];

const FLOW_TYPE_META = {
  api_route:  { icon: '🌐', label: 'API Route',   color: '#34d399' },
  middleware: { icon: '🔒', label: 'Middleware',   color: '#e0a458' },
  service:    { icon: '⚙️', label: 'Service',      color: '#2dd4bf' },
  database:   { icon: '🗄️', label: 'Database',     color: '#6ee7b7' },
  external:   { icon: '🔌', label: 'External API', color: '#f0c07a' },
  util:       { icon: '🔧', label: 'Utility',      color: '#5a6d64' },
};

/* Centered "empty" panel shown before the first message in a mode's thread */
function ModeIntro({ meta, suggestions, onPick }) {
  const Icon = meta.icon;
  return (
    <div className="chat-empty">
      <div className="chat-empty-icon"><Icon size={22} /></div>
      <h3 className="chat-empty-title">{meta.introTitle}</h3>
      <p className="chat-empty-text">{meta.introText}</p>
      {suggestions?.length > 0 && (
        <div className="chat-empty-suggestions">
          {suggestions.map((s, i) => (
            <button key={i} className="btn btn-secondary" style={{ fontSize: '0.78rem', padding: '6px 12px' }} onClick={() => onPick(s)}>{s}</button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
   Helpers (carried over verbatim from the original standalone pages)
   ───────────────────────────────────────────────────────────────── */
function formatAnswer(text) {
  return text
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
      `<pre><code>${code.replace(/</g, '&lt;')}</code></pre>`)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>');
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

function buildMermaid(steps) {
  if (!steps?.length) return '';
  const lines = ['flowchart TD'];
  const colors = {
    api_route: '#059669', middleware: '#b97e34', service: '#0d9488',
    database: '#047857', external: '#a37327', util: '#334b42',
  };
  steps.forEach((s, i) => {
    const id = `N${i}`;
    const fn = s.function ? `\n${s.function}` : '';
    const label = `${s.file}${fn}`.replace(/"/g, "'");
    lines.push(`    ${id}["${label}"]`);
    if (i > 0) lines.push(`    N${i - 1} --> ${id}`);
  });
  steps.forEach((s, i) => {
    const c = colors[s.type] || '#374151';
    lines.push(`    style N${i} fill:${c},stroke:#fff,color:#fff`);
  });
  return lines.join('\n');
}

function SourceFiles({ files }) {
  const [open, setOpen] = useState(false);
  if (!files?.length) return null;
  return (
    <div style={{ marginTop: 10 }}>
      <button
        style={{ background: 'none', border: 'none', color: 'var(--accent)', fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}
        onClick={() => setOpen(v => !v)}
      >
        <FileCode size={13} />
        {files.length} source file(s) referenced
        {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>
      {open && (
        <div className="file-list" style={{ marginTop: 8 }}>
          {files.map((f, i) => (
            <div key={i} className="file-item"><span className="file-path">{f}</span></div>
          ))}
        </div>
      )}
    </div>
  );
}

/* Full-screen Mermaid diagram modal — reused verbatim from FlowTracer */
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

  useEffect(() => {
    const handler = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{ position: 'relative', background: 'var(--bg-surface)', border: '1px solid var(--border-active)', borderRadius: 'var(--radius)', padding: 32, maxWidth: '90vw', maxHeight: '90vh', overflow: 'auto', minWidth: 500 }}
      >
        <button onClick={onClose} style={{ position: 'absolute', top: 12, right: 12, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
          <X size={20} />
        </button>
        <div style={{ fontWeight: 700, fontSize: '1rem', marginBottom: 20 }}>🗺️ Feature Flow Diagram</div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
          {Object.entries(FLOW_TYPE_META).map(([k, v]) => (
            <span key={k} style={{ background: v.color + '22', border: `1px solid ${v.color}55`, borderRadius: 6, padding: '2px 10px', fontSize: '0.75rem', color: v.color, fontWeight: 600 }}>
              {v.icon} {v.label}
            </span>
          ))}
        </div>
        <div className="mermaid" ref={ref} />
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
   Per-mode assistant answer renderers
   ───────────────────────────────────────────────────────────────── */
function QAAnswer({ msg }) {
  return (
    <>
      <div className="prose" dangerouslySetInnerHTML={{ __html: formatAnswer(msg.text) }} />
      {msg.steps?.length > 0 && (
        <div className="steps-list" style={{ marginTop: 12 }}>
          {msg.steps.map((s, si) => <div key={si} className="step-item">{s}</div>)}
        </div>
      )}
      <SourceFiles files={msg.sources} />
    </>
  );
}

function FlowAnswer({ msg, onViewDiagram }) {
  if (msg.error) return <span style={{ color: 'var(--danger)' }}>❌ {msg.error}</span>;
  const result = msg.data;
  const hasStructured = result?.steps_structured?.length > 0;
  const flowSteps = result ? parseFlowSteps(result.explanation) : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {hasStructured && (
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn btn-secondary" onClick={() => onViewDiagram(result.steps_structured)} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.78rem' }}>
            <Maximize2 size={13} /> View as Diagram
          </button>
        </div>
      )}

      {result.disclaimer && (
        <div style={{ background: 'rgba(224,164,88,0.1)', border: '1px solid rgba(224,164,88,0.35)', borderRadius: 'var(--radius-sm)', padding: '10px 14px', fontSize: '0.8rem', color: 'var(--warm)', lineHeight: 1.5 }}>
          {result.disclaimer}
        </div>
      )}

      {hasStructured ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 0 }}>
          {result.steps_structured.map((s, i) => {
            const meta = FLOW_TYPE_META[s.type] || FLOW_TYPE_META.util;
            return (
              <React.Fragment key={i}>
                <div style={{ background: 'var(--bg-base)', border: `1px solid ${meta.color}55`, borderRadius: 'var(--radius-sm)', padding: '12px 16px', width: '100%' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span style={{ background: meta.color + '22', border: `1px solid ${meta.color}55`, borderRadius: 4, padding: '1px 8px', fontSize: '0.7rem', fontWeight: 700, color: meta.color }}>
                      {meta.icon} {meta.label}
                    </span>
                    <span style={{ color: 'var(--accent)', fontWeight: 700, fontSize: '0.8rem' }}>Step {s.step}</span>
                  </div>
                  <div style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: 'var(--text-primary)', marginBottom: 4 }}>
                    {s.file}{s.function ? ` → ${s.function}` : ''}
                  </div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>{s.action}</div>
                </div>
                {i < result.steps_structured.length - 1 && (
                  <div style={{ display: 'flex', justifyContent: 'center', width: '100%', padding: '4px 0' }}>
                    <ArrowDown size={14} style={{ color: 'var(--text-muted)' }} />
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      ) : flowSteps ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 0 }}>
          {flowSteps.map((step, i) => (
            <React.Fragment key={i}>
              <div style={{ background: 'var(--bg-base)', border: '1px solid var(--border-active)', borderRadius: 'var(--radius-sm)', padding: '10px 16px', fontSize: '0.82rem', color: 'var(--text-primary)', width: '100%' }}>
                <span style={{ color: 'var(--accent)', fontWeight: 700, marginRight: 8 }}>{i + 1}.</span>{step}
              </div>
              {i < flowSteps.length - 1 && (
                <div style={{ display: 'flex', justifyContent: 'center', width: '100%', padding: '4px 0' }}>
                  <ArrowDown size={14} style={{ color: 'var(--text-muted)' }} />
                </div>
              )}
            </React.Fragment>
          ))}
        </div>
      ) : (
        <div className="prose" style={{ whiteSpace: 'pre-wrap' }}>{result.explanation}</div>
      )}

      {result.steps?.length > 0 && (
        <div>
          <div className="card-title" style={{ marginBottom: 8 }}>Agent Steps</div>
          <div className="steps-list">{result.steps.map((s, i) => <div key={i} className="step-item">{s}</div>)}</div>
        </div>
      )}

      {result.search_results?.length > 0 && (
        <div>
          <div className="card-title" style={{ marginBottom: 8 }}>
            <GitBranch size={13} style={{ display: 'inline', marginRight: 5 }} />
            Files Involved ({result.search_results.length})
          </div>
          <div className="file-list">
            {[...new Map(result.search_results.map(m => [m.file, m])).values()].slice(0, 12).map((m, i) => (
              <div key={i} className="file-item">
                <span className="file-path">{m.file}</span>
                {m.snippet && (
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem', maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {m.snippet}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ImpactAnswer({ msg }) {
  if (msg.error) return <span style={{ color: 'var(--danger)' }}>❌ {msg.error}</span>;
  const result = msg.data;
  const impact = result?.impact;
  if (!impact) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <FileWarning size={24} style={{ color: 'var(--warning)', flexShrink: 0 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: 4 }}>Modifying</div>
          <div className="file-path" style={{ fontSize: '0.9rem', marginBottom: 8 }}>{impact.target}</div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <span className={`risk-badge risk-${impact.risk}`}>{impact.risk} Risk</span>
            <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>{impact.affected_count} file(s) affected</span>
          </div>
        </div>
      </div>

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
          <div className={`stat-value risk-${impact.risk}`} style={{ background: 'none', border: 'none', padding: 0 }}>{impact.risk}</div>
          <div className="stat-label">Risk Level</div>
        </div>
      </div>

      {result.risk_explanation && (
        <div>
          <div className="card-title">Risk Assessment</div>
          <div className="prose" style={{ whiteSpace: 'pre-wrap' }}>{result.risk_explanation}</div>
        </div>
      )}

      {impact.affected_routes?.length > 0 && (
        <div>
          <div className="card-title">Affected API Routes</div>
          <div className="file-list">
            {impact.affected_routes.map((r, i) => (
              <div key={i} className="file-item">
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={{
                    padding: '2px 8px', borderRadius: 4, fontSize: '0.7rem', fontWeight: 700,
                    background: r.method === 'GET' ? 'rgba(52,211,153,0.15)' : 'rgba(45,212,191,0.15)',
                    color: r.method === 'GET' ? 'var(--success)' : 'var(--accent-3)',
                    border: `1px solid ${r.method === 'GET' ? 'rgba(52,211,153,0.3)' : 'rgba(45,212,191,0.3)'}`,
                  }}>{r.method}</span>
                  <span className="file-path">{r.path}</span>
                </div>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{r.file}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {impact.affected_files?.length > 0 && (
        <div>
          <div className="card-title">Affected Files ({impact.affected_files.length})</div>
          <div className="file-list">
            {impact.affected_files.map((f, i) => <div key={i} className="file-item"><span className="file-path">{f}</span></div>)}
          </div>
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
   MAIN — unified chat surface for Q&A, Flow, Impact
   ───────────────────────────────────────────────────────────────── */
export default function ChatAssistant({ repo, indexName, initialMode }) {
  const [mode, setMode] = useState(initialMode || 'qa');
  const [threads, setThreads] = useState({ qa: [], flow: [], impact: [] });
  const [inputs, setInputs] = useState({ qa: '', flow: '', impact: '' });
  const [loading, setLoading] = useState({ qa: false, flow: false, impact: false });
  const [flowPresets, setFlowPresets] = useState(DEFAULT_FLOW_PRESETS);
  const [impactSuggestions, setImpactSuggestions] = useState([]);
  const [diagramSteps, setDiagramSteps] = useState(null);
  const bottomRef = useRef(null);

  const messages = threads[mode];
  const isLoading = loading[mode];
  const currentMeta = MODES.find(m => m.id === mode);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, mode]);

  // Dynamically build Flow presets from actual API routes in the repo (same effect as original FlowTracer),
  // plus real "try this file" suggestions for Impact mode, sourced from the same graph fetch.
  useEffect(() => {
    if (!repo) return;
    axios.post(`${API}/api/graph/full`, { repo_path: repo })
      .then(res => {
        const nodes = res.data?.nodes || [];
        const routes = [];
        for (const node of nodes) {
          for (const route of (node.api_routes || [])) {
            if (route.method && route.path) routes.push(`Trace ${route.method} ${route.path}`);
          }
          if (routes.length >= 6) break;
        }
        if (routes.length >= 2) setFlowPresets(routes.slice(0, 6));

        const mostConnected = [...nodes]
          .filter(n => n.data?.path)
          .sort((a, b) => ((b.data.in_degree || 0) + (b.data.out_degree || 0)) - ((a.data.in_degree || 0) + (a.data.out_degree || 0)))
          .slice(0, 4)
          .map(n => n.data.path);
        if (mostConnected.length) setImpactSuggestions(mostConnected);
      })
      .catch(() => {});
  }, [repo]);

  const setInput = (v) => setInputs(s => ({ ...s, [mode]: v }));

  const askQA = async (question) => {
    if (!question.trim() || !repo) return;
    setThreads(t => ({ ...t, qa: [...t.qa, { role: 'user', text: question }] }));
    setInputs(s => ({ ...s, qa: '' }));
    setLoading(l => ({ ...l, qa: true }));
    try {
      const res = await axios.post(`${API}/api/agents/qa`, { question, repo_path: repo, index_name: indexName });
      setThreads(t => ({ ...t, qa: [...t.qa, { role: 'assistant', kind: 'qa', text: res.data.answer, sources: res.data.sources || [], steps: res.data.steps || [] }] }));
    } catch (e) {
      setThreads(t => ({ ...t, qa: [...t.qa, { role: 'assistant', kind: 'qa', text: `❌ Error: ${e.response?.data?.detail || e.message}`, sources: [], steps: [] }] }));
    } finally {
      setLoading(l => ({ ...l, qa: false }));
    }
  };

  const traceFlow = async (feature) => {
    if (!feature.trim() || !repo) return;
    setThreads(t => ({ ...t, flow: [...t.flow, { role: 'user', text: feature }] }));
    setInputs(s => ({ ...s, flow: '' }));
    setLoading(l => ({ ...l, flow: true }));
    try {
      const res = await axios.post(`${API}/api/agents/flow`, { feature, repo_path: repo, index_name: indexName });
      setThreads(t => ({ ...t, flow: [...t.flow, { role: 'assistant', kind: 'flow', data: res.data }] }));
    } catch (e) {
      setThreads(t => ({ ...t, flow: [...t.flow, { role: 'assistant', kind: 'flow', error: e.response?.data?.detail || e.message }] }));
    } finally {
      setLoading(l => ({ ...l, flow: false }));
    }
  };

  const analyzeImpact = async (targetFile) => {
    if (!targetFile.trim() || !repo) return;
    setThreads(t => ({ ...t, impact: [...t.impact, { role: 'user', text: targetFile }] }));
    setInputs(s => ({ ...s, impact: '' }));
    setLoading(l => ({ ...l, impact: true }));
    try {
      const res = await axios.post(`${API}/api/agents/impact`, { target_file: targetFile.trim(), repo_path: repo });
      setThreads(t => ({ ...t, impact: [...t.impact, { role: 'assistant', kind: 'impact', data: res.data }] }));
    } catch (e) {
      setThreads(t => ({ ...t, impact: [...t.impact, { role: 'assistant', kind: 'impact', error: e.response?.data?.detail || e.message }] }));
    } finally {
      setLoading(l => ({ ...l, impact: false }));
    }
  };

  const send = () => {
    const value = inputs[mode];
    if (mode === 'qa') return askQA(value);
    if (mode === 'flow') return traceFlow(value);
    return analyzeImpact(value);
  };

  if (!repo) {
    return (
      <div className="empty-state animate-fade">
        <div className="empty-icon">💬</div>
        <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>No repository loaded</h3>
        <p>Load a repository to ask questions, trace feature flows, or run impact analysis.</p>
      </div>
    );
  }

  return (
    <div className="chat-container" style={{ height: 'calc(100vh - 120px)' }}>
      {/* Mode toggle */}
      <div className="mode-toggle-wrap">
        <span className="mode-toggle-label">Choose how to interact</span>
        <div className="mode-toggle">
          {MODES.map(m => {
            const Icon = m.icon;
            return (
              <button key={m.id} className={`mode-toggle-btn ${mode === m.id ? 'active' : ''}`} onClick={() => setMode(m.id)}>
                <Icon size={14} className="tab-icon" /> {m.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* The chat box itself — a single bordered card holding history + input */}
      <div className="chat-box">
        <div className={`chat-messages ${messages.length === 0 ? 'chat-messages--empty' : ''}`}>
          {messages.length === 0 && !isLoading && (
            <ModeIntro
              meta={currentMeta}
              suggestions={mode === 'qa' ? QA_SUGGESTIONS : mode === 'flow' ? flowPresets : impactSuggestions}
              onPick={mode === 'qa' ? askQA : mode === 'flow' ? traceFlow : analyzeImpact}
            />
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`message ${msg.role === 'user' ? 'user' : ''} animate-fade`}>
              <div className="message-avatar">{msg.role === 'user' ? <User size={15} /> : <Bot size={15} />}</div>
              <div className="message-body">
                {msg.role === 'user' && <span>{msg.text}</span>}
                {msg.role === 'assistant' && msg.kind === 'qa' && <QAAnswer msg={msg} />}
                {msg.role === 'assistant' && msg.kind === 'flow' && <FlowAnswer msg={msg} onViewDiagram={setDiagramSteps} />}
                {msg.role === 'assistant' && msg.kind === 'impact' && <ImpactAnswer msg={msg} />}
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="message animate-fade">
              <div className="message-avatar"><Bot size={15} /></div>
              <div className="message-body">
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', color: 'var(--text-muted)', fontSize: '0.84rem' }}>
                  <div className="spinner" />
                  {mode === 'qa' && 'Searching codebase and reasoning with Gemini…'}
                  {mode === 'flow' && 'Searching codebase, expanding dependency graph, tracing flow…'}
                  {mode === 'impact' && 'Traversing dependency graph…'}
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="chat-input-row">
          <input
            id={`${mode}-input`}
            className="input"
            placeholder={currentMeta.placeholder}
            value={inputs[mode]}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
            disabled={isLoading}
          />
          <button
            id={`${mode}-send`}
            className="btn btn-primary"
            onClick={send}
            disabled={isLoading || !inputs[mode].trim()}
            style={{ minWidth: 48 }}
          >
            <Send size={15} />
          </button>
        </div>
      </div>

      {diagramSteps && <MermaidModal steps={diagramSteps} onClose={() => setDiagramSteps(null)} />}
    </div>
  );
}
