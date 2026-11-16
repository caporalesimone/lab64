# Release publishing

Copyright © 2026 - Simone Caporale

`lab64 publish`, implemented by `containers/tools/py/c64publish.py`. The format it writes (`manifest.json`) is described in
[manifest.md](manifest.md).

One folder per version, `out/releases/v<version>/`, with `manifest.json` (the contract with the viewer), the latest N kept
(`C64_KEEP_VERSIONS`, default 5), `out/releases/latest` = link to the newest. Publishing the same version again replaces only the
groups given and keeps the others. Default (`lab64 publish`, run by the default build): the disk as `<name>_v<V>.d64`, the PDFs
of `out/work/manual/`, the memory map with its metrics, the test report if newer than the disk; `--extra GROUP:SRC[:DST]` adds
files (DST must be a relative path inside the version folder: `../` or an absolute path stops the publishing before anything is
removed); `--release` marks the version. Version: `--version`, else `C64_VERSION` (a folder name: no `/`).
A project with its own artefacts and measures calls `c64publish.publish(version, groups, labels=..., kinds=..., tests=...,
metrics=[metric(...)], info=..., source_hash=..., expected=...)` from its build (in `lab64-tools`).

With `C64_PUBLISH_SID_RENDER=1`, `lab64 publish` also writes a 192 kbit/s MP3 of every subtune next to each `.sid` published with
kind `sid` (see [sid-rendering.md](sid-rendering.md)).
