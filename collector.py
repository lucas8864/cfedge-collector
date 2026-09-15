#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import ipaddress
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "20"))
ENABLE_ACTIVE_TEST = os.getenv("ENABLE_ACTIVE_TEST", "false").lower() == "true"
ACTIVE_TEST_LIMIT = int(os.getenv("ACTIVE_TEST_LIMIT", "300"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


# ============================================================
# 数据源
# ============================================================

SOURCES = {
    "vvhan": {
        "type": "vvhan",
        "enabled": True,
        "url": "https://api.4ce.cn/api/bestCFIP",
    },

    "nirevil_v4": {
        "type": "nirevil",
        "enabled": True,
        "version": 4,
        "url": (
            "https://raw.githubusercontent.com/"
            "NiREvil/vless/refs/heads/main/sub/Cf-ipv4.json"
        ),
    },

    "nirevil_v6": {
        "type": "nirevil",
        "enabled": True,
        "version": 6,
        "url": (
            "https://raw.githubusercontent.com/"
            "NiREvil/vless/refs/heads/main/sub/Cf-ipv6.json"
        ),
    },

    "mingyu_v4": {
        "type": "plain_ip",
        "enabled": True,
        "version": 4,
        "url": (
            "https://raw.githubusercontent.com/"
            "ymyuuu/IPDB/refs/heads/main/BestCF/bestcfv4.txt"
        ),
    },

    "mingyu_v6": {
        "type": "plain_ip",
        "enabled": True,
        "version": 6,
        "url": (
            "https://raw.githubusercontent.com/"
            "ymyuuu/IPDB/refs/heads/main/BestCF/bestcfv6.txt"
        ),
    },

    "gslege_speed": {
        "type": "gslege",
        "enabled": True,
        "region": None,
        "url": (
            "https://raw.githubusercontent.com/"
            "gslege/CloudflareIP/refs/heads/main/Cfxyz.txt"
        ),
    },

    "gslege_jp": {
        "type": "gslege",
        "enabled": True,
        "region": "JP",
        "url": (
            "https://raw.githubusercontent.com/"
            "gslege/CloudflareIP/refs/heads/main/JP.txt"
        ),
    },

    "gslege_nl": {
        "type": "gslege",
        "enabled": True,
        "region": "NL",
        "url": (
            "https://raw.githubusercontent.com/"
            "gslege/CloudflareIP/refs/heads/main/NL.txt"
        ),
    },

    "gslege_us": {
        "type": "gslege",
        "enabled": True,
        "region": "US",
        "url": (
            "https://raw.githubusercontent.com/"
            "gslege/CloudflareIP/refs/heads/main/US.txt"
        ),
    },

    "gslege_de": {
        "type": "gslege",
        "enabled": True,
        "region": "DE",
        "url": (
            "https://raw.githubusercontent.com/"
            "gslege/CloudflareIP/refs/heads/main/DE.txt"
        ),
    },

    "gslege_sg": {
        "type": "gslege",
        "enabled": True,
        "region": "SG",
        "url": (
            "https://raw.githubusercontent.com/"
            "gslege/CloudflareIP/refs/heads/main/SG.txt"
        ),
    },

    "zhixuanwang": {
        "type": "zhixuanwang",
        "enabled": True,
        "url": (
            "https://raw.githubusercontent.com/"
            "ZhiXuanWang/cf-speed-dns/refs/heads/main/ipTop10.html"
        ),
    },

    "vps789": {
        "type": "vps789",
        "enabled": True,
        "url": "https://vps789.com/cfip/?remarks=domain",
    },

    "xinyitang": {
        "type": "xinyitang",
        "enabled": True,
        "url": (
            "https://sub.xinyitang.dpdns.org/"
            "sub?host=123&uuid=456"
        ),
    },

    "tiancheng": {
        "type": "tiancheng",
        "enabled": True,
        "url": (
            "https://cm.soso.edu.kg/"
            "sub?host=123&uuid=456"
        ),
    },
}


# ============================================================
# Cloudflare Colo -> Region
# ============================================================

COLO_REGION = {
    "HKG": "HK",
    "TPE": "TW",
    "NRT": "JP",
    "KIX": "JP",
    "SIN": "SG",
    "ICN": "KR",

    "LAX": "US",
    "SJC": "US",
    "SEA": "US",
    "DFW": "US",
    "ORD": "US",
    "IAD": "US",
    "ATL": "US",
    "MIA": "US",

    "FRA": "DE",
    "DUS": "DE",
    "AMS": "NL",
    "LHR": "UK",
    "CDG": "FR",
    "SYD": "AU",
}


ISP_MAP = {
    "CM": "CM",
    "MOBILE": "CM",
    "CHINA MOBILE": "CM",
    "中国移动": "CM",

    "CU": "CU",
    "UNICOM": "CU",
    "CHINA UNICOM": "CU",
    "中国联通": "CU",

    "CT": "CT",
    "TELECOM": "CT",
    "CHINA TELECOM": "CT",
    "中国电信": "CT",
}


REGION_PATTERNS = [
    (r"\bHKG\b|\bHK\b|香港|Hong\s*Kong", "HK"),
    (r"\bSIN\b|\bSG\b|新加坡|Singapore", "SG"),
    (r"\bJPN\b|\bJP\b|日本|Japan", "JP"),
    (r"\bTWN\b|\bTW\b|台湾|Taiwan", "TW"),
    (r"\bKOR\b|\bKR\b|韩国|Korea", "KR"),
    (r"\bUSA\b|\bUS\b|美国|United\s*States", "US"),
    (r"\bGBR\b|\bUK\b|英国|United\s*Kingdom", "UK"),
    (r"\bRUS\b|\bRU\b|俄罗斯|Russia", "RU"),
    (r"\bDEU\b|\bDE\b|德国|Germany", "DE"),
    (r"\bNLD\b|\bNL\b|荷兰|Netherlands", "NL"),
    (r"\bFRA\b|\bFR\b|法国|France", "FR"),
    (r"\bAUS\b|\bAU\b|澳大利亚|Australia", "AU"),
]


# ============================================================
# 基础工具
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs():
    paths = [
        DATA_DIR,
        DATA_DIR / "ip",
        DATA_DIR / "domain",
        DATA_DIR / "region",
        DATA_DIR / "isp",
        DATA_DIR / "quality",
        DATA_DIR / "source",
    ]

    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def fetch(url, timeout=None):
    timeout = timeout or HTTP_TIMEOUT

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=timeout,
        allow_redirects=True,
    )

    response.raise_for_status()

    return response.text


def fetch_json(url):
    text = fetch(url)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 有些接口返回 JSONP / 前后存在无关字符
        start = text.find("{")
        end = text.rfind("}")

        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])

        start = text.find("[")
        end = text.rfind("]")

        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])

        raise


def normalize_ip(value):
    if value is None:
        return None

    value = str(value).strip()

    value = value.strip("[](),;\"'")

    # 去掉可能存在的端口
    if re.match(r"^\d+\.\d+\.\d+\.\d+:\d+$", value):
        value = value.rsplit(":", 1)[0]

    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def detect_ip_version(ip):
    try:
        return ipaddress.ip_address(ip).version
    except Exception:
        return None


def normalize_domain(value):
    if value is None:
        return None

    value = str(value).strip()
    value = value.strip("[](),;\"'")

    if not value:
        return None

    if "://" in value:
        try:
            parsed = urlparse(value)
            value = parsed.hostname or ""
        except Exception:
            return None

    if "/" in value:
        value = value.split("/", 1)[0]

    if ":" in value and value.count(":") == 1:
        host, port = value.rsplit(":", 1)

        if port.isdigit():
            value = host

    value = value.rstrip(".")

    if not value:
        return None

    try:
        if ipaddress.ip_address(value):
            return None
    except Exception:
        pass

    if not re.match(
        r"^(?=.{1,253}$)"
        r"(?:[A-Za-z0-9]"
        r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
        r"[A-Za-z]{2,63}$",
        value,
    ):
        return None

    return value.lower()


def extract_ips(text):
    if not text:
        return []

    results = []

    ipv4_pattern = (
        r"\b(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
        r"(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}\b"
    )

    ipv6_pattern = r"(?<![A-Za-z0-9:])(?:[0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f]{1,4}(?![A-Za-z0-9:])"

    results.extend(re.findall(ipv4_pattern, text))
    results.extend(re.findall(ipv6_pattern, text))

    output = []

    for item in results:
        ip = normalize_ip(item)

        if ip and ip not in output:
            output.append(ip)

    return output


def extract_domains(text):
    if not text:
        return []

    pattern = (
        r"(?<![@A-Za-z0-9-])"
        r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
        r"[A-Za-z]{2,63}"
        r"(?![A-Za-z0-9-])"
    )

    results = []

    for item in re.findall(pattern, text):
        domain = normalize_domain(item)

        if domain and domain not in results:
            results.append(domain)

    return results


def to_number(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()

    if not text:
        return None

    match = re.search(r"-?\d+(?:\.\d+)?", text)

    if not match:
        return None

    try:
        return float(match.group())
    except Exception:
        return None


def normalize_latency(value):
    value = to_number(value)

    if value is None or value < 0:
        return None

    return round(value, 2)


def normalize_speed(value):
    value = to_number(value)

    if value is None or value < 0:
        return None

    text = str(value).lower()

    if "kb/s" in text or "kbps" in text:
        value = value / 1024

    elif "gb/s" in text or "gbps" in text:
        value = value * 1024

    return round(value, 2)


def normalize_isp(value):
    if value is None:
        return None

    text = str(value).strip().upper()

    if not text:
        return None

    for key, result in ISP_MAP.items():
        if key in text:
            return result

    return text[:30]


def infer_region(text):
    if not text:
        return None

    text = str(text)

    for pattern, region in REGION_PATTERNS:
        if re.search(pattern, text, re.I):
            return region

    return None


def region_from_colo(colo):
    if not colo:
        return None

    return COLO_REGION.get(str(colo).upper())


# ============================================================
# Record
# ============================================================

def new_record(
    host,
    source,
    port=443,
    version=None,
    region=None,
    isp=None,
    colo=None,
    latency=None,
    speed=None,
):
    ip = normalize_ip(host)

    if ip:
        host_type = "ip"

        if version is None:
            version = detect_ip_version(ip)

        canonical_host = ip
    else:
        domain = normalize_domain(host)

        if not domain:
            return None

        host_type = "domain"
        canonical_host = domain

    record = {
        "ip": canonical_host if host_type == "ip" else None,
        "domain": canonical_host if host_type == "domain" else None,
        "version": version if host_type == "ip" else None,
        "port": int(port or 443),
        "sources": [source],
        "source_count": 1,
        "isp": [],
        "colo": [],
        "region": [],
        "latency": normalize_latency(latency),
        "speed": normalize_speed(speed),
        "score": 0,
    }

    if isp:
        isp = normalize_isp(isp)

        if isp:
            record["isp"].append(isp)

    if colo:
        colo = str(colo).strip().upper()

        if colo:
            record["colo"].append(colo)

    if region:
        region = infer_region(region) or str(region).upper()

        if region and region not in record["region"]:
            record["region"].append(region)

    return record


def merge_record(target, incoming):
    for source in incoming.get("sources", []):
        if source not in target["sources"]:
            target["sources"].append(source)

    target["source_count"] = len(target["sources"])

    for field in ("isp", "colo", "region"):
        for value in incoming.get(field, []):
            if value and value not in target[field]:
                target[field].append(value)

    incoming_latency = incoming.get("latency")

    if incoming_latency is not None:
        if target["latency"] is None:
            target["latency"] = incoming_latency
        else:
            target["latency"] = min(
                target["latency"],
                incoming_latency,
            )

    incoming_speed = incoming.get("speed")

    if incoming_speed is not None:
        if target["speed"] is None:
            target["speed"] = incoming_speed
        else:
            target["speed"] = max(
                target["speed"],
                incoming_speed,
            )


# ============================================================
# JSON 字段提取
# ============================================================

def find_value(obj, names):
    if not isinstance(obj, dict):
        return None

    lowered = {
        str(k).lower(): v
        for k, v in obj.items()
    }

    for name in names:
        value = lowered.get(name.lower())

        if value is not None:
            return value

    return None


def walk_json_records(obj):
    if isinstance(obj, list):
        for item in obj:
            yield from walk_json_records(item)

    elif isinstance(obj, dict):
        # 当前对象本身可能就是记录
        if any(
            key in {str(k).lower() for k in obj.keys()}
            for key in (
                "ip",
                "address",
                "host",
                "server",
                "ipv4",
                "ipv6",
            )
        ):
            yield obj

        for value in obj.values():
            if isinstance(value, (dict, list)):
                yield from walk_json_records(value)


# ============================================================
# vvhan
# ============================================================

def collect_vvhan(config, source):
    data = fetch_json(config["url"])

    records = []

    for item in walk_json_records(data):
        ip = find_value(
            item,
            [
                "ip",
                "address",
                "host",
                "server",
                "ipv4",
                "ipv6",
            ],
        )

        if isinstance(ip, list):
            ip = ip[0] if ip else None

        ip = normalize_ip(ip)

        if not ip:
            continue

        colo = find_value(
            item,
            [
                "colo",
                "cfcolo",
                "airport",
                "datacenter",
                "dc",
            ],
        )

        latency = find_value(
            item,
            [
                "latency",
                "delay",
                "ping",
                "rtt",
                "time",
            ],
        )

        speed = find_value(
            item,
            [
                "speed",
                "speed_mbps",
                "mbps",
                "download",
                "download_speed",
            ],
        )

        isp = find_value(
            item,
            [
                "isp",
                "line",
                "operator",
                "carrier",
            ],
        )

        region = find_value(
            item,
            [
                "region",
                "country",
                "country_code",
            ],
        )

        record = new_record(
            ip,
            source,
            port=443,
            version=detect_ip_version(ip),
            region=region,
            isp=isp,
            colo=colo,
            latency=latency,
            speed=speed,
        )

        if record:
            records.append(record)

    return records


# ============================================================
# NiREvil
# ============================================================

def collect_nirevil(config, source):
    data = fetch_json(config["url"])

    records = []

    for item in walk_json_records(data):
        ip = find_value(
            item,
            [
                "ip",
                "address",
                "host",
                "server",
                "ipv4",
                "ipv6",
            ],
        )

        if isinstance(ip, list):
            values = ip
        else:
            values = [ip]

        for value in values:
            ip = normalize_ip(value)

            if not ip:
                continue

            colo = find_value(
                item,
                [
                    "colo",
                    "cfcolo",
                    "airport",
                    "datacenter",
                    "dc",
                ],
            )

            latency = find_value(
                item,
                [
                    "latency",
                    "delay",
                    "ping",
                    "rtt",
                ],
            )

            speed = find_value(
                item,
                [
                    "speed",
                    "speed_mbps",
                    "mbps",
                    "download",
                ],
            )

            isp = find_value(
                item,
                [
                    "isp",
                    "line",
                    "operator",
                    "carrier",
                ],
            )

            region = find_value(
                item,
                [
                    "region",
                    "country",
                    "country_code",
                ],
            )

            record = new_record(
                ip,
                source,
                version=detect_ip_version(ip),
                region=region,
                isp=isp,
                colo=colo,
                latency=latency,
                speed=speed,
            )

            if record:
                records.append(record)

    return records


# ============================================================
# Plain IP
# ============================================================

def collect_plain_ip(config, source):
    text = fetch(config["url"])

    records = []

    for ip in extract_ips(text):
        version = detect_ip_version(ip)

        if config.get("version"):
            version = config["version"]

        record = new_record(
            ip,
            source,
            version=version,
        )

        if record:
            records.append(record)

    return records


# ============================================================
# GSlege
# ============================================================

def collect_gslege(config, source):
    text = fetch(config["url"])

    records = []

    for ip in extract_ips(text):
        record = new_record(
            ip,
            source,
            version=detect_ip_version(ip),
            region=config.get("region"),
        )

        if record:
            records.append(record)

    return records


# ============================================================
# ZhiXuanWang
# ============================================================

def collect_zhixuanwang(config, source):
    text = fetch(config["url"])

    records = []

    # 原始文件是 HTML / 文本混合格式。
    # 不假设固定逗号结构，直接扫描 IP。
    for ip in extract_ips(text):
        record = new_record(
            ip,
            source,
            version=detect_ip_version(ip),
        )

        if record:
            records.append(record)

    return records


# ============================================================
# Base64
# ============================================================

def decode_base64_text(text):
    if not text:
        return ""

    text = text.strip()

    candidates = [
        text,
        text.replace("-", "+").replace("_", "/"),
    ]

    for candidate in candidates:
        candidate = re.sub(r"\s+", "", candidate)

        padding = len(candidate) % 4

        if padding:
            candidate += "=" * (4 - padding)

        try:
            decoded = base64.b64decode(
                candidate,
                validate=False,
            )

            result = decoded.decode(
                "utf-8",
                errors="ignore",
            )

            if result:
                return result

        except Exception:
            pass

    return text


# ============================================================
# VLESS
# ============================================================

def parse_vless_line(line):
    line = line.strip()

    if not line:
        return None

    if line.startswith("vless://") is False:
        return None

    try:
        parsed = urlparse(line)

        host = parsed.hostname

        if not host:
            return None

        port = parsed.port or 443

        query = parse_qs(parsed.query)

        remark = unquote(
            parsed.fragment or ""
        )

        region = infer_region(
            remark + " " + line
        )

        sni = query.get("sni", [None])[0]

        if not region and sni:
            region = infer_region(sni)

        return {
            "host": host,
            "port": port,
            "region": region,
            "remark": remark,
            "sni": sni,
        }

    except Exception:
        return None


def collect_vless_source(config, source):
    raw = fetch(config["url"])

    decoded = decode_base64_text(raw)

    records = []

    for line in decoded.splitlines():
        line = line.strip()

        if not line:
            continue

        parsed = parse_vless_line(line)

        if not parsed:
            continue

        host = parsed["host"]
        port = parsed["port"]
        region = parsed["region"]

        ip = normalize_ip(host)

        if ip:
            record = new_record(
                ip,
                source,
                port=port,
                version=detect_ip_version(ip),
                region=region,
            )
        else:
            domain = normalize_domain(host)

            if not domain:
                continue

            record = new_record(
                domain,
                source,
                port=port,
                region=region,
            )

        if record:
            records.append(record)

    return records


def collect_xinyitang(config, source):
    return collect_vless_source(
        config,
        source,
    )


def collect_tiancheng(config, source):
    return collect_vless_source(
        config,
        source,
    )


# ============================================================
# VPS789
# ============================================================

def collect_vps789(config, source):
    """
    VPS789 是动态网页。

    优先使用 Playwright。
    如果 Playwright 不可用，则退化为 requests
    + 正则提取域名。
    """

    records = []

    html = ""

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True
            )

            page = browser.new_page(
                user_agent=HEADERS["User-Agent"]
            )

            page.goto(
                config["url"],
                wait_until="domcontentloaded",
                timeout=HTTP_TIMEOUT * 1000,
            )

            page.wait_for_timeout(1500)

            html = page.content()

            browser.close()

    except Exception as exc:
        print(
            f"[WARN] {source}: Playwright failed: {exc}"
        )

        try:
            html = fetch(config["url"])
        except Exception as fallback_exc:
            print(
                f"[WARN] {source}: "
                f"requests fallback failed: {fallback_exc}"
            )
            return records

    # 从 HTML 中提取所有域名
    domains = extract_domains(html)

    # 排除明显无关域名
    excluded = {
        "w3.org",
        "google.com",
        "googleapis.com",
        "cloudflare.com",
        "github.com",
        "githubusercontent.com",
        "jquery.com",
        "jsdelivr.net",
        "bootstrapcdn.com",
    }

    for domain in domains:
        if domain in excluded:
            continue

        if domain.endswith(
            (
                ".js",
                ".css",
            )
        ):
            continue

        record = new_record(
            domain,
            source,
            port=443,
        )

        if record:
            records.append(record)

    return records


# ============================================================
# Source Dispatcher
# ============================================================

COLLECTORS = {
    "vvhan": collect_vvhan,
    "nirevil": collect_nirevil,
    "plain_ip": collect_plain_ip,
    "gslege": collect_gslege,
    "zhixuanwang": collect_zhixuanwang,
    "xinyitang": collect_xinyitang,
    "tiancheng": collect_tiancheng,
    "vps789": collect_vps789,
}


def collect_source(source, config):
    source_type = config["type"]

    collector = COLLECTORS.get(source_type)

    if not collector:
        raise RuntimeError(
            f"unsupported source type: {source_type}"
        )

    return collector(
        config,
        source,
    )


# ============================================================
# Dedup
# ============================================================

def deduplicate(records):
    merged = {}

    for record in records:
        if record.get("ip"):
            key = (
                "ip",
                record["ip"],
                record["port"],
            )
        elif record.get("domain"):
            key = (
                "domain",
                record["domain"],
                record["port"],
            )
        else:
            continue

        if key not in merged:
            merged[key] = record
        else:
            merge_record(
                merged[key],
                record,
            )

    return list(merged.values())


# ============================================================
# Region
# ============================================================

def finalize_region(record):
    if record["region"]:
        return

    for colo in record.get("colo", []):
        region = region_from_colo(colo)

        if region:
            record["region"].append(region)

    if not record["region"]:
        # 尝试从来源名称判断
        text = " ".join(
            record.get("sources", [])
        )

        region = infer_region(text)

        if region:
            record["region"].append(region)


# ============================================================
# Score
# ============================================================

def calculate_score(record):
    score = 0

    latency = record.get("latency")
    speed = record.get("speed")
    source_count = record.get("source_count", 0)

    if latency is not None:
        if latency <= 50:
            score += 40
        elif latency <= 100:
            score += 30
        elif latency <= 150:
            score += 20
        elif latency <= 200:
            score += 10

    if speed is not None:
        if speed >= 200:
            score += 40
        elif speed >= 100:
            score += 30
        elif speed >= 50:
            score += 20
        elif speed >= 10:
            score += 10

    if source_count >= 5:
        score += 20
    elif source_count >= 3:
        score += 15
    elif source_count == 2:
        score += 10
    elif source_count == 1:
        score += 5

    return min(score, 100)


def finalize_records(records):
    for record in records:
        finalize_region(record)
        record["source_count"] = len(
            record["sources"]
        )
        record["score"] = calculate_score(
            record
        )

    return records


# ============================================================
# Sorting
# ============================================================

def sort_key(record):
    latency = (
        record["latency"]
        if record["latency"] is not None
        else 999999
    )

    speed = (
        record["speed"]
        if record["speed"] is not None
        else -1
    )

    return (
        -record["score"],
        latency,
        -speed,
        record.get("ip")
        or record.get("domain")
        or "",
    )


# ============================================================
# Output
# ============================================================

def format_float(value):
    if value is None:
        return ""

    if float(value).is_integer():
        return str(int(value))

    return str(round(value, 2))


def record_to_line(record):
    host = (
        record["ip"]
        if record.get("ip")
        else record["domain"]
    )

    if record.get("ip") and record["version"] == 6:
        host = f"[{host}]"

    port = record.get("port", 443)

    region = (
        ",".join(record["region"])
        if record["region"]
        else "UNKNOWN"
    )

    isp = (
        ",".join(record["isp"])
        if record["isp"]
        else "UNKNOWN"
    )

    colo = (
        ",".join(record["colo"])
        if record["colo"]
        else "UNKNOWN"
    )

    latency = record.get("latency")

    latency_text = (
        f"{format_float(latency)}ms"
        if latency is not None
        else "-"
    )

    speed = record.get("speed")

    speed_text = (
        f"{format_float(speed)}mbps"
        if speed is not None
        else "-"
    )

    return (
        f"{host}:{port}"
        f"#{region}|{isp}|{colo}|"
        f"{latency_text}|{speed_text}|"
        f"S{record['score']}"
    )


def write_text(path, lines):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as f:
        if lines:
            f.write(
                "\n".join(lines)
                + "\n"
            )


def export_data(records, source_stats):
    sorted_records = sorted(
        records,
        key=sort_key,
    )

    ip_records = [
        r
        for r in sorted_records
        if r.get("ip")
    ]

    domain_records = [
        r
        for r in sorted_records
        if r.get("domain")
    ]

    ipv4_records = [
        r
        for r in ip_records
        if r.get("version") == 4
    ]

    ipv6_records = [
        r
        for r in ip_records
        if r.get("version") == 6
    ]

    ip_lines = [
        record_to_line(r)
        for r in ip_records
    ]

    ipv4_lines = [
        record_to_line(r)
        for r in ipv4_records
    ]

    ipv6_lines = [
        record_to_line(r)
        for r in ipv6_records
    ]

    domain_lines = [
        record_to_line(r)
        for r in domain_records
    ]

    # --------------------------------------------------------
    # IP
    # --------------------------------------------------------

    write_text(
        DATA_DIR / "ip" / "all.txt",
        ip_lines,
    )

    write_text(
        DATA_DIR / "ip" / "ipv4.txt",
        ipv4_lines,
    )

    write_text(
        DATA_DIR / "ip" / "ipv6.txt",
        ipv6_lines,
    )

    # --------------------------------------------------------
    # Domain
    # --------------------------------------------------------

    write_text(
        DATA_DIR / "domain" / "all.txt",
        domain_lines,
    )

    write_text(
        DATA_DIR / "domain" / "top10.txt",
        [
            r["domain"]
            for r in domain_records[:10]
        ],
    )

    write_text(
        DATA_DIR / "domain" / "top20.txt",
        [
            r["domain"]
            for r in domain_records[:20]
        ],
    )

    write_text(
        DATA_DIR / "domain" / "top50.txt",
        [
            r["domain"]
            for r in domain_records[:50]
        ],
    )

    # --------------------------------------------------------
    # Region
    # --------------------------------------------------------

    region_records = defaultdict(list)

    for record in sorted_records:
        for region in record.get(
            "region",
            [],
        ):
            region_records[region].append(
                record
            )

    for region, items in region_records.items():
        write_text(
            DATA_DIR / "region" / f"{region}.txt",
            [
                record_to_line(r)
                for r in items
            ],
        )

    # --------------------------------------------------------
    # ISP
    # --------------------------------------------------------

    isp_records = defaultdict(list)

    for record in sorted_records:
        for isp in record.get(
            "isp",
            [],
        ):
            isp_records[isp].append(
                record
            )

    for isp, items in isp_records.items():
        write_text(
            DATA_DIR / "isp" / f"{isp}.txt",
            [
                record_to_line(r)
                for r in items
            ],
        )

    # --------------------------------------------------------
    # Quality
    # --------------------------------------------------------

    latency100 = [
        record_to_line(r)
        for r in sorted_records
        if r.get("latency") is not None
        and r["latency"] <= 100
    ]

    latency200 = [
        record_to_line(r)
        for r in sorted_records
        if r.get("latency") is not None
        and r["latency"] <= 200
    ]

    speed50 = [
        record_to_line(r)
        for r in sorted_records
        if r.get("speed") is not None
        and r["speed"] >= 50
    ]

    speed100 = [
        record_to_line(r)
        for r in sorted_records
        if r.get("speed") is not None
        and r["speed"] >= 100
    ]

    score60 = [
        record_to_line(r)
        for r in sorted_records
        if r["score"] >= 60
    ]

    score80 = [
        record_to_line(r)
        for r in sorted_records
        if r["score"] >= 80
    ]

    write_text(
        DATA_DIR / "quality" / "latency100.txt",
        latency100,
    )

    write_text(
        DATA_DIR / "quality" / "latency200.txt",
        latency200,
    )

    write_text(
        DATA_DIR / "quality" / "speed50.txt",
        speed50,
    )

    write_text(
        DATA_DIR / "quality" / "speed100.txt",
        speed100,
    )

    write_text(
        DATA_DIR / "quality" / "score60.txt",
        score60,
    )

    write_text(
        DATA_DIR / "quality" / "score80.txt",
        score80,
    )

    # --------------------------------------------------------
    # Source
    # --------------------------------------------------------

    source_records = defaultdict(list)

    for record in sorted_records:
        for source in record.get(
            "sources",
            [],
        ):
            source_records[source].append(
                record
            )

    for source, items in source_records.items():
        write_text(
            DATA_DIR / "source" / f"{source}.txt",
            [
                record_to_line(r)
                for r in items
            ],
        )

    # --------------------------------------------------------
    # index.json
    # --------------------------------------------------------

    index = {
        "generated_at": now_iso(),
        "total": len(sorted_records),
        "ipv4": len(ipv4_records),
        "ipv6": len(ipv6_records),
        "domains": len(domain_records),
        "records": sorted_records,
        "sources": source_stats,
    }

    with (
        DATA_DIR / "index.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            index,
            f,
            ensure_ascii=False,
            indent=2,
        )

    # --------------------------------------------------------
    # stats.json
    # --------------------------------------------------------

    stats = {
        "generated_at": now_iso(),
        "total": len(sorted_records),
        "ipv4": len(ipv4_records),
        "ipv6": len(ipv6_records),
        "domains": len(domain_records),
        "score": {
            "gte_80": len(score80),
            "gte_60": len(score60),
        },
        "quality": {
            "latency_lte_100": len(latency100),
            "latency_lte_200": len(latency200),
            "speed_gte_50": len(speed50),
            "speed_gte_100": len(speed100),
        },
        "sources": source_stats,
    }

    with (
        DATA_DIR / "stats.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            stats,
            f,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# Main
# ============================================================

def main():
    start_time = time.time()

    ensure_dirs()

    print("=" * 70)
    print("CFEdge Collector")
    print("=" * 70)
    print(
        f"Time: {now_iso()}"
    )
    print(
        f"HTTP_TIMEOUT: {HTTP_TIMEOUT}"
    )
    print(
        f"ACTIVE_TEST: {ENABLE_ACTIVE_TEST}"
    )
    print("=" * 70)

    all_records = []

    source_stats = {}

    for source, config in SOURCES.items():
        if not config.get("enabled", True):
            continue

        print()
        print(
            f"[SOURCE] {source}"
        )

        started = time.time()

        try:
            records = collect_source(
                source,
                config,
            )

            source_stats[source] = {
                "status": "ok",
                "type": config["type"],
                "url": config["url"],
                "records": len(records),
                "elapsed": round(
                    time.time() - started,
                    2,
                ),
            }

            all_records.extend(records)

            print(
                f"[OK] {source}: "
                f"{len(records)} records"
            )

        except Exception as exc:
            source_stats[source] = {
                "status": "error",
                "type": config["type"],
                "url": config["url"],
                "records": 0,
                "error": str(exc),
                "elapsed": round(
                    time.time() - started,
                    2,
                ),
            }

            print(
                f"[ERROR] {source}: {exc}"
            )

    print()
    print("=" * 70)
    print(
        f"Raw records: {len(all_records)}"
    )

    records = deduplicate(
        all_records
    )

    print(
        f"After dedup: {len(records)}"
    )

    records = finalize_records(
        records
    )

    # 防止某一个来源全部为空导致整个输出完全没有信息
    if not records:
        print(
            "[WARN] No records collected."
        )

    export_data(
        records,
        source_stats,
    )

    elapsed = time.time() - start_time

    print("=" * 70)
    print(
        f"Finished in {elapsed:.2f}s"
    )

    print(
        f"Total: {len(records)}"
    )

    print(
        f"IPv4: "
        f"{sum(1 for r in records if r.get('version') == 4)}"
    )

    print(
        f"IPv6: "
        f"{sum(1 for r in records if r.get('version') == 6)}"
    )

    print(
        f"Domain: "
        f"{sum(1 for r in records if r.get('domain'))}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()
