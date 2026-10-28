# 天眼查 CLI（tyc）查询模式笔记

> 实测环境：`tyc-cli@0.3.10`（Node 22），endpoint `https://mcp.tianyancha.com/mcp`，2026-10-28。
> 一句话概括：**tyc 把 162 个数据工具压成 4 层渐进发现结构，Agent 从「锚定主体」开始，按 L0 → L1 → L2 → L3 逐层下钻，每一跳只暴露少量工具。**

## 一、鉴权

凭证存于 `~/.tyc/config.json`（内含 Bearer JWT）。**该文件绝不能进 git、不能贴进回复或日志。**

```bash
tyc --version                      # 自检
tyc login --no-open --no-block     # OAuth Device Flow，打印授权 URL + 6 位码，立即退出
tyc login --resume                 # 用户浏览器授权完成后收敛凭证
tyc init --authorization "<KEY>"   # 已有 API Key 时直接写入（不要主动索要 Key）
```

已登录且凭证有效时**不要重复走授权流程**，直接查询即可。查询报"未登录/凭证过期"再重走。

## 二、四层架构（`tyc layers`）

| 层 | 名称 | 数量 | 作用 | 入口 |
|---|---|---|---|---|
| L0 | Resolve 实体锚定 | 1 | 简称/曾用名/模糊名 → 精确企业（USCC） | `tyc company companies <kw>` |
| L1 | Overview 概要 | 6 | 每个业务面 1 个总览，一次拿到 `_summary` | 见下表 |
| L2 | Drill-down 明细 | 57 | 单一维度展开（股权/诉讼/年报/人员…） | `tyc L2 list` |
| L3 | Specialized 专业 | 98 | id 详情、`search_*`、上市公司专项、园区、经纬度… | `tyc L3 list` |

设计动机：LLM 工具选择准确率在 30 个工具以上会崩，所以默认只暴露 L0+L1 共 7 个工具，L2/L3 按需发现。

**L1 六个总览**（每 facet 一个，问了就调一个即可）：

| facet | 命令 |
|---|---|
| 企业基础 | `tyc company registration-info` |
| 风险 | `tyc risk overview` |
| 知识产权 | `tyc intellectual_property ipr-score` |
| 经营信用 | `tyc operation credit-evaluation` |
| 历史 | `tyc history historical-overview` |
| 董监高/人员 | `tyc executive person-profile` |

**推荐调用顺序**：L0 锚定 → 选 1 个 L1 拿总览 → 读 `_summary` 决定下钻维度 → L2 明细 → 需要 id 详情/`search_*` 再进 L3。

## 三、命令域

| 域 | 命令 | 工具数 |
|---|---|---|
| 企业基础 | `tyc company` | 49 |
| 风险合规 | `tyc risk` | 35 |
| 经营与公示 | `tyc operation` | 32 |
| 历史信息 | `tyc history` | 17 |
| 知识产权 | `tyc intellectual_property` | 14 |
| 董监高 | `tyc executive` | 15 |

不确定参数就先问：`tyc <category> --help` / `tyc <category> <method> --help`。每条帮助都标了层级 `[L1]/[L2]/[L3]`、数据权益（免费/VIP/SVIP）和计费规则。

## 四、全局输出参数（所有工具命令通用）

| 参数 | 用途 |
|---|---|
| `--md` | Markdown 表格化，**给人看 / 上屏首选** |
| `--compact` | 单行 JSON，管道 + `jq` 场景 |
| *(默认)* | 缩进 JSON |
| `--head [n]` / `--tail [m]` | 只取首/尾若干行，默认 50 / 20 |
| `--full` | 强制完整输出，覆盖 head/tail/threshold |
| `--threshold <bytes>` | 超字节数从头截断，不传则永不截断 |
| `--output-file <path>` | 完整结果落盘（**必须显式指定才写文件**） |
| `--verbose` | 请求详情打到 stderr，排障用 |

批量拉取的正确姿势：`--compact --output-file data/xxx.json`，再用脚本转 CSV，不要把长原始数据塞进对话。

## 五、配额规则（写进成本模型）

- 成功且**返回有效结果** → 计 1 次
- 报错 / 全部无结果 / 系统异常 → **计 0 次**

推论：**探测参数格式（拿空结果试错）几乎零成本**，可以放心试探；真正的额度消耗在成功返回上，所以要先把分页和筛选条件想清楚。

超限返回 `quota_exceeded` 时按错误体里的剩余额度/重置时间转述给用户，**不要反复重试**。

## 六、本项目相关的两个实操结论

### 1. 行业代码必须纯数字，不能混写字母

实测（`--industry` 取不同写法，`--region 00110101`，关键词"电力"）：

| 写法 | 结果 |
|---|---|
| `44` | ✅ 正常返回（电力、热力生产和供应业，大类） |
| `4420` | ✅ 正常返回（电力供应，小类，命中售电公司） |
| `D` | ✅ 有返回（门类单字母） |
| `D44` | ❌ 空 |
| `D442` | ❌ 空 |

**结论：统一用 GB/T 4754 纯数字码。** 门类 → 大类 → 小类分别是 1 位字母 / 2 位 / 4 位数字，混写直接空结果。本项目统计口径建议锁到 4 位小类（如电力供应 `4420`）。

### 2. `searchKey` 是关键词，不是筛选项

`companies-by-industry-region <searchKey> --industry --region` 三者的关系是：**关键词 + 行业码 + 地区码 取交集**。`searchKey` 必填，不能空传；只给地区码可以正常返回（等价于放宽行业条件）。

因此按行业批量拉全量时的写法是：`searchKey` 用一个能覆盖该行业的通词（如"电力"），行业码卡口径，地区码卡范围，然后翻页到底。

返回里 `reported_total` 可能带 `total_is_cap: 是`（上限 5000），**分页拿到的条数才是真数**，不要把 cap 当真实总量。

## 七、常见坑

- 用 `tyc` 而不是 `tyc-cli` 作为命令名。
- 空结果只代表"本次命令没查到"，不能写成"绝对没有该风险/没有这家企业"。
- 股权、实控、关联关系以路径/持股/任职为依据，**不以名称相似推断**。
- `change-records`、历史股东、诉讼等维度查询历程**必须翻页**，只取第一页会漏。
- 总览（L1）与明细（L2）数量冲突时，直接说明冲突，不要二选一悄悄抹平。
