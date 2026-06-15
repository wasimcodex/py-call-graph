"""
flow_renderer.py - Output renderers for flow / decision trees.

Supports:
  - JSON: Raw structured data
  - Mermaid: Text-based diagram for Markdown
  - HTML: Interactive D3.js collapsible tree with distinct node-type visuals
"""

import json
import os
from typing import Optional


def render_flow_json(flow_tree: dict, output_path: str) -> str:
    """Render the flow tree as a JSON file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(flow_tree, f, indent=2, default=str)
    return output_path


def render_flow_mermaid(flow_tree: dict, output_path: str) -> str:
    """Render the flow tree as a Mermaid diagram in a Markdown file."""
    lines = ['```mermaid', 'graph TD']
    counter = {'id': 0}
    node_ids = {}

    kind_styles = {
        'function':     'fill:#7c3aed,stroke:#a78bfa,color:#fff',
        'call':         'fill:#6366f1,stroke:#818cf8,color:#fff',
        'assign':       'fill:#10b981,stroke:#34d399,color:#fff',
        'mutation':     'fill:#f97316,stroke:#fb923c,color:#fff',
        'branch':       'fill:#f59e0b,stroke:#fbbf24,color:#000',
        'branch_true':  'fill:#22c55e,stroke:#4ade80,color:#000',
        'branch_false': 'fill:#ef4444,stroke:#f87171,color:#fff',
        'branch_elif':  'fill:#eab308,stroke:#facc15,color:#000',
        'loop_for':     'fill:#06b6d4,stroke:#22d3ee,color:#000',
        'loop_while':   'fill:#06b6d4,stroke:#22d3ee,color:#000',
        'loop_body':    'fill:#0891b2,stroke:#06b6d4,color:#fff',
        'try':          'fill:#f59e0b,stroke:#fbbf24,color:#000',
        'except':       'fill:#ef4444,stroke:#f87171,color:#fff',
        'finally':      'fill:#6b7280,stroke:#9ca3af,color:#fff',
        'return':       'fill:#ec4899,stroke:#f472b6,color:#fff',
        'raise':        'fill:#ef4444,stroke:#f87171,color:#fff',
        'context':      'fill:#14b8a6,stroke:#2dd4bf,color:#000',
    }

    def get_id(key: str) -> str:
        if key not in node_ids:
            node_ids[key] = f"N{counter['id']}"
            counter['id'] += 1
        return node_ids[key]

    def sanitize(text: str) -> str:
        return text.replace('"', "'").replace('<', '&lt;').replace('>', '&gt;')[:60]

    def walk(node, parent_id=None):
        uid = f"{node.get('kind','?')}_{node.get('line','?')}_{counter['id']}"
        nid = get_id(uid)
        label = sanitize(node.get('label', '?'))
        kind = node.get('kind', 'other')

        if kind in ('branch', 'branch_elif', 'match', 'case'):
            lines.append(f'    {nid}{{{{{label}}}}}')
        elif kind in ('loop_for', 'loop_while', 'loop_async_for'):
            lines.append(f'    {nid}(["{label}"])')
        else:
            lines.append(f'    {nid}["{label}"]')

        style = kind_styles.get(kind, 'fill:#6b7280,stroke:#9ca3af,color:#fff')
        lines.append(f'    style {nid} {style}')

        if parent_id is not None:
            lines.append(f'    {parent_id} --> {nid}')

        for child in node.get('children', []):
            walk(child, nid)

    walk(flow_tree)
    lines.append('```')

    content = '\n'.join(lines)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"# Flow Tree\n\n{content}\n")
    return output_path


def render_flow_html(flow_tree: dict, output_path: str,
                     project_dir: Optional[str] = None) -> str:
    """Render the flow tree as an interactive HTML page with D3.js."""
    tree_data = json.dumps(flow_tree, default=str)
    project_label = os.path.basename(project_dir) if project_dir else 'Project'

    html = _FLOW_HTML_TEMPLATE.replace('__TREE_DATA__', tree_data).replace(
        '__PROJECT_LABEL__', project_label)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return output_path


_FLOW_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Flow Tree &mdash; __PROJECT_LABEL__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  :root {
    --bg-primary: #0f0f1a;
    --bg-secondary: #1a1a2e;
    --bg-tertiary: #16213e;
    --bg-card: #1a1a2eee;
    --accent-primary: #7c3aed;
    --accent-secondary: #a78bfa;
    --accent-glow: #7c3aed44;
    --text-primary: #e2e8f0;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --border-subtle: #ffffff10;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    overflow: hidden;
    height: 100vh;
    width: 100vw;
  }

  .topbar {
    position: fixed; top: 0; left: 0; right: 0;
    height: 56px;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-subtle);
    display: flex; align-items: center;
    padding: 0 24px; z-index: 100;
    backdrop-filter: blur(12px);
    gap: 16px;
  }

  .topbar .logo {
    font-weight: 700; font-size: 16px;
    color: var(--accent-secondary);
    display: flex; align-items: center; gap: 8px;
    white-space: nowrap;
  }

  .topbar .logo svg { width: 22px; height: 22px; }

  .search-box { flex: 1; max-width: 400px; position: relative; }

  .search-box input {
    width: 100%;
    padding: 8px 12px 8px 36px;
    border-radius: 8px;
    border: 1px solid var(--border-subtle);
    background: var(--bg-primary);
    color: var(--text-primary);
    font-family: 'Inter', sans-serif;
    font-size: 13px; outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
  }

  .search-box input:focus {
    border-color: var(--accent-primary);
    box-shadow: 0 0 0 3px var(--accent-glow);
  }

  .search-box .search-icon {
    position: absolute; left: 10px; top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted); font-size: 14px;
  }

  .stats {
    margin-left: auto; display: flex; gap: 16px;
    font-size: 12px; color: var(--text-secondary);
  }

  .stats .stat {
    display: flex; align-items: center; gap: 4px;
  }

  .stats .stat .dot {
    width: 8px; height: 8px;
    border-radius: 50%; display: inline-block;
  }

  .btn-group { display: flex; gap: 6px; }

  .btn {
    padding: 6px 14px; border-radius: 6px;
    border: 1px solid var(--border-subtle);
    background: var(--bg-primary);
    color: var(--text-secondary);
    font-family: 'Inter', sans-serif;
    font-size: 12px; cursor: pointer;
    transition: all 0.15s;
  }

  .btn:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
    border-color: var(--accent-primary);
  }

  #canvas {
    position: fixed;
    top: 56px; left: 0; right: 0; bottom: 0;
    background:
      radial-gradient(circle at 20% 50%, #7c3aed08 0%, transparent 50%),
      radial-gradient(circle at 80% 20%, #6366f108 0%, transparent 50%),
      var(--bg-primary);
  }

  /* Detail panel */
  .detail-panel {
    position: fixed; top: 56px; right: 0; width: 400px; bottom: 0;
    background: var(--bg-card);
    border-left: 1px solid var(--border-subtle);
    backdrop-filter: blur(16px);
    padding: 24px; overflow-y: auto;
    transform: translateX(100%);
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    z-index: 90;
  }
  .detail-panel.open { transform: translateX(0); }

  .detail-panel .close-btn {
    position: absolute; top: 16px; right: 16px;
    background: none; border: none;
    color: var(--text-muted); font-size: 20px;
    cursor: pointer; transition: color 0.15s;
  }
  .detail-panel .close-btn:hover { color: var(--text-primary); }

  .detail-panel h2 {
    font-size: 16px; font-weight: 600;
    color: var(--accent-secondary);
    margin-bottom: 4px; word-break: break-all;
  }

  .detail-panel .kind-badge {
    display: inline-block; padding: 2px 10px;
    border-radius: 999px; font-size: 10px;
    font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.04em; margin-bottom: 12px;
  }

  .detail-panel .meta-grid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 6px 12px; font-size: 13px; margin-bottom: 12px;
  }
  .detail-panel .meta-grid .label { color: var(--text-muted); font-weight: 500; }
  .detail-panel .meta-grid .value {
    color: var(--text-secondary);
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px; word-break: break-all;
  }

  .detail-panel .code-block {
    background: var(--bg-primary);
    border: 1px solid var(--border-subtle);
    border-radius: 8px; padding: 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px; color: var(--accent-secondary);
    margin-bottom: 12px; overflow-x: auto;
    white-space: pre-wrap; word-break: break-all;
  }

  .detail-panel .section-title {
    font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.05em;
    color: var(--text-muted); margin: 14px 0 6px;
  }

  .detail-panel .flow-list { list-style: none; padding: 0; }
  .detail-panel .flow-list li {
    padding: 4px 8px; font-size: 12px;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-secondary); border-radius: 4px;
  }
  .detail-panel .flow-list li:nth-child(odd) {
    background: var(--bg-primary);
  }

  /* Node styles */
  .node { cursor: pointer; }
  .node text {
    font-family: 'JetBrains Mono', 'Inter', sans-serif;
    font-size: 11px; font-weight: 500;
    transition: fill 0.15s;
  }
  .node text:hover { fill: var(--accent-secondary) !important; }

  .link {
    fill: none; stroke: var(--border-subtle);
    stroke-width: 1.5px; stroke-opacity: 0.5;
    transition: stroke 0.2s;
  }

  /* Tooltip */
  .tooltip {
    position: fixed;
    padding: 8px 12px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    font-size: 12px;
    color: var(--text-primary);
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s;
    z-index: 200;
    max-width: 400px;
    box-shadow: 0 8px 32px #00000066;
  }
  .tooltip.show { opacity: 1; }

  /* Legend */
  .legend {
    position: fixed; bottom: 16px; left: 16px;
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 10px; padding: 14px 18px;
    font-size: 11px; color: var(--text-muted);
    backdrop-filter: blur(12px);
    line-height: 2; z-index: 80;
    max-height: 60vh; overflow-y: auto;
  }
  .legend .legend-title {
    font-weight: 600; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.05em;
    margin-bottom: 6px; color: var(--text-secondary);
  }
  .legend .legend-item {
    display: flex; align-items: center; gap: 8px;
  }
  .legend .legend-dot {
    width: 10px; height: 10px; border-radius: 2px;
    display: inline-block; flex-shrink: 0;
  }
</style>
</head>
<body>

<div class="topbar">
  <div class="logo">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
    </svg>
    PyCallGraph &mdash; Flow Tree
  </div>
  <div class="search-box">
    <span class="search-icon">&#x1F50D;</span>
    <input type="text" id="searchInput" placeholder="Search nodes..." autocomplete="off">
  </div>
  <div class="stats" id="stats"></div>
  <div class="btn-group">
    <button class="btn" id="btnExpandAll">Expand All</button>
    <button class="btn" id="btnCollapseAll">Collapse All</button>
    <button class="btn" id="btnResetZoom">Reset View</button>
  </div>
</div>

<div id="canvas"></div>

<div class="detail-panel" id="detailPanel">
  <button class="close-btn" id="closePanel">&times;</button>
  <div id="panelContent"></div>
</div>

<div class="tooltip" id="tooltip"></div>

<div class="legend">
  <div class="legend-title">Node Types</div>
  <div class="legend-item"><span class="legend-dot" style="background:#7c3aed;border-radius:50%"></span> Function</div>
  <div class="legend-item"><span class="legend-dot" style="background:#6366f1;border-radius:50%"></span> Call</div>
  <div class="legend-item"><span class="legend-dot" style="background:#10b981"></span> Assignment</div>
  <div class="legend-item"><span class="legend-dot" style="background:#f97316"></span> Mutation</div>
  <div class="legend-item"><span class="legend-dot" style="background:#f59e0b;transform:rotate(45deg)"></span> Branch (if)</div>
  <div class="legend-item"><span class="legend-dot" style="background:#22c55e"></span> True branch</div>
  <div class="legend-item"><span class="legend-dot" style="background:#ef4444"></span> False / except</div>
  <div class="legend-item"><span class="legend-dot" style="background:#06b6d4;clip-path:polygon(50% 0%,0% 100%,100% 100%)"></span> Loop</div>
  <div class="legend-item"><span class="legend-dot" style="background:#f59e0b"></span> Try</div>
  <div class="legend-item"><span class="legend-dot" style="background:#ec4899;border-radius:50%"></span> Return</div>
  <div class="legend-item"><span class="legend-dot" style="background:#14b8a6;border-radius:50%"></span> Context (with)</div>
</div>

<script>
const rawData = __TREE_DATA__;

// ── Color & icon maps ─────────────────────────────────
const kindColors = {
  'function':'#7c3aed','call':'#6366f1','assign':'#10b981','mutation':'#f97316',
  'branch':'#f59e0b','branch_true':'#22c55e','branch_false':'#ef4444','branch_elif':'#eab308',
  'loop_for':'#06b6d4','loop_while':'#06b6d4','loop_async_for':'#06b6d4',
  'loop_body':'#0891b2','loop_else':'#0e7490',
  'try':'#f59e0b','try_body':'#d97706','except':'#ef4444','try_else':'#84cc16','finally':'#6b7280',
  'context':'#14b8a6','context_async':'#14b8a6',
  'return':'#ec4899','yield':'#d946ef','raise':'#ef4444','assert':'#8b5cf6',
  'break':'#fb923c','continue':'#fb923c','pass':'#6b7280',
  'import':'#6b7280','def':'#7c3aed','class':'#7c3aed',
  'match':'#f59e0b','case':'#fbbf24',
  'expression':'#94a3b8','recursive':'#f59e0b','depth_limit':'#6b7280',
  'delete':'#f87171','global':'#6b7280','nonlocal':'#6b7280','other':'#6b7280',
};

const kindIcons = {
  'function':'\u0192','call':'\u2192','assign':'\u2190','mutation':'\u21ba',
  'branch':'\u25c6','branch_true':'','branch_false':'','branch_elif':'\u25c6',
  'loop_for':'\u27f3','loop_while':'\u27f3','loop_async_for':'\u27f3',
  'loop_body':'\u21b3','loop_else':'\u21b3',
  'try':'\u26a1','try_body':'\u21b3','except':'\u270b','try_else':'\u21b3','finally':'\u23cf',
  'context':'\ud83d\udce6','context_async':'\ud83d\udce6',
  'return':'\u23ce','yield':'\u23ce','raise':'\ud83d\udca5','assert':'\u2713',
  'break':'\u26d4','continue':'\u21aa','pass':'\u00b7',
  'import':'\ud83d\udce5','def':'\u0192','class':'\u25ce',
  'match':'\u25c6','case':'\u25b8','expression':'\u2022',
  'recursive':'\u21bb','depth_limit':'\u22ef',
  'delete':'\u2715','global':'G','nonlocal':'N','other':'\u2022',
};

// Shapes: 'circle', 'diamond', 'square', 'triangle'
const kindShapes = {
  'function':'circle','call':'circle','recursive':'circle','depth_limit':'circle',
  'branch':'diamond','branch_elif':'diamond','match':'diamond','case':'diamond',
  'assign':'square','mutation':'square','expression':'square','delete':'square',
  'loop_for':'triangle','loop_while':'triangle','loop_async_for':'triangle',
  'return':'circle','yield':'circle','raise':'circle',
};

function getShape(kind) { return kindShapes[kind] || 'circle'; }
function getColor(d) { return kindColors[d.data.kind] || '#6b7280'; }

// ── Stats ──────────────────────────────────────────────
function countStats(d) {
  let total=0, branches=0, calls=0, assigns=0;
  function walk(n) {
    total++;
    if (n.kind==='branch'||n.kind==='branch_elif') branches++;
    if (n.kind==='call') calls++;
    if (n.kind==='assign'||n.kind==='mutation') assigns++;
    (n.children||[]).forEach(walk);
  }
  walk(d);
  return {total,branches,calls,assigns};
}
const stats = countStats(rawData);
document.getElementById('stats').innerHTML =
  `<span class="stat">${stats.total} nodes</span>` +
  `<span class="stat"><span class="dot" style="background:#f59e0b"></span>${stats.branches} branches</span>` +
  `<span class="stat"><span class="dot" style="background:#6366f1"></span>${stats.calls} calls</span>` +
  `<span class="stat"><span class="dot" style="background:#10b981"></span>${stats.assigns} assigns</span>`;

// ── D3 Setup ──────────────────────────────────────────
const margin = {top:40,right:200,bottom:40,left:200};
const width = window.innerWidth;
const height = window.innerHeight - 56;

const svg = d3.select('#canvas').append('svg').attr('width',width).attr('height',height);
const g = svg.append('g').attr('transform',`translate(${margin.left},${height/2})`);

const zoom = d3.zoom().scaleExtent([0.05,5]).on('zoom',(event)=>g.attr('transform',event.transform));
svg.call(zoom);
svg.call(zoom.transform, d3.zoomIdentity.translate(margin.left, height/2));

const root = d3.hierarchy(rawData, d=>d.children);
root.x0 = 0; root.y0 = 0;

function collapseAfterDepth(d, depth) {
  if (d.children && d.depth >= depth) { d._children = d.children; d.children = null; }
  if (d.children) d.children.forEach(c => collapseAfterDepth(c, depth));
  if (d._children) d._children.forEach(c => collapseAfterDepth(c, depth));
}
collapseAfterDepth(root, 3);

const treemap = d3.tree().nodeSize([24, 300]);
const duration = 400;
let nodeIdCounter = 0;

// ── Draw node shapes ──────────────────────────────────
function drawNodeShape(enter) {
  enter.each(function(d) {
    const el = d3.select(this);
    const shape = getShape(d.data.kind);
    const color = getColor(d);

    if (shape === 'diamond') {
      el.append('rect')
        .attr('width', 10).attr('height', 10)
        .attr('x', -5).attr('y', -5)
        .attr('transform', 'rotate(45)')
        .style('fill', d._children ? color : 'var(--bg-primary)')
        .style('stroke', color).style('stroke-width', 2)
        .attr('class','node-shape');
    } else if (shape === 'square') {
      el.append('rect')
        .attr('width', 10).attr('height', 10)
        .attr('x', -5).attr('y', -5)
        .attr('rx', 2).attr('ry', 2)
        .style('fill', d._children ? color : 'var(--bg-primary)')
        .style('stroke', color).style('stroke-width', 2)
        .attr('class','node-shape');
    } else if (shape === 'triangle') {
      el.append('polygon')
        .attr('points', '0,-6 6,5 -6,5')
        .style('fill', d._children ? color : 'var(--bg-primary)')
        .style('stroke', color).style('stroke-width', 2)
        .attr('class','node-shape');
    } else {
      const r = d.data.kind === 'function' ? 8 : 6;
      el.append('circle')
        .attr('r', 0)
        .style('fill', d._children ? color : 'var(--bg-primary)')
        .style('stroke', color).style('stroke-width', 2)
        .attr('class','node-shape');
      if (d.data.kind === 'function') {
        el.select('circle').style('filter', 'drop-shadow(0 0 6px ' + color + ')');
      }
    }
  });
}

function updateNodeShape(sel) {
  sel.each(function(d) {
    const el = d3.select(this);
    const shape = getShape(d.data.kind);
    const color = getColor(d);
    const shapeEl = el.select('.node-shape');

    if (shape === 'circle') {
      const r = d.data.kind === 'function' ? 8 : 6;
      shapeEl.attr('r', r);
    }

    shapeEl.style('fill', d._children ? color : 'var(--bg-primary)')
           .style('stroke', color);
  });
}

function update(source) {
  const treeData = treemap(root);
  const nodes = treeData.descendants();
  const links = treeData.links();

  const node = g.selectAll('g.node').data(nodes, d => d.id || (d.id = ++nodeIdCounter));

  const nodeEnter = node.enter().append('g')
    .attr('class', 'node')
    .attr('transform', () => `translate(${source.y0},${source.x0})`)
    .on('click', (event, d) => {
      if (d.children) { d._children = d.children; d.children = null; }
      else if (d._children) { d.children = d._children; d._children = null; }
      update(d);
    })
    .on('contextmenu', (event, d) => { event.preventDefault(); showPanel(d.data); })
    .on('mouseenter', (event, d) => {
      const tip = document.getElementById('tooltip');
      const icon = kindIcons[d.data.kind] || '';
      let html = `<strong>${icon} ${escapeHtml(d.data.label)}</strong>`;
      html += `<br><span style="color:var(--text-muted);font-size:11px">${d.data.kind}`;
      if (d.data.line) html += ` &middot; line ${d.data.line}`;
      html += '</span>';
      if (d.data.source) html += `<br><span style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted)">${escapeHtml(d.data.source)}</span>`;
      tip.innerHTML = html;
      tip.style.left = (event.clientX + 14) + 'px';
      tip.style.top = (event.clientY - 10) + 'px';
      tip.classList.add('show');
    })
    .on('mouseleave', () => document.getElementById('tooltip').classList.remove('show'));

  drawNodeShape(nodeEnter);

  nodeEnter.append('text')
    .attr('dy', '.35em')
    .attr('x', d => (d.children || d._children) ? -16 : 16)
    .attr('text-anchor', d => (d.children || d._children) ? 'end' : 'start')
    .text(d => {
      const icon = kindIcons[d.data.kind] || '';
      const lbl = d.data.label.length > 70 ? d.data.label.slice(0,67)+'...' : d.data.label;
      return icon ? `${icon} ${lbl}` : lbl;
    })
    .style('fill', d => {
      const c = getColor(d);
      return c;
    })
    .style('font-size', d => d.data.kind === 'function' ? '13px' : '11px')
    .style('font-weight', d => d.data.kind === 'function' ? '700' : '500');

  const nodeUpdate = nodeEnter.merge(node);
  nodeUpdate.transition().duration(duration)
    .attr('transform', d => `translate(${d.y},${d.x})`);

  updateNodeShape(nodeUpdate);

  nodeUpdate.select('text')
    .attr('x', d => (d.children || d._children) ? -16 : 16)
    .attr('text-anchor', d => (d.children || d._children) ? 'end' : 'start');

  const nodeExit = node.exit().transition().duration(duration)
    .attr('transform', () => `translate(${source.y},${source.x})`).remove();
  nodeExit.select('.node-shape').attr('r', 0);
  nodeExit.select('text').style('fill-opacity', 0);

  // Links
  const link = g.selectAll('path.link').data(links, d => d.target.id);

  const linkEnter = link.enter().insert('path', 'g')
    .attr('class', 'link')
    .attr('d', () => { const o={x:source.x0,y:source.y0}; return diagonal(o,o); })
    .style('stroke', d => {
      const c = kindColors[d.target.data.kind];
      return c ? c + '40' : 'var(--border-subtle)';
    });

  linkEnter.merge(link).transition().duration(duration)
    .attr('d', d => diagonal(d.source, d.target));

  link.exit().transition().duration(duration)
    .attr('d', () => { const o={x:source.x,y:source.y}; return diagonal(o,o); }).remove();

  nodes.forEach(d => { d.x0 = d.x; d.y0 = d.y; });
}

function diagonal(s, d) {
  return `M${s.y},${s.x}C${(s.y+d.y)/2},${s.x} ${(s.y+d.y)/2},${d.x} ${d.y},${d.x}`;
}

function escapeHtml(s) {
  if (!s) return '';
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

update(root);

// ── Detail Panel ──────────────────────────────────────
function showPanel(data) {
  const panel = document.getElementById('detailPanel');
  const content = document.getElementById('panelContent');
  const color = kindColors[data.kind] || '#6b7280';
  const icon = kindIcons[data.kind] || '';
  const meta = data.meta || {};

  let html = `<h2>${escapeHtml(icon + ' ' + data.label)}</h2>`;
  html += `<span class="kind-badge" style="background:${color}30;color:${color}">${data.kind}</span>`;

  // Source line
  if (data.source) {
    html += '<div class="section-title">Source</div>';
    html += `<div class="code-block">${escapeHtml(data.source)}</div>`;
  }

  // Meta grid
  html += '<div class="meta-grid">';
  if (data.line) {
    html += `<span class="label">Line</span><span class="value">${data.line}</span>`;
  }
  if (data.detail && data.detail !== data.label) {
    html += `<span class="label">Detail</span><span class="value">${escapeHtml(data.detail)}</span>`;
  }
  html += '</div>';

  // Kind-specific metadata
  if (data.kind === 'call' || (meta.function)) {
    html += '<div class="section-title">Call Info</div>';
    html += '<div class="meta-grid">';
    if (meta.function) html += `<span class="label">Function</span><span class="value">${escapeHtml(meta.function)}</span>`;
    if (meta.resolved_to) html += `<span class="label">Resolved</span><span class="value">${escapeHtml(meta.resolved_to)}</span>`;
    if (meta.inlined) html += `<span class="label">Inlined</span><span class="value" style="color:#22c55e">Yes (expanded)</span>`;
    html += '</div>';

    if (meta.arguments && meta.arguments.length > 0) {
      html += '<div class="section-title">Arguments</div>';
      html += '<ul class="flow-list">';
      meta.arguments.forEach(a => { html += `<li>${escapeHtml(a)}</li>`; });
      html += '</ul>';
    }

    if (meta.data_flow_in && meta.data_flow_in.length > 0) {
      html += '<div class="section-title">Data Flow In &rarr;</div>';
      html += '<ul class="flow-list">';
      meta.data_flow_in.forEach(v => { html += `<li style="color:#10b981">${escapeHtml(v)}</li>`; });
      html += '</ul>';
    }
  }

  if (data.kind === 'assign' || data.kind === 'mutation') {
    html += '<div class="section-title">Assignment</div>';
    html += '<div class="meta-grid">';
    if (meta.targets) html += `<span class="label">Targets</span><span class="value">${escapeHtml(meta.targets.join(', '))}</span>`;
    if (meta.target) html += `<span class="label">Target</span><span class="value">${escapeHtml(meta.target)}</span>`;
    if (meta.operator) html += `<span class="label">Operator</span><span class="value">${escapeHtml(meta.operator)}</span>`;
    if (meta.value) html += `<span class="label">Value</span><span class="value">${escapeHtml(meta.value)}</span>`;
    html += '</div>';
    if (meta.reads && meta.reads.length > 0) {
      html += '<div class="section-title">Reads Variables</div>';
      html += '<ul class="flow-list">';
      meta.reads.forEach(v => { html += `<li>${escapeHtml(v)}</li>`; });
      html += '</ul>';
    }
  }

  if (data.kind === 'branch' || data.kind === 'branch_elif') {
    html += '<div class="section-title">Condition</div>';
    if (meta.condition) html += `<div class="code-block">${escapeHtml(meta.condition)}</div>`;
    if (meta.reads && meta.reads.length > 0) {
      html += '<div class="section-title">Variables Tested</div>';
      html += '<ul class="flow-list">';
      meta.reads.forEach(v => { html += `<li>${escapeHtml(v)}</li>`; });
      html += '</ul>';
    }
  }

  if (data.kind === 'return') {
    if (meta.value) {
      html += '<div class="section-title">Return Value</div>';
      html += `<div class="code-block">${escapeHtml(meta.value)}</div>`;
    }
    if (meta.reads && meta.reads.length > 0) {
      html += '<div class="section-title">Uses Variables</div>';
      html += '<ul class="flow-list">';
      meta.reads.forEach(v => { html += `<li>${escapeHtml(v)}</li>`; });
      html += '</ul>';
    }
  }

  if (data.kind === 'function') {
    if (meta.params && meta.params.length > 0) {
      html += '<div class="section-title">Parameters</div>';
      html += '<ul class="flow-list">';
      meta.params.forEach(p => { html += `<li>${escapeHtml(p)}</li>`; });
      html += '</ul>';
    }
    if (meta.is_async) {
      html += '<div class="section-title">Async</div><p style="font-size:12px;color:var(--text-secondary)">This is an async function</p>';
    }
  }

  if (data.kind.startsWith('loop_')) {
    if (meta.variable) {
      html += '<div class="section-title">Loop Variable</div>';
      html += `<div class="code-block">${escapeHtml(meta.variable)}</div>`;
    }
    if (meta.iterable) {
      html += '<div class="section-title">Iterable</div>';
      html += `<div class="code-block">${escapeHtml(meta.iterable)}</div>`;
    }
    if (meta.condition) {
      html += '<div class="section-title">Condition</div>';
      html += `<div class="code-block">${escapeHtml(meta.condition)}</div>`;
    }
  }

  // Children count
  if (data.children && data.children.length > 0) {
    html += `<div class="section-title">Children (${data.children.length})</div>`;
    html += '<ul class="flow-list">';
    data.children.slice(0, 20).forEach(c => {
      const ci = kindIcons[c.kind] || '';
      const cc = kindColors[c.kind] || '#6b7280';
      html += `<li style="color:${cc}">${ci} ${escapeHtml(c.label.slice(0,60))}</li>`;
    });
    if (data.children.length > 20) html += `<li style="color:var(--text-muted)">... and ${data.children.length - 20} more</li>`;
    html += '</ul>';
  }

  content.innerHTML = html;
  panel.classList.add('open');
}

document.getElementById('closePanel').addEventListener('click', () => {
  document.getElementById('detailPanel').classList.remove('open');
});

// ── Search ────────────────────────────────────────────
document.getElementById('searchInput').addEventListener('input', function() {
  const query = this.value.toLowerCase();
  g.selectAll('g.node').each(function(d) {
    const match = !query ||
      d.data.label.toLowerCase().includes(query) ||
      d.data.kind.toLowerCase().includes(query) ||
      (d.data.source && d.data.source.toLowerCase().includes(query));
    d3.select(this).style('opacity', match ? 1 : 0.12);
  });
});

// ── Buttons ───────────────────────────────────────────
document.getElementById('btnExpandAll').addEventListener('click', () => {
  function expand(d) {
    if (d._children) { d.children = d._children; d._children = null; }
    if (d.children) d.children.forEach(expand);
  }
  expand(root);
  update(root);
});

document.getElementById('btnCollapseAll').addEventListener('click', () => {
  function collapse(d) {
    if (d.children) { d._children = d.children; d.children = null; }
    if (d._children) d._children.forEach(collapse);
  }
  if (root.children) root.children.forEach(collapse);
  update(root);
});

document.getElementById('btnResetZoom').addEventListener('click', () => {
  svg.transition().duration(500).call(
    zoom.transform, d3.zoomIdentity.translate(margin.left, height/2)
  );
});

window.addEventListener('resize', () => {
  svg.attr('width', window.innerWidth).attr('height', window.innerHeight - 56);
});
</script>
</body>
</html>"""
