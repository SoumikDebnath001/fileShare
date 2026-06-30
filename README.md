# fileShare

A tiny self-hosted cloud file storage website. Light enough to run on a
**Raspberry Pi Zero 2 W**, auto-starts on boot, and is reachable through your
own domain so you can upload and download files from anywhere.

- Password-protected login (single shared password)
- Drag-and-drop multi-file upload, download, delete
- Stores files as plain files on disk (point it at a USB drive for more space)
- Runs under `waitress` + `systemd`, fronted by `nginx` for your domain

---

## 1. Try it on your computer first

```bash
pip install -r requirements.txt
FILESHARE_PASSWORD=test python3 app.py
```

Open <http://127.0.0.1:8000>, log in with `test`. Press `Ctrl+C` to stop.

---

## 2. Put it on the Raspberry Pi

These assume you cloned the repo to `/home/pi/fileShare`. Adjust the paths if
your user or location differs (and update `deploy/fileshare.service` to match).

```bash
# On the Pi
cd ~
git clone https://github.com/<you>/fileShare.git
cd fileShare

# Create an isolated Python environment and install deps
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Configure secrets
cp .env.example .env
nano .env        # set FILESHARE_PASSWORD and FILESHARE_SECRET
```

Generate a session secret for `.env`:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

> Tip: to store files on a USB stick instead of the SD card, mount it and set
> `FILESHARE_STORAGE=/mnt/usb` in `.env`.

---

## 3. Auto-start on boot (systemd)

```bash
sudo cp deploy/fileshare.service /etc/systemd/system/fileshare.service
sudo systemctl daemon-reload
sudo systemctl enable --now fileshare      # start now AND on every boot
```

Now the server comes up automatically whenever the Pi powers on — no manual
restarts. Useful commands:

```bash
systemctl status fileshare      # is it running?
journalctl -u fileshare -f      # live logs
sudo systemctl restart fileshare
```

---

## 4. Reach it from your domain (nginx)

Point your domain's DNS A record at the Pi's public IP (or use a Dynamic DNS
service if your home IP changes), and make sure your router forwards port 80
(and 443 for HTTPS) to the Pi.

```bash
sudo apt install nginx
sudo cp deploy/nginx.conf /etc/nginx/sites-available/fileshare
sudo ln -s /etc/nginx/sites-available/fileshare /etc/nginx/sites-enabled/
sudo nano /etc/nginx/sites-available/fileshare   # set your real domain
sudo nginx -t && sudo systemctl reload nginx
```

Add free HTTPS:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d files.yourdomain.com
```

Visit `https://files.yourdomain.com`, log in, and you're done.

---

## How it fits together

```
  Browser ──HTTPS──> nginx (:443, your domain) ──> waitress/Flask (127.0.0.1:8000)
                                                          └── files saved in storage/
```

`systemd` keeps the Flask app alive across reboots and crashes; `nginx`
terminates TLS and forwards requests to it.

---

## Security notes

- Always set a strong `FILESHARE_PASSWORD` before exposing to the internet.
- Keep the app bound to `127.0.0.1` (the default) so only nginx can reach it.
- The `storage/` folder and `.env` are git-ignored — your files and password
  never get committed.
- Consider enabling HTTPS (step 4) so your password isn't sent in plain text.
