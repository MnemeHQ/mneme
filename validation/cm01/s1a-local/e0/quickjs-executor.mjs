import { getQuickJS } from "quickjs-emscripten";

const QuickJS = await getQuickJS();

function errorInfo(context, handle) {
  try {
    const name = context.getProp(handle, "name");
    const message = context.getProp(handle, "message");
    const value = {
      name: name.alive ? context.getString(name) : "Error",
      message: message.alive ? context.getString(message) : context.dump(handle),
    };
    if (name.alive) name.dispose();
    if (message.alive) message.dispose();
    return value;
  } catch {
    return { name: "Error", message: String(context.dump(handle)) };
  }
}

function safeDispose(handle) {
  try {
    if (handle?.alive) handle.dispose();
  } catch {
    // Cleanup must not mask the execution result.
  }
}

function envelope(value) {
  return JSON.stringify({ ok: true, value: value === undefined ? null : value });
}

function failure(name, message) {
  return JSON.stringify({ ok: false, error: { name, message } });
}

export class QuickJSExecutor {
  constructor({
    timeoutMs = 1000,
    memoryLimitBytes = 8 * 1024 * 1024,
    maxStackSizeBytes = 512 * 1024,
    onCleanup = null,
  } = {}) {
    this.timeoutMs = timeoutMs;
    this.memoryLimitBytes = memoryLimitBytes;
    this.maxStackSizeBytes = maxStackSizeBytes;
    this.onCleanup = onCleanup;
    this.lastStats = null;
  }

  stats() {
    return this.lastStats;
  }

  async execute(code, providersOrFns) {
    const stats = {
      hostCalls: 0,
      resolvedCalls: 0,
      failedCalls: 0,
      rejectedCalls: 0,
      timedOut: false,
      interrupted: false,
      pendingAtEnd: 0,
      deferredDisposed: 0,
      cleanupErrors: [],
    };

    const runtime = QuickJS.newRuntime();
    const context = runtime.newContext();
    const deferreds = new Set();
    const active = new Set();
    let providers = [];
    const deadline = Date.now() + this.timeoutMs;
    let interrupt = false;
    let timedOut = false;
    let timeoutTimer = null;
    let pumpTimer = null;

    const pump = () => {
      try {
        const result = runtime.executePendingJobs();
        if (result?.error) {
          const info = errorInfo(context, result.error);
          result.error.dispose();
          stats.cleanupErrors.push(`pending-job error: ${info.name}: ${info.message}`);
        }
      } catch (error) {
        stats.cleanupErrors.push(`pending-job exception: ${error.message}`);
      }
    };

    const settleDeferred = (entry, text) => {
      if (!entry.deferred.alive) return;
      const handle = context.newString(text);
      try {
        entry.deferred.resolve(handle);
      } finally {
        safeDispose(handle);
      }
      active.delete(entry);
      pump();
    };

    const rejectDeferred = (entry, name, message) => {
      if (!entry.deferred.alive) return;
      const handle = context.newString(failure(name, message));
      try {
        entry.deferred.resolve(handle);
      } finally {
        safeDispose(handle);
      }
      active.delete(entry);
      stats.rejectedCalls += 1;
      pump();
    };

    const hostCall = context.newFunction(
      "__hostCall",
      (providerHandle, methodHandle, argsHandle) => {
                const providerName = context.getString(providerHandle);
        const methodName = context.getString(methodHandle);
                let args = {};
        try {
          const rawArgs = context.getString(argsHandle);
                    args = JSON.parse(rawArgs || "{}");
        } catch (error) {
                    return context.newString(failure("HostArgumentError", "host arguments were not JSON"));
        }

                const deferred = context.newPromise();
                const entry = { deferred, providerName, methodName };
                deferreds.add(entry);
                active.add(entry);
                stats.hostCalls += 1;

                const provider = providers.find((candidate) => candidate.name === providerName);
        const fn = provider?.fns?.[methodName];
        if (typeof fn !== "function") {
                    setImmediate(() => rejectDeferred(entry, "MissingHostMethod", `${providerName}.${methodName} is not available`));
          return deferred.handle;
        }

                Promise.resolve()
          .then(() => {
                        return fn(args);
          })
          .then((value) => {
            stats.resolvedCalls += 1;
            settleDeferred(entry, envelope(value));
          })
          .catch((error) => {
            stats.failedCalls += 1;
            settleDeferred(
              entry,
              failure(error?.name || "HostError", error?.message || String(error)),
            );
          });

        return deferred.handle;
      },
    );
    context.setProp(context.global, "__hostCall", hostCall);
    hostCall.dispose();

    try {
      runtime.setMemoryLimit(this.memoryLimitBytes);
      runtime.setMaxStackSize(this.maxStackSizeBytes);
      runtime.setInterruptHandler(() => interrupt || Date.now() > deadline);

      providers = Array.isArray(providersOrFns)
        ? providersOrFns
        : [{ name: "codemode", fns: providersOrFns }];

      const prelude = providers
        .flatMap((provider) => {
          const namespace = provider.name || "codemode";
          return Object.keys(provider.fns || {}).map(
            (method) => `
              globalThis.${namespace} = globalThis.${namespace} || {};
              ${namespace}.${method} = async (args) => {
                const raw = await __hostCall(${JSON.stringify(namespace)}, ${JSON.stringify(method)}, JSON.stringify(args ?? {}));
                const parsed = JSON.parse(raw);
                if (!parsed.ok) {
                  const error = new Error(parsed.error.message);
                  error.name = parsed.error.name || "HostError";
                  throw error;
                }
                return parsed.value;
              };
            `,
          );
        })
        .join("\n");

      if (prelude) {
        const preludeResult = context.evalCode(prelude, "e0-prelude.js");
        if (preludeResult.error) {
          const info = errorInfo(context, preludeResult.error);
          preludeResult.error.dispose();
          return { error: `prelude failed: ${info.name}: ${info.message}`, stats };
        }
        safeDispose(preludeResult.value);
      }

      const fnResult = context.evalCode(`(${code})`, "e0-fixed.js");
      if (fnResult.error) {
        const info = errorInfo(context, fnResult.error);
        fnResult.error.dispose();
        return { error: `evaluation failed: ${info.name}: ${info.message}`, stats };
      }

      const fnHandle = fnResult.value;
      const callResult = context.callFunction(fnHandle, context.undefined);
      safeDispose(fnHandle);
      if (callResult.error) {
        const info = errorInfo(context, callResult.error);
        callResult.error.dispose();
        return { error: `invocation failed: ${info.name}: ${info.message}`, stats };
      }

      const promiseHandle = callResult.value;
      // Some async functions resolve without any host call. Keep QuickJS's
      // job queue moving independently of host-call completion.
      pumpTimer = setInterval(pump, 1);
      const timeoutPromise = new Promise((resolve) => {
        timeoutTimer = setTimeout(() => {
          timedOut = true;
          interrupt = true;
          stats.timedOut = true;
          for (const entry of [...active]) {
            rejectDeferred(entry, "TimeoutError", `execution exceeded ${this.timeoutMs}ms`);
          }
          resolve({ ok: false, error: `execution exceeded ${this.timeoutMs}ms` });
        }, this.timeoutMs);
      });

      const settledPromise = context
        .resolvePromise(promiseHandle)
        .then((result) => {
          if (result.error) {
            const info = errorInfo(context, result.error);
            result.error.dispose();
            return { ok: false, error: `${info.name}: ${info.message}` };
          }
          const value = context.dump(result.value);
          safeDispose(result.value);
          return { ok: true, value };
        })
        .catch((error) => ({ ok: false, error: error?.message || String(error) }));

      const outcome = await Promise.race([settledPromise, timeoutPromise]);
      if (timeoutTimer) clearTimeout(timeoutTimer);
      if (pumpTimer) {
        clearInterval(pumpTimer);
        pumpTimer = null;
      }
      safeDispose(promiseHandle);

      if (timedOut) {
        stats.interrupted = true;
        return { error: outcome.error || `execution exceeded ${this.timeoutMs}ms`, stats };
      }
      if (!outcome.ok) return { error: outcome.error, stats };
      return { result: outcome.value, stats };
    } catch (error) {
      return { error: error?.message || String(error), stats };
    } finally {
      interrupt = true;
      if (pumpTimer) {
        clearInterval(pumpTimer);
        pumpTimer = null;
      }
      if (timeoutTimer) {
        clearTimeout(timeoutTimer);
        timeoutTimer = null;
      }
      for (const entry of [...active]) {
        rejectDeferred(entry, "CancelledError", "execution cleanup cancelled the pending host call");
      }
      stats.pendingAtEnd = active.size;
      for (const entry of deferreds) {
        try {
          entry.deferred.dispose();
          stats.deferredDisposed += 1;
        } catch (error) {
          stats.cleanupErrors.push(`deferred dispose: ${error.message}`);
        }
      }
      if (this.onCleanup) {
        try {
          this.onCleanup();
        } catch (error) {
          stats.cleanupErrors.push(`onCleanup: ${error.message}`);
        }
      }
      try {
        context.dispose();
      } catch (error) {
        stats.cleanupErrors.push(`context dispose: ${error.message}`);
      }
      try {
        runtime.dispose();
      } catch (error) {
        stats.cleanupErrors.push(`runtime dispose: ${error.message}`);
      }
      this.lastStats = stats;
    }
  }
}
