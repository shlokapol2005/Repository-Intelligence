# Code Detective — GitHub App Setup

The PR impact bot runs in two modes, selected automatically:

- **PAT mode (default / current):** uses `GITHUB_TOKEN`. Works only on repos that
  token can access. No app registration needed.
- **App mode:** uses a registered GitHub App. Anyone can **install it in one click**
  on their own repos (public or private) — no webhook/secret/token setup on their end.

App mode activates automatically when `GITHUB_APP_ID` + a private key are configured
**and** the webhook payload carries an `installation.id`. Otherwise it falls back to
the PAT, so nothing breaks before you finish registering the app.

## Prerequisites (do these first)

1. Deploy the backend on an **always-on** host (not a sleeping free tier) — GitHub
   expects the webhook to respond within ~10s. The handler already returns `202`
   immediately and processes in the background, so it just needs to be awake.
2. No persistent disk required: the app **re-clones repos on demand** (`resolve_repo`),
   so it's stateless across restarts.

## Register the GitHub App

1. GitHub → **Settings → Developer settings → GitHub Apps → New GitHub App**.
2. **Webhook URL:** `https://<your-backend-host>/webhook/github`
3. **Webhook secret:** a random string → set it as `GITHUB_WEBHOOK_SECRET`.
4. **Repository permissions:**
   - **Contents:** Read-only  (to clone the repo)
   - **Pull requests:** Read & write  (to read changed files + post the comment)
   - **Metadata:** Read-only  (required)
5. **Subscribe to events:** **Pull request**.
6. Create the app, then **generate a private key** (downloads a `.pem`).
7. Note the **App ID** (shown on the app's page).

## Configure the backend env

```
GITHUB_APP_ID=<your app id>
GITHUB_WEBHOOK_SECRET=<the secret from step 3>

# The private key — choose ONE:
#  (a) inline PEM contents (best for Render/hosted; escape newlines as \n if needed)
GITHUB_APP_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n
#  (b) or a path to the .pem file (local dev)
GITHUB_APP_PRIVATE_KEY_PATH=/path/to/app.private-key.pem
```

`GITHUB_TOKEN` is no longer required once App mode is configured (it remains the
fallback if the app credentials are absent).

## Install & use (this is the "zero setup" part for users)

1. Open the app's public page → **Install** → choose repos (or "All repositories").
2. Open a PR on an installed repo. Within seconds Code Detective clones the repo,
   builds the dependency graph, and posts/updates an **impact analysis** comment
   (blast radius + affected API routes + risk).

That's it — no webhook URL, no secret, no token for the installer.

## How auth works (for reference)

`backend/utils/github_app.py`:
- `generate_app_jwt()` — signs a 10-min JWT with the private key (authenticates *as the app*).
- `get_installation_token(installation_id)` — exchanges the JWT for a ~1h installation
  token (cached until near expiry).
- `get_token(installation_id)` — the single seam: App token if configured, else PAT.

The installation token is what clones private repos (`x-access-token:<token>@github.com/...`,
scrubbed from `.git/config` after use) and posts PR comments **as the app**.
