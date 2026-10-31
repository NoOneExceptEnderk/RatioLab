# RatioLab public website

Static website, download links and searchable English documentation. The build reads all 15 canonical guides directly from `docs/`; there is no second documentation snapshot to synchronise. Output is the repository's `_site/` directory: the documentation/download site plus the self-hosted browser workspace at `/app/` (69 public files). Hosting needs no Python, application server or database; the app runs the shared Python engine through a pinned Pyodide runtime in the browser.

## Build and check

Use Python 3.10 or newer with `venv` support; Python 3.13 is used in CI and recommended for hosting. From the repository root:

```sh
bash website/build.sh
website/.venv/bin/python -B -m unittest discover -s website/tests -v
python3 -m http.server 8872 --bind 127.0.0.1 --directory _site
```

The wrapper creates `website/.venv`, installs only the two pinned pure-Python dependencies in `website/requirements.txt`, and builds both the site and the browser app. Normal builds fetch or reuse six exact size/SHA256-pinned runtime files through `scripts/fetch-web-runtime.py` in ignored `work/webapp-runtime`; there is no CDN fallback at runtime. It does not install RatioLab, GTK or native CAD dependencies. To reuse an existing isolated environment, set `RATIOLAB_SITE_VENV`; `RATIOLAB_SITE_PYTHON` selects the interpreter used to create a new environment.

Each normal build queries GitHub's public latest-release API and requires all seven uploaded installer/checksum assets of a public stable release. Missing assets, API failures and invalid canonical sources fail the build while preserving previous output. Successful discovery refreshes `website/release.json`; no GitHub token is needed. The checked-in cache is a verified public release record, not a substitute for refreshing it before publication.

After dependencies are installed, rebuild without network access using the validated cache:

```sh
website/.venv/bin/python website/build.py --offline --web-runtime-dir work/webapp-runtime
```

`bash website/build.sh --offline` also selects the validated release/runtime caches and disables network dependency installation. Prepare the isolated environment and runtime cache with a normal build first. `--web-runtime-dir PATH` selects an existing runtime cache and always verifies it without fetching, even in a normal build. Missing, edited or symlinked runtime files fail while preserving the previous public output. `--output /path/to/site` selects an output outside the repository; inside the repository, only `_site/` is accepted. Source directories, symlinks and existing directories containing unrelated files are protected.

The builder copies only its public allowlist. Website templates, build code, tests, raw guide Markdown and private work files stay outside `_site/`. The app retains its canonical 32-file bundle, including legal notices, portable `serve.py`, readable engine/source archives and `bundle-manifest.json`. The site validates its exact inventory, pinned runtime, every manifest size/SHA256 and the per-file hosting size limit before swapping output atomically. Extra files/directories, symlinks or edited app bundles in existing output are preserved by refusing replacement; select another output to retain such edits. Documentation source links name an exact commit only when Git verifies clean canonical documents; local changes are labelled honestly. Legacy Italian heading anchors remain valid after the English translation. Search and code copying run locally in the browser.

## Cloudflare Pages

Connect the GitHub repository with **Git integration**, then configure:

| Setting | Value |
|---|---|
| Framework preset | None |
| Root directory | Repository root; leave the field empty |
| Build command | `bash website/build.sh` |
| Build output directory | `_site` |
| Environment variable | `PYTHON_VERSION=3.13` |
| Environment variable | `SKIP_DEPENDENCY_INSTALL=1` |

Set both environment variables for production and preview builds. The skip setting prevents automatic repository dependency installation; the wrapper installs only website requirements and fetches the verified pinned browser runtime. It never installs the native application. See Cloudflare's [build configuration](https://developers.cloudflare.com/pages/configuration/build-configuration/) and [build image settings](https://developers.cloudflare.com/pages/configuration/build-image/).

Git pushes rebuild a connected Pages project. Publishing a GitHub release alone does **not** automatically rebuild that project: after publishing all release assets, trigger a fresh Cloudflare build of the production branch. A [deploy hook](https://developers.cloudflare.com/pages/configuration/deploy-hooks/) can automate this later; none is configured or called here. Account connection, domain configuration and deployment remain hosting setup steps.

The GitHub `Public website` workflow tests and uploads the composed `_site/` as an artifact on relevant website, browser source, shared engine, runtime recipe, legal or documentation changes, stable release publication and manual runs. Unit tests use small pinned runtime fixtures and the real canonical bundle builder; the artifact build fetches and verifies the actual runtime. It has read-only repository permissions and does not deploy to Cloudflare. Its release job checks out the default branch so current guides are published even when a release points to an older tag.

## Maintained presentation assets

Edit the two templates and `assets/` for presentation changes. The approved logo, screenshot, JavaScript and five canonical 3D examples are local assets. There are no analytics, remote fonts or embedded social widgets. Discord and GitHub links are configured in `social.json`.

A normal website build never regenerates geometry. Maintainers can explicitly run `python3 website/generate_showcase.py` from an application development environment to refresh the five canonical examples from `src/`. This is a separate operation that requires the generator's application-side dependencies and a stable source checkout. The ordinary site build copies the explicitly reviewed shared engine source into the browser archives without importing it or regenerating showcase geometry.

## Search metadata and discovery

The production origin is `https://ratiolab.dev`, configured in `website/seo.py`.
Every published page has a unique title and description, an HTTPS apex canonical
URL ending in `/`, and Open Graph/Twitter previews using the real workspace
screenshot. Local internal page links use directory URLs and keep their fragment
anchors. Preview builds deliberately name the production canonical origin.
See Google's [canonical URL guidance](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls).

The homepage includes `WebSite` and [SoftwareApplication](https://schema.org/SoftwareApplication)
structured data. Application version and download URLs come from the same
validated public release used by the download controls, rather than the source
checkout version. The 15 guides have two-level breadcrumbs; the documentation overview declares
a `CollectionPage`. No ratings, reviews or search ranking claims are added.

The build generates [a sitemap](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
for the 17 canonical pages at `https://ratiolab.dev/sitemap.xml` and advertises it
in `robots.txt`. It does not invent update dates or crawler priorities. A top-level
`404.html` is marked `noindex` and uses root-relative assets, so nested missing
addresses retain working styling. Cloudflare Pages [serves this custom 404 instead
of treating the site as a single-page application](https://developers.cloudflare.com/pages/configuration/serving-pages/).

Optionally [verify ownership in Google Search Console](https://support.google.com/webmasters/answer/9008080)
(for example, a Domain property through DNS) and [submit the sitemap](https://support.google.com/webmasters/answer/7451001).
These are manual account steps; no verification tokens or credentials belong in
this repository. Metadata and sitemap availability do not guarantee indexing or
particular search results.


## Browser workspace delivery

`website/build.py` composes `scripts/build-webapp.py` in an external temporary
directory, validates the complete self-hosted bundle, then copies it unchanged
into site staging at `app/`. Website HTML finalization runs before this copy, so
it cannot invalidate the app's checksum manifest or its document-driven title.
The app uses relative assets and worker URLs, keeping `/app/` self-contained.
See [the browser guide](../docs/web-app.md) for requirements and functional limits.

The generated Cloudflare `_headers` disables storage for `/app` and `/app/*`,
including stable HTML, worker, module, runtime and engine archive URLs, to avoid
stale assets mixing across deployments. It explicitly serves WASM as
`application/wasm` and runtime modules as `text/javascript`. There is no service
worker, forced cross-origin isolation or external runtime fallback. The site
keeps its custom 404 so missing bundle assets do not become an app HTML response.
Local `python -m http.server` previews do not apply Cloudflare's `_headers`;
verify response headers on the deployed Pages site as part of publication.
