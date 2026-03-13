# pretix-email-restrictions

A [pretix](https://pretix.eu) plugin that limits the number of tickets a single email address can order per event, and the number of tickets per order.

## Features

- **Per-email limit** – maximum total tickets one email address may hold across all orders for a single event (pending + paid orders count; cancelled and expired do not).
- **Per-order limit** – maximum tickets that can be placed in a single checkout.
- **Configurable error message** – customize the message shown to the customer.
- **Organizer → event hierarchy** – set defaults at organizer level; optionally allow individual events to override them.
- **REST API enforcement** – orders created directly via the pretix REST API are rejected if a limit is exceeded.
- **Inline checkout error** – the error is shown inside the checkout flow before the payment step, with back-links to fix the cart or change the email address.

## Requirements

- pretix ≥ 2026.1.0
- Python ≥ 3.11

## Installation

Install via pip (e.g., into your pretix virtualenv):

```bash
pip install pretix-email-restrictions
```

The plugin is auto-discovered through its `pretix.plugin` entry point.
Enable it per event in the pretix control panel under **Settings → Plugins**.

## Local development with Docker

The repository ships a complete `docker-compose` stack (pretix + PostgreSQL + Redis) with the plugin installed in editable mode so source changes are picked up without rebuilding the image.

### Quick start

```bash
# 1. Build the image and start all services
make up

# 2. Follow the startup logs (takes ~60 s on first run)
make logs

# 3. Seed a complete demo environment (organizer, event, product, limits)
make demo
```

`make demo` prints the shop URL, admin credentials, and the test scenarios
to run once pretix is ready.

**Admin:** http://localhost:8345/control/ · `admin@example.com` / `admin1234`
**Shop:** http://localhost:8345/demo/restrict-test/

The demo event is pre-configured with:
- Max **2 tickets per email address**
- Max **3 tickets per order**
- A custom error message

`make demo` is idempotent — safe to run again after a restart.

### Stopping the stack

```bash
make down
```

## Running the test suite

Tests use `pytest-django` and run against an in-memory SQLite database — no running Docker stack needed.

```bash
# Install pretix and test dependencies
pip install "pretix>=2026.1.0"
pip install pytest pytest-django pytest-cov ruff
pip install -e .

# Run all tests
make test

# Run with coverage
make test-cov
```

## Configuration reference

All settings are stored via pretix's built-in settings mechanism (`event.settings` / `organizer.settings`).

| Setting key | Type | Scope | Description |
|---|---|---|---|
| `email_restriction_max_per_email` | `int` \| `None` | organizer + event | Maximum tickets one email may hold per event. Empty = disabled. |
| `email_restriction_max_per_order` | `int` \| `None` | organizer + event | Maximum tickets per single order. Empty = disabled. |
| `email_restriction_error_message` | `str` | organizer + event | Error message shown when a limit is exceeded. Empty = built-in default. |
| `email_restriction_allow_event_override` | `bool` | organizer only | Whether events can override the organizer defaults. Default: `True`. |

### Hierarchy

1. The organizer sets defaults and (optionally) locks them by setting `email_restriction_allow_event_override = False`.
2. When overrides are allowed, an event's own values take precedence over the organizer defaults.
3. An event can leave a setting empty to inherit the organizer value.

## Architecture

| Component | Location | Purpose |
|---|---|---|
| `restriction.py` | `pretix_email_restrictions/` | Pure validation logic – shared by step and signal |
| `checkoutflow.py` | `pretix_email_restrictions/` | `EmailRestrictionStep` – blocks checkout in the UI |
| `signals.py` | `pretix_email_restrictions/` | `order_placed` receiver – blocks API order creation; navigation signals |
| `forms.py` | `pretix_email_restrictions/` | `SettingsForm` subclasses for event and organizer settings |
| `views.py` | `pretix_email_restrictions/` | Admin views for both scopes |
| `urls.py` | `pretix_email_restrictions/` | URL patterns registered under `plugins:pretix_email_restrictions` |

## License

Apache 2.0
