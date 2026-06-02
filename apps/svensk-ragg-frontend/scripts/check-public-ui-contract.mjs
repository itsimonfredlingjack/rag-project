import fs from "node:fs";
import path from "node:path";

const root = path.resolve(new URL("..", import.meta.url).pathname);

const read = (relativePath) =>
  fs.readFileSync(path.join(root, relativePath), "utf8");

const checks = [
  {
    name: "public banner states the Riksdagen-only demo scope",
    file: "src/App.tsx",
    includes: [
      "Svensk Ragg - demo över Riksdagens öppna data.",
      "Svar genereras lokalt och ska alltid kontrolleras mot källorna.",
    ],
    excludes: [
      "Svensk " + "RAG",
      "Konstitu" + "tionell AI",
      "Constitu" + "tional AI",
    ],
  },
  {
    name: "answer card exposes public answer contract fields",
    file: "src/components/ui/ChatMessage.tsx",
    includes: [
      "dataSourceAttribution",
      "refusalReason",
      "latencyMs",
      "sourceIds",
      "refusal_reason",
    ],
  },
  {
    name: "source inspector renders public provenance metadata",
    file: "src/components/ui/ChatMessage.tsx",
    includes: [
      "Visa hämtade källor",
      "document_id",
      "source_scope",
      "retriever_source",
      "source.url",
    ],
  },
  {
    name: "query result types retain public metadata",
    file: "src/types/queryResult.ts",
    includes: [
      "document_id",
      "source_scope",
      "retriever_source",
      "dataSourceAttribution",
      "refusalReason",
      "latencyMs",
      "citations",
      "retrieval",
    ],
  },
  {
    name: "stream normalization keeps public metadata",
    file: "src/stores/useAppStore.ts",
    includes: [
      "/api/svensk-ragg/agent/query/stream",
      "source_scope",
      "retriever_source",
      "data_source_attribution",
      "refusal_reason",
      "latency_ms",
      "citations",
      "retrieval",
    ],
    excludes: ["/api/" + "constitu" + "tional"],
  },
  {
    name: "browser-forwarded frontend uses same-origin API by default",
    file: "src/stores/useAppStore.ts",
    includes: ['const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "";'],
    excludes: ['|| "http://localhost:8900"'],
  },
  {
    name: "vite proxies same-origin API calls to local backend",
    file: "vite.config.ts",
    includes: ['"/api"', "target: \"http://127.0.0.1:8900\""],
  },
  {
    name: "public copy does not imply generic legal knowledge",
    file: "src/components/ui/ChatMessage.tsx",
    excludes: ["modellens allmänna rättskunskap"],
  },
  {
    name: "chat input footer stays scoped to Riksdagen-only data",
    file: "src/components/ui/ChatInput.tsx",
    includes: ["Riksdagens öppna data"],
    excludes: ["Myndighetsdata"],
  },
];

const failures = [];

for (const check of checks) {
  const contents = read(check.file);
  for (const needle of check.includes ?? []) {
    if (!contents.includes(needle)) {
      failures.push(`${check.name}: missing "${needle}" in ${check.file}`);
    }
  }
  for (const needle of check.excludes ?? []) {
    if (contents.includes(needle)) {
      failures.push(`${check.name}: forbidden "${needle}" in ${check.file}`);
    }
  }
}

if (failures.length > 0) {
  console.error("Public UI contract check failed:");
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  process.exit(1);
}

console.log("Public UI contract check passed.");
