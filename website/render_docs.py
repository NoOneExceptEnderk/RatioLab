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
from seo import IMAGE_VERSION, ORIGIN, documentation_schema, metadata
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
    Document("installation.md", "Installation", "Install RatioLab on Windows, macOS or Linux: system requirements, signing limits, graphics setup and first launch.", "GET STARTED"),
    Document("web-app.md", "Browser app", "Use RatioLab in a browser: fifteen model families, 3D tools, STEP/STL downloads, local project recovery and browser requirements.", "GET STARTED"),
    Document("user-guide.md", "User guide", "Design fifteen gear and reducer families, including Wolfrom: parameters, 3D motion, measurements, projects and CAD export.", "GET STARTED"),
    Document("mcp.md", "MCP and agents", "Connect local agents to the RatioLab desktop MCP server: setup, tools, workspace files, cancellation and resource limits.", "GET STARTED"),
    Document("updates.md", "Application updates", "Check for RatioLab desktop updates, choose a public stable release and install verified downloads with documented privacy controls.", "GET STARTED"),
    Document("fusion360.md", "Autodesk Fusion", "Send RatioLab designs to Autodesk Fusion: optional bridge setup, STEP transfer, Linux/Wine configuration and failure handling.", "GET STARTED"),
    Document("development.md", "Development and builds", "Build and verify RatioLab from source: Python and GTK dependencies, native installers, development checks and optional CAD bridges.", "DEVELOPMENT"),
    Document("technical/calculations.md", "Calculations and references", "RatioLab gear calculations: tooth geometry, theoretical metrology, working backlash, kinematics, Wolfrom ratios and analysis limits.", "TECHNICAL REFERENCE"),
    Document("technical/hardware.md", "Hardware and assembly", "Understand RatioLab bearing seats, fits, shafts and standard hardware: generated dimensions, bills of materials and assembly limits.", "TECHNICAL REFERENCE"),
    Document("technical/io-models.md", "Input and output", "Configure reducer input and output connections: generated mounts, member roles, Wolfrom topology and mechanical limitations.", "TECHNICAL REFERENCE"),
    Document("technical/kinematics.md", "Kinematics", "Understand RatioLab kinematics: represented gear and reducer motions, member speed conventions and nominal export coordinates.", "TECHNICAL REFERENCE"),
    Document("technical/printed-shaft.md", "FDM printed shaft", "Explore the experimental FDM cycloidal eccentric shaft: two-bolt construction, hardware, printed assembly and verification limits.", "TECHNICAL REFERENCE"),
    Document("technical/variants.md", "Variants and limitations", "Compare double-helical, planetary, ZA/ZI worm and strain-wave constructions: generated variants, kinematic arrangements and model limits.", "TECHNICAL REFERENCE"),
    Document("technical/worm.md", "Worm reference", "Reference equations for ZA/ZI cylindrical worms and generated wheels: screw profiles, envelope geometry, sampling and supported limits.", "TECHNICAL REFERENCE"),
    Document("technical/strain-wave.md", "Strain-wave reference", "Understand the strain-wave model: prescribed deformation, generated ring envelope, numerical enclosure and moving-interference checks.", "TECHNICAL REFERENCE"),
    Document("technical/wolfrom.md", "Wolfrom / 3K reference", "Reference for two-rim spur Wolfrom reducers: fixed topology, speed equations, equal planet spacing, nominal profiles and a numerical example.", "TECHNICAL REFERENCE"),
    Document("technical/differential.md", "Bevel differential reference", "Reference for wrist and classic bevel differentials: independent inputs, speed equations, spherical involute geometry and spiral traces.", "TECHNICAL REFERENCE"),
)
DOCUMENTS = DOCUMENTS + (
    Document("tutorials/planetary-gear-generator.md", "Planetary gear generator", "Generate a 4:1 planetary gear set with RatioLab: download a working JSON project, inspect the motion and export STEP or STL.", "WORKED EXAMPLES"),
    Document("tutorials/cycloidal-drive-generator.md", "Cycloidal drive generator", "Generate a 15:1 cycloidal reducer with RatioLab: a real 16-roller project, explained parameters, motion and STEP/STL export.", "WORKED EXAMPLES"),
    Document("technical/parallel.md", "Multistage parallel reducers", "Single-, two- and three-stage parallel-shaft reducers, tooth types, shaft layout and ideal motion conventions.", "TECHNICAL REFERENCE"),
    Document("technical/bevel-pair.md", "Bevel gear pairs", "Straight, spiral and zerol bevel gear pairs: nominal geometry, parameters and model limits.", "TECHNICAL REFERENCE"),
    Document("technical/hypoid.md", "Hypoid gear pairs", "Generated offset hypoid gear pairs: shaft offset, spiral geometry and verification scope.", "TECHNICAL REFERENCE"),
    Document("technical/rack.md", "Rack and pinion", "Spur, helical and double-helical rack and pinion geometry, dimensions and ideal motion.", "TECHNICAL REFERENCE"),
    Document("technical/face-gears.md", "Face gear pairs", "Orthogonal and offset face gear pairs, tooth types, herringbone construction and documented limits.", "TECHNICAL REFERENCE"),
)
TUTORIAL_PROJECTS = {'examples/planetary-browser-guide.config.json', 'examples/cycloidal-browser-guide.config.json'}
TUTORIAL_IMAGES = {'assets/planetary-guide.svg', 'assets/cycloidal-guide.svg'}
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
    if parsed.netloc == urlsplit(ORIGIN).netloc and parsed.scheme == 'https' and path in ('/app/', '/app/index.html'):
        return urlunsplit(('', '', relative_url('app/index.html', route), parsed.query, parsed.fragment))
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
    if candidate in TUTORIAL_PROJECTS or candidate in TUTORIAL_IMAGES:
        localized = relative_url(candidate, route)
    elif candidate.startswith("docs/") and candidate[5:] in BY_SOURCE:
        localized = relative_url(BY_SOURCE[candidate[5:]].route, route)
    elif candidate == "index.html":
        localized = relative_url("index.html", route)
    elif candidate == "assets/screenshots/workspace.png":
        localized = relative_url("assets/workspace.png", route)
        parsed = parsed._replace(query="v=" + IMAGE_VERSION)
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
                if child.type == "link_open" and any(child.attrGet("href").endswith("/" + Path(project).name) for project in TUTORIAL_PROJECTS):
                    child.attrSet("download", Path(child.attrGet("href")).name)
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
    lines = ["# RatioLab documentation", "", "Read the canonical RatioLab guides: the browser and desktop workflows, installation, optional CAD integrations, local MCP and technical references.", "", "## First launch", "", "1. [Open the browser app](https://ratiolab.dev/app/) or [download RatioLab](../index.html#download) for your desktop platform.", "2. Follow the [installation guide](installation.md) for system requirements, signing limitations and first launch.", "3. Choose a model, set dimensions, inspect the 3D preview and export your design.", "", "## Explore the guides", "", "These English pages are built directly from the documentation in the same source checkout. Every build also refreshes the local full-content search index.", ""]
    for document in DOCUMENTS:
        lines.extend([f"### [{document.title}]({document.source})", "", document.description, ""])
    lines.extend(["## Understanding the models", "", "RatioLab includes fifteen gear and transmission families, including planetary, cycloidal, Wolfrom and multistage reducers, bevel/hypoid and face gear pairs, rack and pinion, and bevel differentials. The five interactive models on the homepage are illustrations of selected mechanisms. Refer to the user guide and technical references for supported configurations, equations and limitations. Nominal geometry and ideal motion do not certify strength, service life or manufacturing readiness.", "", "SolidCraft, Autodesk Fusion and the local MCP server are optional integrations. The website and its documentation are static; searches run locally in your browser."])
    return "\n".join(lines)


def build_docs(output_root: Path, repository_root: Path, *, source_ref="main", source_label="View repository source (local checkout)"):
    template = (ROOT / "docs-shell.template.html").read_text(encoding="utf-8")
    channels = load_social_channels()
    social_links = render_social_links(channels)
    discord_ctas = render_discord_ctas(channels)
    landing = Document("", "Documentation", "RatioLab guides for browser and desktop: installation, fifteen gear and reducer families, STEP/STL export, CAD integrations and technical references.", "DOCUMENTATION")
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
        values["seo_head"] = metadata(route, document.title + " — RatioLab docs", document.description, schema=documentation_schema(route, document.title))
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
            index.append({"title": title, "page": document.title, "url": route.removesuffix("index.html") + anchor, "section": document.section, "language": "en", "text": plain_text(chunk)})
    serialized = json.dumps(index, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    (output_root / "assets/search-index.js").write_text("window.RATIOLAB_SEARCH_INDEX=" + serialized + ";\n", encoding="utf-8")
    return len(index)
