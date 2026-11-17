# How-to guides: Revision Rounds

## Create a project

Set up a new project with a contracted revision-round limit

1. Open product/index.html in your browser.
2. Type the project name in **Project name**.
3. Type the number of contracted revision rounds in **Contracted revision rounds** (minimum 1).
4. Click **Create project**.

**Result:** The project view appears showing the project title, round counter (Round 0 of N), and an empty revision list.

## Log a revision request

Record a client revision request and update the round counter

1. In the project view, type a brief description of the client's request in **Revision request description** (e.g., "Client requested header color change and font size increase").
2. Click **Log revision request**.

**Result:** The round counter increments by 1, the request appears in the revision list with a timestamp, and the data is saved to localStorage.

## Export client-ready summary

Generate a shareable summary of scope status for the client

1. In the project view, click **Export client-ready summary**.

**Result:** A text file downloads named `<project-name>-revision-summary.txt` containing project name, contracted rounds, rounds used, rounds remaining, and all logged requests with timestamps.

## Start a new project

Switch to a different project while keeping the previous one saved

1. In the project view, click **New project**.
2. Enter the new project name and contracted rounds.
3. Click **Create project**.

**Result:** The new project becomes active. The previous project's data remains in localStorage but is not displayed until you clear the current project and re-enter its details.

## Clear all data

Permanently delete all saved project data from the browser

1. In the project view, click **Clear all data**.
2. Confirm the deletion in the browser dialog.

**Result:** All localStorage data for Revision Rounds is removed. The create-project view appears again.
