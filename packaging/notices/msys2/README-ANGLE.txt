ANGLE notices: exact MSYS2 UCRT64 package 2.1.r25748.890b5d8f-6
Retrieved and verified: 2026-10-28

Scope
-----
The Windows bundle distributes libEGL.dll and libGLESv2.dll from
mingw-w64-ucrt-x86_64-angleproject. The installed root LICENSE covers ANGLE
itself. These additional, individually selected notices cover code/headers
incorporated into those DLLs. They supplement the native package LICENSE,
even when that LICENSE was successfully attributed by pacman. The build
refuses an unknown ANGLE version or changed license declaration, rather than
treating the installed root LICENSE as sufficient.

No SwiftShader, mock ICD, capture or Vulkan-secondary DLL is distributed.
GPU drivers and Windows system libraries are provided by the operating
system/hardware vendor and are not bundled by this notice collection.

Primary sources and integrity
-----------------------------
Official package page:
https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-angleproject

The official binary package SHA-256 was verified independently:
3c184061a3a3ef6478055e11eb786e20c40e62c1c239a1d65bf1399b7e2e7113
Its .BUILDINFO records ANGLE 2.1.r25748.890b5d8f-6 and RapidJSON 1.1.0-8.
Its installed root LICENSE is byte-identical to 00-LICENSE-ANGLE.txt.
Its libGLESv2.dll imports zlib1.dll and Windows/GCC runtime libraries;
it does not import a separate SPIRV/Vulkan implementation library.

The pinned, official MSYS2 PKGBUILD URL and real SHA-256 are recorded in
registry.json. PKGBUILD.txt is byte-identical to that file. SRCINFO.txt was
read from the leading metadata entries in the official source-only archive.
It identifies the exact ANGLE commit and additional source Git commits.
The complete 2,141,091,794-byte source archive was NOT downloaded or hashed.
source_sha256 and source_package_sha256 are therefore explicitly null for
this VCS-backed record; no full-archive integrity verification is claimed.

Instead, each selected file has an immutable official Gitiles URL, source
repository/commit/path, original full-file SHA-256, and Git blob SHA-1
checked against the parent directory tree at that commit. Two independent
HTTP responses are compared. selection_bytes is a zero-based, half-open
byte range [start, end] into the original file. Each vendored text preserves
those exact bytes, without rewriting copyright statements or line endings.
For complete license files the range spans the entire file. For source files
only complete copyright/license comment blocks are selected; implementation
code, tests and unrelated documentation licenses are excluded.
Where available, source_mirror identifies an immutable official GitHub copy
verified to have exactly the same full-file hash and original Git blob. The
Chromium zlib source mirror is the identical copy in the DEPS-pinned Chromium
tree; its actual Gitiles source/commit remain recorded separately. The VMA
commit is available from the Chromium Gitiles mirror only.

Selected texts and build evidence
---------------------------------
The exact ANGLE commit is 890b5d8fa2988e3719e0d80421bf3e927db9cd5c.
The package recipe pins SPIRV-Headers, SPIRV-Tools, Vulkan-Headers,
Vulkan-Loader and VulkanMemoryAllocator separately in SRCINFO.txt.

00: ANGLE root BSD license.
01: xxHash root BSD license, compiled by the angle_common target.
02: SPIRV-Headers original Khronos copyright and complete MIT permission
    block, from the first section of its root LICENSE. The subsequent
    sections cover XML, build tools and documentation not distributed here.
03: SPIRV-Tools Apache-2.0 text, for the static shader validator.
04-06: Vulkan-Headers original copyright/license overview and referenced
    Apache-2.0/MIT texts.
07: Vulkan-Loader root Apache-2.0 license. Its own overview explicitly says
    that some source files have other, more permissive terms.
08: cJSON original MIT copyright/permission block in the static loader.
09,16: Both original dirent_on_windows header/source license blocks. Their
    copyright years differ, so both are retained.
17: loader_json original MIT block (Khronos, Valve and LunarG).
10: VulkanMemoryAllocator original AMD MIT license.
11-12: Chromium BSD license and compression_utils_portable's original
    Chromium copyright/reference block. The Chromium root license commit
    a9fc4ae13759a05e6f66569039b429aa940618c2 is pinned by ANGLE's DEPS file;
    compression_utils_portable comes from the zlib commit in SRCINFO.txt.
13-15: Original Khronos platform/EGL/GLES header copyright/license blocks;
    the associated Apache-2.0/MIT terms are included above.

Relevant original target graphs at the pinned ANGLE commit:
https://chromium.googlesource.com/angle/angle/+/890b5d8fa2988e3719e0d80421bf3e927db9cd5c/BUILD.gn
https://chromium.googlesource.com/angle/angle/+/890b5d8fa2988e3719e0d80421bf3e927db9cd5c/gni/angle.gni
https://chromium.googlesource.com/angle/angle/+/890b5d8fa2988e3719e0d80421bf3e927db9cd5c/src/common/vulkan/BUILD.gn
https://chromium.googlesource.com/angle/angle/+/890b5d8fa2988e3719e0d80421bf3e927db9cd5c/src/libANGLE/renderer/vulkan/BUILD.gn
https://chromium.googlesource.com/angle/angle/+/890b5d8fa2988e3719e0d80421bf3e927db9cd5c/DEPS

PKGBUILD sets angle_enable_abseil=false, angle_enable_cl=false,
angle_enable_metal=false, and angle_shared_libvulkan=false. Its verified
002-buildflags-fixes.patch also disables ASTC on MinGW. Thus no Abseil,
OpenCL, Metal, ASTC or volk notice is selected. The default
angle_with_capture_by_default=false links libANGLE, not libANGLE_with_capture:
RapidJSON serialization and ceval belong to the capture target and are
excluded. Chromium compression_utils_portable remains a core dependency.
Dynamic zlib/GCC dependencies retain their own package inventory/notices.
Build tools, validation layers, Vulkan tools, test fixtures and documentation
assets are not selected merely because their sources exist in the recipe.

Reproduce without downloading the large source archive
------------------------------------------------------
From a checkout or extracted sdist, run:

  python packaging/notices/msys2/verify_angle.py
  python packaging/notices/msys2/verify_angle.py --online --cache work/angle-verification
  python -m unittest test_bundles.NativeNoticesTests

The first command checks the local recipe/SRCINFO/text checksums and pinned
references. The opt-in online command downloads only the pinned recipe,
individual original files and their parent directory trees. It checks two
independent copies of each original file, full-file SHA-256, actual Git blob
identity, selected byte range and equality to the vendored notice. It writes
proof.json and the original small source files into the requested cache.
The native bundle build itself uses only local, hash-checked notices and
performs no network download or PKGBUILD execution.

Update procedure
----------------
An ANGLE package upgrade requires review of the new exact recipe, source
commits, flags, target graph and distributed DLLs. Update the selected notices
and provenance together, re-run this verifier and native bundle checks, and
review the emitted components.json. Do not reuse this registry entry for an
unverified version or silently drop a missing notice. These notices preserve
upstream license terms; they do not choose a license for RatioLab.
