import React, { useRef, useEffect, useMemo, useState } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import {
  ArrowRight, GitFork, MessageCircle, Zap, GitBranch,
  AlertTriangle, BookOpen, Network, Lightbulb,
  ExternalLink, ArrowDown,
} from 'lucide-react';

/* ══════════════════════════════════════════════════════════════════
   Scroll-reactive "contribution grid" background.
   Faint squares fill in emerald as you scroll — GitHub-graph vibe.
   ══════════════════════════════════════════════════════════════════ */
function ContributionField() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const scroller = canvas.closest('.landing-page');
    if (!scroller) return;

    const CELL = 26, GAP = 5;
    let cols = 0, rows = 0, seeds = [], progress = 0, raf = 0;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = scroller.clientWidth;
      const h = scroller.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = w + 'px';
      canvas.style.height = h + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      cols = Math.ceil(w / (CELL + GAP)) + 1;
      rows = Math.ceil(h / (CELL + GAP)) + 1;
      seeds = Array.from({ length: cols * rows }, () => Math.random());
    };

    const draw = () => {
      const w = scroller.clientWidth;
      const h = scroller.clientHeight;
      ctx.clearRect(0, 0, w, h);
      const maxDiag = cols + rows;
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const seed = seeds[r * cols + c] ?? 0;
          // diagonal wavefront advanced by scroll progress
          const threshold = ((c + r) / maxDiag) * 0.85 + seed * 0.14;
          const lit = progress * 1.25 - threshold;
          const x = c * (CELL + GAP);
          const y = r * (CELL + GAP);
          if (lit > 0) {
            const intensity = Math.min(lit * 2.2, 1) * (0.5 + seed * 0.5);
            ctx.fillStyle = `rgba(52, 211, 153, ${0.06 + intensity * 0.6})`;
            if (intensity > 0.75) {
              ctx.shadowColor = 'rgba(52,211,153,0.8)';
              ctx.shadowBlur = 10;
            } else { ctx.shadowBlur = 0; }
          } else {
            ctx.shadowBlur = 0;
            ctx.fillStyle = 'rgba(110, 231, 183, 0.05)'; // faint base grid
          }
          roundRect(ctx, x, y, CELL, CELL, 5);
          ctx.fill();
        }
      }
      ctx.shadowBlur = 0;
    };

    const roundRect = (c, x, y, w, h, r) => {
      c.beginPath();
      c.moveTo(x + r, y);
      c.arcTo(x + w, y, x + w, y + h, r);
      c.arcTo(x + w, y + h, x, y + h, r);
      c.arcTo(x, y + h, x, y, r);
      c.arcTo(x, y, x + w, y, r);
      c.closePath();
    };

    const onScroll = () => {
      const max = scroller.scrollHeight - scroller.clientHeight;
      progress = max > 0 ? scroller.scrollTop / max : 0;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(draw);
    };

    resize();
    draw();
    scroller.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', () => { resize(); draw(); });

    return () => {
      scroller.removeEventListener('scroll', onScroll);
      cancelAnimationFrame(raf);
    };
  }, []);

  return <canvas ref={canvasRef} className="contribution-field" />;
}

/* ══════════════════════════════════════════════════════════════════
   Auto-rotating decorative 3D network for the hero.
   pointer-events disabled so the page still scrolls normally.
   ══════════════════════════════════════════════════════════════════ */
function HeroGraph3D() {
  const wrapRef = useRef(null);
  const fgRef   = useRef(null);
  const [dims, setDims] = useState({ width: 420, height: 440 });

  const data = useMemo(() => {
    const palette = ['#34d399', '#6ee7b7', '#2dd4bf', '#e0a458'];
    const nodes = Array.from({ length: 16 }, (_, i) => ({
      id: i,
      color: palette[i % palette.length],
      val: 2 + (i % 5),
    }));
    const links = [];
    for (let i = 1; i < nodes.length; i++) {
      links.push({ source: i, target: Math.floor(Math.random() * i) });
    }
    // a few extra cross-links for a richer web
    for (let k = 0; k < 6; k++) {
      links.push({
        source: Math.floor(Math.random() * nodes.length),
        target: Math.floor(Math.random() * nodes.length),
      });
    }
    return { nodes, links };
  }, []);

  useEffect(() => {
    if (!wrapRef.current) return;
    const el = wrapRef.current;
    const measure = () => setDims({ width: el.clientWidth, height: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // auto-orbit
  useEffect(() => {
    let angle = 0, raf = 0;
    const DIST = 220;
    const tick = () => {
      const fg = fgRef.current;
      if (fg) {
        fg.cameraPosition({
          x: DIST * Math.sin(angle),
          y: 40 * Math.sin(angle * 0.6),
          z: DIST * Math.cos(angle),
        });
        angle += 0.0045;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className="hero-graph3d" ref={wrapRef}>
      {dims.width > 0 && (
        <ForceGraph3D
          ref={fgRef}
          width={dims.width}
          height={dims.height}
          graphData={data}
          backgroundColor="rgba(0,0,0,0)"
          showNavInfo={false}
          enablePointerInteraction={false}
          nodeColor="color"
          nodeVal="val"
          nodeOpacity={0.95}
          nodeResolution={20}
          linkColor={() => 'rgba(110,231,183,0.35)'}
          linkWidth={0.7}
          linkDirectionalParticles={2}
          linkDirectionalParticleWidth={1.8}
          linkDirectionalParticleColor={() => '#6ee7b7'}
          linkDirectionalParticleSpeed={0.008}
          warmupTicks={80}
          cooldownTicks={0}
        />
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════ */
export default function LandingPage({ onGetStarted }) {
  const scrollTo = (id) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });

  return (
    <div className="landing-page">
      <ContributionField />

      {/* ═══ HERO ═══════════════════════════════════════════════════ */}
      <section className="landing-hero">
        <div className="hero-content">
          <div className="hero-badge">✨ Structural intelligence for any codebase</div>

          <h1 className="hero-title">
            Read your entire repository
            <span className="gradient-text"> in seconds</span>
          </h1>

          <p className="hero-subtitle">
           Chat-based coding tools retrieve context and reason over it. RepoLens first builds a verified dependency graph from your codebase, giving you graph-backed answers to questions like "What breaks if I change this?" and "Is this file even used?"
          </p>

          <div className="hero-cta-group">
            <button className="btn btn-hero-primary" onClick={onGetStarted}>
              Load Your Repository <ArrowRight size={16} />
            </button>
            <button className="btn btn-hero-secondary" onClick={() => scrollTo('features')}>
              See what it does <ArrowDown size={14} />
            </button>
          </div>

          <div className="hero-platforms">
            <span className="platforms-label">Also available on</span>
            <div className="platform-badges">
              <a href="https://discord.com/oauth2/authorize?client_id=1521116372896055318&permissions=116736&integration_type=0&scope=bot+applications.commands"
                 target="_blank" rel="noopener noreferrer" className="platform-badge">
                <MessageCircle size={14} /> Discord Bot
              </a>
              <a href="https://github.com/apps/repolens-pr-analyzer"
                 target="_blank" rel="noopener noreferrer" className="platform-badge">
                <GitFork size={14} /> GitHub App
              </a>
            </div>
          </div>
        </div>

        {/* 3D hero network */}
        <div className="hero-visual">
          <div className="visual-blob blob-1" />
          <div className="visual-blob blob-2" />
          <HeroGraph3D />
        </div>
      </section>

      {/* ═══ HOW IT WORKS ══════════════════════════════════════════ */}
      <section className="landing-section" id="how">
        <div className="section-header">
          <span className="section-label">How it works</span>
          <h2>Three steps to full repository understanding</h2>
        </div>
        <div className="steps-grid">
          <div className="step-card">
            <div className="step-number">1</div>
            <h3>Point at a repo</h3>
            <p>Paste a GitHub URL or load a local repository. RepoLens clones and begins analysis instantly.</p>
            <div className="step-icon">📁</div>
          </div>
          <div className="step-card">
            <div className="step-number">2</div>
            <h3>We analyze</h3>
            <p>AST parsing, dependency-graph construction, and structural analysis happen in seconds.</p>
            <div className="step-icon">🔍</div>
          </div>
          <div className="step-card">
            <div className="step-number">3</div>
            <h3>Explore &amp; act</h3>
            <p>Interactive 2D/3D graphs, impact analysis, dead-code detection, and AI Q&amp;A at your fingertips.</p>
            <div className="step-icon">⚡</div>
          </div>
        </div>
      </section>

      {/* ═══ FEATURES ═════════════════════════════════════════════ */}
      <section className="landing-section" id="features">
        <div className="section-header">
          <span className="section-label">Capabilities</span>
          <h2>Everything you need to own your codebase</h2>
        </div>
        <div className="features-grid">
          <div className="feature-card">
            <div className="feature-icon dependency"><Network size={20} /></div>
            <h3>Dependency Graph</h3>
            <p>Every file a node, every import an edge — explorable in 2D or real 3D. See your whole structure at a glance.</p>
          </div>
          <div className="feature-card">
            <div className="feature-icon impact"><AlertTriangle size={20} /></div>
            <h3>Blast Radius</h3>
            <p>"If I change this file, what breaks?" Instant transitive dependency analysis with a risk score.</p>
          </div>
          <div className="feature-card">
            <div className="feature-icon dead-code"><MessageCircle size={20} /></div>
            <h3>Discord Bot</h3>
            <p>Bring the whole engine into your team's server — <code>/repobot load</code>, then trace, impact, or ask questions right in the channel.</p>
          </div>
          <div className="feature-card">
            <div className="feature-icon architecture"><GitBranch size={20} /></div>
            <h3>Architecture Diagram</h3>
            <p>Auto-generated, clustered Mermaid diagrams — no overlaps. Understand your system at 10,000 feet.</p>
          </div>
          <div className="feature-card">
            <div className="feature-icon qa"><Lightbulb size={20} /></div>
            <h3>AI-Powered Q&amp;A</h3>
            <p>"Which files handle auth?" Ask in English. Hybrid FAISS + semantic search gives precise answers.</p>
          </div>
          <div className="feature-card">
            <div className="feature-icon pr-bot"><Zap size={20} /></div>
            <h3>PR Impact Bot</h3>
            <p>Automatic GitHub App comments — every PR gets instant blast-radius analysis and a risk assessment.</p>
          </div>
        </div>
      </section>

      {/* ═══ WAYS TO USE ══════════════════════════════════════════ */}
      <section className="landing-section landing-panel" id="use">
        <div className="section-header">
          <span className="section-label">Ways to use it</span>
          <h2>Meet your codebase wherever you work</h2>
        </div>
        <div className="quick-start-grid">
          <div className="quickstart-card">
            <div className="qs-emoji">🌐</div>
            <h3>Right here</h3>
            <p>Load a repo and explore the interactive graph, impact analysis and Q&amp;A in your browser.</p>
            <button className="quick-link quick-link--btn" onClick={onGetStarted}>
              Start now <ArrowRight size={13} />
            </button>
          </div>
          <div className="quickstart-card">
            <div className="qs-emoji">🤖</div>
            <h3>Discord Bot</h3>
            <p>Run <code>/repobot load &lt;url&gt;</code> in any channel, then <code>/repobot impact</code>, <code>arch</code>, <code>qa</code>…</p>
            <a href="https://discord.com/oauth2/authorize?client_id=1521116372896055318&permissions=116736&integration_type=0&scope=bot+applications.commands"
               target="_blank" rel="noopener noreferrer" className="quick-link">
              Add to server <ExternalLink size={12} />
            </a>
          </div>
          <div className="quickstart-card">
            <div className="qs-emoji">🔧</div>
            <h3>GitHub App</h3>
            <p>Install once — every pull request automatically gets an impact + risk comment. Zero config.</p>
            <a href="https://github.com/apps/repolens-pr-analyzer"
               target="_blank" rel="noopener noreferrer" className="quick-link">
              Install app <ExternalLink size={12} />
            </a>
          </div>
        </div>
      </section>

      {/* ═══ CTA FOOTER ═══════════════════════════════════════════ */}
      <section className="landing-footer">
        <div className="footer-content">
          <h2>Ready to understand your codebase?</h2>
          <p>Start with your GitHub repo or a local codebase — no setup required.</p>
          <button className="btn btn-hero-primary btn-large" onClick={onGetStarted}>
            Load Repository Now <ArrowRight size={18} />
          </button>
        </div>
        <div className="footer-links">
          <a href="https://github.com/shlokapol2005/Repository-Intelligence" target="_blank" rel="noopener noreferrer">
            <GitFork size={16} /> Source on GitHub
          </a>
          <a href="https://discord.com/oauth2/authorize?client_id=1521116372896055318" target="_blank" rel="noopener noreferrer">
            <MessageCircle size={16} /> Discord Bot
          </a>
          <a href="https://github.com/apps/repolens-pr-analyzer" target="_blank" rel="noopener noreferrer">
            <GitBranch size={16} /> GitHub App
          </a>
        </div>
      </section>
    </div>
  );
}
