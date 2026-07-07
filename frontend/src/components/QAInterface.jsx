import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, FileCode, ChevronDown, ChevronUp } from 'lucide-react';
import axios from 'axios';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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
            <div key={i} className="file-item">
              <span className="file-path">{f}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function formatAnswer(text) {
  // Simple markdown-ish rendering
  return text
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
      `<pre><code>${code.replace(/</g, '&lt;')}</code></pre>`)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>');
}

export default function QAInterface({ repo, indexName }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: '👋 Hi! I\'m Code Detective. Ask me anything about this repository — authentication flows, feature implementations, dependencies, or architecture patterns.',
      sources: [],
      steps: [],
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const SUGGESTIONS = [
    'Explain the authentication flow',
    'Where is JWT validation implemented?',
    'How does payment processing work?',
    'What are the main API routes?',
  ];

  const ask = async (question) => {
    if (!question.trim() || !repo) return;
    setMessages(m => [...m, { role: 'user', text: question }]);
    setInput('');
    setLoading(true);

    try {
      const res = await axios.post(`${API}/api/agents/qa`, {
        question,
        repo_path: repo,
        index_name: indexName,
      });
      setMessages(m => [...m, {
        role: 'assistant',
        text: res.data.answer,
        sources: res.data.sources || [],
        steps: res.data.steps || [],
      }]);
    } catch (e) {
      setMessages(m => [...m, {
        role: 'assistant',
        text: `❌ Error: ${e.response?.data?.detail || e.message}`,
        sources: [],
        steps: [],
      }]);
    } finally {
      setLoading(false);
    }
  };

  if (!repo) {
    return (
      <div className="empty-state animate-fade">
        <div className="empty-icon">🔍</div>
        <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>No repository loaded</h3>
        <p>Use "Load Repository" in the sidebar to get started.</p>
      </div>
    );
  }

  return (
    <div className="chat-container" style={{ height: 'calc(100vh - 120px)' }}>
      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role === 'user' ? 'user' : ''} animate-fade`}>
            <div className="message-avatar">
              {msg.role === 'user' ? <User size={15} /> : <Bot size={15} />}
            </div>
            <div className="message-body">
              {msg.role === 'assistant' ? (
                <div className="prose" dangerouslySetInnerHTML={{ __html: formatAnswer(msg.text) }} />
              ) : (
                <span>{msg.text}</span>
              )}
              {msg.steps?.length > 0 && (
                <div className="steps-list" style={{ marginTop: 12 }}>
                  {msg.steps.map((s, si) => (
                    <div key={si} className="step-item">{s}</div>
                  ))}
                </div>
              )}
              <SourceFiles files={msg.sources} />
            </div>
          </div>
        ))}
        {loading && (
          <div className="message animate-fade">
            <div className="message-avatar"><Bot size={15} /></div>
            <div className="message-body">
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', color: 'var(--text-muted)', fontSize: '0.84rem' }}>
                <div className="spinner" />
                Searching codebase and reasoning with Gemini…
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      {messages.length === 1 && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', padding: '12px 0' }}>
          {SUGGESTIONS.map((s, i) => (
            <button key={i} className="btn btn-secondary" style={{ fontSize: '0.78rem', padding: '6px 12px' }} onClick={() => ask(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="chat-input-row">
        <input
          id="qa-input"
          className="input"
          placeholder="Ask anything about this codebase…"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && ask(input)}
          disabled={loading}
        />
        <button
          id="qa-send"
          className="btn btn-primary"
          onClick={() => ask(input)}
          disabled={loading || !input.trim()}
          style={{ minWidth: 48 }}
        >
          <Send size={15} />
        </button>
      </div>
    </div>
  );
}
