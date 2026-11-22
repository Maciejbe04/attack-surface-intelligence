/** Extensible discovery modules; add a new entry here to grow the dashboard. */

export type FilterOption = { value: string; label: string };

export type FilterField =
  | {
      key: string;
      label: string;
      type: "text";
      default: string;
      placeholder?: string;
      help?: string;
    }
  | {
      key: string;
      label: string;
      type: "number";
      default: number;
      min?: number;
      max?: number;
      help?: string;
    }
  | {
      key: string;
      label: string;
      type: "select";
      default: string;
      options: FilterOption[];
      help?: string;
    }
  | {
      key: string;
      label: string;
      type: "boolean";
      default: boolean;
      help?: string;
    };

export type ProbeModule = {
  id: string;
  name: string;
  summary: string;
  tool: string;
  category: "discovery" | "http" | "tls" | "signatures" | "pipeline";
  filters: FilterField[];
};

export type ModuleFilterValues = Record<string, string | number | boolean>;

export type ModuleRuntimeConfig = {
  enabled: boolean;
  expanded: boolean;
  filters: ModuleFilterValues;
};

export type ModuleRegistryState = Record<string, ModuleRuntimeConfig>;

/** Safe discovery-only modules; no exploit / brute / login. */
export const PROBE_MODULES: ProbeModule[] = [
  {
    id: "host-discovery",
    name: "Host discovery",
    summary: "ICMP / TCP probes to check if the host responds.",
    tool: "nmap",
    category: "discovery",
    filters: [
      {
        key: "method",
        label: "Method",
        type: "select",
        default: "icmp-tcp",
        options: [
          { value: "icmp", label: "ICMP only" },
          { value: "tcp", label: "TCP ping ports" },
          { value: "icmp-tcp", label: "ICMP + TCP" },
        ],
      },
      {
        key: "tcpPorts",
        label: "TCP ping ports",
        type: "text",
        default: "80,443",
        placeholder: "80,443,22",
        help: "Used when method includes TCP.",
      },
      {
        key: "timeoutSec",
        label: "Timeout (s)",
        type: "number",
        default: 3,
        min: 1,
        max: 30,
      },
    ],
  },
  {
    id: "port-scan",
    name: "Port scan",
    summary: "TCP scan with selectable port profile or custom list.",
    tool: "nmap",
    category: "discovery",
    filters: [
      {
        key: "profile",
        label: "Port profile",
        type: "select",
        default: "discovery-fast",
        options: [
          { value: "discovery-fast", label: "discovery-fast (default)" },
          { value: "discovery-web", label: "discovery-web" },
          { value: "discovery-full", label: "discovery-full (top 1000)" },
          { value: "custom", label: "Custom ports" },
        ],
      },
      {
        key: "customPorts",
        label: "Custom ports",
        type: "text",
        default: "22,80,443,8080,8443",
        placeholder: "22,80,443",
        help: "Used when profile is Custom.",
      },
      {
        key: "timing",
        label: "Timing template",
        type: "select",
        default: "T3",
        options: [
          { value: "T2", label: "T2 polite" },
          { value: "T3", label: "T3 normal" },
          { value: "T4", label: "T4 aggressive" },
        ],
      },
      {
        key: "maxRate",
        label: "Max packets/s",
        type: "number",
        default: 200,
        min: 10,
        max: 5000,
      },
    ],
  },
  {
    id: "service-detect",
    name: "Service detection",
    summary: "Identify services on open ports (-sV).",
    tool: "nmap",
    category: "discovery",
    filters: [
      {
        key: "intensity",
        label: "Version intensity",
        type: "number",
        default: 5,
        min: 0,
        max: 9,
        help: "nmap --version-intensity",
      },
      {
        key: "lightOnly",
        label: "Light probes only",
        type: "boolean",
        default: true,
        help: "Skip aggressive NSE scripts.",
      },
    ],
  },
  {
    id: "http-fingerprint",
    name: "HTTP fingerprint",
    summary: "Status, title, headers, tech detect via httpx.",
    tool: "httpx",
    category: "http",
    filters: [
      {
        key: "schemes",
        label: "Schemes",
        type: "select",
        default: "both",
        options: [
          { value: "http", label: "HTTP" },
          { value: "https", label: "HTTPS" },
          { value: "both", label: "HTTP + HTTPS" },
        ],
      },
      {
        key: "ports",
        label: "HTTP ports",
        type: "text",
        default: "80,443,8080,8443",
        placeholder: "80,443",
      },
      {
        key: "followRedirects",
        label: "Follow redirects",
        type: "boolean",
        default: true,
      },
      {
        key: "maxRedirects",
        label: "Max redirects",
        type: "number",
        default: 3,
        min: 0,
        max: 10,
      },
      {
        key: "techDetect",
        label: "Tech detect",
        type: "boolean",
        default: true,
      },
      {
        key: "timeoutSec",
        label: "Timeout (s)",
        type: "number",
        default: 5,
        min: 1,
        max: 30,
      },
      {
        key: "rateLimit",
        label: "Rate limit (req/s)",
        type: "number",
        default: 50,
        min: 1,
        max: 500,
      },
    ],
  },
  {
    id: "tls-cert",
    name: "TLS certificate",
    summary: "Grab certificate CN, issuer, and expiry.",
    tool: "httpx · tls-grab",
    category: "tls",
    filters: [
      {
        key: "ports",
        label: "TLS ports",
        type: "text",
        default: "443,8443",
        placeholder: "443,8443",
      },
      {
        key: "expireWarnDays",
        label: "Expiry warning (days)",
        type: "number",
        default: 30,
        min: 1,
        max: 365,
      },
      {
        key: "includeChain",
        label: "Include chain metadata",
        type: "boolean",
        default: false,
      },
    ],
  },
  {
    id: "signatures",
    name: "Custom signatures",
    summary: "Run declarative SurfaceX signature rules.",
    tool: "signatures",
    category: "signatures",
    filters: [
      {
        key: "pack",
        label: "Signature pack",
        type: "select",
        default: "builtin",
        options: [
          { value: "builtin", label: "Built-in" },
          { value: "web", label: "Web / CMS" },
          { value: "all", label: "All packs" },
        ],
      },
      {
        key: "minConfidence",
        label: "Min confidence",
        type: "select",
        default: "medium",
        options: [
          { value: "low", label: "Low (1+)" },
          { value: "medium", label: "Medium (40+)" },
          { value: "high", label: "High (70+)" },
        ],
      },
      {
        key: "pathsExtra",
        label: "Extra paths",
        type: "text",
        default: "",
        placeholder: "/login,/admin,/version",
        help: "Relative paths only.",
      },
    ],
  },
  {
    id: "passive-discovery",
    name: "Passive discovery",
    summary: "Certificate Transparency (crt.sh) and RDAP lookup for the target. Does not add hosts or scan them.",
    tool: "crt.sh / RDAP",
    category: "discovery",
    filters: [
      {
        key: "includeCrt",
        label: "Certificate Transparency (crt.sh)",
        type: "boolean",
        default: true,
        help: "Domain targets only. Lists names in scope; does not auto-add targets.",
      },
      {
        key: "includeRdap",
        label: "RDAP summary",
        type: "boolean",
        default: true,
        help: "Owner / network / ASN / nameservers when available.",
      },
    ],
  },
  {
    id: "full-pipeline",
    name: "Full discovery pipeline",
    summary: "nmap → httpx → signatures → confidence score.",
    tool: "pipeline",
    category: "pipeline",
    filters: [
      {
        key: "portProfile",
        label: "Port profile",
        type: "select",
        default: "discovery-fast",
        options: [
          { value: "discovery-fast", label: "discovery-fast" },
          { value: "discovery-web", label: "discovery-web" },
        ],
      },
      {
        key: "includeTls",
        label: "Include TLS grab",
        type: "boolean",
        default: true,
      },
      {
        key: "includeSignatures",
        label: "Include signatures",
        type: "boolean",
        default: true,
      },
      {
        key: "stopOnHostDown",
        label: "Stop if host down",
        type: "boolean",
        default: true,
      },
    ],
  },
];

export function defaultFiltersFor(module: ProbeModule): ModuleFilterValues {
  const values: ModuleFilterValues = {};
  for (const field of module.filters) {
    values[field.key] = field.default;
  }
  return values;
}

export function createInitialModuleState(
  enabledIds: string[] = ["host-discovery", "port-scan", "http-fingerprint"],
): ModuleRegistryState {
  const state: ModuleRegistryState = {};
  for (const mod of PROBE_MODULES) {
    state[mod.id] = {
      enabled: enabledIds.includes(mod.id),
      expanded: false,
      filters: defaultFiltersFor(mod),
    };
  }
  return state;
}

export function summarizeFilters(filters: ModuleFilterValues): string {
  const parts = Object.entries(filters)
    .filter(([, v]) => v !== "" && v !== false)
    .map(([k, v]) => `${k}=${String(v)}`);
  return parts.length ? parts.join(", ") : "defaults";
}
