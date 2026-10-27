# Helpline 1930 register

`index.html` is one self-contained page: HTML, CSS, JavaScript, and icons, with no CDN or build step. It follows the columns in the supplied screenshot. No victim records from the screenshot have been copied into the application.

The page supports:

- New entries: calling helpline, victim name, DOB, PIN/reference, automatic entry date in IST, MO, mobile number, notice helpline, and remarks.
- Permanent entry details. Only the final **Remarks** column is editable after submission.
- A named operator and timestamp for every remarks change, with previous values retained.
- Search, date and helpline filters, 50-record pages, and refresh.
- Exports of **all records**, or filtered records, to CSV and JSON. Full SQLite database download includes all records and remarks history.
- Operator sign-in. Records and passwords are not stored in browser local storage. Only the non-secret API address is remembered. Refreshing the page requires signing in again.

## Why the API is included

GitHub Pages hosts static files and cannot run Python or write to a shared SQLite database. [GitHub's documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site).

This project therefore uses:

```text
GitHub Pages: index.html
        | authenticated HTTPS requests
        v
Private API: backend/server.py (host separately)
        | server-only GitHub token
        v
PRIVATE GitHub repository: data/helpline.sqlite3
```

In `STORAGE_MODE=github`, the SQLite file in the private GitHub repository is the authoritative database. Each successful write commits the SQLite file to that repository. The API reads the file into an in-memory SQLite database and commits changes using the previous file SHA. On a conflict, it reloads and retries instead of overwriting someone else's save. GitHub documents this API in [Repository contents](https://docs.github.com/en/rest/repos/contents).

**Uploading only the HTML to GitHub Pages will display the page; saving requires the deployed API.** Never put a GitHub token in the HTML. Using a token in browser code would let visitors bypass the entry restrictions and access the repository.

## 1. Test on your computer

Requires Python 3.11 or later, with SQLite serialize/deserialize support (the standard Windows Python distribution includes it). No Python packages are needed.

Open PowerShell in this folder:

```powershell
./START-LOCAL.ps1
```

Choose a username and a password of at least 12 characters. Open `http://localhost:8000`, click **Connect**, and sign in with those credentials. Records are saved in `data/helpline.sqlite3` on this computer. The page explicitly marks this as **local testing mode**. Press Ctrl+C in PowerShell to stop the server.

If your execution policy blocks the script, configure the equivalent environment variables in `.env` as described below, set `STORAGE_MODE=local`, and run `python backend/server.py`.

## 2. Create the private GitHub data repository

1. Create a **private** repository, for example `helpline-private-data`. Initialize it with a README so its `main` branch exists. Keep it separate from the public website source repository.
2. Create a fine-grained personal access token restricted to this data repository, with **Contents: Read and write** and metadata read access. Store it only as an API server secret. [GitHub token instructions](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).
3. Use `GITHUB_REPO=YOUR-USERNAME/helpline-private-data` and `GITHUB_BRANCH=main`.
4. The API creates `data/helpline.sqlite3` on the **first successful entry**. Do not upload a blank file manually. The API refuses to use a public data repository.

## 3. Host the API

Use any host that runs a Python web process or the included Dockerfile, behind HTTPS. GitHub Pages cannot host this API. No persistent disk is required in GitHub storage mode.

The start command is:

```text
python backend/server.py
```

Set the following in the host's environment/secret settings. For local configuration, copy `.env.example` to `.env`; `.env` is excluded from Git.

| Variable | Required value |
| --- | --- |
| `STORAGE_MODE` | `github` |
| `GITHUB_REPO` | `YOUR-USERNAME/helpline-private-data` |
| `GITHUB_BRANCH` | `main` (or the initialized branch you chose) |
| `GITHUB_DB_PATH` | `data/helpline.sqlite3` |
| `GITHUB_TOKEN` | Fine-grained token, stored as a secret |
| `USERS_JSON` | `{"operator1":"a-long-unique-password","operator2":"another-long-unique-password"}`; replace the example passwords |
| `SESSION_SECRET` | A random secret of at least 32 characters; keep stable across instances |
| `ALLOWED_ORIGINS` | Your website's origin, e.g. `https://YOUR-USERNAME.github.io` |
| `HOST` | `0.0.0.0` on a hosted server |
| `PORT` | Port provided by the host, or `8000` |

Usernames must be 2–50 letters, digits, underscores, dots, or hyphens. Each password must be at least 12 characters. Generate the session secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and store it as a secret. All configured operators can view, add entries, edit remarks, and export. Remove an account or change its password to invalidate that account's sessions. Sessions also expire after 12 hours.

For `https://YOUR-USERNAME.github.io/helpline/`, the allowed origin is **`https://YOUR-USERNAME.github.io`**, without `/helpline/`. Separate multiple origins with commas. Use HTTPS for the public API; plain HTTP is allowed by the page only for localhost testing. Place the API behind your host's HTTPS reverse proxy; it is a small standard-library HTTP service, without a built-in TLS server. Health check path: `/health`. It reports process readiness, not a live GitHub connection check.

Docker option:

```text
docker build -t helpline-register .
docker run --env-file .env -e HOST=0.0.0.0 -p 8000:8000 helpline-register
```

Put the container behind your host's HTTPS proxy. Do not expose the `.env` file in the website repository or image.

## 4. Put the HTML on GitHub Pages

1. Upload **`index.html`** to the root of your website repository. The API files can stay in your source repository but are not executed by Pages. Keep the private data repository separate.
2. In repository **Settings → Pages**, choose deployment from the `main` branch and `/ (root)`.
3. Open the resulting GitHub Pages URL and click **Connect**.
4. Enter your deployed API base URL, username, and password. The base URL should not end with `/api`.
5. Optional: set `DEFAULT_API_URL` near the start of the script in `index.html` to your API's public HTTPS address. Do not add credentials there.

Use the page's **New entry** button to save a test record with clearly fictional details. Verify it appears from a second browser after signing in, check Remarks history after an update, and download all three export types. Test entries are permanent too, so perform pre-launch testing with local mode or a separate private test repository.

## What is enforced

- There is no delete endpoint or general entry update endpoint.
- PATCH accepts only `remarks` and the current remarks version. An extra field such as `victim_name` is rejected.
- SQLite triggers reject changes to locked entry fields and deletion of entries. Additional triggers preserve remark history.
- Concurrent remarks edits return a conflict, so a user's draft does not silently replace another user's changes. Copy the draft, close the editor, refresh the register, and reopen it to load the latest remarks before retrying.
- New-entry requests include a unique submission ID. Retrying the same request after a network timeout does not create a duplicate record. If the outcome is uncertain, keep the form open and retry it; reopening a new form creates a new submission ID.
- CSV exports neutralize formula-like values for spreadsheet safety and include a UTF-8 BOM for Gujarati and other Unicode text. They are intended for viewing in spreadsheets. JSON and SQLite preserve exact text values and include remarks history.
- Only the API server has repository credentials. All data endpoints require a valid operator session.

**Scope of the lock:** ordinary application users cannot delete or change saved details. A repository owner, backend administrator, or person with direct database/token access can still replace the database or remove its triggers. No HTML page can prevent a repository owner from changing their own files. Downloaded SQLite copies are also under the recipient's control. This is an application restriction, not tamper-proof archival storage.

## Operating limits

This GitHub-file storage design is for a small, low-traffic register. Each read retrieves the database and each change rewrites the full SQLite file; Git stores binary versions. The page refreshes every two minutes while visible and idle. Multiple operators consume the same GitHub API allowance. The implementation sets a **20 MB database limit** and retries write conflicts up to four times. GitHub repository/API limits still apply. [GitHub API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).

For a busy production call centre, use a hosted SQLite-compatible database or dedicated database server and keep GitHub for source/backups. This project does not silently substitute browser storage for the shared register. Exports are downloads; restoring/importing databases is deliberately not offered to operators because it could alter permanent records.

Keep the data repository private and limit its collaborators. Changing it to public would expose its files and history; the API privacy check cannot undo that. Keep exported files private too. Configure host-level throttling for a public API. The built-in sign-in throttle is per process/IP; behind a proxy, several users may share one IP. Multi-instance deployments should add shared throttling at the proxy.

## Verification

Run:

```text
python -m unittest discover -s tests -v
```

The suite uses temporary databases and a simulated GitHub API. It does not contact or change a real repository. The live GitHub integration requires deployment credentials and should be verified with a private test repository before real data entry.
