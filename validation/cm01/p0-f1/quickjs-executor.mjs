import { getQuickJS } from "quickjs-emscripten";

// CM-01-P0-01-F1 versioned executor.
//
// Derived from the frozen S1-A1 executor:
//   validation/cm01/s1a-local/e0/quickjs-executor.mjs
//   SHA-256 4b960124e9218ed124ed34e3b3595b648477b9dab6540c4ce1609d2efaf31313
//
// The frozen artifact is intentionally not modified. This copy adds per-host-call
// cancellation, settlement guards, and bounded cleanup for F1 validation only.

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

function snapshotStats(stats) {
  return JSON.parse(JSON.stringify(stats));
}

export class QuickJSExecutor {
  constructor({
    timeoutMs = 1000,
    memoryLimitBytes = 8 * 1024 * 1024,
    maxStackSizeBytes = 512 * 1024,
    hostCancellationGraceMs = 50,
    onCleanup = null,
    onHostEvent = null,
  } = {}) {
    this.timeoutMs = timeoutMs;
    this.memoryLimitBytes = memoryLimitBytes;
    this.maxStackSizeBytes = maxStackSizeBytes;
    this.hostCancellationGraceMs = hostCancellationGraceMs;
    this.onCleanup = onCleanup;
    this.onHostEvent = onHostEvent;
    this.lastStats = null;
  }

  stats() {
    return this.lastStats;
  }

  async execute(code, providersOrFns) {
    const startedAt = Date.now();
    const stats = {
      hostCalls: 0,
      resolvedCalls: 0,
      failedCalls: 0,
      rejectedCalls: 0,
      cancelledCalls: 0,
      cancelledRejections: 0,
      cancelledLateSuccess: 0,
      cancelledSettled: 0,
      cancelledUnsettled: 0,
      lateHostSettlements: 0,
      timedOut: false,
      interrupted: false,
      pendingAtEnd: 0,
      deferredDisposed: 0,
      drainMs: 0,
      hostCancellationGraceMs: this.hostCancellationGraceMs,
      cleanupErrors: [],
    };

    const runtime = QuickJS.newRuntime();
    const context = runtime.newContext();
    const deferreds = new Set();
    const active = new Set();
    const drainEntries = new Set();
    let providers = [];
    const deadline = Date.now() + this.timeoutMs;
    let interrupt = false;
    let timedOut = false;
    let timeoutTimer = null;
    let pumpTimer = null;
    let disposed = false;

    const emitHostEvent = (type, data = {}) => {
      if (!this.onHostEvent) return;
      try {
        this.onHostEvent({ ts: new Date().toISOString(), type, ...data });
      } catch {
        // Instrumentation must not alter execution.
      }
    };

    const pump = () => {
      if (disposed) return;
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

    const deleteActive = (entry) => {
      active.delete(entry);
    };

    const settleDeferred = (entry, text) => {
      if (entry.deferredSettled) return;
      entry.deferredSettled = true;
      deleteActive(entry);
      if (disposed || !entry.deferred.alive) return;
      const handle = context.newString(text);
      try {
        entry.deferred.resolve(handle);
      } finally {
        safeDispose(handle);
      }
      pump();
    };

    const rejectDeferred = (entry, name, message) => {
      if (entry.deferredSettled) return;
      entry.deferredSettled = true;
      deleteActive(entry);
      if (disposed || !entry.deferred.alive) return;
      const handle = context.newString(failure(name, message));
      try {
        entry.deferred.resolve(handle);
      } finally {
        safeDispose(handle);
      }
      stats.rejectedCalls += 1;
      pump();
    };

    const abortEntry = (entry, reason) => {
      if (!entry || entry.hostSettled || entry.controller.signal.aborted) return false;
      entry.cancelled = true;
      entry.abortReason = String(reason);
      entry.abortedAt = Date.now();
      stats.cancelledCalls += 1;
      drainEntries.add(entry);
      try {
        entry.controller.abort(reason);
      } catch (error) {
        stats.cleanupErrors.push(`host abort: ${error.message}`);
      }
      emitHostEvent("host_call_aborted", {
        callId: entry.callId,
        provider: entry.providerName,
        method: entry.methodName,
        abortedAt: entry.abortedAt,
        reason: entry.abortReason,
      });
      return true;
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
        } catch {
          return context.newString(failure("HostArgumentError", "host arguments were not JSON"));
        }

        const deferred = context.newPromise();
        stats.hostCalls += 1;
        const entry = {
          deferred,
          providerName,
          methodName,
          callId: stats.hostCalls,
          controller: new AbortController(),
          hostPromise: null,
          hostSettled: false,
          deferredSettled: false,
          cancelled: false,
          abortReason: null,
          abortedAt: null,
        };
        deferreds.add(entry);
        active.add(entry);

        const provider = providers.find((candidate) => candidate.name === providerName);
        const fn = provider?.fns?.[methodName];
        if (typeof fn !== "function") {
          setImmediate(() =>
            rejectDeferred(entry, "MissingHostMethod", `${providerName}.${methodName} is not available`),
          );
          return deferred.handle;
        }

        emitHostEvent("host_call_started", {
          callId: entry.callId,
          provider: providerName,
          method: methodName,
        });

        entry.hostPromise = Promise.resolve()
          .then(() => {
            return fn(args, {
              signal: entry.controller.signal,
              callId: entry.callId,
            });
          })
          .then((value) => {
            entry.hostSettled = true;
            if (entry.cancelled) {
              stats.cancelledLateSuccess += 1;
              emitHostEvent("host_call_settled_after_abort", {
                callId: entry.callId,
                provider: providerName,
                method: methodName,
                outcome: "fulfilled",
                afterAbortMs: entry.abortedAt ? Date.now() - entry.abortedAt : null,
              });
              return;
            }
            stats.resolvedCalls += 1;
            settleDeferred(entry, envelope(value));
            emitHostEvent("host_call_settled", {
              callId: entry.callId,
              provider: providerName,
              method: methodName,
              outcome: "fulfilled",
            });
          })
          .catch((error) => {
            entry.hostSettled = true;
            if (entry.cancelled) {
              stats.cancelledRejections += 1;
              emitHostEvent("host_call_settled_after_abort", {
                callId: entry.callId,
                provider: providerName,
                method: methodName,
                outcome: "rejected",
                errorName: error?.name || "HostError",
                errorMessage: error?.message || String(error),
                afterAbortMs: entry.abortedAt ? Date.now() - entry.abortedAt : null,
              });
              settleDeferred(
                entry,
                failure(error?.name || "HostError", error?.message || String(error)),
              );
              return;
            }
            stats.failedCalls += 1;
            settleDeferred(
              entry,
              failure(error?.name || "HostError", error?.message || String(error)),
            );
            emitHostEvent("host_call_settled", {
              callId: entry.callId,
              provider: providerName,
              method: methodName,
              outcome: "rejected",
              errorName: error?.name || "HostError",
              errorMessage: error?.message || String(error),
            });
          });

        return deferred.handle;
      },
    );
    context.setProp(context.global, "__hostCall", hostCall);
    hostCall.dispose();

    const drainHostCalls = async () => {
      if (drainEntries.size === 0) return;
      const entries = [...drainEntries];
      drainEntries.clear();
      const promises = entries.map((entry) => entry.hostPromise).filter(Boolean);
      const drainStarted = Date.now();
      if (promises.length > 0) {
        let timer = null;
        const timeout = new Promise((resolveTimeout) => {
          timer = setTimeout(() => resolveTimeout("timeout"), this.hostCancellationGraceMs);
        });
        const settled = Promise.allSettled(promises).then(() => "settled");
        await Promise.race([settled, timeout]);
        if (timer) clearTimeout(timer);
      }
      stats.drainMs = Date.now() - drainStarted;
      for (const entry of entries) {
        if (entry.hostSettled) {
          stats.cancelledSettled += 1;
        } else {
          stats.cancelledUnsettled += 1;
          emitHostEvent("host_call_unsettled_after_grace", {
            callId: entry.callId,
            provider: entry.providerName,
            method: entry.methodName,
            graceMs: this.hostCancellationGraceMs,
          });
        }
      }
    };

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
        const preludeResult = context.evalCode(prelude, "f1-prelude.js");
        if (preludeResult.error) {
          const info = errorInfo(context, preludeResult.error);
          preludeResult.error.dispose();
          return { error: `prelude failed: ${info.name}: ${info.message}`, stats: snapshotStats(stats) };
        }
        safeDispose(preludeResult.value);
      }

      const fnResult = context.evalCode(`(${code})`, "f1-fixed.js");
      if (fnResult.error) {
        const info = errorInfo(context, fnResult.error);
        fnResult.error.dispose();
        return { error: `evaluation failed: ${info.name}: ${info.message}`, stats: snapshotStats(stats) };
      }

      const fnHandle = fnResult.value;
      const callResult = context.callFunction(fnHandle, context.undefined);
      safeDispose(fnHandle);
      if (callResult.error) {
        const info = errorInfo(context, callResult.error);
        callResult.error.dispose();
        return { error: `invocation failed: ${info.name}: ${info.message}`, stats: snapshotStats(stats) };
      }

      const promiseHandle = callResult.value;
      pumpTimer = setInterval(pump, 1);
      const timeoutPromise = new Promise((resolve) => {
        timeoutTimer = setTimeout(() => {
          timedOut = true;
          interrupt = true;
          stats.timedOut = true;
          const reason = new Error(`Code Mode execution exceeded ${this.timeoutMs}ms`);
          for (const entry of [...active]) {
            abortEntry(entry, reason);
          }
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
        return { error: outcome.error || `execution exceeded ${this.timeoutMs}ms`, stats: snapshotStats(stats) };
      }
      if (!outcome.ok) return { error: outcome.error, stats: snapshotStats(stats) };
      return { result: outcome.value, stats: snapshotStats(stats) };
    } catch (error) {
      return { error: error?.message || String(error), stats: snapshotStats(stats) };
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
        abortEntry(entry, new Error("execution cleanup cancelled the pending host call"));
      }
      for (const entry of [...active]) {
        rejectDeferred(entry, "CancelledError", "execution cleanup cancelled the pending host call");
      }
      await drainHostCalls();
      stats.pendingAtEnd = active.size;
      disposed = true;
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
      stats.durationMs = Date.now() - startedAt;
      this.lastStats = snapshotStats(stats);
    }
  }
}

