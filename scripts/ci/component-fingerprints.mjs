import { createHash } from "node:crypto";
import { appendFile, readFile, readdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const COMPONENTS = ["backend", "mcp", "web"];

function normalizeRelative(value) {
  return value.split(path.sep).join("/").replace(/^\.\//, "");
}

function startsWithIgnoreCase(value, prefix) {
  return value.toLowerCase().startsWith(prefix.toLowerCase());
}

function equalsIgnoreCase(value, expected) {
  return value.localeCompare(expected, undefined, { sensitivity: "accent" }) === 0 || value.toLowerCase() === expected.toLowerCase();
}

export function isComponentPathExcluded(relativePath, componentConfig) {
  const normalized = normalizeRelative(relativePath);
  const lower = normalized.toLowerCase();

  for (const raw of componentConfig.exclude_prefixes ?? []) {
    const prefix = String(raw);
    if (prefix && startsWithIgnoreCase(normalized, prefix)) return true;
  }
  for (const raw of componentConfig.exclude_files ?? []) {
    const file = String(raw);
    if (file && equalsIgnoreCase(normalized, file)) return true;
  }
  for (const raw of componentConfig.exclude_suffixes ?? []) {
    const suffix = String(raw).toLowerCase();
    if (suffix && lower.endsWith(suffix)) return true;
  }
  const leaf = path.posix.basename(normalized).toLowerCase();
  for (const raw of componentConfig.exclude_name_prefixes ?? []) {
    const prefix = String(raw).toLowerCase();
    if (prefix && leaf.startsWith(prefix)) return true;
  }
  return false;
}

async function walkFiles(root) {
  const output = [];
  const visit = async (directory) => {
    const entries = await readdir(directory, { withFileTypes: true });
    entries.sort((a, b) => a.name.localeCompare(b.name, "en", { sensitivity: "variant" }));
    for (const entry of entries) {
      const full = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        await visit(full);
      } else if (entry.isFile()) {
        output.push(full);
      }
    }
  };
  await visit(root);
  return output;
}

async function sha256File(filePath) {
  const buffer = await readFile(filePath);
  return createHash("sha256").update(buffer).digest("hex");
}

export async function computeComponentFingerprint(repoRoot, componentConfig) {
  const resolvedRoot = path.resolve(repoRoot);
  const configuredRoot = String(componentConfig.root ?? "");
  const componentRoot = configuredRoot === "." ? resolvedRoot : path.resolve(resolvedRoot, configuredRoot);
  const rootStats = await stat(componentRoot);
  if (!rootStats.isDirectory()) throw new Error(`Component context root is not a directory: ${configuredRoot}`);

  const records = [];
  for (const fullPath of await walkFiles(componentRoot)) {
    const relative = normalizeRelative(path.relative(resolvedRoot, fullPath));
    if (isComponentPathExcluded(relative, componentConfig)) continue;
    records.push([relative, await sha256File(fullPath)]);
  }
  records.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  const manifest = records.map(([relative, digest]) => `${relative}\t${digest}\n`).join("");
  return createHash("sha256").update(manifest, "utf8").digest("hex");
}

export async function computeComponentFingerprints(repoRoot) {
  const resolvedRoot = path.resolve(repoRoot);
  const policyPath = path.join(resolvedRoot, "release", "component-contexts.json");
  const policy = JSON.parse(await readFile(policyPath, "utf8"));
  const result = {};
  for (const component of COMPONENTS) {
    const config = policy.components?.[component];
    if (!config) throw new Error(`Component context policy does not define '${component}'.`);
    result[component] = await computeComponentFingerprint(resolvedRoot, config);
  }
  return result;
}

function parseArgs(argv) {
  const options = { repoRoot: process.cwd(), githubOutput: "" };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--repo-root") {
      options.repoRoot = argv[++index];
    } else if (value === "--github-output") {
      options.githubOutput = argv[++index];
    } else {
      throw new Error(`Unknown argument: ${value}`);
    }
  }
  return options;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const fingerprints = await computeComponentFingerprints(options.repoRoot);
  const lines = COMPONENTS.map((component) => `${component}_fingerprint=${fingerprints[component]}`);
  if (options.githubOutput) {
    await appendFile(options.githubOutput, `${lines.join("\n")}\n`, "utf8");
  } else {
    process.stdout.write(`${lines.join("\n")}\n`);
  }
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : "";
if (invokedPath && invokedPath === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
