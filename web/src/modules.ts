export type ProbeModuleId =
  | "host-discovery"
  | "port-scan"
  | "service-detect"
  | "http-fingerprint"
  | "tls-cert"
  | "signatures"
  | "full-pipeline";

export type ProbeModule = {
  id: ProbeModuleId;
  name: string;
  summary: string;
  tool: string;
};

/** Safe discovery-only modules — no exploit / brute / login. */
export const PROBE_MODULES: ProbeModule[] = [
  {
    id: "host-discovery",
    name: "Host discovery",
    summary: "ICMP / TCP probes to check if the host responds.",
    tool: "nmap",
  },
  {
    id: "port-scan",
    name: "Port scan",
    summary: "Fast TCP scan of common service ports.",
    tool: "nmap · discovery-fast",
  },
  {
    id: "service-detect",
    name: "Service detection",
    summary: "Identify services on open ports (-sV).",
    tool: "nmap",
  },
  {
    id: "http-fingerprint",
    name: "HTTP fingerprint",
    summary: "Status, title, headers, tech detect via httpx.",
    tool: "httpx",
  },
  {
    id: "tls-cert",
    name: "TLS certificate",
    summary: "Grab certificate CN, issuer, and expiry.",
    tool: "httpx · tls-grab",
  },
  {
    id: "signatures",
    name: "Custom signatures",
    summary: "Run declarative SurfaceX signature rules.",
    tool: "signatures",
  },
  {
    id: "full-pipeline",
    name: "Full discovery pipeline",
    summary: "nmap → httpx → signatures → confidence score.",
    tool: "pipeline",
  },
];
