#!/usr/bin/env node
/**
 * Inject the current git short SHA + UTC date into
 * `frontend/public/methodology.html` so the public-facing methodology
 * companion's "Internal revision marker" stays accurate without manual
 * edits.
 *
 * Wiring:
 *   * `npm run dev`   → triggers `predev` → runs this script.
 *   * `npm run build` → triggers `prebuild` → runs this script.
 *   * `npm run sync:methodology-version` → standalone invocation.
 *
 * The script is idempotent and self-locating:
 *   1. It walks up from its own directory until it finds the git
 *      working tree's `.git` (or stops at the filesystem root).
 *   2. It calls `git rev-parse --short HEAD` to get the current SHA.
 *      If the working tree is dirty, the SHA is suffixed with "-dirty"
 *      so a reader can spot non-committed methodology rendering.
 *   3. It uses today's UTC date as the methodology version date.
 *   4. It rewrites the two `<code data-methodology-version-*>` slots
 *      in `frontend/public/methodology.html` in place.
 *
 * If git is unavailable (e.g. the project was extracted from a tarball)
 * the script falls back to leaving the existing committed values alone
 * so the page is never broken by a missing tool.
 */

import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Minimal dotenv-style loader. Reads `.env.local` first, then `.env`
 * (the more-specific local override wins), parsing simple
 * `KEY=VALUE` lines. Lines beginning with `#` or empty lines are
 * skipped. Surrounding single or double quotes around the value are
 * stripped. An existing `process.env[KEY]` is never overwritten — an
 * inline `KEY=value npm run build` still trumps a file-set value.
 *
 * No `dotenv` dependency is added; this script stays self-contained.
 */
function loadEnvFile(path) {
  if (!existsSync(path)) return;
  const content = readFileSync(path, "utf8");
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (!match) continue;
    const key = match[1];
    let value = match[2];
    // Strip a single matching pair of surrounding quotes.
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (process.env[key] === undefined) {
      process.env[key] = value;
    }
  }
}

const frontendDir = join(__dirname, "..");
loadEnvFile(join(frontendDir, ".env.local"));
loadEnvFile(join(frontendDir, ".env"));

function findGitRoot(start) {
  let current = start;
  while (current && current !== "/" && current.length > 1) {
    if (existsSync(join(current, ".git"))) return current;
    current = dirname(current);
  }
  return null;
}

const gitRoot = findGitRoot(__dirname);
const targetHtmlPath = join(__dirname, "..", "public", "methodology.html");

if (!existsSync(targetHtmlPath)) {
  console.error(`sync-methodology-version: target not found: ${targetHtmlPath}`);
  process.exit(1);
}

const currentDate = new Date().toISOString().slice(0, 10);
let shortSha;
try {
  if (!gitRoot) {
    throw new Error("git working tree not found from " + __dirname);
  }
  shortSha = execFileSync("git", ["rev-parse", "--short", "HEAD"], {
    cwd: gitRoot,
    encoding: "utf8",
  }).trim();
  let dirty = false;
  try {
    const status = execFileSync(
      "git",
      ["status", "--porcelain", "--", "."],
      { cwd: gitRoot, encoding: "utf8" }
    );
    dirty = status.trim().length > 0;
  } catch (statusError) {
    // ignore status errors; we'll still inject the SHA
  }
  if (dirty) {
    shortSha = `${shortSha}-dirty`;
  }
} catch (gitError) {
  console.warn(
    `sync-methodology-version: leaving existing values in place (${gitError.message})`
  );
  process.exit(0);
}

const html = readFileSync(targetHtmlPath, "utf8");

// The placeholder regexes accept ANY inner content (including a previously-
// injected <a> wrapper) so the script is fully idempotent: a later run
// without `METHODOLOGY_REPO_URL` will strip the link, a later run with a
// different URL will re-wrap, and a re-run with the same URL is a no-op.
const dateRegex =
  /(<code\s+data-methodology-version-date[^>]*>)([\s\S]*?)(<\/code>)/;
const shaRegex =
  /(<code\s+data-methodology-version-sha[^>]*>)([\s\S]*?)(<\/code>)/;

if (!dateRegex.test(html) || !shaRegex.test(html)) {
  console.warn(
    "sync-methodology-version: placeholders not found in methodology.html; " +
      "leaving the file unchanged."
  );
  process.exit(0);
}

// Optional: if `METHODOLOGY_REPO_URL` is set in the environment, wrap the
// short SHA in an `<a href="${repoUrl}/commit/${sha}">` so a public reader
// can click straight through to the underlying commit. The anchor lives
// INSIDE the existing `<code data-methodology-version-sha>` tag so the
// CSS hook still applies. A trailing "-dirty" is stripped before building
// the URL (a dirty working tree has no remote commit) but stays in the
// link text so the reader can still see the warning.
const repoUrlRaw = (process.env.METHODOLOGY_REPO_URL || "").trim();
const repoUrl = repoUrlRaw.replace(/\/+$/, "");
let shaInner = shortSha;
if (repoUrl) {
  const cleanShortSha = shortSha.replace(/-dirty$/, "");
  shaInner =
    `<a href="${repoUrl}/commit/${cleanShortSha}" rel="noreferrer" ` +
    `target="_blank">${shortSha}</a>`;
}

const updated = html
  .replace(dateRegex, `$1${currentDate}$3`)
  .replace(shaRegex, `$1${shaInner}$3`);

if (updated === html) {
  console.log(
    `sync-methodology-version: methodology.html already up to date ` +
      `(${currentDate} / ${shortSha}` +
      (repoUrl ? ` linked to ${repoUrl}` : "") +
      `).`
  );
} else {
  writeFileSync(targetHtmlPath, updated, "utf8");
  console.log(
    `sync-methodology-version: methodology.html stamped with ` +
      `${currentDate} / ${shortSha}` +
      (repoUrl ? ` (linked to ${repoUrl})` : "") +
      `.`
  );
}
