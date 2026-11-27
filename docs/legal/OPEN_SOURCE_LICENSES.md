# Open-Source & Third-Party Licences

**Last reviewed: November 25, 2026**

## Project licence

The Lemegeton source code is distributed under the MIT License. See [../LICENSE](../LICENSE) for the complete project licence text. That licence covers the project code within its scope; it does not license user submissions, external media, provider data, brand marks or third-party assets.

## Direct dependency inventory

The following names are direct dependencies declared in the current v3 manifests. This is a dependency pointer list, **not a complete licence or copyright attribution schedule**. Each package retains its own upstream licence and notices.

| Area | Direct dependencies declared |
|---|---|
| Bot runtime | discord.js, sharp, @extractus/article-extractor, cheerio, fast-xml-parser, robots-parser, axios, jsdom, node-html-parser, p-limit, p-retry, playwright, tough-cookie, undici, node-addon-api |
| Dashboard frontend | react, react-dom, next, @react-three/fiber, three, thinking-orbs (MIT; version 0.3.2) |
| Dashboard backend | axum, dotenvy, reqwest, libsql, serde, serde_json, subtle, tokio, tracing, tracing-subscriber, urlencoding, uuid |
| Local storage crate | lemegeton-storage (project-maintained local crate; review its bundled Rust/C++ dependencies separately) |

Source manifests:
- [Bot package.json](../../package.json)
- [Frontend package.json](../../web/frontend/package.json)
- [Dashboard Cargo.toml](../../web/backend/Cargo.toml)
- [Storage Rust manifest](../../src/utility/database/libsql/rust/storage/Cargo.toml)

## Outstanding attribution work

A complete release inventory has not yet been generated from the resolved npm and Cargo dependency graphs. Before distributing a bundled release, generate and review a licence report that includes:

- Every direct and transitive dependency actually included in the release;
- Exact package version and declared licence;
- Required copyright and licence notices;
- Any NOTICE or attribution files that must accompany distribution;
- Excluded, dual-licensed, custom-licensed or otherwise restricted packages;
- Font, icon, shader, image and other non-package assets with their own licences.

Do not infer a package's licence from its name, repository default, or a licence listed for another version. Check the resolved package metadata and upstream licence text for the version actually shipped.

The Discord sign-in symbol is a brand identifier, not a grant of Discord trademark rights. Follow [Discord's brand guidelines](https://discord.com/branding). The [Simple Icons project](https://github.com/simple-icons/simple-icons) also warns that individual brand icons may have rights or licence terms distinct from the package's own licence; do not assume every brand icon is released under the package licence.

## Review

Refresh this document when dependency manifests or lockfiles change and before each distributable release. This register is not a substitute for retaining the original third-party licence and notice files.
