import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

export const S0_SHA = "9eb4057a290795883076ab05bf11c92038c6ca13";
export const DEFAULT_BASE_SHA = "942de7b121994647e99e9b862b44cda784c0ae84";

export const M4_PATTERNS = [
  /^benchmarks\/adr034_m4\//,
  /^tests\/adr034_m4_/,
  /^tests\/test_adr034_m4_/,
  /^scripts\/run_test_battery\.py$/,
  /^docs\/validation\/adr-034-m4-/,
  /^docs\/plans\/.*adr-034-m4/,
];

function git(args, cwd) {
  return execFileSync("git", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

function lines(text) {
  return text ? text.split(/\r?\n/).filter(Boolean) : [];
}

export function checkM4Protection({ cwd = process.cwd(), baseSha = DEFAULT_BASE_SHA } = {}) {
  const root = git(["rev-parse", "--show-toplevel"], cwd);
  const head = git(["rev-parse", "HEAD"], root);

  const groups = {
    committed_vs_base: lines(git(["diff", "--name-only", `${baseSha}...HEAD`], root)),
    staged: lines(git(["diff", "--cached", "--name-only"], root)),
    unstaged: lines(git(["diff", "--name-only"], root)),
    untracked: lines(git(["ls-files", "--others", "--exclude-standard"], root)),
  };

  const violations = [];
  for (const [source, paths] of Object.entries(groups)) {
    for (const path of paths) {
      if (M4_PATTERNS.some((pattern) => pattern.test(path))) {
        violations.push({ source, path });
      }
    }
  }

  return {
    schema: "mneme.cm01.s1a1.e0.m4-guard/v1",
    s0_sha: S0_SHA,
    base_sha: baseSha,
    head_sha: head,
    base_to_head_is_clean: head === baseSha,
    inherited_m4_diff: git(["diff", "--stat", `${S0_SHA}..${baseSha}`], root),
    groups,
    protected_patterns: M4_PATTERNS.map((pattern) => pattern.source),
    violations,
    pass: violations.length === 0,
  };
}

if (import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const result = checkM4Protection({
    cwd: process.cwd(),
    baseSha: process.env.CM01_BASE_SHA || DEFAULT_BASE_SHA,
  });
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  process.exit(result.pass ? 0 : 1);
}
