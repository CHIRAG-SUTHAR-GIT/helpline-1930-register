# Helpline 1930 register

Open the [private register](https://helpline1930-register.new-mesa-3501.chatgpt.site). The [GitHub Pages link](https://chirag-suthar-git.github.io/helpline-1930-register/) opens the same app automatically.

The page and SQLite database are hosted together. There is no API address or separate operator password to configure in the register. Use the host's sign-in if requested. The app starts private, with the owner configured as its admin.

- Personal details, incident details, and the recorded date cannot be changed after an entry is saved. Entries cannot be deleted through the app.
- **Calling helpline and Notice helpline:** only admins can assign or change them, using dropdowns. Operators see read-only assignments. Admin changes retain the previous values, identity, and time.
- **Remarks:** operators can update the last column; every change retains its history.
- **Exports:** download all records as CSV, JSON, or a complete SQLite database. JSON and SQLite include both Remarks and helpline change histories. Filters are optional for CSV/JSON; SQLite always includes everything.

## Source and storage

The full application source is in [hosted/](hosted/), with developer instructions in [hosted/README.md](hosted/README.md). The operator page is [hosted/ui/register.html](hosted/ui/register.html). The root `index.html` is the GitHub Pages entry point that opens the hosted app.

GitHub stores the source code. The actual records are stored privately in hosted Cloudflare D1 (SQLite), outside this public repository. Local preview records and exported databases are excluded from Git. No real records from the original screenshot have been imported or seeded.

Application access is controlled by the host. The owner is the admin; additional operators must be granted access explicitly. The private server setting `HELPLINE_ADMIN_EMAILS` determines admin rights from the verified signed-in identity. It is not included in public source.

The restrictions apply to application users. Hosting/database administrators still control the underlying database, and recipients control downloaded copies.

## Verification

The hosted app has 13 automated checks covering record locks, retries, conflicts, admin-only dropdown assignments, immutable histories, authentication, filters, pagination, and all export formats. From the `hosted` folder, run:

```text
npm ci
node --test tests/register.test.mjs
npm run build
```

In PowerShell, use `npm.cmd` if npm.ps1 is blocked by the local execution policy. Browser QA used fictional data in a separate local SQLite database. The production database was checked for readiness and all nine protection/audit triggers without inserting test records.
