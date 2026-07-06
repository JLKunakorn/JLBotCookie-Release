# JL Bot Cookie Release

Latest release version: `v1.0.1`

This repository contains the Windows bot release staging files and the Cloudflare Worker license/shop backend.

## Project Layout

- `Build EXE/` - packaged Windows release staging folder for `JLmain_V1.0.1_Premium`
- `JLCookie/` - application source and Cloudflare Worker project
- `JLCookie/license_server/cloudflare/` - Worker, D1 schema/migrations, public shop page, and deployment config

## Live Worker

- Customer site: `https://jlcookie-license.aura-secretary.workers.dev/`
- License verify API: `https://jlcookie-license.aura-secretary.workers.dev/api/verify`

Cloudflare secrets such as `ADMIN_TOKEN`, `ADMIN_PATH`, `DOWNLOAD_URL`, and signing keys are not stored in this repository.
