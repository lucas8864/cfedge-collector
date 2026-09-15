对，上一版 README 的代码块确实有嵌套 ``` 导致提前闭合。

下面给你一份**已经修正的完整 `README.md`**。我把 README 内部所有示例代码块统一改成 **四个反引号 ` ```` `**，这样可以安全包含三反引号代码示例。

直接覆盖即可：

# CFEdge Collector

CFEdge Collector 是一个轻量级 Cloudflare IP / Domain 数据聚合工具。

项目从多个公开数据源获取 Cloudflare IP、IPv6、域名及部分测速信息，统一转换为标准数据结构，并进行去重、来源合并、区域归类、运营商归类和质量评分。

项目主要用于：

* Cloudflare IP 数据聚合
* Cloudflare IPv4 / IPv6 收集
* Cloudflare 优选 IP 数据整理
* Cloudflare 优选域名整理
* 多来源数据去重
* 来源交叉验证
* 延迟 / 速度 / 来源数量评分
* GitHub Actions 自动更新
* 为后续 Cloudflare Workers / Pages API 提供静态数据

---

## 一、项目特点

### 1. 多来源

| Source      | 类型       | 数据                                 |
| ----------- | -------- | ---------------------------------- |
| vvhan       | JSON     | IPv4 / IPv6 / 延迟 / 速度 / ISP / Colo |
| nirevil     | JSON     | IPv4 / IPv6 / 延迟 / 速度等             |
| mingyu      | TXT      | IPv4 / IPv6                        |
| gslege      | TXT      | IPv4 / IPv6 / 区域                   |
| zhixuanwang | HTML/TXT | IP                                 |
| vps789      | Web      | Domain                             |
| xinyitang   | VLESS    | IP / Domain                        |
| tiancheng   | VLESS    | IP / Domain                        |

`wetest` 不作为数据源。

---

## 二、数据处理流程

```text
                 ┌───────────────┐
                 │ Cloudflare IP │
                 │ Domain Sources│
                 └───────┬───────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Source Parsers  │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Normalize       │
                │ IP / IPv6 / DNS │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Deduplicate     │
                │ IP + Port       │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Merge Sources   │
                │ ISP / Colo      │
                │ Region / Speed  │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Quality Score   │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ data/           │
                └─────────────────┘
```

---

## 三、目录结构

```text
cfedge-collector/
├── collector.py
├── requirements.txt
├── README.md
│
├── .github/
│   └── workflows/
│       └── collector.yml
│
└── data/
    ├── index.json
    ├── stats.json
    │
    ├── ip/
    │   ├── all.txt
    │   ├── ipv4.txt
    │   └── ipv6.txt
    │
    ├── domain/
    │   ├── all.txt
    │   ├── top10.txt
    │   ├── top20.txt
    │   └── top50.txt
    │
    ├── region/
    │   ├── HK.txt
    │   ├── JP.txt
    │   ├── SG.txt
    │   ├── US.txt
    │   └── ...
    │
    ├── isp/
    │   ├── CM.txt
    │   ├── CU.txt
    │   └── CT.txt
    │
    ├── quality/
    │   ├── latency100.txt
    │   ├── latency200.txt
    │   ├── speed50.txt
    │   ├── speed100.txt
    │   ├── score60.txt
    │   └── score80.txt
    │
    └── source/
        ├── vvhan.txt
        ├── nirevil_v4.txt
        ├── nirevil_v6.txt
        ├── mingyu_v4.txt
        ├── mingyu_v6.txt
        └── ...
```

---

## 四、标准数据结构

IP 数据：

```json
{
  "ip": "1.2.3.4",
  "domain": null,
  "version": 4,
  "port": 443,
  "sources": [
    "vvhan",
    "nirevil_v4"
  ],
  "source_count": 2,
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
  "score": 75
}
```

Domain 数据：

```json
{
  "ip": null,
  "domain": "example.com",
  "version": null,
  "port": 443,
  "sources": [
    "vps789"
  ],
  "source_count": 1,
  "isp": [],
  "colo": [],
  "region": [],
  "latency": null,
  "speed": null,
  "score": 5
}
```

---

## 五、去重规则

IP 使用：

```text
IP + Port
```

例如：

```text
1.2.3.4:443
```

只保留一条。

如果同一个 IP 同时出现在：

```text
vvhan
nirevil
mingyu
gslege
```

则合并为：

```json
{
  "ip": "1.2.3.4",
  "sources": [
    "vvhan",
    "nirevil_v4",
    "mingyu_v4",
    "gslege_speed"
  ],
  "source_count": 4
}
```

---

## 六、测速数据合并规则

如果多个来源提供延迟：

```text
82ms
105ms
91ms
```

采用最小值：

```text
82ms
```

速度：

```text
80Mbps
126Mbps
110Mbps
```

采用最大值：

```text
126Mbps
```

如果来源没有测速数据，则保持为空，不人为填充 `0`。

---

## 七、区域判断

区域判断优先级：

```text
1. 数据源明确提供 region
2. 数据源备注 / 标签
3. Cloudflare Colo
4. 无法判断则 UNKNOWN
```

示例：

```text
HKG -> HK
TPE -> TW
NRT -> JP
KIX -> JP
SIN -> SG
ICN -> KR
LAX -> US
SJC -> US
FRA -> DE
AMS -> NL
LHR -> UK
CDG -> FR
SYD -> AU
```

---

## 八、GSlege 数据

GSlege 当前包含：

```text
Cfxyz.txt
JP.txt
NL.txt
US.txt
DE.txt
SG.txt
```

其中：

```text
JP.txt -> JP
NL.txt -> NL
US.txt -> US
DE.txt -> DE
SG.txt -> SG
```

而：

```text
Cfxyz.txt
```

只作为普通优选 IP / 速度来源处理。

不会因为文件名 `Cfxyz` 自动判断为中国大陆。

---

## 九、质量评分

最高分：

```text
100
```

### 延迟

```text
<= 50ms   +40
<= 100ms  +30
<= 150ms  +20
<= 200ms  +10
```

### 速度

```text
>= 200Mbps  +40
>= 100Mbps  +30
>= 50Mbps   +20
>= 10Mbps   +10
```

### 来源数量

```text
>= 5   +20
>= 3   +15
== 2   +10
== 1   +5
```

最终：

```text
score <= 100
```

---

## 十、输出格式

例如：

```text
1.2.3.4:443#HK|CM|HKG|82ms|126.5mbps|S75
```

IPv6：

```text
[2606:4700::1111]:443#US|UNKNOWN|LAX|-|-|S5
```

Domain：

```text
example.com:443#UNKNOWN|UNKNOWN|UNKNOWN|-|-|S5
```

字段结构：

```text
HOST:PORT
#
REGION
|
ISP
|
COLO
|
LATENCY
|
SPEED
|
SCORE
```

---

## 十一、本地运行

推荐使用 Python 虚拟环境。

```bash
cd ~/cfedge-collector

python3 -m venv .venv

. .venv/bin/activate

python -m pip install --upgrade pip

python -m pip install -r requirements.txt

python -m playwright install chromium

python -m playwright install-deps chromium

python collector.py
```

---

## 十二、查看结果

查看统计：

```bash
cat data/stats.json
```

查看 IPv4：

```bash
cat data/ip/ipv4.txt
```

查看 IPv6：

```bash
cat data/ip/ipv6.txt
```

查看 Domain：

```bash
cat data/domain/all.txt
```

查看高质量节点：

```bash
cat data/quality/score80.txt
```

查看低延迟节点：

```bash
cat data/quality/latency100.txt
```

查看单个数据源：

```bash
cat data/source/vvhan.txt
```

---

## 十三、检查各数据源

可以直接执行：

```bash
python - <<'PY'
import json

with open("data/stats.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for name, item in data.get("sources", {}).items():
    print(
        f"{name}: "
        f"status={item.get('status')} "
        f"records={item.get('records', 0)} "
        f"elapsed={item.get('elapsed', 0)}s"
    )
PY
```

正常情况下会看到：

```text
vvhan: status=ok records=500 elapsed=1.2s
nirevil_v4: status=ok records=300 elapsed=0.8s
nirevil_v6: status=ok records=120 elapsed=0.6s
mingyu_v4: status=ok records=100 elapsed=0.5s
```

如果出现：

```text
vps789: status=error records=0
```

说明该数据源本轮采集失败。

如果出现：

```text
mingyu_v4: status=ok records=0
```

说明 HTTP 请求成功，但是没有解析到有效 IP，需要针对该数据源检查上游格式。

---

## 十四、GitHub Actions

项目包含：

```text
.github/workflows/collector.yml
```

默认每小时运行两次：

```text
17 分
47 分
```

也可以在 GitHub 中手动执行：

```text
Actions
→ CFEdge Collector
→ Run workflow
```

---

## 十五、Actions 自动提交

采集完成后执行：

```text
collector.py
      ↓
data/
      ↓
git add data/
      ↓
git commit
      ↓
git pull --rebase
      ↓
git push
```

因此 GitHub 仓库中的 `data/` 会自动保持最新。

---

## 十六、数据源失败不会影响其他来源

程序采用独立 Source 处理。

例如：

```text
vvhan          OK
nirevil_v4     OK
nirevil_v6     OK
mingyu_v4      OK
mingyu_v6      OK
gslege_speed   OK
gslege_jp      OK
gslege_nl      OK
gslege_us      OK
gslege_de      OK
gslege_sg      OK
zhixuanwang    OK
vps789         ERROR
xinyitang      OK
tiancheng      OK
```

即使 `vps789` 失败，也不会导致其他数据源停止。

---

## 十七、数据质量设计

项目不会为了让数据看起来完整而虚构测速数据。

例如来源只提供：

```text
1.2.3.4
```

则：

```text
latency = null
speed   = null
```

而不是：

```text
latency = 0
speed   = 0
```

这样可以区分：

* 真正测速结果
* 没有测速数据
* 数据源解析失败

---

## 十八、后续扩展

当前项目负责：

```text
采集
 ↓
清洗
 ↓
去重
 ↓
合并
 ↓
评分
 ↓
静态数据
```

后续可以增加 Cloudflare Workers API：

```text
/api/ip
/api/ipv4
/api/ipv6
/api/domain
/api/top
/api/region/HK
/api/region/JP
/api/isp/CM
```

也可以直接把：

```text
data/ip/ipv4.txt
data/ip/ipv6.txt
data/domain/top10.txt
```

作为其他系统的数据源。

---

## 十九、注意事项

1. 数据源均为公开网络数据。
2. 上游数据源格式可能随时间变化。
3. 某个数据源为空不代表整个项目失败。
4. `latency` / `speed` 没有来源数据时保持为空。
5. Region 无法确认时使用 `UNKNOWN`。
6. `Cfxyz.txt` 不自动判断为中国大陆。
7. 默认不执行主动测速。
8. GitHub Actions 负责采集和提交数据。
9. 后续可以将 `data/` 接入 Cloudflare Workers / Pages。
10. 对于动态网页数据源，解析器可能需要根据上游页面变化进行调整。

---

## License

仅用于技术研究、数据整理和自动化实验。

这版不会再出现 README 内部代码块把外层代码块提前关闭的问题。

