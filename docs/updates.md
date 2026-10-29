# Updates and release notes

Installed wheels and native bundles check GitHub for newer RatioLab releases
when the workspace opens and once every 24 hours while it stays open. The
header shows **Update to [version]** only when a newer eligible release exists.
Nothing opens automatically. Click it to read the published notes, then choose
**Download** to open the matching package in your browser. If a matching asset
is unavailable, the release page opens instead. Install the package as usual;
RatioLab does not replace itself, run an installer or overwrite a source checkout.

**Skip this version** hides that release until a newer one appears.
**Remind me later** hides the badge for three days. The project menu's
**Release notes and updates…** entry also opens the notes and local changelog.
The local changelog is labelled separately from notes published for a downloadable
GitHub release. An **Unreleased** section, when present, describes development changes.

Stable builds accept only newer stable versions. Preview builds accept newer
preview/RC/alpha/beta versions and stable releases, using SemVer precedence: for example,
`0.1.0-preview.3` follows `0.1.0-preview.2`, and `0.1.0` follows both. Drafts,
older/equal versions and unrelated release/download URLs are ignored. Nightly
builds are not offered automatically. The canonical
`src/ratiolab_resources/version.json` records the base packaging
version, exact release version and channel. Native installers retain their
numeric base version; `ratiolab --version` reports the exact release identity.
Release maintainers must update that JSON for every release and keep its base
consistent with `pyproject.toml`. Stable versions use the same numeric base and
release identity (for example, `0.1.1`) with the `stable` channel. The bundle
manifest records both identities.

Windows selects the x86-64 setup executable; macOS selects the architecture's
DMG; Linux selects the `.run` installer, or the Debian package for the fixed
`/opt/ratiolab` installation. Unsupported platforms/architectures use the release
page. Package-manager installations should follow their normal upgrade process.
Downloads are opened externally: RatioLab neither downloads nor verifies or
installs an executable in this workflow.

One anonymous HTTPS request reads up to 100 published GitHub releases:

```
GET https://api.github.com/repos/NoOneExceptEnderk/RatioLab/releases?per_page=100
User-Agent: RatioLab-update-check
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
```

It sends no installed version, project data, token, cookie, machine identifier
or usage information. GitHub sees the IP address and request time. The worker
uses a 15-second socket timeout, 2 MiB response limit and no redirects. Offline
or invalid responses remain silent and retry after an hour; rate-limit headers
can extend that delay, persisted across restarts. No network request blocks GTK.

Set `RATIOLAB_UPDATE_CHECK=0` to disable all checks. Source checkouts do not check
by default; `RATIOLAB_UPDATE_CHECK=1` explicitly enables them for development.
Updater skip/reminder/backoff state lives in `updates.json` in RatioLab's user
configuration folder, separately from projects and UI preferences.

This interaction follows the [SolidCraft update pattern](https://docs.solidcraft.io/guide/updates.html)
and uses GitHub's [public releases API](https://docs.github.com/en/rest/releases/releases#list-releases).
