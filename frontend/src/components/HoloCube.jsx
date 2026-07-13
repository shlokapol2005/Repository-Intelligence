import React, { useMemo } from 'react';
import { Folder } from 'lucide-react';

/* ══════════════════════════════════════════════════════════════════
   HoloCube — a floating holographic glass cube representing the whole
   repository: three dense internal layers (Frontend / Backend /
   Database), a glowing wireframe edge, an always-visible repo-tree
   panel, and a periodic scan sweep. Pure CSS 3D — no dependency.

   Unlike a full 360° spin, this uses a FIXED tilt + a few degrees of
   idle sway, so the tree panel and all three layers stay legible at
   all times instead of rotating out of view.
   ══════════════════════════════════════════════════════════════════ */

const FRONTEND_FILES = ['App.jsx', 'LandingPage.jsx', 'GraphExplorer.jsx', 'ChatAssistant.jsx', 'DeadCode.jsx', 'OnboardingMode.jsx'];
const BACKEND_FILES = ['main.py', 'parser.py', 'graph_builder.py', 'scanner.py', 'vector_index.py'];
const DATABASE_FILES = ['faiss_index/', 'graph_cache.json', 'embeddings'];

const LAYERS = [
  { key: 'frontend', label: 'FRONTEND', color: '#34d399', files: FRONTEND_FILES, count: 15, pulseDelay: 4.4 },
  { key: 'backend',  label: 'BACKEND',  color: '#a78bfa', files: BACKEND_FILES,  count: 13, pulseDelay: 2.2 },
  { key: 'database', label: 'DATABASE', color: '#e0b45a', files: DATABASE_FILES, count: 11, pulseDelay: 0 },
];

/* Deterministic pseudo-random layout so positions don't reshuffle on re-render */
function seededLayout(count, seedOffset) {
  return Array.from({ length: count }, (_, i) => {
    const s1 = Math.sin((i + seedOffset) * 12.9898) * 43758.5453;
    const r1 = s1 - Math.floor(s1);
    const s2 = Math.sin((i + seedOffset) * 78.233) * 12345.678;
    const r2 = s2 - Math.floor(s2);
    return { x: 8 + r1 * 84, y: 12 + r2 * 76, delay: (r1 * 3).toFixed(2), dur: (2.6 + r2 * 2.4).toFixed(2) };
  });
}

/* Connect each node to its 2 nearest neighbours — a proper mesh, not a chain */
function nearestNeighbourLinks(positions) {
  const links = [];
  positions.forEach((p, i) => {
    const dists = positions
      .map((q, j) => (j === i ? null : { j, d: (q.x - p.x) ** 2 + (q.y - p.y) ** 2 }))
      .filter(Boolean)
      .sort((a, b) => a.d - b.d)
      .slice(0, 2);
    dists.forEach(({ j }) => {
      const key = i < j ? `${i}-${j}` : `${j}-${i}`;
      if (!links.some(l => l.key === key)) links.push({ key, x1: p.x, y1: p.y, x2: positions[j].x, y2: positions[j].y });
    });
  });
  return links;
}

function Layer({ label, color, files, count, pulseDelay }) {
  const positions = useMemo(() => seededLayout(count, label.charCodeAt(0) + count), [label, count]);
  const links = useMemo(() => nearestNeighbourLinks(positions), [positions]);
  // A couple of "hero" nodes per layer get extra size + brightness, like the reference
  const heroIdx = useMemo(() => new Set([Math.floor(count * 0.3), Math.floor(count * 0.7)]), [count]);

  return (
    <div className="holo-layer" style={{ '--layer-color': color, animationDelay: `-${pulseDelay}s` }}>
      <div className="holo-layer-field">
        <svg className="holo-layer-lines" viewBox="0 0 100 100" preserveAspectRatio="none">
          {links.map(l => <line key={l.key} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} />)}
        </svg>
        {positions.map((p, i) => (
          <div
            key={i}
            className={`holo-filecube ${heroIdx.has(i) ? 'holo-filecube--hero' : ''}`}
            title={files[i] || ''}
            style={{ left: `${p.x}%`, top: `${p.y}%`, animationDelay: `${p.delay}s`, animationDuration: `${p.dur}s` }}
          />
        ))}
        {label === 'DATABASE' && (
          <div className="holo-cylinder" aria-hidden="true">
            <div className="holo-cylinder-top" />
            <div className="holo-cylinder-body" />
          </div>
        )}
      </div>
    </div>
  );
}

const TREE_ROWS = [
  { prefix: '', folder: true, label: 'Repository' },
  { prefix: '├── ', folder: true, label: 'frontend' },
  { prefix: '│   ├── ', folder: true, label: 'src' },
  { prefix: '│   │   ├── ', folder: false, label: 'App.jsx' },
  { prefix: '│   │   ├── ', folder: false, label: 'LandingPage.jsx' },
  { prefix: '│   │   ├── ', folder: false, label: 'GraphExplorer.jsx' },
  { prefix: '│   │   └── ', folder: false, label: 'ChatAssistant.jsx' },
  { prefix: '├── ', folder: true, label: 'backend' },
  { prefix: '│   ├── ', folder: false, label: 'main.py' },
  { prefix: '│   ├── ', folder: false, label: 'parser.py' },
  { prefix: '│   ├── ', folder: false, label: 'graph_builder.py' },
  { prefix: '│   └── ', folder: false, label: 'utils.py' },
  { prefix: '└── ', folder: true, label: 'database' },
  { prefix: '    └── ', folder: false, label: 'faiss_index/' },
];

function RepoTree() {
  return (
    <div className="holo-tree">
      <div className="holo-tree-header"><Folder size={12} /> Repository</div>
      {TREE_ROWS.slice(1).map((r, i) => (
        <div key={i} className="holo-tree-row">
          <span className="holo-tree-prefix">{r.prefix}</span>
          {r.folder && <Folder size={9} className="holo-tree-icon" />}
          <span className={r.folder ? 'holo-tree-folder' : 'holo-tree-file'}>{r.label}</span>
        </div>
      ))}
    </div>
  );
}

export default function HoloCube() {
  return (
    <div className="holocube-scene">
      <div className="holocube-ambient" />
      <div className="holocube-ground" />

      <div className="holocube-assembly">
        {/* Repo tree — a flat glass panel, always visible, floats independently */}
        <div className="holo-tree-panel">
          <RepoTree />
        </div>

        {/* The cube — fixed elegant tilt + gentle sway (no full spin, stays legible) */}
        <div className="holocube-sway">
          <div className="holocube">
            <div className="holocube-face holocube-face--front">
              {LAYERS.map(l => <Layer key={l.key} {...l} />)}
              <div className="holo-scan" />
            </div>
            <div className="holocube-face holocube-face--top" />
            <div className="holocube-face holocube-face--right" />
          </div>
        </div>

        {/* Layer labels — outside the cube, to the right, like the reference */}
        <div className="holo-labels">
          {LAYERS.map(l => (
            <div key={l.key} className="holo-label-row" style={{ '--lc': l.color }}>
              <span>{l.label}</span>
              <i />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
