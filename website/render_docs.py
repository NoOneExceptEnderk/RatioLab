#!/usr/bin/env python3
"""Render the allowlisted public documentation into portable static HTML."""
from __future__ import annotations

import html
import json
import posixpath
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from markdown_it import MarkdownIt
from social_links import load_social_channels, render_discord_ctas, render_social_links

ROOT = Path(__file__).resolve().parent
REPOSITORY = "https://github.com/NoOneExceptEnderk/RatioLab"


@dataclass(frozen=True)
class Document:
    source: str
    title: str
    description: str
    section: str
    language: str = "en"

    @property
    def route(self):
        return "docs/" + self.source.removesuffix(".md") + "/index.html"


DOCUMENTS = (
    Document("installation.md", "Installation", "Installers, system requirements and first launch.", "GET STARTED"),
    Document("user-guide.md", "User guide", "Workspace, parameters, gear and reducer families and CAD export.", "GET STARTED"),
    Document("mcp.md", "MCP and agents", "Local setup, tool contracts and MCP server limits.", "GET STARTED"),
    Document("updates.md", "Application updates", "Update checks, release downloads and installation.", "GET STARTED"),
    Document("fusion360.md", "Autodesk Fusion", "Optional Fusion integration, setup and transfer limits.", "GET STARTED"),
    Document("development.md", "Development and builds", "Source code, dependencies, native installers and verification.", "DEVELOPMENT"),
    Document("technical/calculations.md", "Calculations and references", "Conventions, nominal formulas and geometric analysis limits.", "TECHNICAL REFERENCE"),
    Document("technical/hardware.md", "Hardware and assembly", "Bearings, fits, standard hardware and dimensional references.", "TECHNICAL REFERENCE"),
    Document("technical/io-models.md", "Input and output", "Connections, member roles and mechanical limitations.", "TECHNICAL REFERENCE"),
    Document("technical/kinematics.md", "Kinematics", "Motion represented in the preview and export behavior.", "TECHNICAL REFERENCE"),
    Document("technical/printed-shaft.md", "FDM printed shaft", "Experimental eccentric shaft with two axial through bolts.", "TECHNICAL REFERENCE"),
    Document("technical/variants.md", "Variants and limitations", "Generated variants, documented architectures and model limits.", "TECHNICAL REFERENCE"),
    Document("technical/worm.md", "Worm reference", "ZA and ZI equations, generated geometry and verification limits.", "TECHNICAL REFERENCE"),
    Document("technical/strain-wave.md", "Strain-wave reference", "Prescribed deformation, generated ring and numerical checks.", "TECHNICAL REFERENCE"),
    Document("technical/differential.md", "Bevel differential reference", "Independent inputs, configurations, geometry and kinematic limits.", "TECHNICAL REFERENCE"),
)
BY_SOURCE = {document.source: document for document in DOCUMENTS}


def relative_url(route: str, current_route: str) -> str:
    return posixpath.relpath(route, posixpath.dirname(current_route))


def site_root(current_route: str) -> str:
    return "../" * len(posixpath.dirname(current_route).split("/"))


def safe_url(value: str) -> bool:
    decoded = unquote(html.unescape(value)).strip()
    decoded = "".join(c for c in decoded if ord(c) > 32)
    try:
        parts = urlsplit(decoded)
    except ValueError:
        return False
    return parts.scheme.lower() in ("", "http", "https", "mailto") and not decoded.startswith("//") and "\\" not in decoded


def rewrite_url(value: str, source: str, route: str, source_ref: str = "main") -> str:
    """Localize only published docs and known imagery; keep repository resources real."""
    if not safe_url(value):
        return "#"
    parsed = urlsplit(value)
    path = unquote(parsed.path)
    canonical_prefix = urlsplit(REPOSITORY).path + "/blob/"
    if parsed.netloc == "github.com" and path.startswith(canonical_prefix):
        suffix = path[len(canonical_prefix):]
        ref, _, repository_path = suffix.partition("/")
        if ref in ("main", source_ref):
            candidate = repository_path
        else:
            return value
    elif parsed.scheme or parsed.netloc:
        return value
    elif not path:
        return value
    else:
        candidate = posixpath.normpath(posixpath.join("docs", posixpath.dirname(source), path))
    if candidate.startswith("docs/") and candidate[5:] in BY_SOURCE:
        localized = relative_url(BY_SOURCE[candidate[5:]].route, route)
    elif candidate == "index.html":
        localized = relative_url("index.html", route)
    elif candidate == "assets/screenshots/workspace.png":
        localized = relative_url("assets/workspace.png", route)
    else:
        # The website deliberately does not publish source trees or project examples.
        if candidate.startswith("../") or candidate.startswith("/"):
            return "#"
        kind = "tree" if path.endswith("/") else "blob"
        return urlunsplit(("https", "github.com", urlsplit(REPOSITORY).path + f"/{kind}/{source_ref}/" + quote(candidate, safe="/"), parsed.query, parsed.fragment))
    return urlunsplit(("", "", localized, parsed.query, parsed.fragment))


def slugify(text: str) -> str:
    # GitHub heading fragments keep Unicode letters/numbers, spaces, '_' and '-'.
    return "".join(c for c in text.lower() if c in " _-" or unicodedata.category(c)[0] in "LN").replace(" ", "-")


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(markup: str) -> str:
    parser = PlainText()
    parser.feed(markup)
    return " ".join(" ".join(parser.parts).split())


def render_markdown(markdown: str, source: str, route: str, source_ref: str = "main"):
    renderer = MarkdownIt("commonmark", {"html": False, "breaks": False}).enable("table")
    renderer.validateLink = safe_url
    def legacy_anchor(state, start_line, end_line, silent):
        # Only a standalone legacy ID immediately preceding a Markdown heading.
        # All other raw HTML remains disabled and escaped by markdown-it.
        if state.sCount[start_line] - state.blkIndent >= 4:
            return False
        line = state.src[state.bMarks[start_line] + state.tShift[start_line]:state.eMarks[start_line]]
        match = re.fullmatch(r'<a id="([\w][\w-]*)"></a>', line)
        following = start_line + 1
        while following < end_line and not state.src[state.bMarks[following]:state.eMarks[following]].strip():
            following += 1
        if not match or following >= end_line or not re.match(r'#{1,6} ', state.src[state.bMarks[following]:state.eMarks[following]]):
            return False
        if not silent:
            token = state.push('legacy_anchor', '', 0)
            token.meta = {'id': match[1]}
            token.map = [start_line, start_line + 1]
            state.line = start_line + 1
        return True

    renderer.block.ruler.before('paragraph', 'legacy_anchor', legacy_anchor)
    renderer.renderer.rules['legacy_anchor'] = lambda items, i, *_: ('<span class="anchor-alias" aria-hidden="true" id="' + html.escape(items[i].meta['id'], quote=True) + '"></span>\n')
    tokens = renderer.parse(markdown)
    aliases = [token.meta['id'] for token in tokens if token.type == 'legacy_anchor']
    if len(aliases) != len(set(aliases)):
        raise ValueError('Duplicate legacy heading IDs in ' + source)
    ids = set(aliases)
    headings = []
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            inline = tokens[index + 1]
            text = "".join(child.content for child in inline.children or [] if child.type not in ("html_inline", "image"))
            base = slugify(text)
            anchor = base
            suffix = 0
            while anchor in ids:
                suffix += 1
                anchor = f"{base}-{suffix}"
            ids.add(anchor)
            token.attrSet("id", anchor)
            headings.append((int(token.tag[1]), text, anchor))
        for child in token.children or []:
            if child.type in ("link_open", "image"):
                attr = "href" if child.type == "link_open" else "src"
                child.attrSet(attr, rewrite_url(child.attrGet(attr) or "", source, route, source_ref))
            if child.type == "image":
                child.attrSet("loading", "lazy")
                child.attrSet("decoding", "async")

    fence_count = 0

    def fence_rule(items, index, options, env):
        nonlocal fence_count
        fence_count += 1
        token = items[index]
        language = token.info.strip().split()[0] if token.info.strip() else "text"
        code_id = f"ratiolab-code-{fence_count}"
        while code_id in ids:
            fence_count += 1
            code_id = f"ratiolab-code-{fence_count}"
        ids.add(code_id)
        return (f'<div class="code-block"><div class="code-toolbar"><span>{html.escape(language)}</span>'
                f'<button class="code-copy" type="button" data-copy-target="{code_id}" aria-label="Copy code">Copy</button></div>'
                f'<pre id="{code_id}"><code class="language-{html.escape(language, quote=True)}">{html.escape(token.content)}</code></pre></div>\n')

    renderer.renderer.rules["fence"] = fence_rule
    renderer.renderer.rules["table_open"] = lambda *_: '<div class="table-wrap" tabindex="0" role="region" aria-label="Scrollable table"><table>\n'
    renderer.renderer.rules["table_close"] = lambda *_: '</table></div>\n'
    return renderer.renderer.render(tokens, renderer.options, {}), headings


def render_template(template: str, values: dict) -> str:
    missing = set(re.findall(r"\{\{([a-z_]+)\}\}", template)) - values.keys()
    if missing:
        raise ValueError("Missing template values: " + ", ".join(sorted(missing)))
    return re.sub(r"\{\{([a-z_]+)\}\}", lambda match: values[match[1]], template)


def sidebar(route: str) -> str:
    items = ['<a class="docs-overview' + (' is-active' if route == 'docs/index.html' else '') + '" href="' + relative_url('docs/index.html', route) + '"' + (' aria-current="page"' if route == 'docs/index.html' else '') + '>Overview</a>']
    for section in dict.fromkeys(document.section for document in DOCUMENTS):
        items.append(f'<div class="docs-nav-group"><p>{section}</p><ul>')
        for document in DOCUMENTS:
            if document.section != section:
                continue
            current = ' class="is-active" aria-current="page"' if route == document.route else ""
            items.append(f'<li><a href="{relative_url(document.route, route)}"{current}>{html.escape(document.title)}</a></li>')
        items.append('</ul></div>')
    return "\n".join(items)


def landing_body():
    lines = ["# RatioLab documentation", "", "Read the canonical RatioLab guides: installation, the desktop workflow, optional CAD integrations, local MCP and technical references.", "", "## First launch", "", "1. [Download RatioLab](../index.html#download) for your desktop platform.", "2. Follow the [installation guide](installation.md) for system requirements, signing limitations and first launch.", "3. Choose a model, set dimensions, inspect the 3D preview and export your design.", "", "## Explore the guides", "", "These English pages are built directly from the documentation in the same source checkout. Every build also refreshes the local full-content search index.", ""]
    for document in DOCUMENTS:
        lines.extend([f"### [{document.title}]({document.source})", "", document.description, ""])
    lines.extend(["## Understanding the models", "", "RatioLab includes ten gear and transmission families, including bevel differentials. The five interactive models on the homepage are illustrations of selected mechanisms. Refer to the user guide and technical references for supported configurations, equations and limitations. Nominal geometry and ideal motion do not certify strength, service life or manufacturing readiness.", "", "SolidCraft, Autodesk Fusion and the local MCP server are optional integrations. The website and its documentation are static; searches run locally in your browser."])
    return "\n".join(lines)


def build_docs(output_root: Path, repository_root: Path, *, source_ref="main", source_label="View repository source (local checkout)"):
    template = (ROOT / "docs-shell.template.html").read_text(encoding="utf-8")
    channels = load_social_channels()
    social_links = render_social_links(channels)
    discord_ctas = render_discord_ctas(channels)
    landing = Document("", "Documentation", "Canonical RatioLab guides and technical references.", "DOCUMENTATION")
    index = []
    for document in (landing, *DOCUMENTS):
        route = document.route if document.source else "docs/index.html"
        if document.source:
            path = repository_root / "docs" / document.source
            if path.is_symlink() or not path.resolve().is_relative_to((repository_root / "docs").resolve()):
                raise ValueError("Unsafe documentation source: " + document.source)
            markdown = path.read_text(encoding="utf-8")
        else:
            markdown = landing_body()
        body, headings = render_markdown(markdown, document.source or "index.md", route, source_ref)
        toc = '<ul>' + ''.join(f'<li class="toc-level-{level}"><a href="#{html.escape(anchor, quote=True)}">{html.escape(title)}</a></li>' for level, title, anchor in headings if level == 2) + '</ul>'
        source_url = REPOSITORY + ("/blob/" + source_ref + "/docs/" + document.source if document.source else "/tree/" + source_ref + "/docs")
        values = {"root": site_root(route), "title": html.escape(document.title), "description": html.escape(document.description, quote=True), "eyebrow": html.escape(document.section), "body": body, "toc": toc, "sidebar": sidebar(route), "source_url": html.escape(source_url, quote=True), "source_label": html.escape(source_label), "language": "en", "language_label": "English · canonical documentation", "social_links": social_links, **discord_ctas}
        output = output_root / route
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_template(template, values), encoding="utf-8")
        # Preserve code text while excluding interface toolbar labels from search.
        search_body = re.sub(r'<div class="code-toolbar">.*?</div>', '', body, flags=re.S)
        for chunk in re.split(r'(?=<h[12]\b)', search_body):
            if not plain_text(chunk):
                continue
            heading = re.search(r'<h([12]) id="([^"]*)">(.*?)</h\1>', chunk, re.S)
            anchor = "#" + heading[2] if heading else ""
            title = plain_text(heading[3]) if heading else document.title
            index.append({"title": title, "page": document.title, "url": route + anchor, "section": document.section, "language": "en", "text": plain_text(chunk)})
    serialized = json.dumps(index, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    (output_root / "assets/search-index.js").write_text("window.RATIOLAB_SEARCH_INDEX=" + serialized + ";\n", encoding="utf-8")
    return len(index)
