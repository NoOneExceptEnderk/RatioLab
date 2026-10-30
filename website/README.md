# RatioLab public website

Static website, download links and searchable English documentation. The build reads all 15 canonical guides directly from `docs/`; there is no second documentation snapshot to synchronise. Output is the repository's `_site/` directory: 17 HTML pages and 16 assets. Hosting needs no Python, application server or database.

## Build and check

Use Python 3.10 or newer with `venv` support; Python 3.13 is used in CI and recommended for hosting. From the repository root:

```sh
bash website/build.sh
website/.venv/bin/python -B -m unittest discover -s website/tests -v
python3 -m http.server 8872 --bind 127.0.0.1 --directory _site
```

The wrapper creates `website/.venv`, installs only the two pinned pure-Python dependencies in `website/requirements.txt`, and builds the website. It does not install RatioLab, GTK or native CAD dependencies. To reuse an existing isolated environment, set `RATIOLAB_SITE_VENV`; `RATIOLAB_SITE_PYTHON` selects the interpreter used to create a new environment.

Each normal build queries GitHub's public latest-release API and requires all seven uploaded installer/checksum assets of a public stable release. Missing assets, API failures and invalid canonical sources fail the build while preserving previous output. Successful discovery refreshes `website/release.json`; no GitHub token is needed. The checked-in cache is a verified public release record, not a substitute for refreshing it before publication.

After dependencies are installed, rebuild without network access using the validated cache:

```sh
website/.venv/bin/python website/build.py --offline
```

`bash website/build.sh --offline` also selects the cache, but dependency installation may still require network access. `--output /path/to/site` selects an output outside the repository; inside the repository, only `_site/` is accepted. Source directories, symlinks and existing directories containing unrelated files are protected.

The builder copies only its public allowlist. Templates, Python, tests, Markdown sources and private work files stay outside `_site/`. Documentation source links name an exact commit only when Git verifies clean canonical documents; local changes are labelled honestly. Legacy Italian heading anchors remain valid after the English translation. Search and code copying run locally in the browser.

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

Set both environment variables for production and preview builds. The skip setting prevents automatic repository dependency installation; the wrapper installs only website requirements. See Cloudflare's [build configuration](https://developers.cloudflare.com/pages/configuration/build-configuration/) and [build image settings](https://developers.cloudflare.com/pages/configuration/build-image/).

Git pushes rebuild a connected Pages project. Publishing a GitHub release alone does **not** automatically rebuild that project: after publishing all release assets, trigger a fresh Cloudflare build of the production branch. A [deploy hook](https://developers.cloudflare.com/pages/configuration/deploy-hooks/) can automate this later; none is configured or called here. Account connection, domain configuration and deployment remain hosting setup steps.

The GitHub `Public website` workflow tests and uploads `_site/` as an artifact on relevant pushes, pull requests, stable release publication and manual runs. It has read-only repository permissions and does not deploy to Cloudflare. Its release job checks out the default branch so current guides are published even when a release points to an older tag.

## Maintained presentation assets

Edit the two templates and `assets/` for presentation changes. The approved logo, screenshot, JavaScript and five canonical 3D examples are local assets. There are no analytics, remote fonts or embedded social widgets. Discord and GitHub links are configured in `social.json`.

A normal website build never regenerates geometry. Maintainers can explicitly run `python3 website/generate_showcase.py` from an application development environment to refresh the five canonical examples from `src/`. This is a separate operation that requires the generator's application-side dependencies and a stable source checkout. The website's ordinary build and tests do not import that engine.
