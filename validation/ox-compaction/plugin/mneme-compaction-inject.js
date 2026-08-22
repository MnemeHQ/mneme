// Experimental treatment-only compaction adapter (validation/ox-compaction).
// Loads ONLY from the experiment's isolated XDG_CONFIG_HOME. Never installed globally.
//
// Behavior: on the installed OpenCode compaction lifecycle hook
// (`experimental.session.compacting`), appends the FROZEN Mneme guidance text
// (verbatim, hashed) as an additional context string to the compaction prompt.
// No retrieval, no scoring, no formatting changes - the text is byte-identical
// to validation/ox-compaction/frozen/guidance-frozen.txt.
//
// Structured logging proves: hook executed, guidance hash supplied, session ID,
// arm/repetition/run identity, timestamp.

import { createHash } from "crypto";
import { appendFileSync, readFileSync } from "fs";

const LOG = process.env.MNEME_TREATMENT_LOG;
const GUIDANCE_FILE = process.env.MNEME_TREATMENT_GUIDANCE_FILE;
const META_RAW = process.env.MNEME_TREATMENT_META || "{}";

function meta() {
  try {
    return JSON.parse(META_RAW);
  } catch {
    return {};
  }
}

function sha256(text) {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

function log(event) {
  if (!LOG) return;
  try {
    appendFileSync(LOG, `${JSON.stringify({ ts: new Date().toISOString(), ...event })}\n`);
  } catch {}
}

let guidanceText = null;
let guidanceHash = null;

function loadGuidance() {
  if (guidanceText !== null) return guidanceText;
  const raw = readFileSync(GUIDANCE_FILE, "utf8");
  // Normalize CRLF -> LF so the hash matches the frozen LF-normalized file.
  guidanceText = raw.replace(/\r\n/g, "\n");
  guidanceHash = sha256(guidanceText);
  return guidanceText;
}

export const MnemeCompactionInject = async () => {
  const m = meta();
  log({
    kind: "plugin-init",
    arm: m.arm,
    repetition: m.repetition,
    runId: m.runId,
    guidanceFile: GUIDANCE_FILE,
  });
  return {
    "experimental.session.compacting": async (input, output) => {
      const text = loadGuidance();
      const payload =
        "[Mneme architectural guidance - governing decisions carried across this compaction]\n" +
        text;
      output.context.push(payload);
      log({
        kind: "inject",
        arm: m.arm,
        repetition: m.repetition,
        runId: m.runId,
        sessionID: input.sessionID,
        guidanceSha256: sha256(text),
        injectedChars: payload.length,
      });
    },
    event: async ({ event }) => {
      if (event && String(event.type || "").includes("compact")) {
        log({ kind: "event", type: event.type, runId: m.runId, arm: m.arm });
      }
    },
  };
};
