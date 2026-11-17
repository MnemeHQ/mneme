export function projectGet(result) {
  const record = result?.canonical_decision;
  if (!record) throw new Error("decision.get did not return canonical_decision");
  return {
    decision_id: record.decision_id,
    version: record.version,
    version_id: record.version_id,
    content_digest: record.content_digest,
    lifecycle_status: record.lifecycle_status,
    context_scope: record.context_scope,
    derived_rule_ids: record.derived_rule_ids,
  };
}

export function projectTrace(result) {
  const record = result?.canonical_record;
  if (!record) throw new Error("decision.trace did not return canonical_record");
  return {
    canonical_decision_id: result.canonical_decision_id,
    version: record.version,
    version_id: record.version_id,
    content_digest: record.content_digest,
    derived_rule_ids: (result.derived_rules ?? []).map((rule) => rule.rule_id),
    declared_test_evidence: result.declared_test_evidence ?? [],
  };
}

async function call(mcp, name, args) {
  const result = await mcp.callTool({ name, arguments: args });
  if (result.isError) {
    throw new Error(`MCP ${name} returned isError`);
  }
  return result.structuredContent ?? result.toolResult;
}

export async function runDirectTask(task, mcp) {
  switch (task.id) {
    case "T1": {
      return projectGet(await call(mcp, "decision.get", task.params));
    }
    case "T2": {
      const result = await call(mcp, "decision.search", task.params);
      const ids = result.canonical_decisions.map((row) => row.decision_id).sort();
      return { canonical_ids: ids, count: ids.length };
    }
    case "T3": {
      const result = await call(mcp, "decision.applicable_to", task.params);
      const ids = result.canonical_scope_matches.map((row) => row.decision_id).sort();
      return { canonical_ids: ids, count: ids.length };
    }
    case "T4": {
      return projectTrace(await call(mcp, "decision.trace", task.params));
    }
    case "T5": {
      const search = await call(mcp, "decision.search", task.params);
      const ids = search.canonical_decisions.map((row) => row.decision_id).sort();
      return projectGet(await call(mcp, "decision.get", { record_id: ids[0] }));
    }
    case "T6": {
      const search = await call(mcp, "decision.search", task.params);
      const ids = search.canonical_decisions.map((row) => row.decision_id).sort();
      return projectTrace(await call(mcp, "decision.trace", { record_id: ids[0] }));
    }
    case "T7": {
      const applicable = await call(mcp, "decision.applicable_to", task.params);
      const ids = applicable.canonical_scope_matches
        .filter((row) => row.lifecycle_status === "active")
        .map((row) => row.decision_id)
        .sort();
      const selected = ids[0];
      const get = projectGet(await call(mcp, "decision.get", { record_id: selected }));
      const trace = projectTrace(await call(mcp, "decision.trace", { record_id: selected }));
      return { selected_id: selected, get, trace };
    }
    case "T8": {
      const search = await call(mcp, "decision.search", task.params);
      const ids = search.canonical_decisions
        .filter((row) => Array.isArray(row.derived_rule_ids) && row.derived_rule_ids.length > 0)
        .map((row) => row.decision_id)
        .sort()
        .slice(0, 2);
      const items = [];
      for (const decision_id of ids) {
        const projection = projectGet(await call(mcp, "decision.get", { record_id: decision_id }));
        items.push({
          decision_id: projection.decision_id,
          version: projection.version,
          content_digest: projection.content_digest,
          derived_rule_ids: projection.derived_rule_ids,
        });
      }
      return { items };
    }
    default:
      throw new Error(`unknown task ${task.id}`);
  }
}

const PRELUDE = `
  const projectGet = (r) => {
    const c = r.canonical_decision;
    return {
      decision_id: c.decision_id,
      version: c.version,
      version_id: c.version_id,
      content_digest: c.content_digest,
      lifecycle_status: c.lifecycle_status,
      context_scope: c.context_scope,
      derived_rule_ids: c.derived_rule_ids
    };
  };
  const projectTrace = (t) => {
    const c = t.canonical_record;
    return {
      canonical_decision_id: t.canonical_decision_id,
      version: c.version,
      version_id: c.version_id,
      content_digest: c.content_digest,
      derived_rule_ids: (t.derived_rules || []).map((rule) => rule.rule_id),
      declared_test_evidence: t.declared_test_evidence || []
    };
  };
`;

function q(value) {
  return JSON.stringify(value);
}

export function codeForTask(task) {
  const params = q(task.params);
  let body;
  switch (task.id) {
    case "T1":
      body = `return projectGet(await codemode.decision_get(${params}));`;
      break;
    case "T2":
      body = `const r = await codemode.decision_search(${params}); const ids = r.canonical_decisions.map((d) => d.decision_id).sort(); return { canonical_ids: ids, count: ids.length };`;
      break;
    case "T3":
      body = `const r = await codemode.decision_applicable_to(${params}); const ids = r.canonical_scope_matches.map((d) => d.decision_id).sort(); return { canonical_ids: ids, count: ids.length };`;
      break;
    case "T4":
      body = `return projectTrace(await codemode.decision_trace(${params}));`;
      break;
    case "T5":
      body = `const s = await codemode.decision_search(${params}); const ids = s.canonical_decisions.map((d) => d.decision_id).sort(); return projectGet(await codemode.decision_get({ record_id: ids[0] }));`;
      break;
    case "T6":
      body = `const s = await codemode.decision_search(${params}); const ids = s.canonical_decisions.map((d) => d.decision_id).sort(); return projectTrace(await codemode.decision_trace({ record_id: ids[0] }));`;
      break;
    case "T7":
      body = `const a = await codemode.decision_applicable_to(${params}); const ids = a.canonical_scope_matches.filter((d) => d.lifecycle_status === "active").map((d) => d.decision_id).sort(); const selected = ids[0]; const get = projectGet(await codemode.decision_get({ record_id: selected })); const trace = projectTrace(await codemode.decision_trace({ record_id: selected })); return { selected_id: selected, get, trace };`;
      break;
    case "T8":
      body = `const s = await codemode.decision_search(${params}); const ids = s.canonical_decisions.filter((d) => Array.isArray(d.derived_rule_ids) && d.derived_rule_ids.length > 0).map((d) => d.decision_id).sort().slice(0, 2); const items = []; for (const decision_id of ids) { const p = projectGet(await codemode.decision_get({ record_id: decision_id })); items.push({ decision_id: p.decision_id, version: p.version, content_digest: p.content_digest, derived_rule_ids: p.derived_rule_ids }); } return { items };`;
      break;
    default:
      throw new Error(`unknown task ${task.id}`);
  }
  return `async () => {${PRELUDE}${body}}`;
}
