# 1930 Helpline Register

A private hosted register with SQLite storage included. Open the app, use the host's sign-in if requested, and start working. There is no API address, GitHub token, or separate operator password to enter in the register.

## Daily use

- **New entry:** fill the call details, check the confirmation, and save. The date/time and operator are recorded automatically.
- **Remarks:** use the final table column to add follow-up notes. Previous values, operator identity, and times stay in the history.
- **Helplines:** only admins can assign or change Calling helpline and Notice helpline, using dropdowns. Operators see read-only assignments. Every admin change retains the previous assignment, admin identity, and time.
- **Export data:** download every record as CSV, JSON with remarks history, or a full SQLite database. CSV/JSON can optionally follow the current filters; SQLite always includes the entire register.
- Search, date filters, and helpline filters work across the complete register; tables show 50 rows per page.

The private app uses Sites access control and ChatGPT sign-in. It starts with access for its owner. Team access must be granted explicitly through the host's sharing settings. Making the source code public on GitHub does not grant access to register records.

## Storage and record rules

Data is stored in hosted Cloudflare D1 (SQLite), outside GitHub. The GitHub repository contains source code only. The app makes same-origin requests and never persists records or credentials in browser storage. SQLite downloads are assembled in browser memory using the bundled, self-hosted sql.js library; exports are not saved back into the register.

Server endpoints accept new entries, Remarks updates, and admin-only helpline assignments. Database triggers prevent deletion of saved entries and changes to personal/incident fields, and retain every Remarks and helpline change. Submission IDs make retries safe, and separate version checks prevent conflicting Remarks or helpline edits from silently overwriting each other. Admin status comes from the server's private `HELPLINE_ADMIN_EMAILS` setting and the verified signed-in identity; changing the browser interface cannot grant admin rights.

These rules apply to application users. A hosting/database administrator still controls the database, and a recipient controls their exported copy. Import/restore and deletion are deliberately absent from the operator interface.

## Source structure

- `ui/register.html`: the complete operator page, with its CSS and JavaScript.
- `app/route.ts`: serves the page after host sign-in.
- `app/api/[...path]/route.ts`: connects verified host identity to the API.
- `lib/register-core.mjs`: entry validation, immutable writes, remarks versioning, filtering, and export operations.
- `db/schema.ts`, `drizzle/`: database schema and versioned migrations, including record-protection triggers.
- `.openai/hosting.json`: hosted Site identity and logical D1 binding; contains no database credentials.
- `public/vendor/`: self-hosted sql.js export assets and license.

Keep the host's access control private. Every data API also rejects a missing signed-in identity. `/api/health` exposes only database readiness and the presence of the nine protection/audit triggers, without records or user details.

## Development

Requires Node.js 22.13+ and npm. Use `npm.cmd` instead of `npm` in PowerShell if its script execution policy blocks npm.ps1.

```text
npm ci
node --test tests/register.test.mjs
npm run build
```

For a local D1 preview, first build, then apply each pending migration in order:

```text
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0000_hesitant_maria_hill.sql
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0001_record_locks.sql
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0002_flat_jane_foster.sql
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0003_admin_helpline_permissions.sql
npm run dev
```

Apply migrations once per local database; do not replay applied migrations. Local development simulates host sign-in only on loopback and uses a separate local SQLite database. Hosted publication applies migrations to the production database through Sites. Never seed real case data in migrations or public source.

`node --test tests/register.test.mjs` tests the migration SQL against SQLite, locks, audit history, idempotent saves, conflicts, auth, filters, pagination, all export formats, and the absence of the old setup form. It uses in-memory data only.
