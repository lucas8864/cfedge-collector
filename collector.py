#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CFEdge Collector
================

Cloudflare IP / Domain 聚合采集器

功能：
    1. 多来源采集
    2. IPv4 / IPv6 自动识别
    3. IP 全局去重
    4. 来源合并
    5. ISP 分类
    6. Colo 分类
    7. Region 分类
    8. Latency
    9. Speed
   10. Source Count
   11. Score
   12. TXT 输出
   13. JSON 输出

核心原则：
    一个 collector.py 完成全部数据处理。
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import statistics
import time

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


# ============================================================
# 基础配置
# ============================================================

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "20"))

ENABLE_ACTIVE_TEST = (
    os.getenv("ENABLE_ACTIVE_TEST", "false").lower()
    in ("1", "true", "yes", "y")
)

ACTIVE_TEST_LIMIT = int(
    os.getenv("ACTIVE_TEST_LIMIT", "300")
)

ACTIVE_TEST_WORKERS = int(
    os.getenv("ACTIVE_TEST_WORKERS", "32")
)

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "Chrome/140 Safari/537.36 "
    "CFEdgeCollector/1.0"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "*/*",
}


# ============================================================
# 来源配置
# ============================================================

SOURCE_URLS = {

    # --------------------------------------------------------
    # VVHAN
    # --------------------------------------------------------

    "vvhan":
        "https://api.4ce.cn/api/bestCFIP",

    # --------------------------------------------------------
    # NiREvil
    # --------------------------------------------------------

    "nirevil_v4":
        "https://raw.githubusercontent.com/"
        "NiREvil/vless/refs/heads/main/sub/Cf-ipv4.json",

    "nirevil_v6":
        "https://raw.githubusercontent.com/"
        "NiREvil/vless/refs/heads/main/sub/Cf-ipv6.json",

    # --------------------------------------------------------
    # MingYu
    # --------------------------------------------------------

    "mingyu_v4":
        "https://raw.githubusercontent.com/"
        "ymyuuu/IPDB/refs/heads/main/BestCF/bestcfv4.txt",

    "mingyu_v6":
        "https://raw.githubusercontent.com/"
        "ymyuuu/IPDB/refs/heads/main/BestCF/bestcfv6.txt",

    # --------------------------------------------------------
    # GSlege
    # --------------------------------------------------------

    "gslege_cn":
        "https://raw.githubusercontent.com/"
        "gslege/CloudflareIP/refs/heads/main/Cfxyz.txt",

    "gslege_jp":
        "https://raw.githubusercontent.com/"
        "gslege/CloudflareIP/refs/heads/main/JP.txt",

    "gslege_nl":
        "https://raw.githubusercontent.com/"
        "gslege/CloudflareIP/refs/heads/main/NL.txt",

    "gslege_us":
        "https://raw.githubusercontent.com/"
        "gslege/CloudflareIP/refs/heads/main/US.txt",

    "gslege_de":
        "https://raw.githubusercontent.com/"
        "gslege/CloudflareIP/refs/heads/main/DE.txt",

    "gslege_sg":
        "https://raw.githubusercontent.com/"
        "gslege/CloudflareIP/refs/heads/main/SG.txt",

    # --------------------------------------------------------
    # ZhiXuanWang
    # --------------------------------------------------------

    "zhixuanwang":
        "https://raw.githubusercontent.com/"
        "ZhiXuanWang/cf-speed-dns/refs/heads/main/ipTop10.html",

    # --------------------------------------------------------
    # VPS789
    # --------------------------------------------------------

    "vps789":
        "https://vps789.com/cfip/?remarks=domain",

    # --------------------------------------------------------
    # WeTest
    # --------------------------------------------------------

    "wetest":
        "https://www.wetest.vip/page/cloudflare/address_v4.html",

    # --------------------------------------------------------
    # XinYiTang
    # --------------------------------------------------------

    "xinyitang":
        "https://sub.xinyitang.dpdns.org/"
        "sub?host=123&uuid=456",

    # --------------------------------------------------------
    # TianCheng
    # --------------------------------------------------------

    "tiancheng":
        "https://cm.soso.edu.kg/"
        "sub?host=123&uuid=456",
}


# ============================================================
# 禁用来源
# ============================================================

DISABLED_SOURCES = {
    x.strip()
    for x in os.getenv(
        "DISABLE_SOURCES",
        ""
    ).split(",")
    if x.strip()
}


# ============================================================
# Region 映射
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


# ============================================================
# ISP
# ============================================================

ISP_ALIASES = {

    "CM": "CM",
    "CMCC": "CM",
    "MOBILE": "CM",
    "中国移动": "CM",
    "移动": "CM",

    "CU": "CU",
    "UNICOM": "CU",
    "CHINAUNICOM": "CU",
    "中国联通": "CU",
    "联通": "CU",

    "CT": "CT",
    "TELECOM": "CT",
    "CHINATELECOM": "CT",
    "中国电信": "CT",
    "电信": "CT",
}


REGIONS = [
    "HK",
    "TW",
    "JP",
    "SG",
    "KR",
    "US",
    "DE",
    "NL",
    "UK",
    "FR",
    "AU",
]


ISPS = [
    "CM",
    "CU",
    "CT",
]


# ============================================================
# HTTP Session
# ============================================================

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ============================================================
# HTTP
# ============================================================

def http_get(
    url,
    timeout=None,
    allow_redirects=True,
):

    timeout = timeout or HTTP_TIMEOUT

    try:

        response = SESSION.get(
            url,
            timeout=timeout,
            allow_redirects=allow_redirects,
        )

        response.raise_for_status()

        return response

    except Exception as exc:

        print(
            f"[HTTP ERROR] "
            f"{url} -> {exc}"
        )

        return None


# ============================================================
# IP 标准化
# ============================================================

def normalize_ip(value):

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    value = value.strip(
        "\"'`()[] "
    )

    # IPv6 URL 格式
    if value.startswith("["):

        match = re.match(
            r"^\[([0-9a-fA-F:]+)\](?::\d+)?$",
            value
        )

        if match:
            value = match.group(1)

    # IPv4:port
    elif value.count(":") == 1:

        host, port = value.rsplit(":", 1)

        if port.isdigit():
            value = host

    # IPv6:port
    elif value.count(":") > 1:

        match = re.match(
            r"^(.+):(\d{2,5})$",
            value
        )

        if match:

            candidate = match.group(1)

            try:
                ipaddress.ip_address(candidate)
                value = candidate
            except Exception:
                pass

    try:

        return str(
            ipaddress.ip_address(value)
        )

    except Exception:

        return None


# ============================================================
# IP + Port
# ============================================================

def parse_ip_port(value):

    if not value:
        return None, 443

    value = str(value).strip()

    # IPv6 [addr]:port
    match = re.search(
        r"\[([0-9a-fA-F:]+)\]"
        r"(?::(\d{1,5}))?",
        value
    )

    if match:

        ip = normalize_ip(
            match.group(1)
        )

        port = int(
            match.group(2) or 443
        )

        return ip, port

    # IPv4
    match = re.search(
        r"(?<![\w.])"
        r"((?:\d{1,3}\.){3}\d{1,3})"
        r"(?::(\d{1,5}))?",
        value
    )

    if match:

        ip = normalize_ip(
            match.group(1)
        )

        port = int(
            match.group(2) or 443
        )

        return ip, port

    # IPv6
    match = re.search(
        r"(?<![\w])"
        r"([0-9a-fA-F]{1,4}"
        r"(?:\:[0-9a-fA-F]{1,4}){2,7})"
        r"(?::(\d{1,5}))?",
        value
    )

    if match:

        ip = normalize_ip(
            match.group(1)
        )

        port = int(
            match.group(2) or 443
        )

        return ip, port

    return None, 443


# ============================================================
# Domain
# ============================================================

def normalize_domain(value):

    if not value:
        return None

    value = str(value).strip().lower()

    value = re.sub(
        r"^https?://",
        "",
        value
    )

    value = value.split("/")[0]

    if ":" in value:
        value = value.split(":")[0]

    if re.fullmatch(
        r"(?:[a-z0-9-]+\.)+[a-z]{2,63}",
        value
    ):

        return value

    return None


# ============================================================
# ISP
# ============================================================

def normalize_isp(value):

    if not value:
        return None

    value = str(value).strip()

    key = value.upper()

    return ISP_ALIASES.get(
        key,
        ISP_ALIASES.get(value)
    )


# ============================================================
# 数值
# ============================================================

def number(value):

    if value is None:
        return None

    if isinstance(
        value,
        (int, float)
    ):

        return float(value)

    text = str(value)

    match = re.search(
        r"-?\d+(?:\.\d+)?",
        text
    )

    if not match:
        return None

    try:
        return float(
            match.group()
        )

    except Exception:

        return None


# ============================================================
# 新建记录
# ============================================================

def make_record(
    ip=None,
    domain=None,
    source="unknown",
    port=443,
    isp=None,
    colo=None,
    region=None,
    latency=None,
    speed=None,
):

    ip = normalize_ip(ip)

    if domain:
        domain = normalize_domain(
            domain
        )

    record = {

        "ip": ip,

        "domain": domain,

        "version": (
            ipaddress.ip_address(ip).version
            if ip
            else None
        ),

        "port": int(port or 443),

        "sources": [],

        "isp": [],

        "colo": [],

        "region": [],

        "latency": None,

        "speed": None,

    }

    merge_metadata(
        record,
        source=source,
        isp=isp,
        colo=colo,
        region=region,
        latency=latency,
        speed=speed,
    )

    return record


# ============================================================
# 合并元数据
# ============================================================

def merge_metadata(
    record,
    source=None,
    isp=None,
    colo=None,
    region=None,
    latency=None,
    speed=None,
):

    if source:

        if source not in record["sources"]:

            record["sources"].append(
                source
            )

    isp = normalize_isp(isp)

    if isp and isp not in record["isp"]:

        record["isp"].append(
            isp
        )

    if colo:

        colo = str(
            colo
        ).strip().upper()

        if colo not in record["colo"]:

            record["colo"].append(
                colo
            )

    if region:

        region = str(
            region
        ).strip().upper()

        if region not in record["region"]:

            record["region"].append(
                region
            )

    latency = number(
        latency
    )

    if latency is not None:

        if latency >= 0:

            if (
                record["latency"]
                is None
            ):

                record["latency"] = latency

            else:

                record["latency"] = min(
                    record["latency"],
                    latency
                )

    speed = number(
        speed
    )

    if speed is not None:

        if speed >= 0:

            if (
                record["speed"]
                is None
            ):

                record["speed"] = speed

            else:

                record["speed"] = max(
                    record["speed"],
                    speed
                )


# ============================================================
# VVHAN
# ============================================================

def collect_vvhan():

    if "vvhan" in DISABLED_SOURCES:
        return []

    print("[SOURCE] vvhan")

    response = http_get(
        SOURCE_URLS["vvhan"]
    )

    if not response:
        return []

    result = []

    try:

        data = response.json()

        data = data.get(
            "data",
            {}
        )

        for version in (
            "v4",
            "v6",
        ):

            items = data.get(
                version,
                []
            )

            for item in items:

                if not isinstance(
                    item,
                    dict
                ):
                    continue

                ip, port = parse_ip_port(
                    item.get("ip")
                    or item.get("address")
                )

                if not ip:
                    continue

                result.append(
                    make_record(
                        ip=ip,
                        port=port,
                        source="vvhan",
                        isp=(
                            item.get("isp")
                            or item.get(
                                "operator"
                            )
                        ),
                        colo=item.get(
                            "colo"
                        ),
                        region=item.get(
                            "region"
                        ),
                        latency=item.get(
                            "latency"
                        ),
                        speed=item.get(
                            "speed"
                        ),
                    )
                )

    except Exception as exc:

        print(
            "[ERROR] vvhan:",
            exc
        )

    return result


# ============================================================
# NiREvil
# ============================================================

def collect_nirevil():

    result = []

    for source_name in (
        "nirevil_v4",
        "nirevil_v6",
    ):

        if source_name in DISABLED_SOURCES:
            continue

        print(
            f"[SOURCE] {source_name}"
        )

        response = http_get(
            SOURCE_URLS[source_name]
        )

        if not response:
            continue

        try:

            data = response.json()

            if isinstance(
                data,
                dict
            ):

                items = (
                    data.get("data")
                    or data.get("nodes")
                    or data.get("list")
                    or []
                )

            elif isinstance(
                data,
                list
            ):

                items = data

            else:

                items = []

            for item in items:

                if isinstance(
                    item,
                    str
                ):

                    ip, port = parse_ip_port(
                        item
                    )

                    meta = {}

                elif isinstance(
                    item,
                    dict
                ):

                    ip, port = parse_ip_port(
                        item.get("ip")
                        or item.get(
                            "address"
                        )
                        or item.get(
                            "host"
                        )
                    )

                    meta = item

                else:

                    continue

                if not ip:
                    continue

                result.append(
                    make_record(
                        ip=ip,
                        port=port,
                        source=source_name,
                        isp=(
                            meta.get("isp")
                            or meta.get(
                                "operator"
                            )
                        ),
                        colo=meta.get(
                            "colo"
                        ),
                        region=meta.get(
                            "region"
                        ),
                        latency=meta.get(
                            "latency"
                        ),
                        speed=meta.get(
                            "speed"
                        ),
                    )
                )

        except Exception as exc:

            print(
                f"[ERROR] {source_name}:",
                exc
            )

    return result


# ============================================================
# 普通 TXT IP 源
# ============================================================

def collect_plain_ip(
    source_name,
    region=None,
):

    if source_name in DISABLED_SOURCES:
        return []

    print(
        f"[SOURCE] {source_name}"
    )

    response = http_get(
        SOURCE_URLS[source_name]
    )

    if not response:
        return []

    result = []

    for line in response.text.splitlines():

        ip, port = parse_ip_port(
            line
        )

        if not ip:
            continue

        result.append(
            make_record(
                ip=ip,
                port=port,
                source=source_name,
                region=region,
            )
        )

    return result


# ============================================================
# MingYu
# ============================================================

def collect_mingyu():

    result = []

    for source_name in (
        "mingyu_v4",
        "mingyu_v6",
    ):

        result.extend(
            collect_plain_ip(
                source_name
            )
        )

    return result


# ============================================================
# GSlege
# ============================================================

def collect_gslege():

    mapping = {

        "gslege_cn": None,
        "gslege_jp": "JP",
        "gslege_nl": "NL",
        "gslege_us": "US",
        "gslege_de": "DE",
        "gslege_sg": "SG",

    }

    result = []

    for source_name, region in mapping.items():

        result.extend(
            collect_plain_ip(
                source_name,
                region
            )
        )

    return result


# ============================================================
# ZhiXuanWang
# ============================================================

def collect_zhixuanwang():

    if "zhixuanwang" in DISABLED_SOURCES:
        return []

    print(
        "[SOURCE] zhixuanwang"
    )

    response = http_get(
        SOURCE_URLS[
            "zhixuanwang"
        ]
    )

    if not response:
        return []

    result = []

    text = BeautifulSoup(
        response.text,
        "html.parser"
    ).get_text(
        " "
    )

    # 直接提取 IPv4 / IPv6
    matches = re.findall(
        r"(?<![\w.])"
        r"(?:\d{1,3}\.){3}\d{1,3}"
        r"(?![\w.])"
        r"|"
        r"(?<![\w])"
        r"[0-9a-fA-F]{1,4}"
        r"(?:\:[0-9a-fA-F]{1,4}){2,7}"
        r"(?![\w])",
        text
    )

    for value in matches:

        ip = normalize_ip(
            value
        )

        if not ip:
            continue

        result.append(
            make_record(
                ip=ip,
                source="zhixuanwang"
            )
        )

    return result


# ============================================================
# VPS789
# ============================================================

def collect_vps789():

    if "vps789" in DISABLED_SOURCES:
        return []

    print(
        "[SOURCE] vps789"
    )

    response = http_get(
        SOURCE_URLS[
            "vps789"
        ]
    )

    if not response:
        return []

    result = []

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    for tr in soup.select(
        "tr"
    ):

        cells = [
            x.get_text(
                " ",
                strip=True
            )
            for x in tr.select(
                "td"
            )
        ]

        if not cells:
            continue

        ip, port = parse_ip_port(
            cells[0]
        )

        if not ip:
            continue

        region = None

        if len(cells) > 1:

            value = (
                cells[1]
                .strip()
                .upper()
            )

            if re.fullmatch(
                r"[A-Z]{2,3}",
                value
            ):

                region = value

        result.append(
            make_record(
                ip=ip,
                port=port,
                source="vps789",
                region=region
            )
        )

    return result


# ============================================================
# WeTest
# ============================================================

def collect_wetest():

    if "wetest" in DISABLED_SOURCES:
        return []

    print(
        "[SOURCE] wetest"
    )

    response = http_get(
        SOURCE_URLS[
            "wetest"
        ]
    )

    if not response:
        return []

    result = []

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # 兼容表格结构
    for tr in soup.select(
        "tr"
    ):

        text = tr.get_text(
            " ",
            strip=True
        )

        ip, port = parse_ip_port(
            text
        )

        if not ip:
            continue

        region = None

        upper = text.upper()

        for colo, reg in COLO_REGION.items():

            if colo in upper:

                region = reg

                break

        result.append(
            make_record(
                ip=ip,
                port=port,
                source="wetest",
                region=region
            )
        )

    # 页面有时不是标准 table
    if not result:

        for match in re.findall(
            r"(?<![\w.])"
            r"(?:\d{1,3}\.){3}\d{1,3}"
            r"(?![\w.])",
            response.text
        ):

            ip = normalize_ip(
                match
            )

            if ip:

                result.append(
                    make_record(
                        ip=ip,
                        source="wetest"
                    )
                )

    return result


# ============================================================
# Base64 解码
# ============================================================

def decode_base64(text):

    if not text:
        return ""

    text = text.strip()

    # URL-safe Base64
    text += "=" * (
        (-len(text)) % 4
    )

    try:

        return base64.b64decode(
            text,
            validate=False
        ).decode(
            "utf-8",
            errors="ignore"
        )

    except Exception:

        return ""


# ============================================================
# 从 VLESS 中提取 host
# ============================================================

def parse_vless(
    text,
    source_name
):

    result = []

    for line in text.splitlines():

        line = line.strip()

        if not line.startswith(
            "vless://"
        ):

            continue

        try:

            parsed = urlparse(
                line
            )

            host = parsed.hostname

            port = (
                parsed.port
                or 443
            )

            ip = normalize_ip(
                host
            )

            if not ip:

                continue

            region = None

            upper = line.upper()

            for code, reg in {
                "HKG": "HK",
                "HK": "HK",
                "TPE": "TW",
                "TW": "TW",
                "NRT": "JP",
                "JP": "JP",
                "SIN": "SG",
                "SG": "SG",
                "ICN": "KR",
                "KR": "KR",
                "LAX": "US",
                "US": "US",
                "FRA": "DE",
                "DE": "DE",
            }.items():

                if code in upper:

                    region = reg

                    break

            result.append(
                make_record(
                    ip=ip,
                    port=port,
                    source=source_name,
                    region=region
                )
            )

        except Exception:

            continue

    return result


# ============================================================
# XinYiTang
# ============================================================

def collect_xinyitang():

    if "xinyitang" in DISABLED_SOURCES:
        return []

    print(
        "[SOURCE] xinyitang"
    )

    response = http_get(
        SOURCE_URLS[
            "xinyitang"
        ]
    )

    if not response:
        return []

    text = response.text.strip()

    decoded = decode_base64(
        text
    )

    if not decoded:

        decoded = text

    return parse_vless(
        decoded,
        "xinyitang"
    )


# ============================================================
# TianCheng
# ============================================================

def collect_tiancheng():

    if "tiancheng" in DISABLED_SOURCES:
        return []

    print(
        "[SOURCE] tiancheng"
    )

    response = http_get(
        SOURCE_URLS[
            "tiancheng"
        ]
    )

    if not response:
        return []

    text = response.text.strip()

    decoded = decode_base64(
        text
    )

    if not decoded:

        decoded = text

    return parse_vless(
        decoded,
        "tiancheng"
    )


# ============================================================
# 所有来源
# ============================================================

def collect_all():

    records = []

    collectors = [

        collect_vvhan,

        collect_nirevil,

        collect_mingyu,

        collect_gslege,

        collect_zhixuanwang,

        collect_vps789,

        collect_wetest,

        collect_xinyitang,

        collect_tiancheng,

    ]

    for collector in collectors:

        try:

            rows = collector()

            print(
                f"        -> {len(rows)} records"
            )

            records.extend(
                rows
            )

        except Exception as exc:

            print(
                f"[ERROR] "
                f"{collector.__name__}: "
                f"{exc}"
            )

    return records


# ============================================================
# 全局去重
# ============================================================

def deduplicate(records):

    database = {}

    for record in records:

        ip = record.get(
            "ip"
        )

        domain = record.get(
            "domain"
        )

        key = None

        if ip:

            key = (
                "ip:"
                + ip
            )

        elif domain:

            key = (
                "domain:"
                + domain
            )

        if not key:
            continue

        if key not in database:

            database[key] = record

            continue

        old = database[key]

        # ----------------------------------------------------
        # 来源
        # ----------------------------------------------------

        for source in record[
            "sources"
        ]:

            if source not in old[
                "sources"
            ]:

                old[
                    "sources"
                ].append(
                    source
                )

        # ----------------------------------------------------
        # ISP
        # ----------------------------------------------------

        for isp in record[
            "isp"
        ]:

            if isp not in old[
                "isp"
            ]:

                old[
                    "isp"
                ].append(
                    isp
                )

        # ----------------------------------------------------
        # Colo
        # ----------------------------------------------------

        for colo in record[
            "colo"
        ]:

            if colo not in old[
                "colo"
            ]:

                old[
                    "colo"
                ].append(
                    colo
                )

        # ----------------------------------------------------
        # Region
        # ----------------------------------------------------

        for region in record[
            "region"
        ]:

            if region not in old[
                "region"
            ]:

                old[
                    "region"
                ].append(
                    region
                )

        # ----------------------------------------------------
        # Latency
        # 最低值
        # ----------------------------------------------------

        latency = record.get(
            "latency"
        )

        if latency is not None:

            if old[
                "latency"
            ] is None:

                old[
                    "latency"
                ] = latency

            else:

                old[
                    "latency"
                ] = min(
                    old["latency"],
                    latency
                )

        # ----------------------------------------------------
        # Speed
        # 最高值
        # ----------------------------------------------------

        speed = record.get(
            "speed"
        )

        if speed is not None:

            if old[
                "speed"
            ] is None:

                old[
                    "speed"
                ] = speed

            else:

                old[
                    "speed"
                ] = max(
                    old["speed"],
                    speed
                )

    return list(
        database.values()
    )


# ============================================================
# 根据 Colo 推断 Region
# ============================================================

def infer_region(record):

    if record[
        "region"
    ]:

        return

    for colo in record[
        "colo"
    ]:

        region = COLO_REGION.get(
            colo
        )

        if region:

            record[
                "region"
            ].append(
                region
            )

            return


# ============================================================
# Score
# ============================================================

def calculate_score(
    record
):

    score = 0

    latency = record.get(
        "latency"
    )

    speed = record.get(
        "speed"
    )

    source_count = len(
        record.get(
            "sources",
            []
        )
    )

    # --------------------------------------------------------
    # Latency 最高 40
    # --------------------------------------------------------

    if latency is not None:

        if latency <= 50:

            score += 40

        elif latency <= 100:

            score += 30

        elif latency <= 150:

            score += 20

        elif latency <= 200:

            score += 10

    # --------------------------------------------------------
    # Speed 最高 40
    # --------------------------------------------------------

    if speed is not None:

        if speed >= 200:

            score += 40

        elif speed >= 100:

            score += 30

        elif speed >= 50:

            score += 20

        elif speed >= 10:

            score += 10

    # --------------------------------------------------------
    # Source Count 最高 20
    # --------------------------------------------------------

    if source_count >= 5:

        score += 20

    elif source_count >= 3:

        score += 15

    elif source_count == 2:

        score += 10

    elif source_count == 1:

        score += 5

    return min(
        100,
        score
    )


# ============================================================
# 主动 Latency 测试
# ============================================================

def test_latency(record):

    ip = record.get(
        "ip"
    )

    if not ip:
        return record

    try:

        if ":" in ip:

            host = f"[{ip}]"

        else:

            host = ip

        start = time.perf_counter()

        response = SESSION.get(
            f"https://{host}/",
            timeout=5,
            verify=False,
            stream=True,
        )

        elapsed = (
            time.perf_counter()
            - start
        ) * 1000

        response.close()

        if (
            record["latency"]
            is None
        ):

            record[
                "latency"
            ] = elapsed

        else:

            record[
                "latency"
            ] = min(
                record["latency"],
                elapsed
            )

    except Exception:

        pass

    return record


def active_latency_test(
    records
):

    if not ENABLE_ACTIVE_TEST:

        print(
            "[TEST] "
            "active latency disabled"
        )

        return records

    candidates = sorted(
        records,
        key=lambda x: (
            -len(
                x["sources"]
            ),
            x["latency"]
            if x["latency"]
            is not None
            else 999999,
        )
    )

    candidates = [
        x for x in candidates
        if x.get("ip")
    ][
        :ACTIVE_TEST_LIMIT
    ]

    print(
        f"[TEST] "
        f"active latency: "
        f"{len(candidates)}"
    )

    with ThreadPoolExecutor(
        max_workers=ACTIVE_TEST_WORKERS
    ) as executor:

        futures = [
            executor.submit(
                test_latency,
                record
            )
            for record in candidates
        ]

        for future in as_completed(
            futures
        ):

            try:

                future.result()

            except Exception:

                pass

    return records


# ============================================================
# 最终整理
# ============================================================

def finalize(
    records
):

    for record in records:

        infer_region(
            record
        )

        record[
            "sources"
        ] = sorted(
            set(
                record[
                    "sources"
                ]
            )
        )

        record[
            "isp"
        ] = sorted(
            set(
                record[
                    "isp"
                ]
            )
        )

        record[
            "colo"
        ] = sorted(
            set(
                record[
                    "colo"
                ]
            )
        )

        record[
            "region"
        ] = sorted(
            set(
                record[
                    "region"
                ]
            )
        )

        record[
            "source_count"
        ] = len(
            record[
                "sources"
            ]
        )

        if record[
            "latency"
        ] is not None:

            record[
                "latency"
            ] = round(
                float(
                    record[
                        "latency"
                    ]
                ),
                2
            )

        if record[
            "speed"
        ] is not None:

            record[
                "speed"
            ] = round(
                float(
                    record[
                        "speed"
                    ]
                ),
                2
            )

        record[
            "score"
        ] = calculate_score(
            record
        )

    return sorted(
        records,
        key=lambda x: (
            -x["score"],
            x["latency"]
            if x["latency"]
            is not None
            else 999999,
        )
    )


# ============================================================
# 输出行
# ============================================================

def record_to_line(
    record
):

    ip = record.get(
        "ip"
    )

    domain = record.get(
        "domain"
    )

    if not ip:

        return domain or ""

    port = record.get(
        "port",
        443
    )

    if ":" in ip:

        endpoint = (
            f"[{ip}]:{port}"
        )

    else:

        endpoint = (
            f"{ip}:{port}"
        )

    tags = []

    if record[
        "region"
    ]:

        tags.append(
            "/".join(
                record[
                    "region"
                ]
            )
        )

    if record[
        "isp"
    ]:

        tags.append(
            "/".join(
                record[
                    "isp"
                ]
            )
        )

    if record[
        "colo"
    ]:

        tags.append(
            "/".join(
                record[
                    "colo"
                ]
            )
        )

    if record.get(
        "score"
    ) is not None:

        tags.append(
            f"S{record['score']}"
        )

    if tags:

        return (
            endpoint
            + "#"
            + "|".join(tags)
        )

    return endpoint


# ============================================================
# TXT 输出
# ============================================================

def write_txt(
    path,
    records
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    lines = []

    seen = set()

    for record in records:

        line = record_to_line(
            record
        )

        if not line:
            continue

        if line in seen:
            continue

        seen.add(line)

        lines.append(
            line
        )

    path.write_text(
        "\n".join(lines)
        + (
            "\n"
            if lines
            else ""
        ),
        encoding="utf-8"
    )


# ============================================================
# JSON 输出
# ============================================================

def write_json(
    path,
    data
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# ============================================================
# 输出
# ============================================================

def export_data(
    records
):

    for directory in (
        "ip",
        "domain",
        "region",
        "isp",
        "quality",
    ):

        (
            DATA_DIR
            / directory
        ).mkdir(
            parents=True,
            exist_ok=True
        )

    # --------------------------------------------------------
    # IP
    # --------------------------------------------------------

    ip_records = [
        x for x in records
        if x.get("ip")
    ]

    ipv4 = [
        x for x in ip_records
        if x["version"] == 4
    ]

    ipv6 = [
        x for x in ip_records
        if x["version"] == 6
    ]

    write_txt(
        DATA_DIR
        / "ip/all.txt",
        ip_records
    )

    write_txt(
        DATA_DIR
        / "ip/ipv4.txt",
        ipv4
    )

    write_txt(
        DATA_DIR
        / "ip/ipv6.txt",
        ipv6
    )

    # --------------------------------------------------------
    # Domain
    # --------------------------------------------------------

    domains = [
        x for x in records
        if x.get("domain")
    ]

    write_txt(
        DATA_DIR
        / "domain/all.txt",
        domains
    )

    for count in (
        10,
        20,
        50,
    ):

        write_txt(
            DATA_DIR
            / f"domain/top{count}.txt",
            domains[:count]
        )

    # --------------------------------------------------------
    # Region
    # --------------------------------------------------------

    for region in REGIONS:

        rows = [
            x for x in records
            if region in x[
                "region"
            ]
        ]

        write_txt(
            DATA_DIR
            / "region"
            / f"{region.lower()}.txt",
            rows
        )

    # --------------------------------------------------------
    # ISP
    # --------------------------------------------------------

    for isp in ISPS:

        rows = [
            x for x in records
            if isp in x[
                "isp"
            ]
        ]

        write_txt(
            DATA_DIR
            / "isp"
            / f"{isp.lower()}.txt",
            rows
        )

    # --------------------------------------------------------
    # Quality
    # --------------------------------------------------------

    latency100 = [
        x for x in records
        if (
            x.get("latency")
            is not None
            and x["latency"] <= 100
        )
    ]

    latency200 = [
        x for x in records
        if (
            x.get("latency")
            is not None
            and x["latency"] <= 200
        )
    ]

    speed50 = [
        x for x in records
        if (
            x.get("speed")
            is not None
            and x["speed"] >= 50
        )
    ]

    speed100 = [
        x for x in records
        if (
            x.get("speed")
            is not None
            and x["speed"] >= 100
        )
    ]

    score80 = [
        x for x in records
        if x["score"] >= 80
    ]

    score60 = [
        x for x in records
        if x["score"] >= 60
    ]

    write_txt(
        DATA_DIR
        / "quality/latency100.txt",
        latency100
    )

    write_txt(
        DATA_DIR
        / "quality/latency200.txt",
        latency200
    )

    write_txt(
        DATA_DIR
        / "quality/speed50.txt",
        speed50
    )

    write_txt(
        DATA_DIR
        / "quality/speed100.txt",
        speed100
    )

    write_txt(
        DATA_DIR
        / "quality/score80.txt",
        score80
    )

    write_txt(
        DATA_DIR
        / "quality/score60.txt",
        score60
    )

    # --------------------------------------------------------
    # Source statistics
    # --------------------------------------------------------

    source_stats = {}

    for record in records:

        for source in record[
            "sources"
        ]:

            source_stats[
                source
            ] = (
                source_stats.get(
                    source,
                    0
                )
                + 1
            )

    # --------------------------------------------------------
    # Region statistics
    # --------------------------------------------------------

    region_stats = {}

    for region in REGIONS:

        region_stats[
            region
        ] = sum(
            region in x[
                "region"
            ]
            for x in records
        )

    # --------------------------------------------------------
    # ISP statistics
    # --------------------------------------------------------

    isp_stats = {}

    for isp in ISPS:

        isp_stats[
            isp
        ] = sum(
            isp in x[
                "isp"
            ]
            for x in records
        )

    # --------------------------------------------------------
    # Quality statistics
    # --------------------------------------------------------

    quality = {

        "latency100":
            len(latency100),

        "latency200":
            len(latency200),

        "speed50":
            len(speed50),

        "speed100":
            len(speed100),

        "score80":
            len(score80),

        "score60":
            len(score60),

    }

    # --------------------------------------------------------
    # Index
    # --------------------------------------------------------

    index = {

        "name":
            "CFEdge Collector",

        "version":
            "1.0.0",

        "generated_at":
            time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime()
            ),

        "total":
            len(records),

        "ipv4":
            len(ipv4),

        "ipv6":
            len(ipv6),

        "domains":
            len(domains),

        "sources":
            source_stats,

        "regions":
            region_stats,

        "isp":
            isp_stats,

        "quality":
            quality,

        "records":
            records,

    }

    write_json(
        DATA_DIR
        / "index.json",
        index
    )

    # 单独输出轻量统计文件
    write_json(
        DATA_DIR
        / "stats.json",
        {
            "generated_at":
                index[
                    "generated_at"
                ],

            "total":
                len(records),

            "ipv4":
                len(ipv4),

            "ipv6":
                len(ipv6),

            "domains":
                len(domains),

            "sources":
                source_stats,

            "regions":
                region_stats,

            "isp":
                isp_stats,

            "quality":
                quality,
        }
    )


# ============================================================
# 主程序
# ============================================================

def main():

    print()
    print(
        "=" * 60
    )

    print(
        "CFEdge Collector"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------------------
    # 采集
    # --------------------------------------------------------

    raw_records = collect_all()

    print()
    print(
        f"[COLLECT] "
        f"raw = {len(raw_records)}"
    )

    # --------------------------------------------------------
    # 去重
    # --------------------------------------------------------

    unique_records = deduplicate(
        raw_records
    )

    print(
        f"[DEDUP] "
        f"unique = {len(unique_records)}"
    )

    # --------------------------------------------------------
    # 主动测试
    # --------------------------------------------------------

    unique_records = active_latency_test(
        unique_records
    )

    # --------------------------------------------------------
    # 最终整理
    # --------------------------------------------------------

    final_records = finalize(
        unique_records
    )

    # --------------------------------------------------------
    # 输出
    # --------------------------------------------------------

    export_data(
        final_records
    )

    print()
    print(
        "=" * 60
    )

    print(
        f"TOTAL   : {len(final_records)}"
    )

    print(
        "IPv4    : "
        f"{sum(x['version'] == 4 for x in final_records)}"
    )

    print(
        "IPv6    : "
        f"{sum(x['version'] == 6 for x in final_records)}"
    )

    print(
        "Score>=80: "
        f"{sum(x['score'] >= 80 for x in final_records)}"
    )

    print(
        "Score>=60: "
        f"{sum(x['score'] >= 60 for x in final_records)}"
    )

    print(
        "=" * 60
    )


if __name__ == "__main__":

    main()
