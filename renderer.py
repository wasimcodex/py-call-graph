"""
renderer.py - Output renderers for the call graph.

Supports:
  - JSON: Raw structured data
  - Mermaid: Text-based diagram for Markdown
  - HTML: Interactive D3.js collapsible tree visualization
"""

import json
import os
from typing import Optional


def render_json(call_tree, output_path: str) -> str:
    """Render the call tree as a JSON file."""
    data = call_tree.to_dict()
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str)
    return output_path


def render_mermaid(call_tree, output_path: str) -> str:
    """Render the call tree as a Mermaid diagram in a Markdown file."""
    lines = ['```mermaid', 'graph TD']
    counter = {'id': 0}
    node_ids = {}

    def get_id(qualified_name: str) -> str:
        if qualified_name not in node_ids:
            node_ids[qualified_name] = f"N{counter['id']}"
            counter['id'] += 1
        return node_ids[qualified_name]

    def sanitize(text: str) -> str:
        return text.replace('"', "'").replace('<', '&lt;').replace('>', '&gt;')

    def walk(node_dict, parent_id=None):
        nid = get_id(node_dict['qualified_name'])
        label = sanitize(node_dict['name'])

        if node_dict.get('is_external'):
            lines.append(f'    {nid}(["🔗 {label}"])')
            lines.append(f'    style {nid} fill:#4a4458,stroke:#b8a9c9,color:#e0d6eb')
        elif node_dict.get('is_recursive'):
            lines.append(f'    {nid}(["🔄 {label}"])')
            lines.append(f'    style {nid} fill:#5c3d2e,stroke:#e8a87c,color:#ffecd2')
        else:
            lines.append(f'    {nid}["{label}"]')

        if parent_id is not None:
            lines.append(f'    {parent_id} --> {nid}')

        if not node_dict.get('is_recursive'):
            for child in node_dict.get('children', []):
                walk(child, nid)

    walk(call_tree.to_dict())
    lines.append('```')

    content = '\n'.join(lines)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"# Call Graph\n\n{content}\n")
    return output_path


def render_html(call_tree, output_path: str, project_dir: Optional[str] = None) -> str:
    """Render the call tree as an interactive HTML page with D3.js."""
    tree_data = json.dumps(call_tree.to_dict(), default=str)
    project_label = os.path.basename(project_dir) if project_dir else 'Project'

    html = _HTML_TEMPLATE.replace('__TREE_DATA__', tree_data).replace('__PROJECT_LABEL__', project_label)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return output_path


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Call Graph &mdash; __PROJECT_LABEL__</title>
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
    --node-internal: #7c3aed;
    --node-external: #6366f1;
    --node-recursive: #f59e0b;
    --node-leaf: #10b981;
    --link-color: #334155;
    --border-subtle: #ffffff10;
    --danger: #ef4444;
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

  /* ── Top Bar ────────────────────────────────────────── */
  .topbar {
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 56px;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-subtle);
    display: flex;
    align-items: center;
    padding: 0 24px;
    z-index: 100;
    backdrop-filter: blur(12px);
    gap: 16px;
  }

  .topbar .logo {
    font-weight: 700;
    font-size: 16px;
    color: var(--accent-secondary);
    display: flex;
    align-items: center;
    gap: 8px;
    white-space: nowrap;
  }

  .topbar .logo svg {
    width: 22px;
    height: 22px;
  }

  .search-box {
    flex: 1;
    max-width: 400px;
    position: relative;
  }

  .search-box input {
    width: 100%;
    padding: 8px 12px 8px 36px;
    border-radius: 8px;
    border: 1px solid var(--border-subtle);
    background: var(--bg-primary);
    color: var(--text-primary);
    font-family: 'Inter', sans-serif;
    font-size: 13px;
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
  }

  .search-box input:focus {
    border-color: var(--accent-primary);
    box-shadow: 0 0 0 3px var(--accent-glow);
  }

  .search-box .search-icon {
    position: absolute;
    left: 10px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted);
    font-size: 14px;
  }

  .stats {
    margin-left: auto;
    display: flex;
    gap: 16px;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .stats .stat {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .stats .stat .dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    display: inline-block;
  }

  .btn-group {
    display: flex;
    gap: 6px;
  }

  .btn {
    padding: 6px 14px;
    border-radius: 6px;
    border: 1px solid var(--border-subtle);
    background: var(--bg-primary);
    color: var(--text-secondary);
    font-family: 'Inter', sans-serif;
    font-size: 12px;
    cursor: pointer;
    transition: all 0.15s;
  }

  .btn:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
    border-color: var(--accent-primary);
  }

  /* ── SVG Canvas ───────────────────────────────────── */
  #canvas {
    position: fixed;
    top: 56px; left: 0; right: 0; bottom: 0;
    background:
      radial-gradient(circle at 20% 50%, #7c3aed08 0%, transparent 50%),
      radial-gradient(circle at 80% 20%, #6366f108 0%, transparent 50%),
      var(--bg-primary);
  }

  /* ── Detail Panel ─────────────────────────────────── */
  .detail-panel {
    position: fixed;
    top: 56px;
    right: 0;
    width: 360px;
    bottom: 0;
    background: var(--bg-card);
    border-left: 1px solid var(--border-subtle);
    backdrop-filter: blur(16px);
    padding: 24px;
    overflow-y: auto;
    transform: translateX(100%);
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    z-index: 90;
  }

  .detail-panel.open {
    transform: translateX(0);
  }

  .detail-panel .close-btn {
    position: absolute;
    top: 16px; right: 16px;
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: 20px;
    cursor: pointer;
    transition: color 0.15s;
  }
  .detail-panel .close-btn:hover { color: var(--text-primary); }

  .detail-panel h2 {
    font-size: 18px;
    font-weight: 600;
    color: var(--accent-secondary);
    margin-bottom: 4px;
    word-break: break-all;
  }

  .detail-panel .qualified {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text-muted);
    margin-bottom: 16px;
    word-break: break-all;
  }

  .detail-panel .meta-grid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px 12px;
    font-size: 13px;
    margin-bottom: 16px;
  }

  .detail-panel .meta-grid .label {
    color: var(--text-muted);
    font-weight: 500;
  }

  .detail-panel .meta-grid .value {
    color: var(--text-secondary);
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
  }

  .detail-panel .sig-block {
    background: var(--bg-primary);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--accent-secondary);
    margin-bottom: 12px;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-all;
  }

  .detail-panel .doc-block {
    background: var(--bg-primary);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 12px;
    font-size: 12px;
    color: var(--text-secondary);
    line-height: 1.6;
    margin-bottom: 12px;
    white-space: pre-wrap;
  }

  .detail-panel .children-list {
    list-style: none;
    padding: 0;
  }

  .detail-panel .children-list li {
    padding: 6px 10px;
    font-size: 13px;
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.15s;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .detail-panel .children-list li:hover {
    background: var(--bg-tertiary);
  }

  .detail-panel .section-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin: 16px 0 8px;
  }

  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .badge.internal { background: #7c3aed30; color: #a78bfa; }
  .badge.external { background: #6366f130; color: #818cf8; }
  .badge.recursive { background: #f59e0b30; color: #fbbf24; }
  .badge.leaf { background: #10b98130; color: #34d399; }

  /* ── Tree nodes ────────────────────────────────────── */
  .node circle {
    stroke-width: 2.5px;
    cursor: pointer;
    transition: r 0.2s, filter 0.2s;
  }

  .node circle:hover {
    r: 8;
    filter: drop-shadow(0 0 8px var(--accent-primary));
  }

  .node text {
    font-family: 'Inter', sans-serif;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: fill 0.15s;
  }

  .node text:hover {
    fill: var(--accent-secondary) !important;
  }

  .link {
    fill: none;
    stroke: var(--link-color);
    stroke-width: 1.5px;
    stroke-opacity: 0.6;
    transition: stroke 0.2s, stroke-opacity 0.2s;
  }

  /* ── Tooltip ──────────────────────────────────────── */
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
    max-width: 300px;
    box-shadow: 0 8px 32px #00000066;
  }

  .tooltip.show { opacity: 1; }

  /* ── Help Overlay ────────────────────────────────── */
  .help-overlay {
    position: fixed;
    bottom: 16px;
    left: 16px;
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 14px 18px;
    font-size: 11px;
    color: var(--text-muted);
    backdrop-filter: blur(12px);
    line-height: 1.8;
    z-index: 80;
  }

  .help-overlay kbd {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 4px;
    background: var(--bg-primary);
    border: 1px solid var(--border-subtle);
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--text-secondary);
    margin: 0 2px;
  }
</style>
</head>
<body>

<!-- Top Bar -->
<div class="topbar">
  <div class="logo">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
    </svg>
    PyCallGraph
  </div>
  <div class="search-box">
    <span class="search-icon">&#x1F50D;</span>
    <input type="text" id="searchInput" placeholder="Search functions..." autocomplete="off">
  </div>
  <div class="stats" id="stats"></div>
  <div class="btn-group">
    <button class="btn" id="btnExpandAll">Expand All</button>
    <button class="btn" id="btnCollapseAll">Collapse All</button>
    <button class="btn" id="btnResetZoom">Reset View</button>
  </div>
</div>

<!-- Canvas -->
<div id="canvas"></div>

<!-- Detail Panel -->
<div class="detail-panel" id="detailPanel">
  <button class="close-btn" id="closePanel">&times;</button>
  <div id="panelContent"></div>
</div>

<!-- Tooltip -->
<div class="tooltip" id="tooltip"></div>

<!-- Help -->
<div class="help-overlay">
  <kbd>Click</kbd> node to expand/collapse &middot;
  <kbd>Right-click</kbd> for details &middot;
  <kbd>Scroll</kbd> to zoom &middot;
  <kbd>Drag</kbd> to pan
</div>

<script>
const rawData = __TREE_DATA__;

// ── Counting helpers ──────────────────────────────────
function countNodes(d) {
  let internal = 0, external = 0;
  function walk(n) {
    if (n.is_external) external++; else internal++;
    (n.children || []).forEach(walk);
  }
  walk(d);
  return { internal, external, total: internal + external };
}

const stats = countNodes(rawData);
document.getElementById('stats').innerHTML =
  `<span class="stat"><span class="dot" style="background:var(--node-internal)"></span>${stats.internal} internal</span>` +
  `<span class="stat"><span class="dot" style="background:var(--node-external)"></span>${stats.external} external</span>` +
  `<span class="stat">${stats.total} total</span>`;

// ── Dimensions ──────────────────────────────────────
const margin = { top: 40, right: 200, bottom: 40, left: 200 };
const width = window.innerWidth;
const height = window.innerHeight - 56;

const svg = d3.select('#canvas')
  .append('svg')
  .attr('width', width)
  .attr('height', height);

const g = svg.append('g')
  .attr('transform', `translate(${margin.left},${height / 2})`);

// ── Zoom ──────────────────────────────────────────
const zoom = d3.zoom()
  .scaleExtent([0.1, 4])
  .on('zoom', (event) => g.attr('transform', event.transform));

svg.call(zoom);
svg.call(zoom.transform, d3.zoomIdentity.translate(margin.left, height / 2));

// ── Tree Layout ─────────────────────────────────────
const root = d3.hierarchy(rawData, d => d.children);
root.x0 = 0;
root.y0 = 0;

// Collapse children by default beyond depth 2
function collapseAfterDepth(d, depth) {
  if (d.children && d.depth >= depth) {
    d._children = d.children;
    d.children = null;
  }
  if (d.children) d.children.forEach(c => collapseAfterDepth(c, depth));
  if (d._children) d._children.forEach(c => collapseAfterDepth(c, depth));
}
collapseAfterDepth(root, 2);

const treemap = d3.tree().nodeSize([28, 260]);
const duration = 400;
let nodeIdCounter = 0;

function getNodeColor(d) {
  if (d.data.is_external) return 'var(--node-external)';
  if (d.data.is_recursive) return 'var(--node-recursive)';
  if (!d.children && !d._children) return 'var(--node-leaf)';
  return 'var(--node-internal)';
}

function update(source) {
  const treeData = treemap(root);
  const nodes = treeData.descendants();
  const links = treeData.links();

  // ── Nodes ──────────────────────────
  const node = g.selectAll('g.node')
    .data(nodes, d => d.id || (d.id = ++nodeIdCounter));

  const nodeEnter = node.enter().append('g')
    .attr('class', 'node')
    .attr('transform', () => `translate(${source.y0},${source.x0})`)
    .on('click', (event, d) => {
      if (d.children) {
        d._children = d.children;
        d.children = null;
      } else if (d._children) {
        d.children = d._children;
        d._children = null;
      }
      update(d);
    })
    .on('contextmenu', (event, d) => {
      event.preventDefault();
      showPanel(d.data);
    })
    .on('mouseenter', (event, d) => {
      const tip = document.getElementById('tooltip');
      let html = `<strong>${d.data.name}</strong>`;
      if (d.data.signature) html += `<br><span style="color:var(--text-muted);font-family:'JetBrains Mono',monospace;font-size:11px">${escapeHtml(d.data.signature)}</span>`;
      if (d.data.is_external) html += `<br><span class="badge external">external</span>`;
      if (d.data.is_recursive) html += `<br><span class="badge recursive">recursive</span>`;
      tip.innerHTML = html;
      tip.style.left = (event.clientX + 14) + 'px';
      tip.style.top = (event.clientY - 10) + 'px';
      tip.classList.add('show');
    })
    .on('mouseleave', () => {
      document.getElementById('tooltip').classList.remove('show');
    });

  nodeEnter.append('circle')
    .attr('r', 0)
    .style('fill', d => d._children ? getNodeColor(d) : 'var(--bg-primary)')
    .style('stroke', getNodeColor);

  nodeEnter.append('text')
    .attr('dy', '.35em')
    .attr('x', d => d.children || d._children ? -14 : 14)
    .attr('text-anchor', d => d.children || d._children ? 'end' : 'start')
    .text(d => d.data.name)
    .style('fill', d => d.data.is_external ? 'var(--text-muted)' : 'var(--text-primary)')
    .style('font-style', d => d.data.is_external ? 'italic' : 'normal');

  // Merge
  const nodeUpdate = nodeEnter.merge(node);

  nodeUpdate.transition().duration(duration)
    .attr('transform', d => `translate(${d.y},${d.x})`);

  nodeUpdate.select('circle')
    .attr('r', 6)
    .style('fill', d => d._children ? getNodeColor(d) : 'var(--bg-primary)')
    .style('stroke', getNodeColor);

  nodeUpdate.select('text')
    .attr('x', d => d.children || d._children ? -14 : 14)
    .attr('text-anchor', d => d.children || d._children ? 'end' : 'start');

  // Exit
  const nodeExit = node.exit().transition().duration(duration)
    .attr('transform', () => `translate(${source.y},${source.x})`)
    .remove();

  nodeExit.select('circle').attr('r', 0);
  nodeExit.select('text').style('fill-opacity', 0);

  // ── Links ──────────────────────────
  const link = g.selectAll('path.link')
    .data(links, d => d.target.id);

  const linkEnter = link.enter().insert('path', 'g')
    .attr('class', 'link')
    .attr('d', () => {
      const o = { x: source.x0, y: source.y0 };
      return diagonal(o, o);
    });

  linkEnter.merge(link).transition().duration(duration)
    .attr('d', d => diagonal(d.source, d.target));

  link.exit().transition().duration(duration)
    .attr('d', () => {
      const o = { x: source.x, y: source.y };
      return diagonal(o, o);
    }).remove();

  // Stash positions
  nodes.forEach(d => { d.x0 = d.x; d.y0 = d.y; });
}

function diagonal(s, d) {
  return `M${s.y},${s.x}C${(s.y + d.y) / 2},${s.x} ${(s.y + d.y) / 2},${d.x} ${d.y},${d.x}`;
}

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

update(root);

// ── Detail Panel ──────────────────────────────────
function showPanel(data) {
  const panel = document.getElementById('detailPanel');
  const content = document.getElementById('panelContent');

  let badge = '';
  if (data.is_external) badge = '<span class="badge external">External</span>';
  else if (data.is_recursive) badge = '<span class="badge recursive">Recursive</span>';
  else if (!data.children || data.children.length === 0) badge = '<span class="badge leaf">Leaf</span>';
  else badge = '<span class="badge internal">Internal</span>';

  let html = `<h2>${escapeHtml(data.name)}</h2>`;
  html += `<div class="qualified">${escapeHtml(data.qualified_name)}</div>`;
  html += badge;

  html += '<div class="meta-grid" style="margin-top:16px">';
  if (data.file_path) {
    const short = data.file_path.split('/').slice(-2).join('/');
    html += `<span class="label">File</span><span class="value">${escapeHtml(short)}</span>`;
  }
  if (data.line_start) {
    html += `<span class="label">Lines</span><span class="value">${data.line_start}&ndash;${data.line_end || '?'}</span>`;
  }
  html += '</div>';

  if (data.signature) {
    html += '<div class="section-title">Signature</div>';
    html += `<div class="sig-block">${escapeHtml(data.signature)}</div>`;
  }

  if (data.docstring) {
    html += '<div class="section-title">Docstring</div>';
    html += `<div class="doc-block">${escapeHtml(data.docstring)}</div>`;
  }

  if (data.children && data.children.length > 0) {
    html += '<div class="section-title">Calls (' + data.children.length + ')</div>';
    html += '<ul class="children-list">';
    data.children.forEach(c => {
      const icon = c.is_external ? '🔗' : c.is_recursive ? '🔄' : '▸';
      html += `<li>${icon} ${escapeHtml(c.name)}</li>`;
    });
    html += '</ul>';
  }

  content.innerHTML = html;
  panel.classList.add('open');
}

document.getElementById('closePanel').addEventListener('click', () => {
  document.getElementById('detailPanel').classList.remove('open');
});

// ── Search ──────────────────────────────────────────
document.getElementById('searchInput').addEventListener('input', function() {
  const query = this.value.toLowerCase();
  g.selectAll('g.node').each(function(d) {
    const match = !query || d.data.name.toLowerCase().includes(query) ||
                  (d.data.qualified_name && d.data.qualified_name.toLowerCase().includes(query));
    d3.select(this).style('opacity', match ? 1 : 0.15);
  });
});

// ── Buttons ─────────────────────────────────────────
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
    zoom.transform, d3.zoomIdentity.translate(margin.left, height / 2)
  );
});

// ── Resize ──────────────────────────────────────────
window.addEventListener('resize', () => {
  svg.attr('width', window.innerWidth).attr('height', window.innerHeight - 56);
});
</script>
</body>
</html>"""
