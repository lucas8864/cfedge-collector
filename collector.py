import base64
import ipaddress
import json
import os
import re
import socket
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "20"))
ENABLE_ACTIVE_TEST = os.getenv("ENABLE_ACTIVE_TEST", "false").lower() == "true"
ACTIVE_TEST_LIMIT = int(os.getenv("ACTIVE_TEST_LIMIT", "300"))
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36"

# 说明：保留现有数据源配置；不修改 GitHub Actions 和 data/ 目录结构。
SOURCES = {
    "vvhan": {"type": "vvhan", "enabled": True, "url": "https://api.4ce.cn/api/bestCFIP"},
    "nirevil_v4": {"type": "nirevil", "enabled": True, "version": 4, "url": "https://raw.githubusercontent.com/NiREvil/vless/refs/heads/main/sub/Cf-ipv4.json"},
    "nirevil_v6": {"type": "nirevil", "enabled": True, "version": 6, "url": "https://raw.githubusercontent.com/NiREvil/vless/refs/heads/main/sub/Cf-ipv6.json"},
    "mingyu_v4": {"type": "plain_ip", "enabled": True, "version": 4, "url": "https://raw.githubusercontent.com/ymyuuu/IPDB/refs/heads/main/BestCF/bestcfv4.txt"},
    "mingyu_v6": {"type": "plain_ip", "enabled": True, "version": 6, "url": "https://raw.githubusercontent.com/ymyuuu/IPDB/refs/heads/main/BestCF/bestcfv6.txt"},
    "gslege_speed": {"type": "gslege", "enabled": True, "region": None, "url": "https://raw.githubusercontent.com/gslege/CloudflareIP/refs/heads/main/Cfxyz.txt"},
    "gslege_jp": {"type": "gslege", "enabled": True, "region": "JP", "url": "https://raw.githubusercontent.com/gslege/CloudflareIP/refs/heads/main/JP.txt"},
    "gslege_nl": {"type": "gslege", "enabled": True, "region": "NL", "url": "https://raw.githubusercontent.com/gslege/CloudflareIP/refs/heads/main/NL.txt"},
    "gslege_us": {"type": "gslege", "enabled": True, "region": "US", "url": "https://raw.githubusercontent.com/gslege/CloudflareIP/refs/heads/main/US.txt"},
    "gslege_de": {"type": "gslege", "enabled": True, "region": "DE", "url": "https://raw.githubusercontent.com/gslege/CloudflareIP/refs/heads/main/DE.txt"},
    "gslege_sg": {"type": "gslege", "enabled": True, "region": "SG", "url": "https://raw.githubusercontent.com/gslege/CloudflareIP/refs/heads/main/SG.txt"},
    "zhixuanwang": {"type": "zhixuanwang", "enabled": True, "url": "https://raw.githubusercontent.com/ZhiXuanWang/cf-speed-dns/refs/heads/main/ipTop10.html"},
    "vps789": {"type": "vps789", "enabled": True, "url": "https://vps789.com/cfip/?remarks=domain"},
    "xinyitang": {"type": "xinyitang", "enabled": True, "url": "https://sub.xinyitang.dpdns.org/sub?host=123&uuid=456"},
    "tiancheng": {"type": "tiancheng", "enabled": True, "url": "https://cm.soso.edu.kg/sub?host=123&uuid=456"},
}

COLO_REGION = {
    "HKG": "HK", "SIN": "SG", "NRT": "JP", "KIX": "JP", "TYO": "JP", "OSA": "JP",
    "ICN": "KR", "TPE": "TW", "IAD": "US", "LAX": "US", "SJC": "US", "SEA": "US",
    "ORD": "US", "DFW": "US", "ATL": "US", "AMS": "NL", "FRA": "DE", "LHR": "UK",
    "CDG": "FR", "SYD": "AU", "MEL": "AU", "YYZ": "CA", "YVR": "CA",
}

ISP_MAP = {
    "CM": "CM", "CMMOBILE": "CM", "CHINAMOBILE": "CM", "中国移动": "CM", "移动": "CM",
    "CU": "CU", "CHINAUNICOM": "CU", "中国联通": "CU", "联通": "CU",
    "CT": "CT", "CHINATELECOM": "CT", "中国电信": "CT", "电信": "CT",
    "CF": "CF", "CLOUDFLARE": "CF",
}

REGION_ALIASES = {
    "HONGKONG": "HK", "HONG KONG": "HK", "香港": "HK", "SINGAPORE": "SG", "新加坡": "SG",
    "JAPAN": "JP", "日本": "JP", "UNITEDSTATES": "US", "UNITED STATES": "US", "美国": "US",
    "GERMANY": "DE", "德国": "DE", "NETHERLANDS": "NL", "荷兰": "NL", "TAIWAN": "TW", "台湾": "TW",
    "KOREA": "KR", "韩国": "KR", "UNITEDKINGDOM": "UK", "UNITED KINGDOM": "UK", "英国": "UK",
    "FRANCE": "FR", "法国": "FR", "CANADA": "CA", "加拿大": "CA", "AUSTRALIA": "AU", "澳大利亚": "AU",
}

REGION_PATTERNS = [
    (r"(?<![A-Z])HKG(?![A-Z])", "HK"), (r"(?<![A-Z])SIN(?![A-Z])", "SG"),
    (r"(?<![A-Z])JPN(?![A-Z])", "JP"), (r"(?<![A-Z])TYO(?![A-Z])", "JP"), (r"(?<![A-Z])NRT(?![A-Z])", "JP"),
    (r"(?<![A-Z])TWN(?![A-Z])", "TW"), (r"(?<![A-Z])KOR(?![A-Z])", "KR"),
    (r"(?<![A-Z])USA(?![A-Z])", "US"), (r"(?<![A-Z])DEU(?![A-Z])", "DE"),
    (r"(?<![A-Z])NLD(?![A-Z])", "NL"), (r"(?<![A-Z])GBR(?![A-Z])", "UK"), (r"(?<![A-Z])RUS(?![A-Z])", "RU"),
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def fetch(url, timeout=HTTP_TIMEOUT):
    r = SESSION.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text


def fetch_json(url, timeout=HTTP_TIMEOUT):
    r = SESSION.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def normalize_ip(value):
    if value is None:
        return None
    text = str(value).strip().strip("[]")
    if text.startswith(("http://", "https://")):
        text = urlparse(text).hostname or ""
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return None


def ip_version(ip):
    try:
        return ipaddress.ip_address(ip).version
    except ValueError:
        return None


def normalize_port(value, default=443):
    try:
        p = int(value)
        return p if 1 <= p <= 65535 else default
    except (TypeError, ValueError):
        return default


def normalize_text(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"DEFAULT", "NONE", "UNKNOWN", "-", "NULL", "N/A"}:
        return None
    return text


def normalize_region(value):
    value = normalize_text(value)
    if not value:
        return None
    text = value.strip().upper()
    if text in REGION_ALIASES:
        return REGION_ALIASES[text]
    if re.fullmatch(r"[A-Z]{2}", text):
        return text
    for pattern, region in REGION_PATTERNS:
        if re.search(pattern, text):
            return region
    return None


def normalize_isp(value):
    value = normalize_text(value)
    if not value:
        return None
    text = value.upper().replace(" ", "").replace("_", "").replace("-", "")
    if text in ISP_MAP:
        return ISP_MAP[text]
    for raw, normalized in ISP_MAP.items():
        if raw in text:
            return normalized
    return None


def normalize_colo(value):
    value = normalize_text(value)
    if not value:
        return None
    value = value.upper().replace("_", "").replace("-", "")
    return value if re.fullmatch(r"[A-Z]{3}", value) else None


def normalize_latency(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            n = float(value)
        else:
            text = str(value).strip().lower()
            if text in {"", "0", "0ms", "none", "unknown", "-", "default"}:
                return None
            m = re.search(r"(-?\d+(?:\.\d+)?)", text)
            if not m:
                return None
            n = float(m.group(1))
        return round(n, 2) if 0 < n <= 60000 else None
    except (TypeError, ValueError):
        return None


def normalize_speed(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            n = float(value)
        else:
            text = str(value).strip().lower()
            if text in {"", "0", "0mbps", "none", "unknown", "-", "default"}:
                return None
            m = re.search(r"(-?\d+(?:\.\d+)?)", text)
            if not m:
                return None
            n = float(m.group(1))
        return round(n, 2) if 0 < n <= 1000000 else None
    except (TypeError, ValueError):
        return None


def infer_region_from_colo(colo):
    return COLO_REGION.get((colo or "").upper())


def infer_region_from_text(text):
    if not text:
        return None
    raw = str(text).upper()
    for marker, region in REGION_ALIASES.items():
        # 中文和完整英文名称直接匹配；两字母代码不在这里做裸 substring 匹配。
        if len(marker) > 2 and marker in raw:
            return region
    for pattern, region in REGION_PATTERNS:
        if re.search(pattern, raw):
            return region
    return None


def normalize_domain(value):
    if value is None:
        return None
    text = str(value).strip()
    if "://" in text:
        text = urlparse(text).hostname or ""
    text = text.split("/", 1)[0].split("#", 1)[0].strip().strip("[]").rstrip(".")
    if ":" in text:
        host, port = text.rsplit(":", 1)
        if port.isdigit():
            text = host
    if not re.fullmatch(r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}", text):
        return None
    return text.lower()


def make_record(ip=None, source=None, version=None, port=443, region=None, isp=None, colo=None,
                 latency=None, speed=None, domain=None, remark=None, evidence_type="source", evidence_scope="metadata"):
    ip = normalize_ip(ip)
    if not ip:
        return None
    version = version or ip_version(ip)
    if version not in {4, 6}:
        return None
    return {
        "ip": ip,
        "version": version,
        "port": normalize_port(port),
        "region": normalize_region(region),
        "isp": normalize_isp(isp),
        "colo": normalize_colo(colo),
        "latency": normalize_latency(latency),
        "speed": normalize_speed(speed),
        "domain": normalize_domain(domain),
        "remark": normalize_text(remark),
        "source": source,
        "evidence_type": evidence_type,
        "evidence_scope": evidence_scope,
    }


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def collect_vvhan(source_name, cfg):
    data = fetch_json(cfg["url"])
    records = []

    def walk(value, inherited_isp=None):
        if isinstance(value, dict):
            current_isp = inherited_isp
            for key in ("group", "line", "isp", "operator", "carrier", "name"):
                candidate = normalize_isp(value.get(key))
                if candidate:
                    current_isp = candidate
                    break
            ip = next((normalize_ip(value.get(k)) for k in ("ip", "IP", "addr", "address", "host") if normalize_ip(value.get(k))), None)
            if ip:
                records.append(make_record(
                    ip=ip, source=source_name, version=ip_version(ip), port=value.get("port", 443),
                    isp=current_isp, colo=value.get("colo") or value.get("coloName") or value.get("cf_colo"),
                    latency=value.get("latency"), speed=value.get("speed"), remark=value.get("remark") or value.get("name"),
                    evidence_type="vvhan", evidence_scope="metadata"))
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child, current_isp)
        elif isinstance(value, list):
            for child in value:
                walk(child, inherited_isp)

    walk(data)
    return [x for x in records if x]


def collect_nirevil(source_name, cfg):
    data = fetch_json(cfg["url"])
    records = []
    for item in walk_json(data):
        ip = next((normalize_ip(item.get(k)) for k in ("ip", "IP", "address", "host") if normalize_ip(item.get(k))), None)
        if not ip:
            continue
        line = item.get("line") or item.get("group") or item.get("remark")
        records.append(make_record(
            ip=ip, source=source_name, version=cfg.get("version") or ip_version(ip), port=item.get("port", 443),
            region=item.get("region"), isp=item.get("isp") or item.get("operator"),
            colo=item.get("colo") or item.get("coloName") or item.get("cf_colo"),
            latency=item.get("latency"), speed=item.get("speed"), remark=line,
            evidence_type="nirevil", evidence_scope="metadata"))
    return [x for x in records if x]


def collect_plain_ip(source_name, cfg):
    text = fetch(cfg["url"])
    return [make_record(ip=ip, source=source_name, version=cfg.get("version") or ip_version(ip), evidence_type="plain_ip", evidence_scope="membership")
            for line in text.splitlines() if (ip := normalize_ip(line.strip()))]


def collect_gslege(source_name, cfg):
    text = fetch(cfg["url"])
    records = []
    explicit_region = normalize_region(cfg.get("region"))
    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        ip_part, _, remark = raw.partition("#")
        ip = normalize_ip(ip_part)
        if not ip:
            continue
        # 关键规则：GSlege 文件名地区只保存为 source evidence，不作为最终 region。
        region = explicit_region or infer_region_from_text(remark)
        records.append(make_record(
            ip=ip, source=source_name, version=ip_version(ip), region=region,
            remark=remark, evidence_type=(f"{source_name}:filename" if explicit_region else "gslege:remark"),
            evidence_scope="source_label"))
    return [x for x in records if x]


def collect_zhixuanwang(source_name, cfg):
    text = fetch(cfg["url"])
    records, seen = [], set()
    for token in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text):
        ip = normalize_ip(token)
        if ip and ip not in seen:
            seen.add(ip)
            records.append(make_record(ip=ip, source=source_name, version=4, evidence_type="html", evidence_scope="membership"))
    for token in re.split(r"[\s,;\"'<>()[\]{}]+", text):
        ip = normalize_ip(token)
        if ip and ip_version(ip) == 6 and ip not in seen:
            seen.add(ip)
            records.append(make_record(ip=ip, source=source_name, version=6, evidence_type="html", evidence_scope="membership"))
    return records


def decode_base64_text(text):
    if not text:
        return ""
    candidates = [text.strip(), re.sub(r"\s+", "", text)]
    for candidate in candidates:
        try:
            padding = "=" * ((4 - len(candidate) % 4) % 4)
            decoded = base64.b64decode(candidate + padding, altchars=b"-_", validate=False).decode("utf-8", errors="ignore")
            if "vless://" in decoded.lower() or "trojan://" in decoded.lower():
                return decoded
        except Exception:
            pass
    return text


def parse_vless_line(line, source_name):
    if not line.strip().lower().startswith("vless://"):
        return None
    try:
        parsed = urlparse(line.strip())
        host = parsed.hostname
        port = parsed.port or 443
        query = parse_qs(parsed.query)
        remark = parsed.fragment or None
        region = normalize_region((query.get("region") or [None])[0]) or normalize_region((query.get("country") or [None])[0])
        if not region:
            region = infer_region_from_text(remark)
        return make_record(
            ip=host, source=source_name, version=ip_version(host), port=port, region=region,
            domain=host if not normalize_ip(host) else None, remark=remark,
            evidence_type="vless:remark", evidence_scope="node_metadata")
    except Exception:
        return None


def parse_vless_text(text, source_name):
    return [r for line in text.splitlines() if (r := parse_vless_line(line, source_name))]


def collect_xinyitang(source_name, cfg):
    try:
        text = fetch(cfg["url"])
    except Exception:
        text = ""
    return parse_vless_text(decode_base64_text(text), source_name)


def collect_tiancheng(source_name, cfg):
    text = ""
    for _ in range(3):
        try:
            text = fetch(cfg["url"])
            if text:
                break
        except Exception:
            time.sleep(1)
    return parse_vless_text(decode_base64_text(text), source_name)


def extract_domains_from_text(text):
    pattern = re.compile(r"(?<![@A-Za-z0-9_-])(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}(?![A-Za-z0-9_-])")
    excluded = {"vps789.com", "github.com", "raw.githubusercontent.com", "cloudflare.com"}
    result, seen = [], set()
    for match in pattern.findall(text or ""):
        domain = normalize_domain(match)
        if domain and domain not in excluded and domain not in seen:
            seen.add(domain)
            result.append(domain)
    return result


def collect_vps789(source_name, cfg):
    text = fetch(cfg["url"])
    return [{"domain": d, "source": source_name, "region": None, "isp": None, "colo": None,
             "remark": d, "evidence_type": "web-domain"} for d in extract_domains_from_text(text)]


def resolve_domain(domain):
    addresses = set()
    try:
        for item in socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM):
            if item[4] and (ip := normalize_ip(item[4][0])):
                addresses.add(ip)
    except Exception:
        pass
    return sorted(addresses)


def new_aggregate():
    return {"ip": None, "version": None, "port": 443, "regions": [], "isps": [], "colos": [],
            "latencies": [], "speeds": [], "sources": [], "remarks": [], "domains": []}


def add_evidence(bucket, field, value, source, evidence_type, scope):
    if value is None:
        return
    item = {"value": value, "source": source, "type": evidence_type, "scope": scope}
    if item not in bucket[field]:
        bucket[field].append(item)


def add_record_to_aggregate(agg, record):
    if not record:
        return
    source = record.get("source") or "unknown"
    etype = record.get("evidence_type") or "source"
    scope = record.get("evidence_scope") or "metadata"
    agg["ip"] = record.get("ip") or agg["ip"]
    agg["version"] = record.get("version") or agg["version"]
    agg["port"] = normalize_port(record.get("port"), agg["port"])
    if source not in agg["sources"]:
        agg["sources"].append(source)
    if (v := normalize_region(record.get("region"))):
        add_evidence(agg, "regions", v, source, etype, scope)
    if (v := normalize_isp(record.get("isp"))):
        add_evidence(agg, "isps", v, source, etype, scope)
    if (v := normalize_colo(record.get("colo"))):
        add_evidence(agg, "colos", v, source, etype, scope)
    if (v := normalize_latency(record.get("latency"))) is not None:
        agg["latencies"].append({"value": v, "source": source, "type": etype, "scope": scope})
    if (v := normalize_speed(record.get("speed"))) is not None:
        agg["speeds"].append({"value": v, "source": source, "type": etype, "scope": scope})
    if (v := normalize_text(record.get("remark"))) and v not in agg["remarks"]:
        agg["remarks"].append(v)
    if (v := normalize_domain(record.get("domain"))) and v not in agg["domains"]:
        agg["domains"].append(v)


def choose_region(candidates):
    if not candidates:
        return None
    # source_label（GSlege 文件名）只能作为 evidence，绝不能成为最终 Region。
    rank = {
        "node_metadata": 0,
        "metadata": 1,
        "geoip": 2,
        "asn": 3,
        "source_label": 99,
        "membership": 100,
    }
    return sorted(candidates, key=lambda x: (rank.get(x.get("scope"), 50), x["source"], x["type"]))[0]


def choose_isp(candidates):
    if not candidates:
        return None
    rank = {"metadata": 0, "node_metadata": 0, "geoip": 1, "asn": 2, "source_label": 99, "membership": 100}
    source_rank = {"vvhan": 0, "nirevil_v4": 1, "nirevil_v6": 1}
    return sorted(candidates, key=lambda x: (rank.get(x.get("scope"), 50), source_rank.get(x["source"], 10), x["source"]))[0]


def choose_colo(candidates):
    if not candidates:
        return None
    rank = {"metadata": 0, "node_metadata": 0, "geoip": 1, "asn": 2, "source_label": 99, "membership": 100}
    source_rank = {"vvhan": 0, "nirevil_v4": 1, "nirevil_v6": 1}
    return sorted(candidates, key=lambda x: (rank.get(x.get("scope"), 50), source_rank.get(x["source"], 10), x["source"]))[0]


def finalize_aggregate(agg):
    region = choose_region(agg["regions"])
    isp = choose_isp(agg["isps"])
    colo = choose_colo(agg["colos"])
    latency = min(agg["latencies"], key=lambda x: x["value"]) if agg["latencies"] else None
    speed = max(agg["speeds"], key=lambda x: x["value"]) if agg["speeds"] else None

    # Colo 只用于辅助 evidence，不从 colo 反推最终 region。
    # 这一步专门防止 Cloudflare Anycast IP 被错误标成国家/地区。
    evidence = {
        "region": list(agg["regions"]),
        "isp": list(agg["isps"]),
        "colo": list(agg["colos"]),
        "latency": list(agg["latencies"]),
        "speed": list(agg["speeds"]),
    }

    return {
        "ip": agg["ip"],
        "version": agg["version"] or ip_version(agg["ip"]),
        "port": agg["port"],
        "region": region["value"] if region else None,
        "isp": isp["value"] if isp else None,
        "colo": colo["value"] if colo else None,
        "latency": latency["value"] if latency else None,
        "speed": speed["value"] if speed else None,
        "sources": sorted(agg["sources"]),
        "source_count": len(agg["sources"]),
        "remark": agg["remarks"][0] if agg["remarks"] else None,
        "domains": sorted(agg["domains"]),
        "evidence": evidence,
    }


def attach_domain_dns(domain_records, ip_records):
    by_ip = {r["ip"]: r for r in ip_records}
    output = []
    for item in domain_records:
        domain = normalize_domain(item.get("domain"))
        if not domain:
            continue
        ips = resolve_domain(domain)
        linked = [by_ip[ip] for ip in ips if ip in by_ip]
        region = normalize_region(item.get("region"))
        isp = normalize_isp(item.get("isp"))
        colo = normalize_colo(item.get("colo"))
        # 域名本身没有明确 metadata 时，DNS 仅作为“关联 IP”证据，不把 Cloudflare Anycast IP 的国家当真。
        if not region:
            for r in linked:
                if r.get("region"):
                    region = r["region"]
                    break
        if not isp:
            for r in linked:
                if r.get("isp"):
                    isp = r["isp"]
                    break
        if not colo:
            for r in linked:
                if r.get("colo"):
                    colo = r["colo"]
                    break
        output.append({
            "domain": domain, "port": 443, "region": region, "isp": isp, "colo": colo,
            "ips": ips, "linked_ips": [r["ip"] for r in linked], "source": item.get("source"),
            "remark": item.get("remark"),
            "evidence": {
                "region": {"value": region, "source": item.get("source"), "type": "dns-inherit"} if region else None,
                "isp": {"value": isp, "source": item.get("source"), "type": "dns-inherit"} if isp else None,
                "colo": {"value": colo, "source": item.get("source"), "type": "dns-inherit"} if colo else None,
            },
        })
    return output


def calculate_score(record):
    score = 0
    latency = normalize_latency(record.get("latency"))
    speed = normalize_speed(record.get("speed"))
    source_count = int(record.get("source_count") or 0)
    if latency is not None:
        score += 40 if latency <= 30 else 35 if latency <= 60 else 30 if latency <= 100 else 20 if latency <= 150 else 10 if latency <= 250 else 5
    if speed is not None:
        score += 40 if speed >= 500 else 35 if speed >= 200 else 30 if speed >= 100 else 20 if speed >= 50 else 10 if speed >= 10 else 5
    score += 20 if source_count >= 4 else 15 if source_count == 3 else 10 if source_count == 2 else 5 if source_count == 1 else 0
    return min(100, score)


def display_value(value, unknown="UNKNOWN"):
    return normalize_text(value) or unknown


def format_host(ip):
    return f"[{ip}]" if ip_version(ip) == 6 else ip


def record_to_line(record):
    latency = normalize_latency(record.get("latency"))
    speed = normalize_speed(record.get("speed"))
    latency_text = str(int(latency)) if latency is not None and latency.is_integer() else str(latency) if latency is not None else "-"
    speed_text = str(int(speed)) if speed is not None and speed.is_integer() else str(speed) if speed is not None else "-"
    return f"{format_host(record['ip'])}:{normalize_port(record.get('port'), 443)}#{display_value(record.get('region'))}|{display_value(record.get('isp'))}|{display_value(record.get('colo'))}|{latency_text}|{speed_text}|S{calculate_score(record)}"


def sort_key(record):
    latency = normalize_latency(record.get("latency"))
    speed = normalize_speed(record.get("speed"))
    return (int(record.get("version") or 9), -calculate_score(record), latency if latency is not None else 999999, -(speed or 0), record["ip"])


def write_text(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")


def export_data(ip_records, domain_records, source_stats):
    ip_records = sorted(ip_records, key=sort_key)
    ipv4 = [record_to_line(r) for r in ip_records if r.get("version") == 4]
    ipv6 = [record_to_line(r) for r in ip_records if r.get("version") == 6]
    write_text(DATA_DIR / "ip" / "ipv4.txt", ipv4)
    write_text(DATA_DIR / "ip" / "ipv6.txt", ipv6)
    write_text(DATA_DIR / "ip" / "all.txt", ipv4 + ipv6)

    domains = []
    for r in sorted(domain_records, key=lambda x: (str(x.get("region") or "ZZ"), x.get("domain", ""))):
        domains.append(f"{r['domain']}:443#{display_value(r.get('region'))}|{display_value(r.get('isp'))}|{display_value(r.get('colo'))}|-|-|S0")
    write_text(DATA_DIR / "domain" / "all.txt", domains)

    by_region = defaultdict(list)
    by_isp = defaultdict(list)
    for r in ip_records:
        by_region[r.get("region") or "UNKNOWN"].append(r)
        by_isp[r.get("isp") or "UNKNOWN"].append(r)
    for key, records in by_region.items():
        write_text(DATA_DIR / "region" / f"{key}.txt", [record_to_line(r) for r in sorted(records, key=sort_key)])
    for key, records in by_isp.items():
        write_text(DATA_DIR / "isp" / f"{key}.txt", [record_to_line(r) for r in sorted(records, key=sort_key)])

    quality = defaultdict(list)
    for r in ip_records:
        s = calculate_score(r)
        key = "80plus" if s >= 80 else "60plus" if s >= 60 else "40plus" if s >= 40 else "20plus" if s >= 20 else "all"
        quality[key].append(r)
    for key, records in quality.items():
        write_text(DATA_DIR / "quality" / f"{key}.txt", [record_to_line(r) for r in sorted(records, key=sort_key)])

    source_map = defaultdict(list)
    for r in ip_records:
        for source in r.get("sources", []):
            source_map[source].append(r)
    for source, records in source_map.items():
        write_text(DATA_DIR / "source" / f"{source}.txt", [record_to_line(r) for r in sorted(records, key=sort_key)])

    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(ip_records), "ipv4": len(ipv4), "ipv6": len(ipv6), "domains": len(domains),
        "records": ip_records, "domain_records": domain_records,
    }
    (DATA_DIR / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def build_stats(ip_records, domain_records, source_stats, started_at):
    stats = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed": round(time.time() - started_at, 2),
        "total": len(ip_records),
        "ipv4": sum(r.get("version") == 4 for r in ip_records),
        "ipv6": sum(r.get("version") == 6 for r in ip_records),
        "domains": len(domain_records),
        "measured_latency": sum(normalize_latency(r.get("latency")) is not None for r in ip_records),
        "measured_speed": sum(normalize_speed(r.get("speed")) is not None for r in ip_records),
        "sources": source_stats,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def collect_source(name, cfg):
    started = time.time()
    result = {"status": "error", "records": 0, "domains": 0, "elapsed": 0, "error": None}
    if not cfg.get("enabled", True):
        result["status"] = "disabled"
        return [], result
    try:
        handlers = {
            "vvhan": collect_vvhan, "nirevil": collect_nirevil, "plain_ip": collect_plain_ip,
            "gslege": collect_gslege, "zhixuanwang": collect_zhixuanwang,
            "xinyitang": collect_xinyitang, "tiancheng": collect_tiancheng, "vps789": collect_vps789,
        }
        records = handlers[cfg["type"]](name, cfg)
        result.update({"status": "ok", "records": sum(bool(x.get("ip")) for x in records), "domains": sum(bool(x.get("domain")) for x in records)})
        return records, {**result, "elapsed": round(time.time() - started, 2)}
    except Exception as exc:
        result["elapsed"] = round(time.time() - started, 2)
        result["error"] = f"{type(exc).__name__}: {exc}"
        return [], result


def main():
    started_at = time.time()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    aggregates = {}
    domain_candidates = []
    source_stats = {}

    print("==========================================")
    print("CFEdge Collector")
    print("==========================================")

    for name, cfg in SOURCES.items():
        print(f"[+] collecting {name} ...")
        records, stats = collect_source(name, cfg)
        source_stats[name] = stats
        print(f"    status={stats['status']} records={stats.get('records', 0)} domains={stats.get('domains', 0)} elapsed={stats.get('elapsed', 0)}s")
        if stats.get("error"):
            print(f"    error={stats['error']}")
        for record in records:
            if record.get("ip"):
                key = (record["ip"], normalize_port(record.get("port"), 443))
                aggregates.setdefault(key, new_aggregate())
                add_record_to_aggregate(aggregates[key], record)
            elif record.get("domain"):
                domain_candidates.append(record)

    ip_records = [finalize_aggregate(a) for a in aggregates.values() if a.get("ip")]
    domain_records = attach_domain_dns(domain_candidates, ip_records)
    export_data(ip_records, domain_records, source_stats)
    stats = build_stats(ip_records, domain_records, source_stats, started_at)

    print("==========================================")
    print("Finished")
    print("==========================================")
    print(f"IPv4: {stats['ipv4']}")
    print(f"IPv6: {stats['ipv6']}")
    print(f"IP total: {stats['total']}")
    print(f"Domains: {stats['domains']}")
    print(f"Latency measured: {stats['measured_latency']}")
    print(f"Speed measured: {stats['measured_speed']}")
    print(f"Elapsed: {stats['elapsed']}s")


if __name__ == "__main__":
    main()
