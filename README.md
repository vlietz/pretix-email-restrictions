# pretix-email-restrictions

A [pretix](https://pretix.eu) plugin that limits how often a given email address can be used when ordering tickets for an event.

## Features

- **Per-order-email limit** – how many orders a single email address may place for one event (pending + paid count; cancelled and expired do not).
- **Per-attendee-email limit** – how many tickets a single email address may appear on as the attendee email, across all orders (including multiple positions in the same order).
- **Configurable error message** – customize the message shown to the customer.
- **Organizer → event hierarchy** – set defaults at organizer level; optionally allow individual events to override them.
- **REST API enforcement** – orders created via the pretix REST API are rejected if a limit is exceeded.
- **Inline checkout error** – shown inside the checkout flow before the payment step, with options to fix the cart or change the email address.

## Requirements

- pretix ≥ 2026.1.0
- Python ≥ 3.11

---

## Installation

### General (any pretix installation)

The plugin is installed into the same Python environment that runs pretix.

**Install directly from GitHub:**

```bash
pip install git+https://github.com/vlietz/pretix-email-restrictions.git
```

**Or build and install inside the container (recommended when host and server architectures differ):**

Clone the repo on the server, copy the source into the running container, and let pip build and install it there. This ensures the wheel is compiled for the correct OS and CPU architecture (important when your dev machine is macOS/ARM and the server is Linux/x86).

```bash
# 1. SSH into your server
ssh yourserver

# 2. Clone the repo on the server
git clone https://github.com/vlietz/pretix-email-restrictions.git /opt/pretix-email-restrictions

# 3. Copy the source into the running pretix container
docker compose cp /opt/pretix-email-restrictions pretix:/tmp/plugin

# 4. Build and install inside the container
docker compose exec pretix pip3 install /tmp/plugin

# 5. Restart pretix to pick up the new package
docker compose restart pretix
```

**Updating to a newer version:**

```bash
# Pull the latest source on the server
cd /opt/pretix-email-restrictions && git pull

# Copy updated source into the container and reinstall
docker compose cp /opt/pretix-email-restrictions pretix:/tmp/plugin
docker compose exec pretix pip3 install --upgrade /tmp/plugin
docker compose restart pretix
```

After installing, **restart the pretix web workers** so the new package is picked up:

```bash
# Typical systemd setup
systemctl restart pretix-web

# Or supervisord
supervisorctl restart pretixweb
```

Then **enable the plugin** per event in the pretix control panel:
**Settings → Plugins → Email Restrictions → Enable**

**Updating to a newer version:**

```bash
pip install --upgrade git+https://github.com/vlietz/pretix-email-restrictions.git
systemctl restart pretix-web
```

---

### Docker Compose (pretix/standalone image)

If your production pretix runs via Docker Compose using the official `pretix/standalone` image, the recommended approach is to extend that image with the plugin installed inside it.

#### Step 1 — Create a custom Dockerfile

In your pretix deployment directory (where your `docker-compose.yml` lives), create a `Dockerfile`:

```dockerfile
FROM pretix/standalone:stable

USER root
RUN pip3 install git+https://github.com/vlietz/pretix-email-restrictions.git
USER pretixuser
```

#### Step 2 — Update docker-compose.yml to build the custom image

Replace the `image:` line for the pretix service with a `build:` directive:

```yaml
services:
  pretix:
    build: .          # build from the Dockerfile above
    # image: pretix/standalone:stable   ← remove or comment out this line
    restart: unless-stopped
    # ... rest of your config unchanged
```

#### Step 3 — Build and restart

```bash
docker compose build pretix
docker compose up -d pretix
```

#### Updating to a newer version

```bash
docker compose build --no-cache pretix
docker compose up -d pretix
```

The `--no-cache` flag forces pip to fetch the latest commit from GitHub.

#### Enable the plugin

Log in to the pretix control panel, go to the event's **Settings → Plugins** and enable **Email Restrictions**.

---

## Configuration

Once the plugin is enabled for an event, go to **Settings → Email Restrictions** to configure it.

| Setting | Description |
|---|---|
| **Maximum orders per order email** | How many orders a single email address may place for this event. A fresh email always passes regardless of how many tickets are in the cart. Leave empty to disable. |
| **Maximum tickets per attendee email** | How many tickets a single email address may appear on as the attendee email, across all orders (including within the same order). Leave empty to disable. |
| **Error message** | Message shown to the customer when a limit is exceeded. Leave empty to use the built-in default. |
| **'Back to ticket selection' button label** | Customize the button label on the error page. |
| **'Change email address' button label** | Customize the button label on the error page. |

The same settings are available at organizer level (**Organizer → Email Restrictions**) as defaults for all events. The organizer can also disable event-level overrides to enforce a single policy across all events.

### Limit hierarchy

1. The organizer sets defaults and can lock them by disabling **Allow individual events to override these defaults**.
2. When overrides are allowed, an event's own values take precedence.
3. An event can leave a setting empty to inherit the organizer value.

---

## Local development with Docker

The repository ships a complete `docker-compose` stack (pretix + PostgreSQL + Redis) with the plugin installed in editable mode so source changes are picked up without rebuilding the image.

```bash
# Build and start
make up

# Seed a demo environment (organizer, event, limits, test vouchers)
make demo

# Run tests
make test
```

**Admin:** http://localhost:8345/control/ · `admin@example.com` / `admin1234`
**Shop:** http://localhost:8345/demo/restrict-test/

---

## Architecture

| Component | Purpose |
|---|---|
| `restriction.py` | Core validation logic shared by the checkout step and the order_placed signal |
| `checkoutflow.py` | `EmailRestrictionStep` — blocks the checkout UI when a limit is exceeded |
| `signals.py` | `order_placed` receiver — enforces limits for API-created orders |
| `forms.py` | Settings forms for event and organizer scopes |
| `views.py` | Admin views for both scopes |

## License

Apache 2.0
