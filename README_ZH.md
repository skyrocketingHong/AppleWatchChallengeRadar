<p align="center">
  <a href="README.md">English</a> | 简体中文
</p>

<h1 align="center">AppleWatchChallengeRadar</h1>

<p align="center">
  面向 Apple Watch 限定挑战的双源监控、ICS 日历订阅与变更通知服务
</p>

<p align="center">
  <a href="https://github.com/skyrocketingHong/AppleWatchChallengeRadar/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/skyrocketingHong/AppleWatchChallengeRadar/ci.yml?branch=main&amp;label=CI" alt="CI 状态"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.11 或更高版本">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue" alt="AGPL-3.0 许可证"></a>
</p>

AppleWatchChallengeRadar 持续监控 Apple MobileAsset 中的 Apple Watch 限定挑战定义，将来自 Current 与 Legacy 数据源的信息规范化、合并并写入 SQLite；随后生成可订阅的 ICS 日历，并在挑战新增、业务规则变更或未来挑战撤回时推送通知。

服务以 systemd timer 触发的一次性任务运行，无需常驻 Web 进程。它适合部署在 Debian/Ubuntu 服务器上，通过现有 Caddy 静态托管日历文件。

## 核心特性

- 将 Current 与 Legacy 两套 MobileAsset 数据源隔离处理；单一源失败不会影响另一源或已保存的数据。
- 以统一的 Canonical Challenge Model 管理挑战标识、日期、地区范围、完成条件与触发器。
- 按“人工 Override → Current → Legacy → 推导”进行字段级合并，并记录可追溯的冲突。
- 将 Predicate 规则转换为可读中文条件，例如 <code>workout.duration &gt;= 1170</code> 会显示为“完成至少 20 分钟任意锻炼”。
- 生成 <code>all</code>、<code>history</code>、<code>upcoming</code>、<code>global</code>、<code>cn</code> 与 <code>us</code> 六个稳定的 ICS Feed。
- 使用原子写入、长期稳定 UID 与递增 SEQUENCE，避免日历客户端重复事件或错误覆盖。
- 通过唯一 <code>event_key</code> 防止重复通知；首次 Bootstrap 只建立基线，不推送历史挑战。
- 支持 Webhook、Bark 与 ntfy；任一通知通道失败不会中断更新流程。

## Apple 数据源

运行时默认使用以下公开的 Apple MobileAsset catalog。它们是配置中的数据入口，并非 Apple 承诺稳定的公开 API；Apple 可能随时调整其 Schema、可用性或内容。

| 数据源 | Asset Type | 运行时 Catalog |
| :--- | :--- | :--- |
| Legacy | <code>com.apple.MobileAsset.Activity.Achievements</code> | [Activity.Achievements Catalog](https://mesu.apple.com/assets/com_apple_MobileAsset_Activity_Achievements/com_apple_MobileAsset_Activity_Achievements.xml) |
| Current | <code>com.apple.MobileAsset.ActivityChallengeAssets</code> | [ActivityChallengeAssets Catalog](https://mesu.apple.com/assets/com_apple_MobileAsset_ActivityChallengeAssets/com_apple_MobileAsset_ActivityChallengeAssets.xml) |

Current Source 用于获取较新的挑战定义；Legacy Source 用于保留较早记录，且不会被按 Current Source 的 Schema 强行解析。

## 设计原则

- **双源独立 Adapter。** Current 与 Legacy 分别拥有 Adapter 和 Schema；源特定逻辑不泄漏到日历、存储和通知模块。
- **先统一身份，再生成输出。** 两个源均归一化为稳定的 <code>canonical_id</code>；identifier alias 只能由显式配置提供，不能按标题模糊匹配。
- **可追溯的合并策略。** 字段优先级为人工 Override → Current → Legacy → 程序推导；冲突会保留记录，而不是静默覆盖。
- **两级 Diff。** 先分别识别 source asset 的变更，再识别 canonical challenge 的业务变更；只有后者才会触发 ICS 和通知。
- **失败不等于删除。** 只有某源当轮抓取并解析成功，才允许判断该源记录被移除；网络或解析失败会保留既有数据。
- **保留不确定性。** 未知 Predicate、运动类型和地区范围保留为 raw 或 <code>unknown</code>；地区未知绝不误判为全球。
- **日历一致性。** ICS 采用临时文件、校验、<code>fsync</code> 与原子替换；UID 长期稳定，业务变更才递增 SEQUENCE。
- **发现与提醒分离。** Notification 用于发现或变更，ICS VALARM 用于临近挑战的日历提醒；Bootstrap 只建基线，不发送历史通知。

## 规划与研究参考资料

上方两个 MESU Catalog 是唯一的运行时数据输入。以下链接保留自项目规划、逆向分析与历史交叉核对：它们不是运行依赖；第三方资料不代表 Apple 的认可、隶属或官方承诺。

| 类别 | 规划阶段保留的参考资料 |
| :--- | :--- |
| Apple 平台与 Asset 研究 | [The Apple Wiki — Asset Types](https://theapplewiki.com/wiki/List_of_asset_types)、[The Apple Wiki — MobileAssets](https://theapplewiki.com/wiki/MobileAssets)、[NewOSXBook — activityawardsd entitlements](https://newosxbook.com/ent.php?exec=activityawardsd)、[Apple Developer — HKWorkoutActivityType](https://developer.apple.com/documentation/healthkit/hkworkoutactivitytype)、[Apple Support — 活动圆环目标](https://support.apple.com/guide/watch/adjust-your-activity-ring-goals-apd29b30023c/watchos) |
| 官方挑战公告 | [Apple Newsroom — Get active with Apple Watch（2025）](https://www.apple.com/newsroom/2025/04/get-active-with-apple-watch/)、[Apple Newsroom — New Year（2026）](https://www.apple.com/newsroom/2026/01/stay-active-in-the-new-year-with-apple-watch/) |
| 挑战历史交叉核对 | [9to5Mac — Yoga Day 2026](https://9to5mac.com/2026/06/16/this-sundays-apple-watch-activity-challenge-celebrates-international-day-of-yoga/)、[9to5Mac — National Fitness Day 2026](https://9to5mac.com/2026/08/04/apple-watch-national-fitness-day-challenge-returns-this-weekend/)、[MacRumors Activity Challenge guide](https://www.macrumors.com/guide/activity-challenge/)、[Kyle Seth Gray 的特殊成就归档](https://kylesethgray.com/a-list-of-apple-watch-special-achievements/)、[Peter Wunder 成就归档](https://projects.peterwunder.de/achievements/) |

## 技术栈

| 类别 | 主要技术 |
| :--- | :--- |
| 运行时 | Python 3.11+ |
| 数据源 | Apple MobileAsset MESU（Current / Legacy） |
| 数据处理 | 标准库、PyYAML、Canonical Model、字段级合并 |
| 持久化 | SQLite |
| 日历输出 | icalendar、RFC 5545 |
| 调度与托管 | systemd timer、Caddy |
| 质量保障 | pytest、GitHub Actions |

## 环境要求

本地开发需要 Python 3.11 或更高版本，以及可访问 Apple MESU 数据源的网络。生产环境建议使用 Debian/Ubuntu、Conda、systemd 与 Caddy；服务本身不依赖 Docker、数据库服务或常驻 Python Web 进程。

## 快速开始

~~~bash
git clone https://github.com/skyrocketingHong/AppleWatchChallengeRadar.git
cd AppleWatchChallengeRadar

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

python -m pytest
challenge-radar bootstrap --state-dir ./var --output-dir ./output
~~~

首次执行 <code>bootstrap</code> 会建立本地数据基线并生成日历，但不会为历史挑战发送通知。后续使用 <code>update</code> 获取增量变更。

如使用 Conda，可改为：

~~~bash
conda env create -f environment.yml
conda activate apple-watch-challenge-radar
python -m pip install -e ".[dev]"
~~~

## 常用命令

| 命令 | 用途 |
| :--- | :--- |
| <code>challenge-radar bootstrap</code> | 首次全量导入；仅记录通知去重键，不推送历史事件 |
| <code>challenge-radar update</code> | 拉取、解析、合并、持久化、通知并生成 ICS |
| <code>challenge-radar generate</code> | 仅从 SQLite 重新生成 ICS，不访问网络 |
| <code>challenge-radar status</code> | 输出数据源健康状态与挑战统计 |
| <code>challenge-radar inspect-sources</code> | 输出两个数据源的 catalog 发现结果 |

<code>bootstrap</code> 与 <code>update</code> 可通过 <code>--state-dir</code> 和 <code>--output-dir</code> 覆盖默认运行目录，便于本地验证。

## 架构与数据流

~~~text
Apple MobileAsset MESU
        │
        ├── Legacy Source ──► Legacy Adapter
        └── Current Source ─► Current Adapter
                                 │
                    Canonical Normalize / Alias / Merge
                                 │
                              SQLite
                         ┌───────┴────────┐
                         ▼                ▼
                    ICS Generator   Notification Manager
                         │                │
                    Caddy 静态托管   Webhook / Bark / ntfy
                         │
                    日历客户端订阅
~~~

数据源的抓取、解析、缓存和差异检测均以源为边界独立执行。Canonical 层只在成功结果间合并，因此临时网络错误或 Apple 上游结构变化不会误删已知挑战。

## 配置与安全边界

配置目录按以下顺序查找：<code>$CHALLENGE_RADAR_CONFIG_DIR</code> → <code>/opt/apple-watch-challenge-radar/config</code> → <code>&lt;仓库根&gt;/config</code>。

<code>config/</code> 中包含挑战名称、Legacy alias、运动类型以及服务配置。Webhook URL、Bark Device Key、ntfy Topic 等敏感值应通过环境变量注入，不能写入 Git 仓库或 ICS 输出。

| 文件 | 用途 |
| :--- | :--- |
| <code>config/config.yaml</code> | 数据源、路径、Feed 与通知开关 |
| <code>config/challenge-names.yaml</code> | 挑战标识到中文名称的最长前缀映射 |
| <code>config/challenge-aliases.yaml</code> | Legacy identifier 到 Canonical identifier 的映射 |
| <code>config/workout-types.yaml</code> | 运动类型编号到中文名称的映射 |

## 构建与质量检查

提交前建议执行：

~~~bash
python -m pytest
python -m compileall -q src tests
~~~

GitHub Actions 会在 <code>main</code> 的推送与 Pull Request 中安装开发依赖并运行测试。生成的 SQLite 数据库、ICS 输出、虚拟环境、Python 缓存和本地编辑器文件均已由 <code>.gitignore</code> 排除。

## 项目结构

~~~text
.github/workflows/         GitHub Actions 持续集成
config/                    可版本控制的公开 YAML 配置
docs/
├── DEPLOYMENT.md          English deployment and operations guide
└── DEPLOYMENT_ZH.md       简体中文部署、运维与排障指南
scripts/                   安装与卸载脚本
src/challenge_radar/       应用包：数据源、解析、合并、存储、ICS、通知
tests/
├── fixtures/              可重复的挑战定义样本
├── unit/                  模块级测试
└── integration/           管道级测试
environment.yml            Conda 环境定义
pyproject.toml             Python 包与开发依赖定义
~~~

## 文档

| 文档 | 内容 |
| :--- | :--- |
| [DEPLOYMENT.md](./docs/DEPLOYMENT.md) | English installation, systemd, Caddy, operations, upgrades, and troubleshooting |
| [DEPLOYMENT_ZH.md](./docs/DEPLOYMENT_ZH.md) | Debian/Ubuntu 安装、systemd、Caddy、运维、升级与故障排查 |

## 许可证

本项目使用 [GNU Affero General Public License v3.0](./LICENSE)。通过网络向用户提供修改后的版本时，应遵守 AGPL-3.0 对应源代码提供义务。

## AI 辅助开发

本项目在开发过程中使用生成式 AI 协助编码。

[![Vibe PR](https://raw.githubusercontent.com/fenxer/llm-things/main/stickers/vibe-pr.svg)](https://github.com/fenxer/llm-things/blob/main/stickers/vibe-pr.svg)
