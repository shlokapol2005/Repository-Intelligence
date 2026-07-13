import React, { useMemo } from 'react';
import { Folder } from 'lucide-react';

/* ══════════════════════════════════════════════════════════════════
   HoloCube — isometric holographic glass cube of the repository.
   Matches the reference composition: 3/4 view (top + left + front
   faces visible), repo tree rendered ON the angled left face,
   translucent divider slabs inside, node fields at two depths for
   parallax, a pedestal underneath, and a periodic scan sweep.
   Pure CSS 3D — no dependency.
   ══════════════════════════════════════════════════════════════════ */

const LAYERS = [
  { key: 'frontend', label: 'FRONTEND', color: '#34d399' },
  { key: 'backend',  label: 'BACKEND',  color: '#a78bfa' },
  { key: 'database', label: 'DATABASE', color: '#e0b45a' },
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

/* Connect each node to its 2 nearest neighbours — a mesh, not a chain */
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

function LayerField({ color, count, seed, pulseDelay, showCylinder }) {
  const positions = useMemo(() => seededLayout(count, seed), [count, seed]);
  const links = useMemo(() => nearestNeighbourLinks(positions), [positions]);
  const particles = useMemo(() => seededLayout(14, seed + 57), [seed]);
  // A couple of "hero" nodes per layer get extra size + brightness
  const heroIdx = useMemo(() => new Set([Math.floor(count * 0.3), Math.floor(count * 0.7)]), [count]);

  return (
    <div className="holo-layer" style={{ '--layer-color': color, animationDelay: `-${pulseDelay}s` }}>
      <div className="holo-layer-field">
        <svg className="holo-layer-lines" viewBox="0 0 100 100" preserveAspectRatio="none">
          {links.map(l => <line key={l.key} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} />)}
        </svg>
        {particles.map((p, i) => (
          <span
            key={`p${i}`}
            className="holo-particle"
            style={{ left: `${p.x}%`, top: `${p.y}%`, animationDelay: `${p.delay}s`, animationDuration: `${p.dur}s` }}
          />
        ))}
        {positions.map((p, i) => (
          <div
            key={i}
            className={`holo-filecube ${heroIdx.has(i) ? 'holo-filecube--hero' : ''}`}
            style={{ left: `${p.x}%`, top: `${p.y}%`, animationDelay: `${p.delay}s`, animationDuration: `${p.dur}s` }}
          />
        ))}
        {showCylinder && (
          <div className="holo-cylinder" aria-hidden="true">
            <div className="holo-cylinder-top" />
            <div className="holo-cylinder-body" />
          </div>
        )}
      </div>
    </div>
  );
}

/* Three stacked layer fields (used on the front face AND on a deeper
   interior plane with different seeds, giving the volume parallax) */
function LayerStack({ seedBase, counts, withCylinder }) {
  const pulseDelays = [4.4, 2.2, 0];
  return (
    <>
      {LAYERS.map((l, i) => (
        <LayerField
          key={l.key}
          color={l.color}
          count={counts[i]}
          seed={seedBase + i * 17}
          pulseDelay={pulseDelays[i]}
          showCylinder={withCylinder && l.key === 'database'}
        />
      ))}
    </>
  );
}

const TREE_ROWS = [
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
      <div className="holo-tree-header"><Folder size={13} /> Repository</div>
      {TREE_ROWS.map((r, i) => (
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

      {/* The cube — fixed isometric pose + slow sway */}
      <div className="holocube-sway">
        <div className="holocube">
          {/* glass shell (back first so the volume reads through it) */}
          <div className="holocube-face holocube-face--back" />
          <div className="holocube-face holocube-face--top" />
          <div className="holocube-face holocube-face--left">
            <RepoTree />
          </div>

          {/* translucent slabs splitting the volume into three layers */}
          <div className="holo-slab holo-slab--1" />
          <div className="holo-slab holo-slab--2" />

          {/* deep interior node plane (parallax) */}
          <div className="holo-plane">
            <LayerStack seedBase={41} counts={[12, 10, 8]} withCylinder />
          </div>

          {/* front glass face with the main node fields + scan */}
          <div className="holocube-face holocube-face--front">
            <LayerStack seedBase={7} counts={[16, 14, 11]} />
            <div className="holo-scan" />
          </div>

          {/* pedestal */}
          <div className="holo-base" />
        </div>
      </div>

      {/* Layer labels — flat overlay, right of the cube */}
      <div className="holo-labels">
        {LAYERS.map(l => (
          <div key={l.key} className="holo-label-row" style={{ '--lc': l.color }}>
            <span>{l.label}</span>
            <i />
          </div>
        ))}
      </div>
    </div>
  );
}
