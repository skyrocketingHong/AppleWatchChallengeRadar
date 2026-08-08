<p align="center">
  English | <a href="DEPLOYMENT_ZH.md">简体中文</a>
</p>

# AppleWatchChallengeRadar Deployment Guide

This guide deploys AppleWatchChallengeRadar on a Debian or Ubuntu server with systemd and Caddy. The service runs without a resident process: a systemd timer invokes <code>challenge-radar update</code> once per hour, then the process exits.

## 1. Layout and Operating Model

~~~text
/opt/apple-watch-challenge-radar/        Repository checkout
├── config/                              YAML configuration
├── src/                                 Python package
├── environment.yml
├── scripts/install.sh
└── scripts/uninstall.sh

/var/lib/apple-watch-challenge-radar/    Persistent SQLite state
/var/www/apple-watch-challenges/         Generated ICS files served by Caddy
~~~

Configuration lookup order is:

1. <code>$CHALLENGE_RADAR_CONFIG_DIR</code>
2. <code>/opt/apple-watch-challenge-radar/config</code>
3. <code>&lt;repository root&gt;/config</code>

## 2. Prerequisites

| Item | Requirement |
| :--- | :--- |
| Operating system | Debian or Ubuntu with systemd |
| Python | 3.11, provided by Conda |
| Conda | Miniconda or compatible Conda installation |
| Network | Access to <code>https://mesu.apple.com</code> |
| Web server | Optional Caddy instance for publishing ICS files |

Use the account that owns the Conda installation as the service user. A separate system account often cannot access a user-local Conda environment.

## 3. Recommended Installation

~~~bash
sudo mkdir -p /opt/apple-watch-challenge-radar
sudo chown "$USER" /opt/apple-watch-challenge-radar
git clone https://github.com/skyrocketingHong/AppleWatchChallengeRadar.git /opt/apple-watch-challenge-radar

# Review notification settings before the first production run.
sudoedit /opt/apple-watch-challenge-radar/config/config.yaml

sudo /opt/apple-watch-challenge-radar/scripts/install.sh
~~~

The installer verifies Debian and Conda, creates or updates the <code>apple-watch-challenge-radar</code> environment, installs the package, creates the persistent and output directories, writes the systemd units, and bootstraps the database only when it has not already been initialized.

## 4. Manual Installation

### 4.1 Create the environment and install the package

~~~bash
cd /opt/apple-watch-challenge-radar
conda env create -f environment.yml
conda env update -n apple-watch-challenge-radar -f environment.yml --prune
conda run -n apple-watch-challenge-radar python -m pip install .
~~~

### 4.2 Create persistent directories

~~~bash
sudo mkdir -p /var/lib/apple-watch-challenge-radar /var/www/apple-watch-challenges
sudo chown -R "$USER" /var/lib/apple-watch-challenge-radar /var/www/apple-watch-challenges
~~~

### 4.3 Configure the service

Review <code>config/config.yaml</code>. In production, set:

- <code>calendar.uidDomain</code> to your stable domain name. Do not change it casually after subscribers exist.
- <code>notifications.*</code> only for providers you intend to use.
- <code>paths.state</code> and <code>paths.output</code> only when you intentionally deviate from the documented layout.

### 4.4 Bootstrap and verify

~~~bash
challenge-radar bootstrap
challenge-radar status
ls -la /var/www/apple-watch-challenges/
~~~

Bootstrap imports all currently available challenges and generates the feeds, but it records notification keys instead of sending alerts for historical data. A healthy first run reports <code>Bootstrap: complete</code> and successful Current and Legacy source states.

## 5. systemd Units

Find the executable path inside the Conda environment:

~~~bash
conda run -n apple-watch-challenge-radar python -c 'import sys; print(sys.prefix)'
~~~

Use the resulting environment prefix in <code>ExecStart</code>. Do not run <code>conda activate</code> from a systemd unit.

Create <code>/etc/systemd/system/apple-watch-challenge-radar.service</code>:

~~~ini
[Unit]
Description=Apple Watch Challenge Radar
Documentation=https://github.com/skyrocketingHong/AppleWatchChallengeRadar
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=<service-user>
Group=<service-group>
WorkingDirectory=/opt/apple-watch-challenge-radar
ExecStart=/actual/conda/env/bin/challenge-radar update
NoNewPrivileges=true
PrivateTmp=true
ReadWritePaths=/var/lib/apple-watch-challenge-radar
ReadWritePaths=/var/www/apple-watch-challenges
~~~

Create <code>/etc/systemd/system/apple-watch-challenge-radar.timer</code>:

~~~ini
[Unit]
Description=Apple Watch Challenge Radar Hourly Check

[Timer]
OnCalendar=*-*-* *:17:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
~~~

Enable the timer:

~~~bash
sudo systemctl daemon-reload
sudo systemctl enable --now apple-watch-challenge-radar.timer
~~~

The timer runs at approximately minute 17 each hour with a random delay of up to five minutes.

## 6. Notification Secrets

Providers are configured in <code>notifications.providers</code>, but credentials belong in environment variables rather than YAML:

| Environment variable | Overrides |
| :--- | :--- |
| <code>RADAR_WEBHOOK_URL</code> | <code>notifications.providers.webhook.url</code> |
| <code>RADAR_BARK_SERVER</code> | <code>notifications.providers.bark.server</code> |
| <code>RADAR_BARK_DEVICE_KEY</code> | <code>notifications.providers.bark.deviceKey</code> |
| <code>RADAR_NTFY_SERVER</code> | <code>notifications.providers.ntfy.server</code> |
| <code>RADAR_NTFY_TOPIC</code> | <code>notifications.providers.ntfy.topic</code> |

For example, add an override with:

~~~bash
sudo systemctl edit apple-watch-challenge-radar.service
~~~

~~~ini
[Service]
Environment=RADAR_BARK_DEVICE_KEY=your-key
Environment=RADAR_NTFY_TOPIC=watch-challenges
~~~

Environment values override YAML values. The provider still requires its <code>enabled</code> field to be true.

## 7. Serve ICS Files with Caddy

AppleWatchChallengeRadar writes static files and does not modify an existing Caddyfile. A minimal virtual host is:

~~~caddyfile
watch.example.com {
    root * /var/www/apple-watch-challenges
    file_server
}
~~~

Typical subscription URLs:

~~~text
https://watch.example.com/all.ics
https://watch.example.com/upcoming.ics
https://watch.example.com/cn.ics
https://watch.example.com/us.ics
~~~

For a subpath, use <code>handle_path /calendar/*</code> and point it to the same output directory. Optionally set the ICS response type:

~~~caddyfile
header *.ics {
    Content-Type "text/calendar; charset=utf-8"
}
~~~

## 8. Operations

| Task | Command |
| :--- | :--- |
| List timers | <code>systemctl list-timers apple-watch-challenge-radar.timer</code> |
| Run one update | <code>sudo systemctl start apple-watch-challenge-radar.service</code> |
| Inspect unit status | <code>systemctl status apple-watch-challenge-radar.service</code> |
| Read recent logs | <code>journalctl -u apple-watch-challenge-radar.service -n 200</code> |
| Follow logs | <code>journalctl -u apple-watch-challenge-radar.service -f</code> |
| Regenerate feeds only | <code>challenge-radar generate</code> |
| Inspect source catalogs | <code>challenge-radar inspect-sources</code> |

## 9. Upgrade and Uninstall

Upgrade without losing SQLite state:

~~~bash
cd /opt/apple-watch-challenge-radar
sudo -u "$USER" git pull
sudo ./scripts/install.sh
~~~

To remove the units while preserving the database and Conda environment:

~~~bash
sudo /opt/apple-watch-challenge-radar/scripts/uninstall.sh
~~~

Deleting <code>/var/lib/apple-watch-challenge-radar</code>, <code>/var/www/apple-watch-challenges</code>, or the Conda environment permanently removes data or deployment state. Do so only when a full removal is intended.

## 10. Troubleshooting

| Symptom | What to check |
| :--- | :--- |
| <code>Bootstrap: pending</code> | Run <code>challenge-radar bootstrap</code> once |
| A source is <code>UNKNOWN</code> | Inspect journal logs; that source has not completed successfully yet |
| Current source fetch failure | Check connectivity to MESU; the other source and existing data remain isolated |
| Definition download or parse failure | The definition stays pending and is retried on the next run |
| No notification | Check global and event switches, provider <code>enabled</code>, and injected environment variables |
| ICS did not change after update | A no-op run intentionally avoids rewriting files; use <code>challenge-radar generate</code> to force regeneration |

## 11. Security Boundaries

- systemd enables <code>NoNewPrivileges=true</code> and <code>PrivateTmp=true</code>, with writes limited to the state and calendar output directories.
- Notification credentials are injected at runtime and are never stored in the repository.
- The two upstream sources are failure-isolated; a source failure does not deactivate known challenges.
- Unknown Predicate values and fields are retained as raw or unparsed data instead of being guessed.
