# Updates and release notes

Installed desktop copies check GitHub when the workspace opens and once a day
while it stays open, unless automatic checks are turned off. Source checkouts
start with automatic checks off; they can check manually or save an automatic
check preference in the same window. A newer eligible release adds **Update to [version]** to
the header. Checking does not open a window or start an installation by itself.
Click the badge to read the published notes and choose how to update.

The project menu's **Release notes and updates…** opens the update window and
checks for a release. **Check now** runs another check, including when
**Check for updates automatically** is off. The window shows progress, the
available version, installation type, an up-to-date result or an error. GitHub rate limits still
apply to manual checks. The automatic preference is saved separately from
project files and other UI preferences.

**Skip this version** hides that release's badge until a newer one appears.
**Remind me later** hides it for three days. A manual check can still show a
skipped or deferred release. The window presents readable published release
notes and numbered version history. Development sections headed **Unreleased**
are excluded. Links within those notes are displayed as plain captions; the
explicit release and download buttons open the trusted project URLs.

## Download and install

Where the installation can be identified, the primary update button downloads the matching
package in the background, with progress and cancellation. RatioLab obtains
`SHA256SUMS` from the same GitHub release and checks the complete package before
starting the installation or opening the verified package. A changed, truncated
or mismatched package cannot be installed. Checksums provide integrity against
the published release; RatioLab
does not currently claim publisher signatures or notarization for these files.

| Installation | Action after verification |
| --- | --- |
| Linux per-user `.run` installation | **Update now** downloads, verifies, closes, installs in the same marked application folder and reopens RatioLab. Custom installation paths are retained. |
| Windows per-user Setup installation | **Update now** closes RatioLab, runs the verified Setup with a progress window and reopens the verified target version in the recorded installation folder. There is no installer wizard. |
| macOS application in writable `/Applications` or `~/Applications` | **Update now** closes RatioLab, verifies the disk image and application, replaces the application in the same folder, and reopens it. Protected, read-only, Downloads, translocated and unproven custom locations retain manual installation. |
| Debian/Ubuntu `.deb` | **Update now** closes RatioLab, requests normal system authorization, updates the verified package with apt-get, checks the installed version and runtime, and reopens RatioLab. If PolicyKit or the required package tools are unavailable, use Download manually with your system installer. |
| Source, Python environment or unmarked portable tree | Use the original installation method or the browser download; RatioLab does not replace these directories. |

Closing for an installer uses the normal **Save / Discard / Cancel** prompt.
Cancel, a failed save or an outdated answer keeps the application open and does
not arm the installer. Projects and preferences remain outside the managed
runtime by default. The Linux installer also preserves unlisted files saved
inside its installation folder, and checks the staged runtime before replacing
the previous one. Its rollback ends once installation succeeds; there is no
promise of rollback after a later application failure. Windows Setup is not a
transactional rollback service. Restart does not restore a project's undo history.

Windows Setup uses its documented silent mode with visible progress, a pinned
installation folder and a private setup log. It cannot reboot the computer or
close/restart other applications. A required system reboot is reported as
incomplete rather than success. Before reopening, RatioLab verifies the target
manifest, complete listed file inventory, exact runtime version and native
dependency check. A failed Setup can reopen the previous version only if its
original manifest, complete inventory and runtime still validate.

Older Windows copies, including 0.1.13, may need Setup 0.2.4 run manually once
in their existing installation folder. Fixes in the 0.1.14 helper do not
retroactively change an already installed older updater. Once 0.1.14 is installed,
subsequent eligible updates use the corrected helper.

Debian updates first check the archive's exact package name (`ratiolab`), version
and architecture using dpkg-deb. After the protected application closes, a helper
rechecks the archive and installed identity, then requests PolicyKit authorization
for the fixed system command `apt-get --yes --no-remove install` and that local
package. Authorization does not elevate a shell or the application. Cancelled
authorization reopens the unchanged previous runtime when it still validates.
A package-manager failure can leave a partially updated runtime; RatioLab does
not reopen that unverified runtime or promise a package-manager rollback.

For supported macOS installations, the helper waits for the original process
to exit, rechecks the downloaded image, and mounts it read-only in a private
location. It checks the application identifier, exact version, architecture
and strict deep code signature. A private sibling copy is checked again and
runs the headless self-test before replacing the application. Same-volume
renames retain the old copy until the new location passes signature, version
and runtime checks. A failure restores the old application when possible; if
restoration itself fails, the backup is retained and its location appears in
the update log. The disk image is detached during cleanup.

macOS updates never re-sign code, remove quarantine attributes, disable system
security checks, request a password, or migrate the application to another
folder. This updater does not elevate privileges: a protected Applications
folder needs the normal manual macOS installation workflow. Source/Python
environments and applications running directly from an image or Downloads are
never replaced automatically.

Replacement is offered only for a matching native installation whose ownership
and format can be established. Linux replacement also requires a writable
installation and parent directory owned by the user. External helpers wait for
the old process to exit and recheck the package before starting an installer.
Preparation failures leave the current application available. Helper logs are
retained in the private update cache for diagnosing failures after exit.

Older Linux installers could create group-writable installation metadata or a
group-writable default application folder under a permissive umask. Those older
applications may refuse their own native update before downloading it. In that
case, run the latest installer once against the existing installation folder;
it updates that folder and preserves unlisted user files. New installers protect
their marker and managed default parent so default per-user installations remain
eligible for subsequent in-app updates.

On native desktop installations, the helper records its actual terminal result before requesting a
restart. The next launch of that installation displays the result once, with a
**View update log** action. Success requires both a completed installation and
the target version actually running. An installer failure or a restart of the
older version is explained as a failed or incomplete update. This receipt does
not change projects, undo history, or session recovery.

**Download manually** remains a secondary browser fallback. It opens the matching package, or the
release page if no supported package exists. Browser downloads are installed
manually and are not verified by RatioLab's in-app download process. Package
manager updates use their system's normal authorization and package manager.

[Native CI](https://github.com/NoOneExceptEnderk/RatioLab/actions/runs/41249327987)
used the new 0.1.14 production helper on Windows to upgrade a public 0.1.12
installation to 0.1.14 at the same location. Package hashes matched, user-data
sentinels were preserved, and the terminal receipt was consumed exactly once.
GUI restart was disabled in this harness. Separate GUI restart guard tests do
not establish the old public 0.1.13 Windows client flow. Windows GUI rendering
remains unverified because the hosted runner could not create an OpenGL context.
A separate disposable Linux check used the public 0.1.13 helper to install and
reopen 0.1.14 and passed real GTK/OpenGL checks; that older helper does not produce
the new terminal receipt.

Debian adapter tests use harmless command fixtures and temporary packages, without
installing a system package or requesting elevated privileges.
macOS transaction tests execute the generated shell helper with harmless
command fixtures on Linux, including signature/identity rejection, rollback,
cleanup and parent-process state changes. The native CI run linked above also
mounted real DMGs, copied the application and verified strict deep code signatures
on both macOS architectures. It used the new helper for 0.1.12 to 0.1.14 upgrades
with GUI restart disabled. LaunchServices restart and the old public 0.1.13 macOS
client flow remain unverified.

Version 0.1.15 isolates self-test preferences and exports through a temporary
Python environment mapping without changing the native process environment that
GTK/font workers may read concurrently. The mapping is restored on success or
failure. This addresses a demonstrated concurrent environment-read failure
mechanism; it does not establish the cause of every previous native crash.

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

`RATIOLAB_UPDATE_CHECK=0` disables all checks, including manual checks, and makes
the automatic checkbox unavailable. Source checkouts allow **Check now** without
changing launch settings, and their automatic opt-in persists across launches.
`RATIOLAB_UPDATE_CHECK=1` changes the default for development checks; a saved
automatic preference still takes precedence. Source and Python installations
are never overwritten by the native updater. The window explains disabled checks. Update preferences,
skip/reminder choices and rate-limit state live in `updates.json` in the user
configuration folder.

The interaction follows the [SolidCraft update flow](https://docs.solidcraft.io/guide/updates.html),
adapted to RatioLab's existing installers, and uses GitHub's
[public releases API](https://docs.github.com/en/rest/releases/releases#list-releases).
Native handoffs follow the documented [Inno Setup command-line parameters](https://jrsoftware.org/ishelp/topic_setupcmdline.htm),
[silent-run behavior](https://jrsoftware.org/ishelp/topic_runsection.htm),
[PolicyKit authorization and return codes](https://www.freedesktop.org/software/polkit/docs/latest/pkexec.1.html)
and [dpkg-deb package metadata](https://manpages.debian.org/bookworm/dpkg/dpkg-deb.1.en.html).
macOS signature verification follows Apple's
[Code Signing Guide](https://developer.apple.com/library/archive/documentation/Security/Conceptual/CodeSigningGuide/Procedures/Procedures.html)
and [TN2206](https://developer.apple.com/library/archive/technotes/tn2206/_index.html).
