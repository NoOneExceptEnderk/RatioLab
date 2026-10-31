# Updates and release notes

Installed desktop copies check GitHub when the workspace opens and once a day
while it stays open. A newer eligible release adds **Update to [version]** to
the header. Checking does not open a window or start an installation by itself.
Click the badge to read the published notes and choose how to update.

The project menu's **Release notes and updates…** opens the update window and
checks for a release. **Check now** runs another check, including when
**Check for updates automatically** is off. The window shows progress, the
available version, an up-to-date result or an error. GitHub rate limits still
apply to manual checks. The automatic preference is saved separately from
project files and other UI preferences.

**Skip this version** hides that release's badge until a newer one appears.
**Remind me later** hides it for three days. A manual check can still show a
skipped or deferred release. Local changelog entries are labelled separately
from the notes of the downloadable release; **Unreleased** describes development
work, rather than an available installer.

## Download and install

Where the installation can be identified, **Update now** downloads the matching
package in the background, with progress and cancellation. RatioLab obtains
`SHA256SUMS` from the same GitHub release and checks the complete package before
starting the installation or opening the verified package. A changed, truncated
or mismatched package cannot be installed. Checksums provide integrity against
the published release; RatioLab
does not currently claim publisher signatures or notarization for these files.

| Installation | Action after verification |
| --- | --- |
| Linux per-user `.run` installation | Close, install in the same marked application folder and restart. Custom installation paths are retained. |
| Windows per-user Setup installation | Close RatioLab and start the verified interactive Setup for the recorded installation folder. Setup handles the remaining choices. |
| macOS application | Open the verified DMG. Quit RatioLab and drag the new application to Applications to replace the previous copy. |
| Debian/Ubuntu `.deb` | Open the verified package with the system installer. A quoted `sudo apt install …` command is also available for manual use. |
| Source, Python environment or unmarked portable tree | Use the original installation method or the browser download; RatioLab does not replace these directories. |

Closing for an installer uses the normal **Save / Discard / Cancel** prompt.
Cancel, a failed save or an outdated answer keeps the application open and does
not arm the installer. Projects and preferences remain outside the managed
runtime by default. The Linux installer also preserves unlisted files saved
inside its installation folder, and checks the staged runtime before replacing
the previous one. Its rollback ends once installation succeeds; there is no
promise of rollback after a later application failure. Windows Setup is not a
transactional rollback service. Restart does not restore a project's undo history.

Replacement is offered only for a matching native installation whose ownership
and format can be established. Linux replacement also requires a writable
installation and parent directory owned by the user. External helpers wait for
the old process to exit and recheck the package before starting an installer.
Preparation failures leave the current application available. Helper logs are
retained in the private update cache for diagnosing failures after exit.

**Download** remains a browser fallback. It opens the matching package, or the
release page if no supported package exists. Browser downloads are installed
manually and are not verified by RatioLab's in-app download process. Package
manager installations continue to use their system's installation workflow.

## Release selection and privacy

Stable builds accept newer stable versions; preview builds also accept newer
preview, RC, alpha and beta releases, using SemVer precedence. Drafts, equal or
older versions, nightly releases and unrelated release URLs are ignored.
`src/ratiolab_resources/version.json` records the installed identity and channel;
its base version must match `pyproject.toml`. A source push alone does not create
a downloadable update.

Release discovery makes one anonymous, bounded HTTPS request:

```text
GET https://api.github.com/repos/NoOneExceptEnderk/RatioLab/releases?per_page=100
User-Agent: RatioLab-update-check
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
```

Choosing the in-app download additionally requests the release's checksum list
and selected package from GitHub, following only supported HTTPS asset redirects.
It sends no project, installed version, token, cookie, machine identifier or
usage data. GitHub sees the IP address and request time. Metadata is limited to
2 MiB, checksum lists to 1 MiB and packages to 512 MiB, with socket timeouts and
a bounded download deadline. Failed or cancelled downloads remove their own
partial files. Automatic failures retry later without opening a window; manual
checks display their result.

`RATIOLAB_UPDATE_CHECK=0` disables all checks, including manual checks. Source
checkouts do not check by default; `RATIOLAB_UPDATE_CHECK=1` explicitly enables
development checks. The window explains disabled checks. Update preferences,
skip/reminder choices and rate-limit state live in `updates.json` in the user
configuration folder.

The interaction follows the [SolidCraft update flow](https://docs.solidcraft.io/guide/updates.html),
adapted to RatioLab's existing installers, and uses GitHub's
[public releases API](https://docs.github.com/en/rest/releases/releases#list-releases).
