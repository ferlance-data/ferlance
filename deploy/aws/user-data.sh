#!/bin/bash
# Ferlance on one AWS EC2 server (Ubuntu 24.04). Paste this whole file into
# "Advanced details → User data" when launching the instance. It runs once, on first boot:
#   - adds 2 GB of swap (a t3.micro has 1 GB of memory)
#   - installs Docker, git and Caddy
#   - downloads Ferlance from GitHub and builds it
#   - starts it, with free HTTPS at https://<your-ip-with-dashes>.sslip.io (no domain needed)
# Everything it does is logged to /var/log/ferlance-setup.log. Data lives in /srv/ferlance/data.
set -euxo pipefail
exec > >(tee -a /var/log/ferlance-setup.log) 2>&1

# Your sign-in email, so you get the Admin page. You can also change it later (see docs/DEPLOY.md).
ADMIN_EMAIL=""

if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io git caddy curl
systemctl enable --now docker

mkdir -p /srv/ferlance/data
[ -d /srv/ferlance/app/.git ] || git clone https://github.com/ferlance-data/ferlance.git /srv/ferlance/app

# Settings. The secret key is generated here and never leaves this server.
if [ ! -f /srv/ferlance/ferlance.env ]; then
  umask 077
  cat > /srv/ferlance/ferlance.env <<EOF
FERLANCE_SECRET_KEY=$(head -c 64 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 48)
FERLANCE_COOKIE_SECURE=true
FERLANCE_DATA_DIR=/var/data
FERLANCE_ADMIN_EMAILS=${ADMIN_EMAIL}
FERLANCE_EXPORT_BUCKET=ferlance-bucket
AWS_REGION=eu-west-1
OPENROUTER_KEY=
EOF
  umask 022
fi

# ferlance-start: (re)create the app container from the current image and settings.
cat > /usr/local/bin/ferlance-start <<'EOF'
#!/bin/bash
set -euo pipefail
docker rm -f ferlance >/dev/null 2>&1 || true
# Host networking: the app listens on 127.0.0.1:8000 only (Caddy faces the internet), and it can
# reach the instance role for S3 without changing the metadata hop limit.
docker run -d --name ferlance --restart unless-stopped --network host \
  -e HOST=127.0.0.1 -e PORT=8000 \
  -v /srv/ferlance/data:/var/data \
  --env-file /srv/ferlance/ferlance.env ferlance
EOF

# ferlance-update: get the latest code from GitHub, rebuild, restart. Run after each release.
cat > /usr/local/bin/ferlance-update <<'EOF'
#!/bin/bash
set -euo pipefail
cd /srv/ferlance/app
git pull --ff-only
docker build -t ferlance .
ferlance-start
docker image prune -f >/dev/null
echo "Ferlance updated: https://$(cat /srv/ferlance/address)"
EOF

# ferlance-address: point Caddy at this server's public IP (runs on every boot; the IP changes
# only if the instance is stopped and started, not on a reboot).
cat > /usr/local/bin/ferlance-address <<'EOF'
#!/bin/bash
set -euo pipefail
TOKEN=$(curl -sfX PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
IP=$(curl -sf -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)
HOST="${IP//./-}.sslip.io"
printf '%s {\n\treverse_proxy 127.0.0.1:8000\n}\n' "$HOST" > /etc/caddy/Caddyfile
echo "$HOST" > /srv/ferlance/address
systemctl reload-or-restart caddy
EOF
# ferlance-restore YYYY-MM-DD: replace this server's data with that day's backup from S3.
# The current data is kept in /srv/ferlance/data.before-restore-<time> in case you change your mind.
cat > /usr/local/bin/ferlance-restore <<'EOF'
#!/bin/bash
set -euo pipefail
DAY="${1:?Usage: sudo ferlance-restore YYYY-MM-DD}"
WORK=$(mktemp -d /srv/ferlance/restore-XXXX)
docker run --rm -i --network host -v "$WORK":/restore --env-file /srv/ferlance/ferlance.env ferlance python - "$DAY" <<'PY'
import hashlib, json, os, sys
import boto3
day = sys.argv[1]
bucket = os.environ["FERLANCE_EXPORT_BUCKET"]
prefix = f"{os.environ.get('FERLANCE_EXPORT_PREFIX', 'exports')}/_backup/dt={day}"
s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION") or None)
for name in ("manifest.json", "ferlance.sqlite3.gz", "files.tar.gz"):
    s3.download_file(bucket, f"{prefix}/{name}", f"/restore/{name}")
manifest = json.load(open("/restore/manifest.json"))
for name, meta in manifest["files"].items():
    with open(f"/restore/{name}", "rb") as handle:
        if hashlib.sha256(handle.read()).hexdigest() != meta["sha256"]:
            sys.exit(f"{name} does not match its checksum; not restoring.")
print("Backup downloaded and checked.")
PY
docker rm -f ferlance >/dev/null 2>&1 || true
mv /srv/ferlance/data "/srv/ferlance/data.before-restore-$(date +%Y%m%d%H%M%S)"
mkdir -p /srv/ferlance/data
gunzip -c "$WORK/ferlance.sqlite3.gz" > /srv/ferlance/data/ferlance.sqlite3
tar -xzf "$WORK/files.tar.gz" -C /srv/ferlance/data
rm -rf "$WORK"
ferlance-start
echo "Restored the backup from $DAY."
EOF

chmod 755 /usr/local/bin/ferlance-start /usr/local/bin/ferlance-update /usr/local/bin/ferlance-address /usr/local/bin/ferlance-restore

cat > /etc/systemd/system/ferlance-address.service <<'EOF'
[Unit]
Description=Point Caddy at this server's public sslip.io address
Wants=network-online.target
After=network-online.target caddy.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/ferlance-address

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable caddy ferlance-address
systemctl start ferlance-address

cd /srv/ferlance/app
docker build -t ferlance .
ferlance-start
echo "Ferlance is starting at https://$(cat /srv/ferlance/address)"
