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

const dateRegex =
  /(<code\s+data-methodology-version-date[^>]*>)([^<]*)(<\/code>)/;
const shaRegex =
  /(<code\s+data-methodology-version-sha[^>]*>)([^<]*)(<\/code>)/;

if (!dateRegex.test(html) || !shaRegex.test(html)) {
  console.warn(
    "sync-methodology-version: placeholders not found in methodology.html; " +
      "leaving the file unchanged."
  );
  process.exit(0);
}

const updated = html
  .replace(dateRegex, `$1${currentDate}$3`)
  .replace(shaRegex, `$1${shortSha}$3`);

if (updated === html) {
  console.log(
    `sync-methodology-version: methodology.html already up to date ` +
      `(${currentDate} / ${shortSha}).`
  );
} else {
  writeFileSync(targetHtmlPath, updated, "utf8");
  console.log(
    `sync-methodology-version: methodology.html stamped with ` +
      `${currentDate} / ${shortSha}.`
  );
}
