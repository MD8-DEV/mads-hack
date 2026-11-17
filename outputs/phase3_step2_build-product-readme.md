# Revision Rounds

A single-file web tool for solo freelance web/UI designers to track client revision requests against a contracted round limit on fixed-price projects.

## Usage

1. Open `product/index.html` in any modern browser (Chrome, Firefox, Safari, Edge). No server or build step required.
2. Enter a project name and the number of revision rounds included in your contract.
3. Click **Create project**.
4. When a client requests a change, type a brief description and click **Log revision request**. The round counter updates immediately.
5. At any point, click **Export client-ready summary** to download a plain-text file you can send to the client. The summary shows:
   - Project name
   - Contracted rounds
   - Rounds used
   - Rounds remaining
   - Each logged request with timestamp
6. To start a new project, click **New project** (this keeps the current project saved in your browser).
7. To wipe all data, click **Clear all data** and confirm.

Data persists in your browser's localStorage under the key `revision-rounds-project`. No account, login, or internet connection is needed after the initial page load.

## Data and privacy

- All data stays in your browser. Nothing is sent to any server.
- The only storage used is `localStorage` (one namespaced key).
- Export creates a downloadable text file via a Blob; no network request occurs.
- Clearing data removes the localStorage entry immediately.

## Limitations

- Single project at a time (switching projects retains the previous one in localStorage).
- No multi-user collaboration, cloud sync, or client-facing portal.
- No email notifications or automated client communication.
- No analytics, tracking, or third-party scripts.
- No payments, subscriptions, or monetization features.
- Export is plain text; PDF generation would require a library (excluded to keep the file self-contained and under 200 KB).
- Tested in current versions of Chrome, Firefox, Safari, and Edge.
