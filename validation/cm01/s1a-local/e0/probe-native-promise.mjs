import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
import { QuickJSExecutor } from "./quickjs-executor.mjs";
import { createSyntheticHost } from "./synthetic-host.mjs";

const CODE = `async () => {
  const a = await codemode.read({ key: "a", delayMs: 15 });
  const b = await codemode.read({ key: "b", delayMs: 1 });
  const c = await codemode.read({ key: "c", delayMs: 5 });
  return [a.key, b.key, c.key];
}`;

export async function probeNativePromiseBridge() {
  const host = createSyntheticHost({ delays: { a: 15, b: 1, c: 5 } });
  const executor = new QuickJSExecutor({
    timeoutMs: 500,
    memoryLimitBytes: 8 * 1024 * 1024,
    onCleanup: () => host.cancelAll(),
  });
  const outcome = await executor.execute(CODE, [
    { name: "codemode", fns: { read: host.read } },
  ]);
  const starts = host.calls.filter((call) => call.phase === "start").map((call) => call.key);
  const ends = host.calls.filter((call) => call.phase === "end").map((call) => call.key);
  const pass =
    !outcome.error &&
    JSON.stringify(outcome.result) === JSON.stringify(["a", "b", "c"]) &&
    JSON.stringify(starts) === JSON.stringify(["a", "b", "c"]) &&
    JSON.stringify(ends) === JSON.stringify(["a", "b", "c"]);

  return {
    pass,
    native_bridge_supported: pass,
    asyncify_selected: false,
    result: outcome.result ?? null,
    error: outcome.error ?? null,
    starts,
    ends,
    stats: outcome.stats,
  };
}

if (import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const result = await probeNativePromiseBridge();
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  process.exit(result.pass ? 0 : 1);
}
