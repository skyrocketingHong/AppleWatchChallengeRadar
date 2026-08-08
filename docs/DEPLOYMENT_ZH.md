<p align="center">
  <a href="DEPLOYMENT.md">English</a> | 简体中文
</p>

# AppleWatchChallengeRadar 部署指南

AppleWatchChallengeRadar —— Debian/Ubuntu 服务器部署指南。

目标环境：任意 Debian 系服务器（有 systemd、可访问 mesu.apple.com）。
运行形态：**无常驻进程**。每小时第 17 分钟 + 0~5 分钟随机延迟，由 systemd timer
触发一次 `challenge-radar update`（oneshot），完成后进程退出。

---

## 1. 架构与目录布局

```
/opt/apple-watch-challenge-radar/        # 项目（仓库克隆位置）
├── config/                              # 配置文件目录（YAML）
├── src/                                 # Python 包
├── environment.yml
├── scripts/install.sh                   # 一键安装脚本
└── scripts/uninstall.sh                 # 卸载脚本

/var/lib/apple-watch-challenge-radar/    # SQLite 状态目录（challenges.db）
/var/www/apple-watch-challenges/         # ICS 输出目录（Caddy 静态托管）
```

配置目录解析顺序（`Config.find_config_dir`）：

```text
1. $CHALLENGE_RADAR_CONFIG_DIR（显式覆盖）
2. /opt/apple-watch-challenge-radar/config（生产布局）
3. <仓库根>/config（开发布局）
```

---

## 2. 前置条件

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Debian / Ubuntu（systemd 可用） |
| Python | 3.11（由 Conda 环境提供） |
| Miniconda | 已安装，`conda` 在 root PATH 中 |
| 网络 | 可访问 `https://mesu.apple.com`（数据源） |
| 域名 | 可选，用于 Caddy 托管 ICS |

---

## 3. 方式一：一键安装（推荐）

```bash
# 1. 克隆仓库到固定路径（install.sh 硬编码此路径）
sudo mkdir -p /opt/apple-watch-challenge-radar
sudo chown "$USER" /opt/apple-watch-challenge-radar
git clone https://github.com/skyrocketingHong/AppleWatchChallengeRadar.git /opt/apple-watch-challenge-radar

# 2. 按需修改配置（通知令牌等，见第 6 节）
#    sudoedit /opt/apple-watch-challenge-radar/config/config.yaml

# 3. 执行安装（root）
sudo /opt/apple-watch-challenge-radar/scripts/install.sh
```

安装脚本完成：

1. 检测 Debian 环境与 `conda`
2. 创建 / 更新 Conda 环境 `apple-watch-challenge-radar`（`environment.yml`）
3. `pip install .` 安装包，确认 `challenge-radar` CLI 存在
4. 创建 `/var/lib/apple-watch-challenge-radar` 与 `/var/www/apple-watch-challenges`，属主为调用 sudo 的用户
5. 写入 systemd service + timer
6. `daemon-reload`；若 `status` 未通过则执行首次 `bootstrap`（不发送历史通知）
7. `enable --now` 启用 timer

> 运行用户 = 执行 `sudo` 的用户（`SUDO_USER`）。不要为此服务创建独立用户——
> 独立用户无法读取个人目录下的 Conda 环境（详见下文 systemd 单元配置）。

---

## 4. 方式二：手动部署

### 4.1 安装 Conda 环境与包

```bash
conda env create -f environment.yml            # 创建环境 apple-watch-challenge-radar
conda env update -n apple-watch-challenge-radar -f environment.yml --prune   # 或更新
conda run -n apple-watch-challenge-radar python -m pip install .
```

### 4.2 创建目录与权限

```bash
sudo mkdir -p /opt/apple-watch-challenge-radar /var/lib/apple-watch-challenge-radar /var/www/apple-watch-challenges
sudo chown -R "$USER" /opt/apple-watch-challenge-radar /var/lib/apple-watch-challenge-radar /var/www/apple-watch-challenges
```

### 4.3 配置

```bash
sudo vim /opt/apple-watch-challenge-radar/config/config.yaml
```

生产环境只需关注：

- `paths.state` / `paths.output`：默认即上述目录，无需修改
- `calendar.uidDomain`：改为你的域名（ICS UID 后缀，**长期稳定，勿随意改**）
- `notifications.*`：见第 6 节

### 4.4 首次导入（必须 bootstrap，不能直接 update）

```bash
challenge-radar bootstrap
```

Bootstrap 语义：全量导入、生成全部 ICS、**不发送任何历史通知**，
但会把去重键写入 `notifications` 表，保证后续 update 不会补发。

### 4.5 验证

```bash
challenge-radar status
```

预期输出要点：

```text
Bootstrap: complete

Legacy: OK
Current: OK
```

检查 ICS：

```bash
ls -la /var/www/apple-watch-challenges/
# all.ics  history.ics  upcoming.ics  global.ics  cn.ics  us.ics
```

抽查内容（中文条件可读化）：

```bash
grep -c "SUMMARY" /var/www/apple-watch-challenges/upcoming.ics
grep "完成至少" /var/www/apple-watch-challenges/upcoming.ics | head -3
```

### 4.6 安装 systemd 单元

`/etc/systemd/system/apple-watch-challenge-radar.service`：

```ini
[Unit]
Description=Apple Watch Challenge Radar
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=<运行用户>
Group=<运行用户组>
WorkingDirectory=/opt/apple-watch-challenge-radar
ExecStart=/实际Conda环境路径/bin/challenge-radar update
NoNewPrivileges=true
PrivateTmp=true
ReadWritePaths=/var/lib/apple-watch-challenge-radar
ReadWritePaths=/var/www/apple-watch-challenges
```

`ExecStart` 必须是 Conda 环境内真实可执行文件（**不要** `source activate` / `conda activate`，
systemd 无 shell 环境，运行链路越短越好）：

```bash
# 查实际路径
conda run -n apple-watch-challenge-radar python -c 'import sys; print(sys.prefix)'
# 例如 /home/youruser/miniconda3/envs/apple-watch-challenge-radar/bin/challenge-radar
```

`/etc/systemd/system/apple-watch-challenge-radar.timer`：

```ini
[Unit]
Description=Apple Watch Challenge Radar Hourly Check

[Timer]
OnCalendar=*-*-* *:17:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

即：每小时约第 17 分钟执行 + 0~5 分钟随机延迟，避免固定整点请求。

### 4.7 启用

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now apple-watch-challenge-radar.timer
```

---

## 5. 日常运维

| 操作 | 命令 |
| --- | --- |
| 查看 timer | `systemctl list-timers apple-watch-challenge-radar.timer` |
| 手动执行一次更新 | `sudo systemctl start apple-watch-challenge-radar.service` |
| 查看服务状态 | `systemctl status apple-watch-challenge-radar.service` |
| 查看最近日志 | `journalctl -u apple-watch-challenge-radar.service -n 200` |
| 实时日志 | `journalctl -u apple-watch-challenge-radar.service -f` |
| 手动 CLI 更新 | `challenge-radar update` |
| 仅重生成 ICS（无网络） | `challenge-radar generate` |
| 查看源发现统计 | `challenge-radar inspect-sources` |

---

## 6. 通知配置

`config.yaml` 中 `notifications.providers` 支持三种 Provider：
webhook（通用 JSON POST）、bark、ntfy。

**敏感令牌不写入 YAML**，通过环境变量注入（`config.py` 的 `ENV_OVERRIDES`）：

| 环境变量 | 覆盖配置项 |
| --- | --- |
| `RADAR_WEBHOOK_URL` | `notifications.providers.webhook.url` |
| `RADAR_BARK_SERVER` | `notifications.providers.bark.server` |
| `RADAR_BARK_DEVICE_KEY` | `notifications.providers.bark.deviceKey` |
| `RADAR_NTFY_SERVER` | `notifications.providers.ntfy.server` |
| `RADAR_NTFY_TOPIC` | `notifications.providers.ntfy.topic` |

systemd 环境下注入方式（避免明文写在 unit 文件里）：

```bash
sudo systemctl edit apple-watch-challenge-radar.service
```

```ini
[Service]
Environment=RADAR_BARK_DEVICE_KEY=你的key
Environment=RADAR_NTFY_TOPIC=watch-challenges
```

> 环境变量优先级高于 YAML：设置了环境变量即视为启用（`enabled` 仍须为 true）。

事件类型开关（`notifications.events`）：`newChallenge` / `updatedChallenge` /
`removedFutureChallenge`。关闭 `notifications.enabled` 可整体禁用。

---

## 7. Caddy 静态托管

本项目只输出静态文件，**不修改用户现有 Caddyfile**。

最简示例（`/etc/caddy/Caddyfile`）：

```caddyfile
watch.example.com {
    root * /var/www/apple-watch-challenges
    file_server
}
```

订阅地址：

```text
https://watch.example.com/all.ics
https://watch.example.com/upcoming.ics
https://watch.example.com/cn.ics
https://watch.example.com/us.ics
```

子路径示例：

```caddyfile
watch.example.com {
    handle_path /calendar/* {
        root * /var/www/apple-watch-challenges
        file_server
    }
}
```

```text
https://watch.example.com/calendar/cn.ics
```

建议（可选）：

```caddyfile
header *.ics {
    Content-Type "text/calendar; charset=utf-8"
}
```

---

## 8. 升级

```bash
# 1. 拉取新代码
cd /opt/apple-watch-challenge-radar && sudo -u "$USER" git pull

# 2. 重新安装（环境 + 包 + 单元文件 + bootstrap 检查 + timer）
sudo /opt/apple-watch-challenge-radar/scripts/install.sh
```

数据库自动兼容：`Database.init_schema()` 幂等执行 `CREATE TABLE IF NOT EXISTS`，
升级不丢数据。

---

## 9. 卸载

```bash
sudo /opt/apple-watch-challenge-radar/scripts/uninstall.sh
```

卸载脚本：停止并禁用 timer、删除两个 unit 文件、`daemon-reload`。
**保留**数据目录与 Conda 环境，如需彻底删除手动执行：

```bash
sudo rm -rf /var/lib/apple-watch-challenge-radar /var/www/apple-watch-challenges /opt/apple-watch-challenge-radar
conda env remove -n apple-watch-challenge-radar
```

---

## 10. 故障排查

| 现象 | 排查 |
| --- | --- |
| `status` 显示 `Bootstrap: pending` | 未执行过 bootstrap；先 `challenge-radar bootstrap` |
| 某源 `status: UNKNOWN` | 该源从未成功过；看日志定位（`journalctl -u ... -n 200`） |
| 日志 `current source fetch failed` | mesu.apple.com 不可达 / catalog 变更；不影响另一源与已有数据（故障隔离） |
| 日志 `definition download/parse failed` | 单个定义损坏；保持 pending，下轮自动重试，不崩全局 |
| 通知未发送 | 检查 `notifications.enabled`、事件开关、Provider `enabled: true`、环境变量是否注入 |
| 重新部署后重复通知 | 不应发生：`event_key` 唯一约束 + bootstrap 预记录去重键 |
| ICS 未更新 | `update` 只在有新增/变更/撤回时重写 ICS（noop 轮次不写盘，属正常） |
| 手动 update 想强制重写 | `challenge-radar generate`（仅从 SQLite 重生成，无网络） |

---

## 11. 安全边界

- systemd 单元开启 `NoNewPrivileges=true`、`PrivateTmp=true`，写路径仅限
  state 与 output 两目录
- 通知令牌只经环境变量注入，不落盘
- 管道对两个数据源完全隔离：任一源失败不误删另一源资产、不 deactivate 挑战
- 未知 Predicate / 未知字段**不猜测**：保留 raw 并标记 unparsed，宁可 unknown 也不误判
