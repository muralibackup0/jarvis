"""Cybersecurity assistant: CVE lookups, log analysis, Nmap command building and report drafting.

Nothing here attacks or scans anything - Nmap commands are built for the user to run themselves
against systems they own or are authorised to test.
"""
import collections
import datetime
import ipaddress
import os
import re
from pathlib import Path

import requests

from ..automation.common import HOME, known_folder
from ..automation.files import resolve
from ..core.registry import context, tool


@tool("Switch Jarvis between the normal assistant and cybersecurity expert mode.",
      mode=("string", "Mode", ["assistant", "security"]))
def set_mode(mode):
    context["ai"].mode = mode
    if mode == "security":
        return ("Cybersecurity mode engaged. I can explain CVEs, OWASP issues and Burp findings, analyse logs, "
                "build Nmap commands and draft VAPT reports, for systems you're authorised to test.")
    return "Back to standard assistant mode."


@tool("Look up a CVE in the US National Vulnerability Database: description, CVSS score, severity and references.",
      cve_id=("string", "CVE ID, e.g. CVE-2021-44228"))
def lookup_cve(cve_id):
    m = re.search(r"CVE[-\s]?(\d{4})[-\s]?(\d{4,7})", cve_id, re.I)
    if not m:
        return f"{cve_id} doesn't look like a CVE ID. They look like CVE-2021-44228."
    cid = f"CVE-{m[1]}-{m[2]}"
    try:
        r = requests.get("https://services.nvd.nist.gov/rest/json/cves/2.0", params={"cveId": cid}, timeout=20)
        r.raise_for_status()
        vulns = r.json().get("vulnerabilities", [])
    except (requests.RequestException, ValueError) as e:
        return f"I couldn't reach the NVD database: {e}"
    if not vulns:
        return f"NVD has no record of {cid}."
    cve = vulns[0]["cve"]
    desc = next((d["value"] for d in cve.get("descriptions", []) if d["lang"] == "en"), "No description.")
    metrics, score = cve.get("metrics", {}), "no CVSS score yet"
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        if metrics.get(key):
            d = metrics[key][0]["cvssData"]
            sev = d.get("baseSeverity") or metrics[key][0].get("baseSeverity", "")
            score = f"CVSS {d.get('version')} {d.get('baseScore')} {sev}, vector {d.get('vectorString')}"
            break
    cwes = sorted({x["value"] for w in cve.get("weaknesses", []) for x in w.get("description", [])})
    refs = [x["url"] for x in cve.get("references", [])][:3]
    return (f"{cid} (published {cve.get('published', '')[:10]}, status {cve.get('vulnStatus', '')}): {score}. "
            f"Weakness: {', '.join(cwes) or 'not specified'}. {desc} References: {' '.join(refs)}")


# ---------------------------------------------------------------- log analysis

LOG_SIGNATURES = {
    "SQL injection attempt": r"union(\s|%20|\+)+select|'\s*or\s*'?1'?\s*=\s*'?1|sleep\(\d+\)|information_schema|%27(%20|\+)or",
    "Cross-site scripting attempt": r"<script|%3cscript|javascript:|onerror\s*=|alert\(",
    "Path traversal attempt": r"\.\./|\.\.%2f|%2e%2e/|/etc/passwd|win\.ini|boot\.ini",
    "Command injection attempt": r";\s*(cat|ls|id|whoami|wget|curl)\b|\|\s*(nc|bash|sh)\b|\$\(.*\)|`[^`]+`",
    "Scanner or attack tool": r"nmap|sqlmap|nikto|dirbuster|gobuster|ffuf|wpscan|masscan|nuclei|hydra|acunetix|burp",
    "Failed login": r"failed password|authentication fail|invalid user|login failed|failed login|event ?id[:= ]*4625|unauthorized",
    "Privilege change": r"sudo:|su\[|event ?id[:= ]*4672|added to (the )?administrators|usermod|net localgroup",
    "Web shell or sensitive file access": r"\.(php|jsp|aspx?)\?(cmd|exec)=|/(\.env|\.git|wp-config\.php|config\.php)\b",
}
IP_RX = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
STATUS_RX = re.compile(r'"\s(\d{3})\s')


@tool("Analyse a log file (web server, auth, firewall, Windows event export...) for attacks and anomalies. "
      "Returns statistics and suspicious lines for you to explain.",
      path=("string", "Full path or file name of the log"))
def analyze_log_file(path):
    p = resolve(path, want_dir=False)
    if not p or not p.is_file():
        return f"I couldn't find the log file {path}."
    size = p.stat().st_size
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read(20_000_000).splitlines()
    ips, statuses, hits, samples = collections.Counter(), collections.Counter(), collections.Counter(), []
    ip_alerts = collections.Counter()
    for line in lines:
        found_ips = IP_RX.findall(line)
        ips.update(ip for ip in found_ips if _is_ip(ip))
        s = STATUS_RX.search(line)
        if s:
            statuses[s.group(1)] += 1
        for label, rx in LOG_SIGNATURES.items():
            if re.search(rx, line, re.I):
                hits[label] += 1
                if found_ips:
                    ip_alerts[found_ips[0]] += 1
                if len(samples) < 12:
                    samples.append(f"[{label}] {line.strip()[:300]}")
    out = [f"File {p.name}: {len(lines)} lines, {size / 1024:.0f} KB."]
    if ips:
        out.append("Top source IPs: " + ", ".join(f"{ip} ({n})" for ip, n in ips.most_common(5)) + ".")
    if statuses:
        out.append("HTTP status codes: " + ", ".join(f"{c}: {n}" for c, n in sorted(statuses.items())) + ".")
    if hits:
        out.append("Suspicious activity: " + ", ".join(f"{k}: {v}" for k, v in hits.most_common()) + ".")
        if ip_alerts:
            out.append("IPs behind suspicious lines: " + ", ".join(f"{ip} ({n})" for ip, n in ip_alerts.most_common(5)) + ".")
        out.append("Examples:\n" + "\n".join(samples))
    else:
        out.append("No known attack signatures matched.")
    return "\n".join(out)


def _is_ip(s):
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------- nmap

NMAP_PROFILES = {
    "quick": ("-T4 -F", "fast scan of the 100 most common ports"),
    "full": ("-T4 -p-", "all 65535 TCP ports"),
    "service": ("-sV -sC -T4", "service versions plus default safe scripts"),
    "os": ("-O -sV", "operating system and service detection (needs admin)"),
    "vuln": ("-sV --script vuln", "service detection plus NSE vulnerability scripts"),
    "udp": ("-sU --top-ports 100", "top 100 UDP ports (slow, needs admin)"),
    "stealth": ("-sS -T3", "TCP SYN scan (needs admin)"),
    "ping": ("-sn", "host discovery only, no port scan"),
    "web": ("-sV -p 80,443,8000,8080,8443 --script http-title,http-headers,ssl-cert", "web ports with HTTP and TLS details"),
}


@tool("Build (not run) an Nmap command for an authorised target, with an explanation of each option.",
      target=("string", "IP, CIDR range or hostname the user is authorised to scan"),
      scan_type=("string", "Scan profile", list(NMAP_PROFILES)))
def build_nmap_command(target, scan_type):
    t = target.strip()
    try:
        ipaddress.ip_network(t, strict=False)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", t):
            return f"{target} isn't a valid IP, range or hostname."
    flags, desc = NMAP_PROFILES[scan_type]
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    cmd = f"nmap {flags} -oA scan_{scan_type}_{stamp} {t}"
    return (f"Command: {cmd}\nThis runs a {scan_type} scan: {desc}. -oA saves normal, XML and grepable output. "
            f"Only run it against systems you own or have written permission to test. I won't run it for you.")


# ---------------------------------------------------------------- reports

@tool("Save a long document (VAPT report, findings write-up, notes) as a Markdown file in Documents/Jarvis Reports and open it.",
      title=("string", "Report title"), content=("string", "Full report content in Markdown"))
def save_report(title, content):
    folder = (known_folder("documents") or HOME) / "Jarvis Reports"
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\- ]", "", title).strip()[:60] or "report"
    path = folder / f"{datetime.datetime.now():%Y-%m-%d_%H%M} {safe}.md"
    path.write_text(f"# {title}\n\n{content}\n", encoding="utf-8")
    os.startfile(path)
    return f"Saved and opened {path.name} in Documents, Jarvis Reports."
