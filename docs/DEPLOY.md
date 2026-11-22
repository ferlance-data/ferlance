# Deploying Ferlance

## The short version

Ferlance is **one web service**, even though the code has a `frontend/` folder and a `backend/` folder. The React frontend is built into static files (`frontend/dist`), and FastAPI serves those files and the API from the same address. There is nothing to deploy separately, and there's no CORS or cross-site cookie setup to manage.

**Recommendation: stay on Render, using the Docker setup in this repo.**

| | Render (recommended now) | AWS |
| --- | --- | --- |
| What runs | One Docker web service plus a 1 GB persistent disk | One small VM (Lightsail or EC2) running Docker, plus HTTPS you set up |
| Your work | Connect the repo once; every push to `main` deploys | You patch the OS, set up HTTPS (for example Caddy), restarts and backups |
| Fits SQLite | Yes: the disk keeps the database and uploads across deploys | Yes on a VM. **No** on App Runner or Lightsail *containers*, which have no lasting disk |
| Rough cost | Starter instance plus disk, about US$7–8 a month (check current prices on render.com) | Lightsail from about US$5–10 a month, plus your time |

Move to AWS when there's a reason to: more than one server, a managed Postgres database, or data that must stay in a particular region. The Docker image runs unchanged on a VM, so moving later is cheap.

> Ferlance's frontend is React and TypeScript, built with Vite. There's no Vue.

## Why the old Render setup doesn't work any more

The old site was plain HTML, CSS and JS, so Render could serve the files as they were. Now the frontend has to be **built** with Node before Python can serve it. The `Dockerfile` does both steps:

1. A Node 22 stage runs `npm ci` and `npm run build`, which produces `frontend/dist`.
2. A Python 3.12 stage installs `requirements.txt`, copies `backend/` and the built `frontend/dist`, and starts `uvicorn` on Render's `$PORT`.

`render.yaml` describes the service, its disk and its settings, so Render can set it all up from the repo.

## Walkthrough: Render

### 1. Before you start
- **Free instances lose files.** Without a persistent disk, the SQLite database and uploads are wiped on every deploy or restart, and a free instance also falls asleep, which stops the daily export. The blueprint uses the `starter` plan with a disk for that reason.
- **Moving old data?** If the old service had a disk with `ferlance.sqlite3` on it, set `FERLANCE_SECRET_KEY` to the **old value** instead of a new one. The key encrypts stored integration keys and signs logins. If the old service had no disk, there's no data to move.

### 2. Create the service from the blueprint
1. Merge the PR that adds `Dockerfile` and `render.yaml` into `main`.
2. In the Render dashboard, choose **New → Blueprint** and pick the `ferlance-data/ferlance` repository.
3. Render reads `render.yaml` and shows one web service, `ferlance`, with a 1 GB disk mounted at `/var/data`.
4. Render then asks for the values marked `sync: false`:

   | Setting | What to put |
   | --- | --- |
   | `FERLANCE_ADMIN_EMAILS` | Your own sign-in email (this gives you the Admin page) |
   | `OPENROUTER_KEY` | The AI key: use a **new** one, since the old one was pasted in chat |
   | `FERLANCE_EXPORT_BUCKET` | `ferlance-bucket` |
   | `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` | The `ferlance-export` IAM user's key, never a root key |

   `FERLANCE_SECRET_KEY` is generated for you, unless you're moving old data (step 1).
5. Click **Apply**. The first build takes a few minutes; later builds reuse cached layers.

### 3. Check it
- Open `https://<your-service>.onrender.com/health`. It should show `{"status":"ok"}`.
- Open the site, sign up with the email you put in `FERLANCE_ADMIN_EMAILS`, and check that **Admin** appears in the menu.
- Under **Admin → Data export**, click **Export now** and check that it says *Exported*.
- If the service doesn't start, open **Logs**. A message about `FERLANCE_SECRET_KEY` means the key is missing or shorter than 32 characters. The app refuses to run in production with a weak key.

### 4. Your domain and the old service
1. In the new service, go to **Settings → Custom Domains**, add your domain and update its DNS as Render instructs.
2. When the new service works on your domain, suspend the old one, then delete it.

### 5. Day to day
- **Deploys:** every push to `main` builds and deploys. A service with a disk restarts during a deploy, so expect a few seconds of downtime.
- **Settings:** change them under **Environment** in the dashboard; Render restarts the service.
- **Backups:** the daily S3 export keeps a copy of every business's data. Check whether your Render plan includes disk snapshots and how long they're kept.
- **Size:** 1 GB is plenty to start. You can grow the disk in the dashboard, but you can't shrink it.

## Walkthrough: AWS (when you need it)

These are the steps for an AWS Lightsail VM. It's more work than Render, so use it only if you need what AWS offers.

1. Create a Lightsail **instance** (not a container service): Ubuntu, 1 GB RAM or more, in `eu-west-1`. Attach a static IP.
2. Install Docker, clone the repo, and build the image:

   ```bash
   docker build -t ferlance .
   ```

3. Run the container with a lasting data folder and your settings in an `--env-file` (keep that file only on the server):

   ```bash
   docker run -d --restart unless-stopped -p 127.0.0.1:8000:8000 -v /srv/ferlance:/var/data --env-file /srv/ferlance.env ferlance
   ```

4. Put **Caddy** in front of it for HTTPS (`reverse_proxy 127.0.0.1:8000`), and point your domain at the static IP.
5. Turn on automatic Lightsail snapshots, and keep the daily S3 export running.
6. For updates, run `git pull`, then `docker build`, then restart the container.
