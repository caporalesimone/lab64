# Playwright (with Chromium) — NOT included

**What it is**: Node library that drives Chromium. The `headless/c64d.js` daemon uses it only internally to open the emulator page. It is not included in the package: install it with `npm i -g playwright && npx playwright install chromium` (in Docker: `playwright@1.63.0`).

**Origin**: https://github.com/microsoft/playwright · https://playwright.dev
**License**: Apache-2.0 (general knowledge, not verified here). Chromium, downloaded by Playwright, has its own licenses (BSD and third-party components): https://chromium.googlesource.com/chromium/src/+/main/LICENSE
