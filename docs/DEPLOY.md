# Deploying Ferlance

Ferlance is **one web service**. The React frontend is built into static files, and FastAPI serves those files and the API from the same address. The database is a single SQLite file, and uploads sit next to it in a data folder. **That folder must live on a lasting disk.** On a host with a temporary disk, such as a free Render instance, every deploy or restart starts empty. That is why data kept disappearing.

## Which host

| Option | Cost | Keeps data | Notes |
| --- | --- | --- | --- |
| **AWS EC2 t3.micro** (this guide) | $0 while your AWS free-plan credits last (6 months at most) | Yes (EBS disk) | You already have the account; HTTPS works without a domain |
| Google Cloud e2-micro | $0 with no time limit, within its limits | Yes | 1 GB memory, US regions only; the best place to move to when the AWS credits end |
| Oracle Cloud Always Free | $0 with no time limit | Yes | More memory, but it can reclaim idle servers and often has no capacity |
| Render Starter with a disk | About US$7–8 a month | Yes | The easiest to run; `render.yaml` sets it up |

**About the AWS free plan:** it ends 6 months after you opened the account, or sooner if the credits run out. AWS then **closes the account and deletes everything within 90 days, the S3 bucket included**, unless you upgrade. Set a reminder for month 5 and either move to Google Cloud or upgrade. The nightly backup makes moving one command.

A t3.micro with a 20 GB disk and a public IP uses roughly US$12–14 of credits a month, which fits within the base US$100 for 6 months. Don't pick a bigger server: on the free plan, the account closes when the credits run out.

## AWS walkthrough (about 20 minutes of clicking)

Work in the **Europe (Ireland) eu-west-1** region (top right of the console), the same region as `ferlance-bucket`.

### 1. Give the server permission to write backups (once)

The server uses an **IAM role** instead of access keys, so no key is ever stored on it.

1. Open **IAM → Roles → Create role**.
2. For **Trusted entity**, choose *AWS service*, then **Use case:** *EC2*. Click **Next**.
3. Skip the permissions list (click **Next**). Name the role `ferlance-server` and click **Create role**.
4. Open the role, then choose **Add permissions → Create inline policy → JSON**. Paste this, then name it `ferlance-bucket-access`:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       { "Sid": "WriteExportsAndBackups", "Effect": "Allow", "Action": "s3:PutObject",
         "Resource": "arn:aws:s3:::ferlance-bucket/exports/*" },
       { "Sid": "ReadBackupsToRestore", "Effect": "Allow", "Action": "s3:GetObject",
         "Resource": "arn:aws:s3:::ferlance-bucket/exports/_backup/*" }
     ]
   }
   ```

The server can add exports and backups, and read backups back only to restore them. It can't list or delete anything.

5. **Keep 30 days of backups.** Open **S3 → ferlance-bucket → Management → Create lifecycle rule**. Name it `expire-old-backups`, limit it to the prefix `exports/_backup/`, tick **Expire current versions of objects**, and enter **30** days. Without this rule, a copy is kept every day forever.

**What a backup contains:** everything the app holds, including accounts (passwords are stored only as salted hashes), sessions and encrypted integration keys. Keep the bucket private (Block all public access stays on) and share bucket access with no one you wouldn't give the server to.

### 2. Launch the server

Open **EC2 → Launch instance** and set:

| Setting | Value |
| --- | --- |
| Name | `ferlance` |
| Application and OS image | **Ubuntu Server 24.04 LTS** (64-bit x86) |
| Instance type | **t3.micro** (marked *Free tier eligible*) |
| Key pair | **Proceed without a key pair** (you'll connect from the browser) |
| Network settings | Tick **Allow SSH traffic**, **Allow HTTPS traffic** and **Allow HTTP traffic** from the internet. HTTP is only used to get the HTTPS certificate. |
| Configure storage | **20 GiB gp3** |
| Advanced details → IAM instance profile | `ferlance-server` |
| Advanced details → User data | The whole of `deploy/aws/user-data.sh`. **First** put your sign-in email between the quotes on the `ADMIN_EMAIL=""` line. |

Click **Launch instance**.

### 3. Open your app

1. Wait about 10 minutes: the first build is slow on a small server.
2. On the instance's page, copy the **Public IPv4 address**, for example `3.250.1.2`.
3. Your app is at **`https://3-250-1-2.sslip.io`**: the same address with dashes, followed by `.sslip.io`. It resolves to your server, and Caddy gets a real HTTPS certificate for it automatically.
4. Sign up with the email you put in `ADMIN_EMAIL`. You should see **Admin** in the menu.
5. Under **Admin → Data export**, click **Export now**. The business should show *Exported*, and you should see *Last restorable backup* with today's date. That confirms the server can write to S3.

**Not loading yet?** On the instance's page, choose **Connect → EC2 Instance Connect → Connect**, which opens a terminal in your browser, and run:

```bash
sudo tail -n 50 /var/log/ferlance-setup.log
```

The last line says `Ferlance is starting at https://…` when setup has finished.

### 4. Add the AI key and other settings

The settings live in one file on the server, readable only by the administrator. Connect as in step 3, then run:

```bash
sudo nano /srv/ferlance/ferlance.env
```

Set `OPENROUTER_KEY=` to a **new** key (the old one was pasted in chat), and `FERLANCE_ADMIN_EMAILS=` if you left it empty. Save with Ctrl+O, Enter, then exit with Ctrl+X. Then restart the app:

```bash
sudo ferlance-start
```

### 5. Day to day

| Task | Command (run in EC2 Instance Connect) |
| --- | --- |
| Update to the latest release on GitHub | `sudo ferlance-update` |
| Restart after changing settings | `sudo ferlance-start` |
| See the app's logs | `sudo docker logs --tail 100 ferlance` |
| Restore a backup (data is replaced; the old copy is kept) | `sudo ferlance-restore 2026-11-22` |
| See this server's address | `cat /srv/ferlance/address` |

- **Reboot is fine. Don't stop and start the instance:** a stop and start gives the server a new IP and so a new `sslip.io` address. If it does happen, the server points itself at the new address on boot; just use the new one.
- **Backups:** each day after 02:00 UTC, along with the export, the server uploads a restorable copy to `ferlance-bucket/exports/_backup/dt=<date>/`. Admin → Data export shows the last one. To also guard against the server itself being lost, you can add **EC2 → Lifecycle Manager → snapshot policy** for the disk. Snapshots use a little of your credits.
- **Credits:** in **Billing and Cost Management → Free Tier**, check the credits left and the end date of your plan.

### Restore from a backup

1. Connect to the server (step 3) and run `sudo ferlance-restore <date>`, using a date from `exports/_backup/` in the S3 console.
2. The server downloads that day's database and files, checks them against their checksums, swaps them in, and restarts. Your previous data stays in `/srv/ferlance/data.before-restore-…`.

**Moving to a new server**, for example Google Cloud, works the same way. Set up the new server, give it read access to the backups, and run `ferlance-restore` with the latest date.

## Render (paid alternative)

If you ever want to pay to stop managing a server, `render.yaml` sets up a Render web service with a persistent disk. Choose **New → Blueprint**, pick this repo, and fill in the requested settings. Free Render instances have no lasting disk, so they will lose data.

## How the image is built

`Dockerfile`:
1. A Node 22 stage runs `npm ci` and `npm run build`, which produces `frontend/dist`.
2. A Python 3.12 stage installs `requirements.txt`, copies `backend/` and the built frontend, and runs `uvicorn` on `$HOST:$PORT`.

`.dockerignore` keeps `.env`, local data and editor files out of the image.
