#!/usr/bin/env python3
"""把一个目录下的 Markdown 设计文档合成单个 HTML，浏览器打开即可查看（Mermaid 图在页面内渲染）。

用法：python3 scripts/render_design_html.py docs/business/2026-11-18-service-v1
输出：<目录>/index.html
"""

import json
import sys
from pathlib import Path

TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  :root { --fg:#1f2328; --muted:#59636e; --line:#d1d9e0; --bg:#fff; --side:#f6f8fa; --accent:#0969da; }
  * { box-sizing: border-box; }
  body { margin:0; font:15px/1.7 -apple-system, "PingFang SC", "Helvetica Neue", sans-serif; color:var(--fg); background:var(--bg); }
  nav { position:fixed; top:0; left:0; bottom:0; width:260px; overflow:auto; background:var(--side); border-right:1px solid var(--line); padding:16px 12px; }
  nav h1 { font-size:15px; margin:0 0 12px; }
  nav a { display:block; padding:6px 10px; border-radius:6px; color:var(--fg); text-decoration:none; font-size:14px; }
  nav a:hover { background:#eaeef2; }
  nav a.active { background:var(--accent); color:#fff; }
  nav .toc a { font-size:13px; color:var(--muted); padding:3px 10px 3px 22px; }
  nav .toc a.h3 { padding-left:34px; }
  nav .gen { margin-top:16px; font-size:12px; color:var(--muted); padding:0 10px; }
  main { margin-left:260px; padding:24px 48px 80px; max-width:1200px; }
  main h1 { border-bottom:1px solid var(--line); padding-bottom:8px; }
  main h2 { border-bottom:1px solid var(--line); padding-bottom:6px; margin-top:36px; }
  table { border-collapse:collapse; display:block; overflow:auto; margin:12px 0; }
  th, td { border:1px solid var(--line); padding:6px 12px; vertical-align:top; }
  th { background:var(--side); }
  tr:nth-child(2n) td { background:#fafbfc; }
  code { background:#eff1f3; padding:2px 5px; border-radius:4px; font-size:13px; }
  pre { background:#f6f8fa; padding:12px 16px; border-radius:6px; overflow:auto; }
  pre code { background:none; padding:0; }
  blockquote { margin:0; padding:0 16px; color:var(--muted); border-left:4px solid var(--line); }
  .mermaid { background:#fff; border:1px solid var(--line); border-radius:8px; padding:16px; margin:16px 0; overflow:auto; text-align:center; }
  .mermaid-error { border-color:#cf222e; text-align:left; }
  .mermaid-error p { color:#cf222e; margin:0 0 8px; font-size:13px; }
  @media print { nav { display:none; } main { margin:0; } }
</style>
</head>
<body>
<nav>
  <h1>__TITLE__</h1>
  <div id="files"></div>
  <div class="toc" id="toc"></div>
  <div class="gen">由 Markdown 源文件生成，以源文件为准。</div>
</nav>
<main id="content"></main>
<script id="docs" type="application/json">__DOCS__</script>
<script>
  const docs = JSON.parse(document.getElementById('docs').textContent);
  mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'default' });

  const renderer = new marked.Renderer();
  const baseCode = renderer.code.bind(renderer);
  renderer.code = function (token) {
    const text = typeof token === 'object' ? token.text : token;
    const lang = typeof token === 'object' ? token.lang : arguments[1];
    if ((lang || '').trim() === 'mermaid') {
      const div = document.createElement('div');
      div.className = 'mermaid';
      div.textContent = text;
      return div.outerHTML;
    }
    return baseCode.apply(this, arguments);
  };
  marked.setOptions({ renderer, gfm: true });

  const filesEl = document.getElementById('files');
  const tocEl = document.getElementById('toc');
  const contentEl = document.getElementById('content');

  function slug(s, i) { return 'h-' + i + '-' + s.replace(/\\s+/g, '-').replace(/[^\\w\\u4e00-\\u9fa5-]/g, ''); }

  async function show(idx) {
    const doc = docs[idx];
    contentEl.innerHTML = marked.parse(doc.md);
    // 文档间相对链接改为页内切换
    contentEl.querySelectorAll('a[href]').forEach(a => {
      const name = a.getAttribute('href').split('#')[0].split('/').pop();
      const target = docs.findIndex(d => d.name === name);
      if (target >= 0) a.addEventListener('click', e => { e.preventDefault(); location.hash = docs[target].name; });
    });
    tocEl.innerHTML = '';
    contentEl.querySelectorAll('h2, h3').forEach((h, i) => {
      h.id = slug(h.textContent, i);
      const a = document.createElement('a');
      a.href = '#' + doc.name + '::' + h.id;
      a.textContent = h.textContent;
      a.className = h.tagName.toLowerCase();
      a.addEventListener('click', e => { e.preventDefault(); h.scrollIntoView(); });
      tocEl.appendChild(a);
    });
    filesEl.querySelectorAll('a').forEach((a, i) => a.classList.toggle('active', i === idx));
    window.scrollTo(0, 0);
    const blocks = [...contentEl.querySelectorAll('.mermaid')];
    for (let i = 0; i < blocks.length; i++) {
      const el = blocks[i];
      const src = el.textContent;
      try {
        const { svg } = await mermaid.render('m' + idx + '-' + i, src);
        el.innerHTML = svg;
      } catch (err) {
        el.classList.add('mermaid-error');
        el.innerHTML = '';
        const p = document.createElement('p');
        p.textContent = '这张图渲染失败：' + (err.message || err);
        const pre = document.createElement('pre');
        pre.textContent = src;
        el.append(p, pre);
      }
    }
  }

  docs.forEach((d, i) => {
    const a = document.createElement('a');
    a.href = '#' + d.name;
    a.textContent = d.title;
    filesEl.appendChild(a);
  });

  function route() {
    const name = decodeURIComponent(location.hash.slice(1)).split('::')[0];
    const idx = Math.max(0, docs.findIndex(d => d.name === name));
    show(idx);
  }
  window.addEventListener('hashchange', route);
  route();
</script>
</body>
</html>
"""


def title_of(md: str, fallback: str) -> str:
    for line in md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("用法：python3 scripts/render_design_html.py <文档目录>")
    folder = Path(sys.argv[1])
    files = sorted(folder.glob("*.md"), key=lambda p: (p.name != "README.md", p.name))
    if not files:
        sys.exit(f"{folder} 下没有 Markdown 文件")
    docs = []
    for path in files:
        md = path.read_text(encoding="utf-8")
        docs.append({"name": path.name, "title": title_of(md, path.stem), "md": md})
    payload = json.dumps(docs, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.replace("__TITLE__", "GEO 运营第一版设计").replace("__DOCS__", payload)
    out = folder / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"已生成 {out}（{len(docs)} 份文档）")


if __name__ == "__main__":
    main()
