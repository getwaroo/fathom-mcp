# Cloud Storage Integration Guide

This guide explains how to integrate cloud storage (Google Drive, Dropbox, OneDrive, S3, etc.) with the file-knowledge-mcp server.

## Why Sync is Outside the MCP Server

The `file-knowledge-mcp` server is designed as a **read-only knowledge base** that provides AI clients with secure access to local documents. Cloud synchronization is intentionally **not** part of the MCP server for these reasons:

1. **Security**: Exposing sync tools to AI clients creates risks:
   - Data exfiltration to unauthorized locations
   - Unauthorized access to cloud accounts
   - Command injection vulnerabilities

2. **Single Responsibility**: The server focuses on one task - providing search and read access to local files

3. **Better Architecture**: Separating concerns allows you to:
   - Use specialized sync tools (rclone, cloud clients)
   - Configure sync independently of the MCP server
   - Maintain different security boundaries

## Recommended Approaches

### Option 1: rclone mount (Recommended)

Mount your cloud storage as a local filesystem. The MCP server sees it as regular files.

#### Advantages
- Real-time access to cloud files
- No disk space needed (virtual filesystem)
- Read-only mode for safety
- Works with any cloud provider

#### Setup

**1. Install rclone**
```bash
# macOS
brew install rclone

# Ubuntu/Debian
sudo apt install rclone

# Windows
# Download from https://rclone.org/downloads/
```

**2. Configure your remote**
```bash
# Interactive configuration wizard
rclone config

# Example: Configure Google Drive
# Name: gdrive
# Storage: drive
# Follow prompts to authenticate
```

**3. Test the connection**
```bash
# List remote contents
rclone ls gdrive:MyKnowledge

# Check that files are accessible
rclone lsd gdrive:
```

**4. Mount the remote**
```bash
# Mount Google Drive to local directory
mkdir -p /data/knowledge
rclone mount gdrive:MyKnowledge /data/knowledge \
  --read-only \
  --vfs-cache-mode full \
  --vfs-cache-max-age 24h \
  --daemon
```

**5. Start MCP server**
```bash
file-knowledge-mcp --root /data/knowledge
```

#### Mount Options Explained

- `--read-only`: Prevents accidental writes (recommended)
- `--vfs-cache-mode full`: Caches files locally for better performance
- `--vfs-cache-max-age 24h`: Keep cache for 24 hours
- `--daemon`: Run in background

#### Systemd Service (Linux)

Create `/etc/systemd/system/rclone-knowledge.service`:

```ini
[Unit]
Description=Rclone mount for knowledge base
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
User=youruser
Group=yourgroup
ExecStart=/usr/bin/rclone mount gdrive:MyKnowledge /data/knowledge \
  --read-only \
  --vfs-cache-mode full \
  --vfs-cache-max-age 24h \
  --log-level INFO \
  --log-file /var/log/rclone-knowledge.log
ExecStop=/bin/fusermount -uz /data/knowledge
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable rclone-knowledge
sudo systemctl start rclone-knowledge
```

---

### Option 2: Cloud Desktop Clients

Use official sync clients from cloud providers. Simplest option for casual use.

#### Google Drive Desktop

**1. Install**
- Download from https://www.google.com/drive/download/
- Sign in with your Google account

**2. Configure selective sync**
- Choose which folders to sync locally
- Set sync location (e.g., `~/GoogleDrive`)

**3. Start MCP server**
```bash
file-knowledge-mcp --root ~/GoogleDrive/Knowledge
```

#### Dropbox

**1. Install**
- Download from https://www.dropbox.com/install
- Sign in to your account

**2. Configure Selective Sync**
- Preferences → Sync → Selective Sync
- Choose specific folders

**3. Start MCP server**
```bash
file-knowledge-mcp --root ~/Dropbox/Knowledge
```

#### OneDrive

**1. Install**
- Windows: Built-in
- macOS: Download from https://onedrive.live.com/about/download/

**2. Configure**
- Sign in with Microsoft account
- Choose folders to sync

**3. Start MCP server**
```bash
file-knowledge-mcp --root ~/OneDrive/Knowledge
```

#### Advantages
- Simple setup
- Automatic background sync
- Native OS integration

#### Disadvantages
- Uses local disk space
- Syncs entire folders (can't be selective per-file)
- May sync unnecessary files

---

### Option 3: Scheduled Sync with rclone

Periodically copy files from cloud to local directory. Good for servers.

#### Setup

**1. Create sync script**

Create `/usr/local/bin/sync-knowledge.sh`:

```bash
#!/bin/bash
set -e

SOURCE="gdrive:MyKnowledge"
DEST="/data/knowledge"
LOG="/var/log/knowledge-sync.log"

echo "[$(date)] Starting sync from $SOURCE to $DEST" >> "$LOG"

rclone sync "$SOURCE" "$DEST" \
  --log-level INFO \
  --log-file "$LOG" \
  --exclude ".git/**" \
  --exclude "*.tmp" \
  --exclude "*.draft.*"

echo "[$(date)] Sync complete" >> "$LOG"
```

Make executable:
```bash
chmod +x /usr/local/bin/sync-knowledge.sh
```

**2. Test manually**
```bash
/usr/local/bin/sync-knowledge.sh
```

**3. Schedule with cron**

Edit crontab:
```bash
crontab -e
```

Add entry (sync every 30 minutes):
```
*/30 * * * * /usr/local/bin/sync-knowledge.sh
```

**4. Or use systemd timer**

Create `/etc/systemd/system/knowledge-sync.service`:

```ini
[Unit]
Description=Sync knowledge base from cloud
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/sync-knowledge.sh
User=youruser
Group=yourgroup
```

Create `/etc/systemd/system/knowledge-sync.timer`:

```ini
[Unit]
Description=Run knowledge sync every 30 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
Persistent=true

[Install]
WantedBy=timers.target
```

Enable timer:
```bash
sudo systemctl daemon-reload
sudo systemctl enable knowledge-sync.timer
sudo systemctl start knowledge-sync.timer
```

Check status:
```bash
systemctl status knowledge-sync.timer
journalctl -u knowledge-sync.service
```

#### Advantages
- Full control over sync timing
- Works with any cloud provider via rclone
- Can run on servers without desktop environment
- Efficient - only syncs changes

#### Disadvantages
- Not real-time (delayed by interval)
- Requires scripting knowledge
- Needs monitoring

---

## Provider-Specific Examples

### Google Drive

```bash
# Configure
rclone config
# Name: gdrive
# Storage: drive
# Scope: drive.readonly (for read-only access)

# Mount
rclone mount gdrive:Knowledge /data/knowledge --read-only --daemon

# Sync (scheduled)
rclone sync gdrive:Knowledge /data/knowledge --exclude ".*" --exclude "*.tmp"
```

### Dropbox

```bash
# Configure
rclone config
# Name: dropbox
# Storage: dropbox

# Mount
rclone mount dropbox:Knowledge /data/knowledge --read-only --daemon

# Sync
rclone sync dropbox:Knowledge /data/knowledge
```

### OneDrive

```bash
# Configure
rclone config
# Name: onedrive
# Storage: onedrive

# Mount
rclone mount onedrive:Knowledge /data/knowledge --read-only --daemon

# Sync
rclone sync onedrive:Knowledge /data/knowledge
```

### Amazon S3

```bash
# Configure
rclone config
# Name: s3
# Storage: s3
# Provider: AWS
# Access Key ID and Secret from AWS Console

# Mount
rclone mount s3:my-knowledge-bucket /data/knowledge --read-only --daemon

# Sync
rclone sync s3:my-knowledge-bucket /data/knowledge
```

### Self-hosted (WebDAV, SFTP, etc.)

```bash
# WebDAV
rclone config
# Name: webdav
# Storage: webdav
# URL: https://your-server.com/webdav
# Vendor: nextcloud (or other)

# SFTP
rclone config
# Name: sftp
# Storage: sftp
# Host: your-server.com
# User: youruser
# SSH key or password

# Mount
rclone mount webdav:Knowledge /data/knowledge --read-only --daemon
rclone mount sftp:knowledge /data/knowledge --read-only --daemon
```

---

## Docker Integration

### With rclone mount

**1. Mount on host**
```bash
# On host system
rclone mount gdrive:Knowledge /data/knowledge --read-only --daemon
```

**2. Run container**
```bash
docker run -v /data/knowledge:/knowledge:ro file-knowledge-mcp
```

### With cloud client sync

**1. Cloud client syncs to host directory**
```bash
# Example: Dropbox syncs to ~/Dropbox/Knowledge
```

**2. Run container**
```bash
docker run -v ~/Dropbox/Knowledge:/knowledge:ro file-knowledge-mcp
```

### docker-compose example

```yaml
version: "3.8"

services:
  file-knowledge-mcp:
    image: file-knowledge-mcp:latest
    volumes:
      # Mount synced directory (managed outside container)
      - /data/knowledge:/knowledge:ro
      - ./config.yaml:/config/config.yaml:ro
    stdin_open: true
    tty: true
```

**Note**: Always mount as read-only (`:ro`) for security.

---

## Troubleshooting

### rclone mount issues

**Problem**: Mount fails with "Transport endpoint not connected"
```bash
# Unmount first
fusermount -uz /data/knowledge
# Or on macOS
umount /data/knowledge

# Remount
rclone mount gdrive:Knowledge /data/knowledge --read-only --daemon
```

**Problem**: Slow file access
```bash
# Increase cache
rclone mount gdrive:Knowledge /data/knowledge \
  --read-only \
  --vfs-cache-mode full \
  --vfs-cache-max-size 10G \
  --vfs-cache-max-age 24h \
  --daemon
```

**Problem**: Permission denied
```bash
# Check ownership
ls -la /data/knowledge

# Fix permissions if needed
sudo chown -R youruser:yourgroup /data/knowledge
```

### Sync script issues

**Problem**: Cron job not running
```bash
# Check cron service
sudo systemctl status cron  # or crond

# Check logs
tail -f /var/log/syslog | grep CRON

# Test script manually
/usr/local/bin/sync-knowledge.sh
```

**Problem**: Permission denied in cron
```bash
# Ensure script has correct ownership
sudo chown root:root /usr/local/bin/sync-knowledge.sh
sudo chmod 755 /usr/local/bin/sync-knowledge.sh

# Or run as specific user
crontab -u youruser -e
```

### Cloud client issues

**Problem**: Files not syncing
- Check internet connection
- Check available disk space
- Restart sync client
- Check selective sync settings

**Problem**: High CPU/memory usage
- Limit sync to specific folders
- Pause sync when not needed
- Increase sync interval

---

## Security Best Practices

### 1. Use Read-Only Access

**rclone mount**:
```bash
rclone mount gdrive:Knowledge /data/knowledge --read-only
```

**Docker**:
```bash
docker run -v /data/knowledge:/knowledge:ro file-knowledge-mcp
```

**rclone config**:
```bash
# Use read-only scope when possible
# For Google Drive: drive.readonly
```

### 2. Limit Access Scope

Configure cloud app permissions to minimum required:
- Google Drive: Read-only access to specific folders
- Dropbox: App folder access only
- AWS S3: Read-only IAM policy

Example S3 IAM policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::my-knowledge-bucket",
        "arn:aws:s3:::my-knowledge-bucket/*"
      ]
    }
  ]
}
```

### 3. Encrypt Sensitive Data

If storing sensitive documents:
```bash
# Use rclone crypt
rclone config
# Name: encrypted
# Storage: crypt
# Remote: gdrive:Knowledge-Encrypted
# Password: [your-password]
# Password2: [salt-password]

# Mount encrypted remote
rclone mount encrypted: /data/knowledge --read-only --daemon
```

### 4. Monitor Sync Logs

```bash
# Check for errors
tail -f /var/log/rclone-knowledge.log

# Alert on failures (add to sync script)
if ! rclone sync ...; then
  echo "Sync failed!" | mail -s "Knowledge Sync Failed" admin@example.com
fi
```

### 5. Firewall Rules

If using self-hosted storage:
```bash
# Allow only specific IP ranges
# Example: iptables rule for SFTP
sudo iptables -A INPUT -p tcp --dport 22 -s 192.168.1.0/24 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 22 -j DROP
```

---

## Performance Optimization

### rclone mount tuning

```bash
rclone mount gdrive:Knowledge /data/knowledge \
  --read-only \
  --vfs-cache-mode full \
  --vfs-cache-max-size 10G \       # Cache up to 10GB locally
  --vfs-cache-max-age 24h \        # Keep cache for 24 hours
  --dir-cache-time 5m \            # Cache directory listings
  --buffer-size 64M \              # Read buffer size
  --transfers 4 \                  # Parallel transfers
  --checkers 8 \                   # Parallel file checks
  --daemon
```

### Scheduled sync optimization

```bash
# Only sync changed files
rclone sync gdrive:Knowledge /data/knowledge \
  --fast-list \                    # Use recursive file listing
  --transfers 8 \                  # More parallel transfers
  --checkers 16 \                  # More parallel checks
  --checksum \                     # Verify with checksums
  --exclude ".git/**" \
  --exclude "*.tmp"
```

### Network optimization

```bash
# For slow connections
rclone mount gdrive:Knowledge /data/knowledge \
  --read-only \
  --vfs-cache-mode full \
  --bwlimit 10M \                  # Limit to 10MB/s
  --daemon

# For fast connections
rclone sync gdrive:Knowledge /data/knowledge \
  --transfers 16 \
  --multi-thread-streams 4
```

---

## Monitoring and Maintenance

### Check mount health

```bash
# Test if mount is responsive
ls /data/knowledge

# Check rclone process
ps aux | grep rclone

# Check mount statistics
rclone rc vfs/stats
```

### Automated health checks

Create `/usr/local/bin/check-knowledge-mount.sh`:

```bash
#!/bin/bash
MOUNT_POINT="/data/knowledge"
TIMEOUT=5

if timeout "$TIMEOUT" ls "$MOUNT_POINT" > /dev/null 2>&1; then
  echo "Mount OK"
  exit 0
else
  echo "Mount failed, attempting remount..."
  fusermount -uz "$MOUNT_POINT" || umount -f "$MOUNT_POINT"
  sleep 2
  rclone mount gdrive:Knowledge "$MOUNT_POINT" --read-only --daemon
  exit 1
fi
```

Add to crontab (check every 5 minutes):
```
*/5 * * * * /usr/local/bin/check-knowledge-mount.sh
```

### Log rotation

Create `/etc/logrotate.d/knowledge-sync`:

```
/var/log/knowledge-sync.log {
  daily
  rotate 7
  compress
  delaycompress
  missingok
  notifempty
}
```

---

## Comparison Table

| Feature | rclone mount | Cloud Clients | Scheduled Sync |
|---------|--------------|---------------|----------------|
| Real-time access | ✅ Yes | ✅ Yes | ❌ Delayed |
| Disk space usage | ✅ Minimal (cache only) | ❌ Full copy | ❌ Full copy |
| Setup complexity | 🟡 Medium | ✅ Easy | 🟡 Medium |
| OS integration | 🟡 Good | ✅ Excellent | ❌ None |
| Server-friendly | ✅ Yes | ❌ Desktop only | ✅ Yes |
| Any cloud provider | ✅ Yes (70+ supported) | ❌ Provider-specific | ✅ Yes |
| Read-only mode | ✅ Yes | 🟡 Manual | ✅ Yes |
| Resource usage | ✅ Low | 🟡 Medium | ✅ Very low |

---

## Conclusion

For most users, we recommend:
- **Development/Desktop**: Cloud desktop clients (simplest)
- **Production/Server**: rclone mount (most flexible)
- **Batch processing**: Scheduled sync (most efficient)

All approaches keep cloud synchronization **outside** the MCP server, maintaining:
- ✅ Clear security boundaries
- ✅ Simple server architecture
- ✅ Flexibility in sync strategies
- ✅ Better maintainability

Choose the approach that best fits your infrastructure and use case.
