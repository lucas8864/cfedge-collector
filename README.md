# CFEdge Collector

一个轻量级的 Cloudflare Edge IP / Domain 数据采集、聚合、去重、测速信息整理与 API 发布项目。

项目通过多个公开数据源获取 Cloudflare IP、IPv4、IPv6、节点域名、区域、ISP、Colo、延迟、速度等信息，统一标准化后进行去重和合并，并生成 TXT / JSON 数据。

项目设计目标：

* 多来源统一采集
* IP 自动去重
* 多来源数据自动合并
* 区域 / ISP / Colo 分类
* 延迟、速度、来源数量评分
* 自动生成 IPv4 / IPv6 数据
* 自动生成区域数据
* 自动生成 ISP 数据
* 自动生成质量筛选数据
* GitHub Actions 自动更新
* Cloudflare Worker 提供 API
* 尽量保持 Python 单文件、低依赖、易维护

---

## 1. 项目结构

```text
cfedge-collector/
├── collector.py
├── requirements.txt
├── .gitignore
├── README.md
│
├── data/
│   ├── index.json
│   ├── stats.json
│   │
│   ├── ip/
│   │   ├── all.txt
│   │   ├── ipv4.txt
│   │   └── ipv6.txt
│   │
│   ├── domain/
│   │   ├── all.txt
│   │   ├── top10.txt
│   │   ├── top20.txt
│   │   └── top50.txt
│   │
│   ├── region/
│   │   ├── hk.txt
│   │   ├── tw.txt
│   │   ├── jp.txt
│   │   ├── sg.txt
│   │   ├── kr.txt
│   │   ├── us.txt
│   │   ├── de.txt
│   │   ├── nl.txt
│   │   ├── uk.txt
│   │   ├── fr.txt
│   │   └── au.txt
│   │
│   ├── isp/
│   │   ├── cm.txt
│   │   ├── cu.txt
│   │   └── ct.txt
│   │
│   └── quality/
│       ├── latency100.txt
│       ├── latency200.txt
│       ├── speed50.txt
│       ├── speed100.txt
│       ├── score60.txt
│       └── score80.txt
│
├── .github/
│   └── workflows/
│       └── collector.yml
│
└── worker/
    ├── index.js
    └── wrangler.toml
```

核心采集逻辑全部集中在：

```text
collector.py
```

不拆分成大量 Python 模块，方便部署、修改和维护。

---

# 2. 工作流程

```text
                ┌──────────────────┐
                │    多个公开数据源   │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │    collector.py  │
                │     数据采集       │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │    数据标准化       │
                │ IP / Domain / ISP │
                │ Region / Colo     │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │      IP 去重       │
                │   多来源数据合并    │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │    质量评分        │
                │ Latency / Speed   │
                │ Source Count      │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │     data/         │
                │ TXT + JSON        │
                └────────┬─────────┘
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
      GitHub Actions          Cloudflare Worker
       自动定时更新               API / 静态数据
```

---

# 3. 数据来源

当前支持多个公开数据源。

主要包括：

| Source      | 类型           | 数据                                      |
| ----------- | ------------ | --------------------------------------- |
| vvhan       | API          | IP / IPv4 / IPv6 / ISP / Colo / 延迟 / 速度 |
| nirevil     | JSON         | IPv4 / IPv6 / Colo / 延迟 / 速度            |
| mingyu      | TXT          | IPv4 / IPv6                             |
| gslege      | TXT          | IPv4 / 地区                               |
| zhixuanwang | HTML         | Cloudflare IP                           |
| vps789      | HTML         | Cloudflare IP / Domain                  |
| wetest      | HTML         | Cloudflare IP / 优选地址                    |
| xinyitang   | Base64/VLESS | IP / Domain / Port / Region             |
| tiancheng   | Base64/VLESS | IP / Domain / Port / Region             |

数据源定义位于：

```python
SOURCE_URLS
```

可以直接在：

```text
collector.py
```

中增加或修改数据源。

---

# 4. 数据统一格式

内部统一使用类似以下结构：

```json
{
  "ip": "1.2.3.4",
  "version": 4,
  "port": 443,
  "sources": [
    "vvhan",
    "nirevil",
    "mingyu"
  ],
  "isp": [
    "CM"
  ],
  "colo": [
    "HKG"
  ],
  "region": [
    "HK"
  ],
  "latency": 82,
  "speed": 126.5,
  "source_count": 3,
  "score": 85
}
```

字段说明：

| 字段           | 说明              |
| ------------ | --------------- |
| ip           | IP 地址           |
| version      | IP 版本，4 或 6     |
| port         | 端口              |
| sources      | 数据来源            |
| isp          | ISP             |
| colo         | Cloudflare Colo |
| region       | 国家 / 地区         |
| latency      | 延迟，单位 ms        |
| speed        | 速度              |
| source_count | 被多少数据源收录        |
| score        | 综合评分            |

---

# 5. IP 去重

项目使用 IP 地址作为核心唯一标识。

例如：

```text
1.2.3.4
```

同时出现在：

```text
vvhan
nirevil
mingyu
gslege
```

最终只保留一条记录：

```json
{
  "ip": "1.2.3.4",
  "sources": [
    "vvhan",
    "nirevil",
    "mingyu",
    "gslege"
  ],
  "source_count": 4
}
```

这样可以避免不同数据源产生大量重复 IP。

---

# 6. 数据合并规则

同一个 IP 从多个来源获取数据后自动合并。

## Source

所有来源进行合并：

```text
vvhan
nirevil
mingyu
```

最终：

```json
"sources": [
  "vvhan",
  "nirevil",
  "mingyu"
]
```

---

## ISP

ISP 自动去重。

支持：

```text
CM = China Mobile
CU = China Unicom
CT = China Telecom
```

---

## Colo

例如：

```text
HKG
NRT
SIN
LAX
FRA
```

自动去重。

---

## Region

优先使用数据源提供的区域。

如果没有明确区域，则根据 Cloudflare Colo 推断。

例如：

```text
HKG → HK
NRT → JP
SIN → SG
ICN → KR
LAX → US
FRA → DE
```

---

## Latency

多个来源存在延迟数据时：

```text
取最低延迟
```

例如：

```text
vvhan     82ms
nirevil   96ms
wetest    71ms
```

最终：

```text
71ms
```

---

## Speed

多个来源存在速度数据时：

```text
取最高速度
```

例如：

```text
vvhan     126.5
nirevil   88.2
wetest    151.3
```

最终：

```text
151.3
```

---

# 7. 综合评分

当前评分最高：

```text
100
```

评分由三个部分组成。

## 延迟

```text
≤ 50ms    +40
≤ 100ms   +30
≤ 150ms   +20
≤ 200ms   +10
```

## 速度

```text
≥ 200     +40
≥ 100     +30
≥ 50      +20
≥ 10      +10
```

## 来源数量

```text
≥ 5       +20
≥ 3       +15
= 2       +10
= 1       +5
```

最终限制：

```text
0 - 100
```

例如：

```text
Latency     82ms   → +30
Speed       126    → +30
Source      4      → +15

Score = 75
```

---

# 8. 输出数据

## IPv4

```text
data/ip/ipv4.txt
```

包含全部 IPv4 数据。

---

## IPv6

```text
data/ip/ipv6.txt
```

包含全部 IPv6 数据。

---

## 全部 IP

```text
data/ip/all.txt
```

同时包含 IPv4 和 IPv6。

---

# 9. 区域数据

区域文件位于：

```text
data/region/
```

例如：

```text
hk.txt
tw.txt
jp.txt
sg.txt
kr.txt
us.txt
de.txt
nl.txt
uk.txt
fr.txt
au.txt
```

例如：

```text
data/region/hk.txt
```

只包含香港相关节点。

---

# 10. ISP 数据

ISP 文件位于：

```text
data/isp/
```

包括：

```text
cm.txt
cu.txt
ct.txt
```

对应：

```text
CM = 中国移动
CU = 中国联通
CT = 中国电信
```

---

# 11. 质量筛选

质量数据位于：

```text
data/quality/
```

包括：

```text
latency100.txt
latency200.txt

speed50.txt
speed100.txt

score60.txt
score80.txt
```

例如：

```text
latency100.txt
```

表示：

```text
Latency <= 100ms
```

而：

```text
score80.txt
```

表示：

```text
Score >= 80
```

---

# 12. Domain 数据

域名数据位于：

```text
data/domain/
```

包括：

```text
all.txt
top10.txt
top20.txt
top50.txt
```

域名按照来源、出现次数等信息进行统计。

例如：

```text
example.pages.dev
example.workers.dev
```

---

# 13. JSON 数据

完整数据：

```text
data/index.json
```

示例：

```json
{
  "generated_at": "2026-09-15T00:00:00Z",
  "total": 1000,
  "ipv4": 950,
  "ipv6": 50,
  "records": []
}
```

统计数据：

```text
data/stats.json
```

用于快速查看当前数据规模。

---

# 14. 本地运行

## 14.1 安装 Python

建议：

```text
Python 3.10+
```

推荐：

```text
Python 3.12
```

检查：

```bash
python3 --version
```

---

## 14.2 安装依赖

```bash
python3 -m pip install -r requirements.txt
```

---

## 14.3 执行采集

```bash
python3 collector.py
```

执行完成后：

```text
data/
```

会生成新的数据。

---

# 15. 使用虚拟环境

Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python collector.py
```

Windows：

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python collector.py
```

---

# 16. 环境变量

默认配置：

```text
HTTP_TIMEOUT=20
ENABLE_ACTIVE_TEST=false
ACTIVE_TEST_LIMIT=300
ACTIVE_TEST_WORKERS=32
```

例如：

```bash
HTTP_TIMEOUT=30 python3 collector.py
```

---

# 17. 主动延迟测试

默认：

```text
ENABLE_ACTIVE_TEST=false
```

原因是：

* 数据源已经提供延迟时没有必要重复测试
* 大量 IP 主动测试会增加 GitHub Actions 执行时间
* Cloudflare IP 的 HTTPS 直接 IP 测试存在 SNI / TLS 问题
* 免费 GitHub Actions 不适合高频大规模主动测速

如果需要开启：

```bash
ENABLE_ACTIVE_TEST=true python3 collector.py
```

可以设置：

```bash
ACTIVE_TEST_LIMIT=300
ACTIVE_TEST_WORKERS=32
```

例如：

```bash
ENABLE_ACTIVE_TEST=true \
ACTIVE_TEST_LIMIT=200 \
ACTIVE_TEST_WORKERS=32 \
python3 collector.py
```

---

# 18. 禁用数据源

可以通过环境变量关闭指定数据源。

例如：

```bash
DISABLED_SOURCES="vps789,wetest" python3 collector.py
```

多个数据源使用：

```text
,
```

分隔。

例如：

```bash
DISABLED_SOURCES="vps789,wetest,xinyitang,tiancheng"
```

---

# 19. GitHub Actions

项目提供：

```text
.github/workflows/collector.yml
```

默认每小时执行两次：

```text
17 分
47 分
```

也就是：

```text
17 * * * *
47 * * * *
```

执行流程：

```text
Checkout
   ↓
安装 Python
   ↓
安装 requirements
   ↓
运行 collector.py
   ↓
生成 data/
   ↓
检查数据变化
   ↓
自动 git commit
   ↓
自动 git push
```

---

# 20. 手动执行 GitHub Actions

进入 GitHub：

```text
Actions
```

选择：

```text
CFEdge Collector
```

然后：

```text
Run workflow
```

即可立即运行。

---

# 21. GitHub Actions 权限

Workflow 使用：

```yaml
permissions:
  contents: write
```

因此 Action 可以自动提交：

```text
data/
```

如果仓库权限设置正常，不需要额外配置 GitHub Token。

---

# 22. Cloudflare Worker API

项目提供一个非常轻量的 Worker。

目录：

```text
worker/
```

文件：

```text
worker/index.js
worker/wrangler.toml
```

Worker 不负责采集数据。

它只负责：

```text
读取 data/
       ↓
HTTP API
       ↓
返回 JSON / TXT
```

因此不会增加采集端复杂度。

---

# 23. Worker API

部署后：

```text
/api
```

返回完整 API 信息。

---

## 完整数据

```text
/api/index
```

对应：

```text
data/index.json
```

---

## 统计信息

```text
/api/stats
```

对应：

```text
data/stats.json
```

---

## IPv4

```text
/api/ipv4
```

对应：

```text
data/ip/ipv4.txt
```

---

## IPv6

```text
/api/ipv6
```

对应：

```text
data/ip/ipv6.txt
```

---

## 全部 IP

```text
/api/ip
```

对应：

```text
data/ip/all.txt
```

---

# 24. 区域 API

例如：

```text
/api/region/hk
/api/region/tw
/api/region/jp
/api/region/sg
/api/region/kr
/api/region/us
/api/region/de
/api/region/nl
```

---

# 25. ISP API

例如：

```text
/api/isp/cm
/api/isp/cu
/api/isp/ct
```

---

# 26. 质量 API

例如：

```text
/api/quality/latency100
/api/quality/latency200
/api/quality/speed50
/api/quality/speed100
/api/quality/score60
/api/quality/score80
```

---

# 27. Domain API

例如：

```text
/api/domain/all
/api/domain/top10
/api/domain/top20
/api/domain/top50
```

---

# 28. Cloudflare Worker 部署

进入 Worker 目录：

```bash
cd worker
```

安装 Wrangler：

```bash
npm install -g wrangler
```

登录：

```bash
wrangler login
```

部署：

```bash
wrangler deploy
```

具体部署参数以当前 Wrangler 版本为准。

---

# 29. 数据更新模式

推荐使用：

```text
GitHub Actions
        │
        ▼
collector.py
        │
        ▼
data/
        │
        ▼
git commit
        │
        ▼
GitHub Repository
        │
        ▼
Cloudflare Worker
        │
        ▼
API / TXT
```

这样采集和访问完全分离。

---

# 30. 为什么不直接使用数据库

本项目默认不使用：

```text
MySQL
PostgreSQL
Redis
D1
MongoDB
```

原因是当前数据属于：

```text
批量采集
→ 批量计算
→ 批量生成
→ 静态读取
```

因此直接生成：

```text
TXT
JSON
```

更加简单。

同时：

* GitHub 可以保存历史数据
* Cloudflare 可以直接缓存
* Worker 不需要数据库连接
* 部署成本低
* 维护简单

---

# 31. 数据缓存

Worker 返回的数据设置缓存响应头。

因此大量用户请求：

```text
/api/ipv4
```

不会要求 Worker 每次重新生成数据。

采集任务和用户访问完全解耦。

---

# 32. 数据源异常处理

单个数据源失败不会导致整个采集任务失败。

例如：

```text
vvhan       SUCCESS
nirevil     SUCCESS
mingyu      SUCCESS
gslege      FAILED
wetest      SUCCESS
```

最终仍然会生成数据。

失败的数据源只会影响自身的数据。

这样可以避免因为一个上游网站临时不可访问导致整个任务失败。

---

# 33. 数据源变化

公开网站的 HTML / JSON / Base64 / API 格式可能发生变化。

如果某个数据源出现：

```text
0 records
```

或者：

```text
parse failed
```

优先检查：

```text
collector.py
```

对应的：

```python
collect_xxx()
```

函数。

不需要修改项目整体架构。

---

# 34. 添加新数据源

只需要在：

```text
collector.py
```

增加：

```python
SOURCE_URLS
```

以及对应：

```python
collect_xxx()
```

然后在：

```python
collect_all()
```

中加入。

最终统一返回：

```python
{
    "ip": "...",
    "port": 443,
    "source": "...",
    "isp": [],
    "colo": [],
    "region": [],
    "latency": None,
    "speed": None
}
```

之后由统一处理流程自动完成：

```text
标准化
↓
去重
↓
合并
↓
区域推断
↓
评分
↓
输出
```

---

# 35. 设计原则

本项目刻意保持简单。

核心原则：

```text
一个 Python 核心脚本
+
一个 requirements.txt
+
GitHub Actions
+
静态数据
+
可选 Cloudflare Worker
```

不引入不必要的：

```text
数据库
消息队列
Redis
Celery
FastAPI
Django
Node.js 后端
```

---

# 36. 项目适用场景

可以作为：

* Cloudflare IP 数据聚合
* Cloudflare 优选 IP 数据源
* IPv4 / IPv6 数据接口
* 区域 IP 数据接口
* ISP IP 数据接口
* Cloudflare 节点筛选
* 延迟筛选
* 速度筛选
* VLESS / Clash / sing-box 数据源的上游数据
* 其他订阅生成项目的 IP 数据后端

---

# 37. 注意事项

本项目只负责：

```text
数据采集
数据整理
数据分类
数据评分
数据发布
```

不负责：

```text
代理服务端
VLESS 服务端
Trojan 服务端
Shadowsocks 服务端
节点转发
流量代理
```

因此它可以独立运行，也可以作为其他代理订阅项目的数据源。

---

# 38. License

本项目代码部分可根据实际需要采用开源许可证。

项目所采集的数据来自第三方公开来源。

使用第三方数据时，应遵守对应网站的：

```text
Terms of Service
Robots Policy
API 使用规则
```

项目本身不对第三方数据的准确性、稳定性和持续可用性作保证。

---

# 39. 快速开始

最简单的运行方式：

```bash
git clone https://github.com/lucas8864/cfedge-collector.git
cd cfedge-collector

python3 -m pip install -r requirements.txt

python3 collector.py
```

查看结果：

```bash
cat data/stats.json
```

查看 IPv4：

```bash
head -20 data/ip/ipv4.txt
```

查看 IPv6：

```bash
head -20 data/ip/ipv6.txt
```

查看高质量节点：

```bash
head -20 data/quality/score80.txt
```

---

# 40. 最终架构

```text
                 Internet
                    │
          ┌─────────┴─────────┐
          │   Public Sources  │
          └─────────┬─────────┘
                    │
                    ▼
             ┌─────────────┐
             │ collector.py│
             └──────┬──────┘
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
      IP          Domain       Metadata
       │            │            │
       └────────────┼────────────┘
                    ▼
              Normalize
                    │
                    ▼
              Deduplicate
                    │
                    ▼
                 Merge
                    │
                    ▼
                 Score
                    │
                    ▼
              ┌───────────┐
              │   data/   │
              └─────┬─────┘
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
       GitHub              Worker
          │                   │
          │                   ▼
          │               HTTP API
          │
          ▼
   GitHub Actions
   Automatic Update
```

**核心目标：**

> 用尽可能少的代码，把多个 Cloudflare IP / Domain 数据源统一成一个标准化、可自动更新、可直接通过 TXT / JSON / API 使用的数据源。

