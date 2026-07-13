import React, {
  useState, useCallback, useEffect, useRef, useMemo,
} from 'react';
import {
  ReactFlow, Background, Controls, MiniMap,
  useNodesState, useEdgesState, useReactFlow,
  ReactFlowProvider, MarkerType, Panel,
  Handle, Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import axios from 'axios';
import {
  GitBranch, X, Search, Zap, AlertTriangle, Code2,
  FileCode2, FileJson, Layers, Activity, Cpu,
  ChevronRight, ExternalLink, Filter, RefreshCw,
  Loader2, Radio, BarChart2, Box,
  Plus, Minus, ChevronDown, ChevronUp,
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/* ─────────────────────────────────────────────────────────────────
   HELPERS
   ───────────────────────────────────────────────────────────────── */

/** Safely get the name from a function/class entry (handles both string and {name} dict) */
function getName(entry) {
  if (typeof entry === 'string') return entry;
  if (entry && typeof entry === 'object') return entry.name || '?';
  return '?';
}
function getLine(entry) {
  if (entry && typeof entry === 'object') return entry.line;
  return null;
}
function getMethods(entry) {
  if (entry && typeof entry === 'object' && Array.isArray(entry.methods)) return entry.methods;
  return [];
}

/* ─────────────────────────────────────────────────────────────────
   LANGUAGE COLOUR PALETTES
   ───────────────────────────────────────────────────────────────── */
const LANG_CONFIG = {
  python:     { color: '#6366f1', glow: 'rgba(99,102,241,0.5)',  label: 'PY',  bg: 'rgba(99,102,241,0.12)'  },
  javascript: { color: '#06b6d4', glow: 'rgba(6,182,212,0.5)',   label: 'JS',  bg: 'rgba(6,182,212,0.12)'   },
  typescript: { color: '#3b82f6', glow: 'rgba(59,130,246,0.5)',  label: 'TS',  bg: 'rgba(59,130,246,0.12)'  },
  unknown:    { color: '#64748b', glow: 'rgba(100,116,139,0.3)', label: '?',   bg: 'rgba(100,116,139,0.08)' },
};

function getLangConfig(lang) {
  return LANG_CONFIG[lang] || LANG_CONFIG.unknown;
}

/* ─────────────────────────────────────────────────────────────────
   LAYOUT HELPER  (simple top-down layered layout)
   ───────────────────────────────────────────────────────────────── */
function computeLayout(nodes, edges) {
  // Separate file nodes from child nodes for layout
  const fileNodes = nodes.filter(n => !n.data?._isChild);
  const childNodes = nodes.filter(n => n.data?._isChild);
  const fileIds = new Set(fileNodes.map(n => n.id));

  // Build directional adjacency (file nodes only), both forward & reverse
  const inDeg = {};
  const fwd = {};   // source → [targets]
  const rev = {};   // target → [sources]
  fileNodes.forEach(n => { inDeg[n.id] = 0; fwd[n.id] = []; rev[n.id] = []; });
  edges.forEach(e => {
    if (fileIds.has(e.source) && fileIds.has(e.target) && e.source !== e.target) {
      fwd[e.source].push(e.target);
      rev[e.target].push(e.source);
      inDeg[e.target]++;
    }
  });

  // Kahn's algorithm for layering (on a copy of the degrees)
  const deg = { ...inDeg };
  const layers = [];
  let queue = fileNodes.filter(n => deg[n.id] === 0).map(n => n.id);
  const visited = new Set();

  while (queue.length > 0) {
    layers.push([...queue]);
    queue.forEach(id => visited.add(id));
    const next = [];
    queue.forEach(id => {
      fwd[id].forEach(tid => {
        deg[tid]--;
        if (deg[tid] === 0 && !visited.has(tid)) next.push(tid);
      });
    });
    queue = next;
  }

  // Assign remaining nodes (cycles) to a final layer
  const remaining = fileNodes.filter(n => !visited.has(n.id)).map(n => n.id);
  if (remaining.length) layers.push(remaining);

  // ── Crossing reduction: barycenter ordering sweeps ──────────────
  // Reorder nodes within each layer so connected nodes line up, which
  // dramatically reduces edge crossings without any manual dragging.
  const orderIndex = {};
  layers.forEach(layer => layer.forEach((id, i) => { orderIndex[id] = i; }));

  const barycenter = (id, neigh) => {
    const ns = neigh[id] || [];
    let sum = 0, cnt = 0;
    ns.forEach(n => { if (orderIndex[n] != null) { sum += orderIndex[n]; cnt++; } });
    return cnt ? sum / cnt : orderIndex[id];
  };

  for (let sweep = 0; sweep < 4; sweep++) {
    // downward pass — order each layer by its predecessors
    for (let li = 1; li < layers.length; li++) {
      layers[li].sort((a, b) => barycenter(a, rev) - barycenter(b, rev));
      layers[li].forEach((id, i) => { orderIndex[id] = i; });
    }
    // upward pass — order each layer by its successors
    for (let li = layers.length - 2; li >= 0; li--) {
      layers[li].sort((a, b) => barycenter(a, fwd) - barycenter(b, fwd));
      layers[li].forEach((id, i) => { orderIndex[id] = i; });
    }
  }

  // Wider spacing so edges have room to breathe
  const NODE_W = 220;
  const NODE_H = 90;
  const H_GAP  = 110;
  const V_GAP  = 170;

  const positioned = {};
  layers.forEach((layer, yi) => {
    const totalW = layer.length * (NODE_W + H_GAP) - H_GAP;
    layer.forEach((id, xi) => {
      positioned[id] = {
        x: xi * (NODE_W + H_GAP) - totalW / 2,
        y: yi * (NODE_H + V_GAP),
      };
    });
  });

  // Position child nodes relative to their parent using columns (chains)
  childNodes.forEach(cn => {
    const parentId = cn.data._parentId;
    const parentPos = positioned[parentId];
    if (parentPos) {
      const idx = cn.data._chainIndex || 0;
      const row = cn.data._chainRow || 0;
      const total = cn.data._totalChains || 1;
      
      const horizontalGap = 180;
      const verticalGap = 100;
      
      positioned[cn.id] = {
        x: parentPos.x + 20 - ((total - 1) * horizontalGap) / 2 + idx * horizontalGap,
        y: parentPos.y + 110 + row * verticalGap,
      };
    } else {
      positioned[cn.id] = { x: Math.random() * 800, y: Math.random() * 600 };
    }
  });

  return nodes.map(n => ({
    ...n,
    position: positioned[n.id] || { x: Math.random() * 800, y: Math.random() * 600 },
  }));
}

/* ─────────────────────────────────────────────────────────────────
   CHILD NODE GENERATION
   ───────────────────────────────────────────────────────────────── */

function generateChildNodesAndEdges(fileNode) {
  const d = fileNode.data;
  const parentId = fileNode.id;
  const childNodes = [];
  const childEdges = [];

  const rawFunctions = d.functions || [];
  const rawClasses = d.classes || [];
  const rawRoutes = d.api_routes || [];

  // 1. Create node objects first (positions are computed in computeLayout)
  const classes = rawClasses.map(cls => {
    const clsName = getName(cls);
    return {
      id: `${parentId}::cls::${clsName}`,
      type: 'classNode',
      data: {
        label: clsName,
        line: getLine(cls),
        methods: getMethods(cls),
        language: d.language,
        _isChild: true,
        _parentId: parentId,
        _childType: 'class',
      },
      position: { x: 0, y: 0 },
    };
  });

  const functions = rawFunctions.map(fn => {
    const fnName = getName(fn);
    return {
      id: `${parentId}::fn::${fnName}`,
      type: 'functionNode',
      data: {
        label: fnName,
        line: getLine(fn),
        parameters: fn.parameters || [],
        language: d.language,
        _isChild: true,
        _parentId: parentId,
        _childType: 'function',
      },
      position: { x: 0, y: 0 },
    };
  });

  const routes = rawRoutes.map(route => {
    const method = route.method || 'GET';
    const path = route.path || '/';
    const handler = route.handler || '';
    return {
      id: `${parentId}::route::${method}:${path}`,
      type: 'routeNode',
      data: {
        label: `${method} ${path}`,
        method,
        path,
        handler,
        line: route.line,
        language: d.language,
        _isChild: true,
        _parentId: parentId,
        _childType: 'route',
      },
      position: { x: 0, y: 0 },
    };
  });

  // 2. Build semantic columns (chains) of related elements
  const chains = [];
  const usedNodeIds = new Set();

  // Route chains: Class -> Route -> Function
  routes.forEach(routeNode => {
    const chain = { route: routeNode, class: null, function: null };
    usedNodeIds.add(routeNode.id);

    // Find handler function node
    const handlerName = routeNode.data.handler;
    if (handlerName) {
      const fnNode = functions.find(f => f.data.label === handlerName);
      if (fnNode) {
        chain.function = fnNode;
        usedNodeIds.add(fnNode.id);

        // Find Pydantic/Request model class that matches function parameter annotations
        if (fnNode.data.parameters && Array.isArray(fnNode.data.parameters)) {
          const paramClass = classes.find(c => fnNode.data.parameters.includes(c.data.label));
          if (paramClass) {
            chain.class = paramClass;
            usedNodeIds.add(paramClass.id);
          }
        }
      }
    }

    // Heuristic fallback matching for Class if param annotation didn't resolve
    if (!chain.class) {
      const routePath = routeNode.data.path || '';
      const cleanPath = routePath.split('/').pop().replace(/[^a-zA-Z]/g, '').toLowerCase();
      const handlerClean = (handlerName || '').replace(/[^a-zA-Z]/g, '').toLowerCase();
      
      const matchedClass = classes.find(c => {
        if (usedNodeIds.has(c.id)) return false;
        const cName = c.data.label.toLowerCase();
        return (cleanPath && cName.includes(cleanPath)) || 
               (handlerClean && (cName.includes(handlerClean) || handlerClean.includes(cName.replace('request', ''))));
      });
      if (matchedClass) {
        chain.class = matchedClass;
        usedNodeIds.add(matchedClass.id);
      }
    }

    chains.push(chain);
  });

  // Remaining standalone classes
  classes.forEach(clsNode => {
    if (!usedNodeIds.has(clsNode.id)) {
      chains.push({ route: null, class: clsNode, function: null });
      usedNodeIds.add(clsNode.id);
    }
  });

  // Remaining standalone functions
  functions.forEach(fnNode => {
    if (!usedNodeIds.has(fnNode.id)) {
      chains.push({ route: null, class: null, function: fnNode });
      usedNodeIds.add(fnNode.id);
    }
  });

  // 3. Populate node positions & build structured flow edges
  chains.forEach((chain, chainIdx) => {
    let highestNode = null;

    if (chain.class) {
      highestNode = chain.class;
      chain.class.data._chainIndex = chainIdx;
      chain.class.data._chainRow = 0;
      childNodes.push(chain.class);
    }

    if (chain.route) {
      if (!highestNode) highestNode = chain.route;
      chain.route.data._chainIndex = chainIdx;
      chain.route.data._chainRow = 1;
      childNodes.push(chain.route);
    }

    if (chain.function) {
      if (!highestNode) highestNode = chain.function;
      chain.function.data._chainIndex = chainIdx;
      chain.function.data._chainRow = 2;
      childNodes.push(chain.function);
    }

    // A. Draw very subtle, dotted containment lines with NO arrowheads to the highest node of each column
    if (highestNode) {
      childEdges.push({
        id: `e-contain-${parentId}-${highestNode.id}`,
        source: parentId,
        target: highestNode.id,
        type: 'smoothstep',
        animated: false,
        style: { stroke: '#334155', strokeWidth: 1.2, strokeDasharray: '3 3', opacity: 0.5 },
        data: { _isContain: true },
      });
    }

    // B. Build logical flow connections
    // Class → Route (Request schema input)
    if (chain.class && chain.route) {
      childEdges.push({
        id: `e-request-${chain.class.id}-${chain.route.id}`,
        source: chain.class.id,
        target: chain.route.id,
        type: 'smoothstep',
        animated: true,
        label: 'request',
        style: { stroke: '#a78bfa', strokeWidth: 1.5 },
        labelStyle: { fill: '#a78bfa', fontSize: 9, fontWeight: 700 },
        labelBgStyle: { fill: 'transparent' },
        markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#a78bfa' },
      });
    }

    // Route → Function (Route handler execution)
    if (chain.route && chain.function) {
      childEdges.push({
        id: `e-handler-${chain.route.id}-${chain.function.id}`,
        source: chain.route.id,
        target: chain.function.id,
        type: 'smoothstep',
        animated: true,
        label: 'handler',
        style: { stroke: '#f59e0b', strokeWidth: 1.5 },
        labelStyle: { fill: '#f59e0b', fontSize: 9, fontWeight: 700 },
        labelBgStyle: { fill: 'transparent' },
        markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#f59e0b' },
      });
    }

    // Class → Function (Direct invocation / parameter fallback when no route exists)
    if (chain.class && chain.function && !chain.route) {
      childEdges.push({
        id: `e-param-${chain.class.id}-${chain.function.id}`,
        source: chain.class.id,
        target: chain.function.id,
        type: 'smoothstep',
        animated: true,
        label: 'param',
        style: { stroke: '#818cf8', strokeWidth: 1.5 },
        labelStyle: { fill: '#818cf8', fontSize: 9, fontWeight: 700 },
        labelBgStyle: { fill: 'transparent' },
        markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#818cf8' },
      });
    }
  });

  // Store total chain length for layout centering
  childNodes.forEach(cn => {
    cn.data._totalChains = chains.length;
  });

  return { childNodes, childEdges };
}

/* ─────────────────────────────────────────────────────────────────
   CUSTOM NODE: FunctionNode
   ───────────────────────────────────────────────────────────────── */
function FunctionNode({ data, selected }) {
  return (
    <div className={`child-node function-node ${selected ? 'code-node--selected' : ''}`}>
      <Handle type="target" position={Position.Top}    style={{ opacity: 0, width: 6, height: 6 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, width: 6, height: 6 }} />
      <div style={{ display: 'flex', alignItems: 'center' }}>
        <span className="child-icon">ƒ</span>
        <span className="child-label">{data.label}()</span>
      </div>
      {data.line && <div className="child-meta">line {data.line}</div>}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
   CUSTOM NODE: ClassNode
   ───────────────────────────────────────────────────────────────── */
function ClassNode({ data, selected }) {
  const methods = data.methods || [];
  return (
    <div className={`child-node class-node ${selected ? 'code-node--selected' : ''}`}>
      <Handle type="target" position={Position.Top}    style={{ opacity: 0, width: 6, height: 6 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, width: 6, height: 6 }} />
      <div style={{ display: 'flex', alignItems: 'center' }}>
        <span className="child-icon">◆</span>
        <span className="child-label">{data.label}</span>
      </div>
      {methods.length > 0 && (
        <div className="child-methods">
          {methods.slice(0, 6).map((m, i) => (
            <span key={i} className="method-chip">{m}()</span>
          ))}
          {methods.length > 6 && (
            <span className="method-chip" style={{ opacity: 0.5 }}>+{methods.length - 6}</span>
          )}
        </div>
      )}
      {data.line && <div className="child-meta" style={{ marginTop: 4 }}>line {data.line}</div>}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
   CUSTOM NODE: RouteNode
   ───────────────────────────────────────────────────────────────── */
function RouteNode({ data, selected }) {
  const method = data.method || 'GET';
  return (
    <div className={`child-node route-node ${selected ? 'code-node--selected' : ''}`}>
      <Handle type="target" position={Position.Top}    style={{ opacity: 0, width: 6, height: 6 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, width: 6, height: 6 }} />
      <span className={`route-method route-method--${method}`}>{method}</span>
      <div>
        <div className="route-path">{data.path}</div>
        {data.handler && <div className="route-handler">→ {data.handler}()</div>}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
   CUSTOM NODE: CodeNode (file-level — updated with expand button)
   ───────────────────────────────────────────────────────────────── */
function CodeNode({ data, selected }) {
  const cfg   = getLangConfig(data.language);
  const isApi = data.api_routes?.length > 0;
  const isDead     = data.is_dead;
  const isEntry    = data.is_entrypoint;
  const isExpanded = data._expanded;

  // Check if this file has anything to expand
  const fnCount    = (data.functions || []).length;
  const clsCount   = (data.classes || []).length;
  const routeCount = (data.api_routes || []).length;
  const hasChildren = fnCount + clsCount + routeCount > 0;

  let borderColor = cfg.color;
  let glowColor   = cfg.glow;
  let bgColor     = cfg.bg;
  let opacity     = 1;
  let ringColor   = cfg.color;

  if (isApi)   { borderColor = '#f59e0b'; glowColor = 'rgba(245,158,11,0.6)'; bgColor = 'rgba(245,158,11,0.10)'; }
  if (isEntry) { borderColor = '#10b981'; glowColor = 'rgba(16,185,129,0.5)'; }
  if (isDead)  { opacity = 0.45; borderColor = '#ef4444'; glowColor = 'rgba(239,68,68,0.3)'; }
  if (selected){ borderColor = '#ffffff'; glowColor = 'rgba(255,255,255,0.4)'; }

  const totalDeg = (data.in_degree || 0) + (data.out_degree || 0);
  const ringSize = Math.min(48 + totalDeg * 4, 80);

  return (
    <div
      className={`code-node ${isDead ? 'code-node--dead' : ''} ${isEntry ? 'code-node--entry' : ''} ${isApi ? 'code-node--api' : ''} ${selected ? 'code-node--selected' : ''} ${isExpanded ? 'code-node--expanded' : ''} ${hasChildren && !isExpanded ? 'expand-hint' : ''}`}
      style={{
        background: bgColor,
        border: `1.5px ${isExpanded ? 'dashed' : 'solid'} ${borderColor}`,
        boxShadow: selected
          ? `0 0 0 2px ${borderColor}, 0 0 24px ${glowColor}`
          : isExpanded
            ? `0 0 24px rgba(99,102,241,0.4)`
            : `0 0 12px ${glowColor}`,
        opacity,
        borderRadius: 10,
        padding: '10px 14px',
        minWidth: 160,
        maxWidth: 220,
        position: 'relative',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        userSelect: 'none',
      }}
    >
      {/* Language badge */}
      <div style={{
        position: 'absolute', top: -10, right: 10,
        background: borderColor, color: '#fff',
        fontSize: '0.6rem', fontWeight: 800, letterSpacing: '0.06em',
        padding: '2px 7px', borderRadius: 99,
      }}>
        {isEntry ? 'ENTRY' : isApi ? 'API' : cfg.label}
      </div>

      {/* Ring indicator (connectivity) */}
      <div style={{
        position: 'absolute', top: -8, left: -8,
        width: Math.min(ringSize, 24), height: Math.min(ringSize, 24),
        borderRadius: '50%',
        border: `2px solid ${ringColor}`,
        opacity: 0.25,
        animation: isApi ? 'pulse 2s infinite' : 'none',
      }} />

      {/* File name */}
      <div style={{
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: '0.78rem',
        fontWeight: 700,
        color: selected ? '#fff' : '#f1f5f9',
        marginBottom: 6,
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        maxWidth: 190,
      }}>
        {data.label}
      </div>

      {/* Mini stats row */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {fnCount > 0 && (
          <span style={{ fontSize: '0.65rem', color: '#94a3b8' }}>
            <span style={{ color: cfg.color, fontWeight: 700 }}>{fnCount}</span> fn
          </span>
        )}
        {clsCount > 0 && (
          <span style={{ fontSize: '0.65rem', color: '#94a3b8' }}>
            <span style={{ color: '#a78bfa', fontWeight: 700 }}>{clsCount}</span> cls
          </span>
        )}
        {routeCount > 0 && (
          <span style={{ fontSize: '0.65rem', color: '#94a3b8' }}>
            <span style={{ color: '#f59e0b', fontWeight: 700 }}>{routeCount}</span> routes
          </span>
        )}
        <span style={{ fontSize: '0.65rem', color: '#4b5563' }}>
          ↑{data.in_degree} ↓{data.out_degree}
        </span>
      </div>

      {/* Expand/collapse button */}
      {hasChildren && (
        <div
          className={`node-expand-btn ${isExpanded ? 'node-expand-btn--expanded' : ''}`}
          title={isExpanded ? 'Double-click to collapse' : 'Double-click to expand'}
        >
          {isExpanded ? '−' : '+'}
        </div>
      )}

      {/* React Flow handles */}
      <Handle type="target" position={Position.Top}    style={{ opacity: 0, width: 8, height: 8 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, width: 8, height: 8 }} />
    </div>
  );
}

const NODE_TYPES = {
  codeNode: CodeNode,
  functionNode: FunctionNode,
  classNode: ClassNode,
  routeNode: RouteNode,
};

/* ─────────────────────────────────────────────────────────────────
   SIDE PANEL
   ───────────────────────────────────────────────────────────────── */
function SidePanel({ node, onClose, onRunImpact, impactResult, impactLoading, allEdges }) {
  if (!node) return null;
  const d   = node.data;
  const cfg = getLangConfig(d.language);

  // Check if this is a child node
  const isChild = d._isChild;

  const imports  = allEdges.filter(e => e.source === node.id && !e.data?._isContain).map(e => e.target);
  const importedBy = allEdges.filter(e => e.target === node.id && !e.data?._isContain).map(e => e.source);

  return (
    <div className="graph-side-panel animate-slide">
      {/* Header */}
      <div className="gsp-header">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '0.84rem',
            fontWeight: 700,
            color: '#f1f5f9',
            marginBottom: 4,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {isChild && (
              <span style={{
                fontSize: '0.65rem',
                color: d._childType === 'function' ? '#818cf8' : d._childType === 'class' ? '#a78bfa' : '#f59e0b',
                marginRight: 6,
              }}>
                {d._childType === 'function' ? 'ƒ' : d._childType === 'class' ? '◆' : '🌐'}
              </span>
            )}
            {d.label}
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {isChild ? (
              <span style={{
                padding: '2px 8px', borderRadius: 99,
                fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.06em',
                background: d._childType === 'function' ? 'rgba(99,102,241,0.2)' : d._childType === 'class' ? 'rgba(167,139,250,0.2)' : 'rgba(245,158,11,0.2)',
                color: d._childType === 'function' ? '#818cf8' : d._childType === 'class' ? '#a78bfa' : '#f59e0b',
              }}>
                {d._childType?.toUpperCase()}
              </span>
            ) : (
              <span style={{
                padding: '2px 8px', borderRadius: 99,
                fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.06em',
                background: cfg.color, color: '#fff',
              }}>
                {d.language?.toUpperCase()}
              </span>
            )}
            {!isChild && d.is_entrypoint && <span className="gsp-badge gsp-badge--entry">ENTRY</span>}
            {!isChild && d.api_routes?.length > 0 && <span className="gsp-badge gsp-badge--api">API</span>}
            {!isChild && d.is_dead && <span className="gsp-badge gsp-badge--dead">DEAD</span>}
          </div>
        </div>
        <button className="gsp-close" onClick={onClose}><X size={15} /></button>
      </div>

      {/* Stats pills — only for file nodes */}
      {!isChild && (
        <div className="gsp-stats">
          {[
            { label: 'Lines',     value: d.lines     || 0, color: '#6366f1' },
            { label: 'Functions', value: (d.functions || []).length, color: '#06b6d4' },
            { label: 'Classes',   value: (d.classes || []).length,   color: '#a78bfa' },
            { label: 'Routes',    value: (d.api_routes || []).length, color: '#f59e0b' },
            { label: 'Imports',   value: d.out_degree || 0, color: '#94a3b8' },
            { label: 'Used by',   value: d.in_degree  || 0, color: '#10b981' },
          ].map(s => (
            <div key={s.label} className="gsp-stat">
              <div style={{ fontSize: '1.2rem', fontWeight: 800, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: '0.65rem', color: '#4b5563', fontWeight: 600, textTransform: 'uppercase' }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Child-specific info */}
      {isChild && d._childType === 'function' && (
        <div className="gsp-section">
          <div className="gsp-section-title">Function Details</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '0.78rem', color: '#818cf8' }}>
            {d.label}()
          </div>
          {d.line && <div style={{ fontSize: '0.72rem', color: '#4b5563', marginTop: 4 }}>Defined at line {d.line}</div>}
          <div style={{ fontSize: '0.72rem', color: '#4b5563', marginTop: 4 }}>
            In file: <span style={{ color: '#94a3b8' }}>{d._parentId}</span>
          </div>
        </div>
      )}

      {isChild && d._childType === 'class' && (
        <div className="gsp-section">
          <div className="gsp-section-title">Class Details</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '0.78rem', color: '#a78bfa' }}>
            {d.label}
          </div>
          {d.line && <div style={{ fontSize: '0.72rem', color: '#4b5563', marginTop: 4 }}>Defined at line {d.line}</div>}
          {d.methods?.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: '0.65rem', color: '#4b5563', fontWeight: 700, textTransform: 'uppercase', marginBottom: 6 }}>
                Methods ({d.methods.length})
              </div>
              <div className="gsp-chips">
                {d.methods.map((m, i) => (
                  <span key={i} className="gsp-chip gsp-chip--fn">{m}()</span>
                ))}
              </div>
            </div>
          )}
          <div style={{ fontSize: '0.72rem', color: '#4b5563', marginTop: 4 }}>
            In file: <span style={{ color: '#94a3b8' }}>{d._parentId}</span>
          </div>
        </div>
      )}

      {isChild && d._childType === 'route' && (
        <div className="gsp-section">
          <div className="gsp-section-title">Route Details</div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span className={`route-method route-method--${d.method}`} style={{ fontSize: '0.7rem', padding: '3px 8px' }}>
              {d.method}
            </span>
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '0.84rem', color: '#fcd34d' }}>
              {d.path}
            </span>
          </div>
          {d.handler && (
            <div style={{ fontSize: '0.72rem', color: '#4b5563', marginTop: 6 }}>
              Handler: <span style={{ color: '#818cf8' }}>{d.handler}()</span>
            </div>
          )}
          {d.line && <div style={{ fontSize: '0.72rem', color: '#4b5563', marginTop: 4 }}>Line {d.line}</div>}
          <div style={{ fontSize: '0.72rem', color: '#4b5563', marginTop: 4 }}>
            In file: <span style={{ color: '#94a3b8' }}>{d._parentId}</span>
          </div>
        </div>
      )}

      {/* Path — file nodes only */}
      {!isChild && (
        <div className="gsp-section">
          <div className="gsp-section-title">File Path</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '0.72rem', color: '#94a3b8', wordBreak: 'break-all' }}>
            {d.path}
          </div>
        </div>
      )}

      {/* Functions — file nodes only */}
      {!isChild && (d.functions || []).length > 0 && (
        <div className="gsp-section">
          <div className="gsp-section-title">Functions ({d.functions.length})</div>
          <div className="gsp-chips">
            {d.functions.slice(0, 20).map((fn, i) => (
              <span key={i} className="gsp-chip gsp-chip--fn">{getName(fn)}</span>
            ))}
          </div>
        </div>
      )}

      {/* Classes — file nodes only */}
      {!isChild && (d.classes || []).length > 0 && (
        <div className="gsp-section">
          <div className="gsp-section-title">Classes ({d.classes.length})</div>
          <div className="gsp-chips">
            {d.classes.map((cls, i) => (
              <span key={i} className="gsp-chip gsp-chip--cls">{getName(cls)}</span>
            ))}
          </div>
        </div>
      )}

      {/* API Routes — file nodes only */}
      {!isChild && (d.api_routes || []).length > 0 && (
        <div className="gsp-section">
          <div className="gsp-section-title">API Routes</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {d.api_routes.map((r, i) => (
              <div key={i} style={{ display: 'flex', gap: 7, alignItems: 'center', fontSize: '0.75rem' }}>
                <span style={{
                  padding: '1px 6px', borderRadius: 4, fontSize: '0.62rem', fontWeight: 800,
                  background: r.method === 'GET' ? 'rgba(16,185,129,0.2)' : 'rgba(99,102,241,0.2)',
                  color: r.method === 'GET' ? '#10b981' : '#6366f1',
                  border: `1px solid ${r.method === 'GET' ? 'rgba(16,185,129,0.4)' : 'rgba(99,102,241,0.4)'}`,
                }}>
                  {r.method}
                </span>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", color: '#f1f5f9' }}>{r.path}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Imports — file nodes only */}
      {!isChild && imports.length > 0 && (
        <div className="gsp-section">
          <div className="gsp-section-title">Imports ({imports.length} files)</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {imports.slice(0, 8).map((f, i) => (
              <div key={i} style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '0.7rem', color: '#6366f1', display: 'flex', alignItems: 'center', gap: 5 }}>
                <ChevronRight size={10} /> {f}
              </div>
            ))}
            {imports.length > 8 && <div style={{ fontSize: '0.7rem', color: '#4b5563' }}>+{imports.length - 8} more…</div>}
          </div>
        </div>
      )}

      {/* Imported by — file nodes only */}
      {!isChild && importedBy.length > 0 && (
        <div className="gsp-section">
          <div className="gsp-section-title">Used by ({importedBy.length} files)</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {importedBy.slice(0, 8).map((f, i) => (
              <div key={i} style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '0.7rem', color: '#10b981', display: 'flex', alignItems: 'center', gap: 5 }}>
                <ChevronRight size={10} /> {f}
              </div>
            ))}
            {importedBy.length > 8 && <div style={{ fontSize: '0.7rem', color: '#4b5563' }}>+{importedBy.length - 8} more…</div>}
          </div>
        </div>
      )}

      {/* Impact button — file nodes only */}
      {!isChild && (
        <div className="gsp-impact">
          <button
            className="btn btn-primary"
            style={{ width: '100%', justifyContent: 'center' }}
            onClick={onRunImpact}
            disabled={impactLoading}
          >
            {impactLoading
              ? <><Loader2 size={14} style={{ animation: 'spin 0.7s linear infinite' }} /> Running…</>
              : <><Zap size={14} /> Simulate Impact</>}
          </button>

          {impactResult && (
            <div className="impact-result animate-fade">
              {/* Risk summary row */}
              <div className="impact-summary">
                <span className={`risk-badge risk-${impactResult.risk}`}>{impactResult.risk} Risk</span>
                <span className="impact-summary-count">
                  <strong>{impactResult.affected_count}</strong> file{impactResult.affected_count === 1 ? '' : 's'} affected
                  {impactResult.affected_routes?.length > 0 && (
                    <> · <strong>{impactResult.affected_routes.length}</strong> route{impactResult.affected_routes.length === 1 ? '' : 's'} at risk</>
                  )}
                </span>
              </div>

              {impactResult.affected_count === 0 && (
                <div className="impact-safe">
                  ✅ Nothing else imports this file — safe to change in isolation.
                </div>
              )}

              {/* Affected files list — mirrors the red glow on the canvas */}
              {impactResult.affected_files?.length > 0 && (
                <div className="impact-block">
                  <div className="gsp-section-title" style={{ marginBottom: 6 }}>
                    Affected Files ({impactResult.affected_files.length})
                  </div>
                  <div className="impact-file-list">
                    {impactResult.affected_files.map((f, i) => (
                      <div key={i} className="impact-file-item">
                        <span className="impact-dot" /> {f}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Affected API routes */}
              {impactResult.affected_routes?.length > 0 && (
                <div className="impact-block">
                  <div className="gsp-section-title" style={{ marginBottom: 6 }}>
                    Affected Routes ({impactResult.affected_routes.length})
                  </div>
                  <div className="impact-file-list">
                    {impactResult.affected_routes.map((r, i) => (
                      <div key={i} className="impact-file-item">
                        <span className={`route-method route-method--${r.method}`} style={{ fontSize: '0.6rem', padding: '1px 5px' }}>
                          {r.method}
                        </span>
                        <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>{r.path}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
   STATS HUD
   ───────────────────────────────────────────────────────────────── */
function StatsHud({ stats, selectedNode, expandedCount }) {
  if (!stats) return null;
  const langs = stats.languages || {};
  return (
    <div className="graph-stats-hud">
      <div className="gsh-row">
        <Box size={12} style={{ color: '#6366f1' }} />
        <span><strong style={{ color: '#f1f5f9' }}>{stats.total_nodes}</strong> nodes</span>
        <span style={{ color: '#4b5563' }}>·</span>
        <span><strong style={{ color: '#f1f5f9' }}>{stats.total_edges}</strong> edges</span>
      </div>
      <div className="gsh-langs">
        {Object.entries(langs).map(([lang, cnt]) => {
          const cfg = getLangConfig(lang);
          return (
            <span key={lang} style={{ color: cfg.color, fontSize: '0.7rem', fontWeight: 700 }}>
              {cfg.label}: {cnt}
            </span>
          );
        })}
      </div>
      {stats.dead_code_count > 0 && (
        <div style={{ fontSize: '0.7rem', color: '#ef4444' }}>
          ⚠ {stats.dead_code_count} dead files
        </div>
      )}
      {expandedCount > 0 && (
        <div style={{ fontSize: '0.7rem', color: '#6366f1' }}>
          ⊕ {expandedCount} files expanded
        </div>
      )}
      {stats.most_connected && (
        <div style={{ fontSize: '0.68rem', color: '#4b5563', marginTop: 4 }}>
          Most connected:{' '}
          <span style={{ color: '#6366f1', fontFamily: "'JetBrains Mono', monospace" }}>
            {stats.most_connected.split('/').pop()}
          </span>
        </div>
      )}
      {selectedNode && (
        <div style={{
          marginTop: 8, paddingTop: 8,
          borderTop: '1px solid rgba(255,255,255,0.07)',
          fontSize: '0.7rem', color: '#94a3b8',
        }}>
          Selected:{' '}
          <span style={{ color: '#f1f5f9', fontFamily: "'JetBrains Mono', monospace" }}>
            {selectedNode.data.label}
          </span>
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
   LEGEND
   ───────────────────────────────────────────────────────────────── */
function Legend() {
  const items = [
    { color: '#6366f1', label: 'Python' },
    { color: '#06b6d4', label: 'JavaScript' },
    { color: '#3b82f6', label: 'TypeScript' },
    { color: '#f59e0b', label: 'API Route' },
    { color: '#10b981', label: 'Entrypoint' },
    { color: '#ef4444', label: 'Dead Code', dim: true },
    { color: '#818cf8', label: 'ƒ Function', icon: true },
    { color: '#a78bfa', label: '◆ Class', icon: true },
    { color: '#fcd34d', label: '🌐 Route', icon: true },
  ];
  return (
    <div className="graph-legend">
      {items.map(it => (
        <div key={it.label} style={{ display: 'flex', alignItems: 'center', gap: 5, opacity: it.dim ? 0.6 : 1 }}>
          {!it.icon ? (
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: it.color, flexShrink: 0 }} />
          ) : (
            <div style={{ width: 10, height: 10, borderRadius: 2, background: it.color, flexShrink: 0, opacity: 0.6 }} />
          )}
          <span style={{ fontSize: '0.68rem', color: '#64748b', whiteSpace: 'nowrap' }}>{it.label}</span>
        </div>
      ))}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
   MAIN GRAPH EXPLORER INNER
   ───────────────────────────────────────────────────────────────── */
function GraphExplorerInner({ repo }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [rawNodes, setRawNodes] = useState([]);
  const [rawEdges, setRawEdges] = useState([]);
  const [stats, setStats]       = useState(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');

  const [selectedNode, setSelectedNode] = useState(null);
  const [impactResult, setImpactResult]  = useState(null);
  const [impactLoading, setImpactLoading] = useState(false);
  const [impactNodeIds, setImpactNodeIds] = useState(new Set());

  const [search, setSearch]     = useState('');
  const [langFilter, setLangFilter] = useState('all');

  // Track which file nodes are expanded
  const [expandedFiles, setExpandedFiles] = useState(new Set());

  // First-run instructions banner (dismissible, remembered)
  const [showHelp, setShowHelp] = useState(() => localStorage.getItem('cd_graph_help') !== '0');
  const dismissHelp = () => { setShowHelp(false); localStorage.setItem('cd_graph_help', '0'); };

  const { fitView } = useReactFlow();

  /* ── Fetch graph data ── */
  const fetchGraph = useCallback(async (forceRefresh = false) => {
    if (!repo) return;
    setLoading(true);
    setError('');
    setSelectedNode(null);
    setImpactResult(null);
    setImpactNodeIds(new Set());
    setExpandedFiles(new Set());
    try {
      // forceRefresh (the "Rebuild Graph" button) pulls the latest code + rebuilds;
      // the initial load uses the cached graph for speed.
      const res = await axios.post(`${API}/api/graph/full`, { repo_path: repo, refresh: forceRefresh });
      const { nodes: rn, edges: re, stats: rs } = res.data;
      setRawNodes(rn);
      setRawEdges(re);
      setStats(rs);

      const laid = computeLayout(rn, re);
      setNodes(laid);
      setEdges(re.map(e => ({
        ...e,
        markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: '#4b5563' },
        style: { stroke: '#4b5563', strokeWidth: 1.5 },
        labelStyle: { fill: '#4b5563', fontSize: 10 },
        labelBgStyle: { fill: 'transparent' },
      })));

      setTimeout(() => fitView({ padding: 0.15, duration: 600 }), 100);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [repo, fitView, setNodes, setEdges]);

  useEffect(() => { fetchGraph(); }, [fetchGraph]);

  /* ── Rebuild displayed nodes when expand state or filters change ── */
  const rebuildDisplay = useCallback(() => {
    if (!rawNodes.length) return;

    const q = search.toLowerCase().trim();

    // Filter file nodes
    const filtered = rawNodes.filter(n => {
      const matchSearch = !q || n.data.label.toLowerCase().includes(q) || n.data.path.toLowerCase().includes(q);
      const matchLang   = langFilter === 'all' || n.data.language === langFilter;
      return matchSearch && matchLang;
    });

    const filteredIds = new Set(filtered.map(n => n.id));

    // Mark expanded nodes
    const displayNodes = filtered.map(n => ({
      ...n,
      data: {
        ...n.data,
        _expanded: expandedFiles.has(n.id),
      },
    }));

    // Generate child nodes for expanded files
    const allChildNodes = [];
    const allChildEdges = [];
    expandedFiles.forEach(fileId => {
      const fileNode = displayNodes.find(n => n.id === fileId);
      if (!fileNode) return;
      const { childNodes, childEdges } = generateChildNodesAndEdges(fileNode);
      allChildNodes.push(...childNodes);
      allChildEdges.push(...childEdges);
    });

    const allNodes = [...displayNodes, ...allChildNodes];
    const fileEdges = rawEdges.filter(e => filteredIds.has(e.source) && filteredIds.has(e.target));
    const allEdgesArr = [...fileEdges, ...allChildEdges];

    const laid = computeLayout(allNodes, allEdgesArr);

    setNodes(laid.map(n => ({
      ...n,
      style: {
        opacity: filteredIds.has(n.id) || n.data?._isChild ? 1 : 0.15,
        transition: 'opacity 0.3s ease',
      },
    })));

    setEdges(allEdgesArr.map(e => ({
      ...e,
      markerEnd: e.markerEnd || { type: MarkerType.ArrowClosed, width: 12, height: 12, color: '#4b5563' },
      style: e.style || { stroke: '#4b5563', strokeWidth: 1.5 },
    })));

    setTimeout(() => fitView({ padding: 0.15, duration: 400 }), 50);
  }, [rawNodes, rawEdges, search, langFilter, expandedFiles, fitView, setNodes, setEdges]);

  useEffect(() => { rebuildDisplay(); }, [rebuildDisplay]);

  /* ── Node click (select) — also clears any stuck impact styling ── */
  const onNodeClick = useCallback((_, node) => {
    setSelectedNode(node);
    setImpactResult(null);
    setImpactNodeIds(new Set());
    setNodes(nds => nds.map(n => ({
      ...n,
      selected: n.id === node.id,
      style: n.data?._isChild ? n.style : { opacity: 1, transition: 'opacity 0.3s ease' },
    })));
    // Restore file-to-file edges to default; leave child/contain edges alone
    setEdges(eds => eds.map(e => {
      const isFileEdge = !String(e.source).includes('::') && !String(e.target).includes('::');
      if (!isFileEdge) return e;
      return {
        ...e,
        style: { stroke: '#4b5563', strokeWidth: 1.5 },
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: '#4b5563' },
      };
    }));
  }, [setNodes, setEdges]);

  /* ── Node double-click (expand/collapse) ── */
  const onNodeDoubleClick = useCallback((_, node) => {
    // Only file nodes can be expanded
    if (node.data?._isChild) return;

    const fns = node.data.functions || [];
    const cls = node.data.classes || [];
    const routes = node.data.api_routes || [];
    if (fns.length + cls.length + routes.length === 0) return;

    setExpandedFiles(prev => {
      const next = new Set(prev);
      if (next.has(node.id)) {
        next.delete(node.id);
      } else {
        next.add(node.id);
      }
      return next;
    });
  }, []);

  /* ── Pane click (deselect) ── */
  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
    setImpactResult(null);
    setImpactNodeIds(new Set());
    setNodes(nds => nds.map(n => ({ ...n, selected: false })));
    setEdges(eds => eds.map(e => ({
      ...e,
      style: e.data?._isContain
        ? e.style
        : { stroke: '#4b5563', strokeWidth: 1.5 },
      animated: e.data?._isContain ? e.animated : true,
    })));
  }, [setNodes, setEdges]);

  /* ── Run Impact ── */
  const runImpact = useCallback(async () => {
    if (!selectedNode || !repo) return;
    setImpactLoading(true);
    setImpactResult(null);
    try {
      const res = await axios.post(`${API}/api/graph/impact`, {
        repo_path: repo,
        target_file: selectedNode.id,
      });
      const data = res.data;
      setImpactResult(data);

      const affectedSet = new Set(data.affected_files || []);
      setImpactNodeIds(affectedSet);

      // Origin node = bright white ring; affected = red glow; rest dimmed
      setNodes(nds => nds.map(n => {
        if (n.data?._isChild) return n;
        if (n.id === selectedNode.id) {
          return {
            ...n,
            selected: true,
            style: { opacity: 1, filter: 'drop-shadow(0 0 14px rgba(255,255,255,0.6))' },
          };
        }
        if (affectedSet.has(n.id)) {
          return {
            ...n,
            selected: false,
            style: { opacity: 1, filter: 'drop-shadow(0 0 12px rgba(248,113,113,0.95))' },
          };
        }
        return { ...n, selected: false, style: { opacity: 0.15, transition: 'opacity 0.3s ease' } };
      }));

      // Highlight the blast-radius edges red; fade the rest (file edges only)
      setEdges(eds => eds.map(e => {
        const isFileEdge = !String(e.source).includes('::') && !String(e.target).includes('::');
        if (!isFileEdge) return e;
        const isAffectedEdge = affectedSet.has(e.source) || affectedSet.has(e.target)
          || e.source === selectedNode.id || e.target === selectedNode.id;
        return {
          ...e,
          style: {
            stroke: isAffectedEdge ? '#f87171' : '#16241d',
            strokeWidth: isAffectedEdge ? 2.5 : 1,
          },
          animated: isAffectedEdge,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 14, height: 14,
            color: isAffectedEdge ? '#f87171' : '#16241d',
          },
        };
      }));
    } catch (e) {
      console.error('Impact error:', e);
    } finally {
      setImpactLoading(false);
    }
  }, [selectedNode, repo, setNodes, setEdges]);

  /* ── Languages available in current graph ── */
  const availableLangs = useMemo(() => {
    const langs = new Set(rawNodes.map(n => n.data.language).filter(Boolean));
    return Array.from(langs);
  }, [rawNodes]);

  if (!repo) {
    return (
      <div className="empty-state animate-fade" style={{ height: '100%' }}>
        <div className="empty-icon">🕸️</div>
        <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>No repository loaded</h3>
        <p>Load a repository first to explore the code graph.</p>
      </div>
    );
  }

  return (
    <div className="graph-explorer-shell">
      {/* ── Toolbar ── */}
      <div className="graph-toolbar">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
          <Search size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
          <input
            className="graph-search"
            placeholder="Search files…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <Filter size={13} style={{ color: '#4b5563' }} />
          {['all', ...availableLangs].map(lang => (
            <button
              key={lang}
              className={`graph-filter-btn ${langFilter === lang ? 'active' : ''}`}
              onClick={() => setLangFilter(lang)}
              style={langFilter === lang ? { borderColor: getLangConfig(lang).color, color: getLangConfig(lang).color } : {}}
            >
              {lang === 'all' ? 'All' : lang.toUpperCase()}
            </button>
          ))}
        </div>

        {expandedFiles.size > 0 && (
          <button
            className="btn btn-secondary"
            style={{ padding: '6px 12px', fontSize: '0.72rem' }}
            onClick={() => setExpandedFiles(new Set())}
            title="Collapse all expanded files"
          >
            <Minus size={12} /> Collapse All
          </button>
        )}

        <button
          className="btn btn-secondary"
          style={{ padding: '6px 12px', fontSize: '0.78rem' }}
          onClick={() => fetchGraph(true)}
          disabled={loading}
        >
          {loading
            ? <Loader2 size={13} style={{ animation: 'spin 0.7s linear infinite' }} />
            : <RefreshCw size={13} />}
          {loading ? 'Building…' : 'Rebuild Graph'}
        </button>
      </div>

      {/* ── Error ── */}
      {error && (
        <div style={{ padding: '10px 20px', background: 'rgba(239,68,68,0.1)', borderBottom: '1px solid rgba(239,68,68,0.3)', fontSize: '0.84rem', color: '#ef4444' }}>
          ❌ {error}
        </div>
      )}

      {/* ── First-run instructions ── */}
      {showHelp && !loading && (
        <div className="graph-help-bar">
          <span className="graph-help-title">
            <Activity size={14} style={{ color: 'var(--accent)' }} /> Explore your graph
          </span>
          <span className="graph-help-step"><b>Click</b> a node to inspect its functions, classes &amp; routes</span>
          <span className="graph-help-sep">·</span>
          <span className="graph-help-step"><b>Double-click</b> to expand a file's internals</span>
          <span className="graph-help-sep">·</span>
          <span className="graph-help-step">Select a node → <b>Simulate Impact</b> to see the blast radius in red</span>
          <span className="graph-help-sep">·</span>
          <span className="graph-help-step">Scroll to zoom, drag to pan</span>
          <button className="graph-help-close" onClick={dismissHelp} title="Dismiss"><X size={14} /></button>
        </div>
      )}

      {/* ── Canvas + Side Panel ── */}
      <div style={{ flex: 1, display: 'flex', position: 'relative', overflow: 'hidden' }}>

        {/* Loading overlay */}
        {loading && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 50,
            background: 'rgba(10,12,20,0.85)',
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16,
          }}>
            <div className="graph-loader-ring" />
            <div style={{ color: '#94a3b8', fontSize: '0.875rem' }}>Building dependency graph…</div>
            <div style={{ color: '#4b5563', fontSize: '0.78rem' }}>Parsing AST, resolving imports, computing layout</div>
          </div>
        )}

        {/* React Flow canvas */}
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onNodeDoubleClick={onNodeDoubleClick}
          onPaneClick={onPaneClick}
          nodeTypes={NODE_TYPES}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          minZoom={0.05}
          maxZoom={3}
          defaultEdgeOptions={{ animated: true }}
          style={{ background: 'transparent' }}
          proOptions={{ hideAttribution: true }}
        >
          <Background
            variant="dots"
            gap={28}
            size={1}
            color="rgba(255,255,255,0.04)"
          />
          <Controls
            style={{
              background: 'rgba(22,25,41,0.9)',
              border: '1px solid rgba(255,255,255,0.07)',
              borderRadius: 10,
              backdropFilter: 'blur(12px)',
            }}
          />
          <MiniMap
            style={{
              background: 'rgba(15,18,32,0.95)',
              border: '1px solid rgba(255,255,255,0.07)',
              borderRadius: 10,
            }}
            nodeColor={n => {
              if (n.data?._childType === 'function') return '#818cf8';
              if (n.data?._childType === 'class')    return '#a78bfa';
              if (n.data?._childType === 'route')    return '#f59e0b';
              const cfg = getLangConfig(n.data?.language);
              if (n.data?.api_routes?.length)  return '#f59e0b';
              if (n.data?.is_entrypoint)        return '#10b981';
              if (n.data?.is_dead)              return '#ef4444';
              return cfg.color;
            }}
            maskColor="rgba(10,12,20,0.6)"
          />

          {/* Stats HUD */}
          <Panel position="top-left">
            <StatsHud stats={stats} selectedNode={selectedNode} expandedCount={expandedFiles.size} />
          </Panel>

          {/* Legend */}
          <Panel position="bottom-left">
            <Legend />
          </Panel>

          {/* Expand hint */}
          {expandedFiles.size === 0 && rawNodes.length > 0 && (
            <Panel position="bottom-right" style={{ marginBottom: 8, marginRight: 8 }}>
              <div style={{
                background: 'rgba(15,18,32,0.92)',
                border: '1px solid rgba(99,102,241,0.3)',
                borderRadius: 8, padding: '8px 12px',
                fontSize: '0.7rem', color: '#94a3b8',
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                <Plus size={12} style={{ color: '#6366f1' }} />
                Double-click a file to expand its internals
              </div>
            </Panel>
          )}

          {/* Impact badge */}
          {impactNodeIds.size > 0 && (
            <Panel position="top-right" style={{ marginRight: selectedNode ? 340 : 16 }}>
              <div style={{
                background: 'rgba(239,68,68,0.12)',
                border: '1px solid rgba(239,68,68,0.4)',
                borderRadius: 8, padding: '8px 14px',
                display: 'flex', alignItems: 'center', gap: 8,
                animation: 'pulse 2s infinite',
              }}>
                <Radio size={13} style={{ color: '#ef4444' }} />
                <span style={{ fontSize: '0.78rem', color: '#ef4444', fontWeight: 700 }}>
                  {impactNodeIds.size} files impacted
                </span>
              </div>
            </Panel>
          )}
        </ReactFlow>

        {/* Side Panel */}
        {selectedNode && (
          <SidePanel
            node={selectedNode}
            onClose={() => { onPaneClick(); }}
            onRunImpact={runImpact}
            impactResult={impactResult}
            impactLoading={impactLoading}
            allEdges={[...rawEdges, ...edges.filter(e => e.data?._isContain)]}
          />
        )}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
   EXPORT (wrap with ReactFlowProvider)
   ───────────────────────────────────────────────────────────────── */
export default function GraphExplorer({ repo }) {
  return (
    <ReactFlowProvider>
      <GraphExplorerInner repo={repo} />
    </ReactFlowProvider>
  );
}
