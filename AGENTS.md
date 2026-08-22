# AGENTS.md · AppleWatchChallengeRadar

本文件是 AppleWatchChallengeRadar 的项目级 Agent 约定文件。任何 agent 在修改本项目前必须先读取本文件。

- 任务开始：先读取本文件；项目内另有 README.md / README_ZH.md 与 docs/ 文档，按需阅读。
- 任务结束：若本次任务产生了新的偏好或偏好调整，必须写回本文件。

## 全局约定（适用于扶摇skyrocketing 全部项目）

- 作者署名：扶摇skyrocketing，GitHub 主页 <https://github.com/skyrocketingHong>。
- 双语 README：英文 `README.md` + 简体中文 `README_ZH.md`，顶部语言切换行、居中标题、shields.io 徽章行；修改任一侧必须同一次提交内同步另一侧。
- 许可证：`AGPL-3.0-only`。
- 风格：简体中文；全角标点；严禁 Emoji（回复、文档、Commit Message）；保持客观冷峻；严禁臆造数据或引用。
- Commit：英文 Conventional Commits；发布提交固定为 `chore(release): <营销版本>`；默认不 push，仅在用户明确要求时推送远程。
- 版本：营销版本统一 `主版本.次版本`；内部版本使用合法 SemVer。
- 安全红线：私钥路径、密码、别名、令牌、订阅地址等敏感信息不得写进源码、文档、日志或长期记忆。

## 项目档案

- 仓库：<https://github.com/skyrocketingHong/AppleWatchChallengeRadar>（主分支 `main`）
- 定位：监控 Apple MobileAsset 中 Apple Watch 限定挑战定义的双源服务，生成六个稳定 ICS Feed 并在变更时推送通知；以 systemd timer 触发的一次性任务运行，无 Web 常驻进程，部署目标 Debian/Ubuntu + Caddy 静态托管。
- 技术栈：Python 3.11+（pyproject.toml + environment.yml）、SQLite、ICS 生成、Webhook/Bark/ntfy 通知。

### 关键设计原则（修改时必须遵守）

- Current 与 Legacy 双源独立 Adapter，源特定逻辑不得泄漏到日历、存储、通知模块；单一源失败不影响另一源与已存数据。
- 字段合并优先级：人工 Override → Current → Legacy → 程序推导；冲突必须记录，禁止静默覆盖。
- identifier alias 只能由显式配置提供，禁止按标题模糊匹配。
- 失败不等于删除：只有抓取解析成功才允许判断记录被移除。
- 保留不确定性：未知 Predicate、运动类型、地区保留 raw 或 unknown；地区未知绝不误判为全球。
- ICS 用临时文件 + 校验 + fsync 原子替换；UID 长期稳定，业务变更才递增 SEQUENCE；Bootstrap 只建基线不推送历史。
- 通过唯一 `event_key` 防止重复通知；任一通知通道失败不中断更新流程。
