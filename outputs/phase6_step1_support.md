# 6.1 Support: Support workflow, FAQ and response templates

`[Phase 6: Operate and learn | Step 6.1 | Repeat 0/2 | Last gate: GO]`

Venture: **Revision Rounds - scope tracker for freelance web designers** | Run `20261117-193518-revision-rounds-scope-tracker-for-freela` | Attempt 0 | Generated 2026-11-17T19:51:14Z

**What I'm doing now:** Set up support with 7 FAQ entries, 7 ticket categories and 7 response templates. The gate needs real tickets with timestamps.

## FAQ / knowledge base (from the step 3.3 user docs)

**How do I create a new project with a revision round limit?**  
Open the app, click **New Project**, enter a project name and set the number of revision rounds agreed with the client. The project is then saved in your browser’s localStorage.  
_Source: quick-start_

**How can I log a client revision request?**  
Within an open project click the **Log Revision** button. Each click records one revision request and updates the round counter automatically.  
_Source: how-to_

**How do I see the current round count versus the contracted limit?**  
The dashboard shows **Round X of Y** for the active project, where *X* is the number logged and *Y* is the limit you set when creating the project.  
_Source: quick-start_

**How can I export a client‑ready summary?**  
Click the **Export Summary** button on the project page. The tool generates a single HTML file (you can print to PDF) that lists all logged revisions and the remaining round count.  
_Source: faq_

**What happens to my data if I clear my browser’s localStorage?**  
All project data is stored only in the browser’s localStorage. If you clear browser data or click **Clear all data**, the project information is permanently lost.  
_Source: limitations_

**Can I use Revision Rounds on more than one device?**  
No. The current version does not sync data between devices; each browser instance holds its own copy of the project data.  
_Source: limitations_

**Which browsers are supported?**  
The tool has been tested in the latest versions of Chrome, Firefox, Safari, and Edge. Other browsers may work but are not officially supported.  
_Source: limitations_

## Ticket categories

| Id | Category | Description | Examples |
|---|---|---|---|
| onboarding | Onboarding | Questions or issues that arise when a new user first opens the tool, creates a project, or sets the revision limit. | User cannot find the **New Project** button.; User reports that the round counter does not appear after creating a project. |
| confusion | Confusion | User does not understand how a feature works or misinterprets UI elements. | User thinks clicking **Log Revision** adds a new project instead of a revision.; User is unsure whether the exported file is PDF or HTML. |
| missing_feature | Missing Feature | Requests for functionality that is not part of the MVP or documented limitations. | User asks for cloud sync across devices.; User wants a client‑facing portal to view revision status. |
| reliability | Reliability | Bugs that cause crashes, data loss, or the tool to become unusable. | App freezes after logging a revision.; Data disappears after switching browsers. |
| fulfillment | Fulfillment | Problems with delivering the expected output, such as export failures. | Exported HTML file is empty.; Download of the summary is blocked by the browser. |
| trust_privacy | Trust & Privacy | Concerns about how data is stored, security, or privacy implications of localStorage. | User worries that client data could be accessed by other sites.; User asks whether data is encrypted. |
| offer_misunderstanding | Offer Misunderstanding | User expectations that differ from the documented product scope. | User expects multi‑user collaboration.; User believes the tool includes email notifications. |

## Severity levels

| Level | Definition | First-response target (hours) |
|---|---|---|
| critical | Issue prevents any use of the product or results in total data loss (e.g., app crashes on launch, localStorage cleared unintentionally). | 4 |
| high | Major functionality broken that blocks core workflow (e.g., export fails, round counter never updates). | 8 |
| medium | Non‑critical bug or UI issue that hampers efficiency but work can continue (e.g., mis‑labelled button, minor layout glitch). | 24 |
| low | Minor annoyance, typo, or cosmetic issue that does not affect functionality. | 48 |

## Response templates

### Help with Getting Started (`onboarding`)

Hi {{user_name}},

Thanks for reaching out. I understand you’re having trouble with the initial setup. To help you get started, could you let me know which step you’re stuck on (e.g., creating a new project or setting the revision limit)? Once I have that detail I can walk you through the exact clicks.

Best,
Support Team

### Clarifying Feature Usage (`confusion`)

Hi {{user_name}},

I see the {{feature}} is causing some confusion. It works by {{brief_explanation}}. Could you share a screenshot or describe what you see on your screen? That will let me confirm you’re using it as intended.

Thanks,
Support Team

### Feature Request Received (`missing_feature`)

Hi {{user_name}},

Thank you for the suggestion about {{requested_feature}}. The current version does not include that capability (see the Limitations doc). I’ll forward your request to the product team for future consideration. In the meantime, let me know if there’s a workaround we can suggest.

Regards,
Support Team

### Bug Report Acknowledgement (`reliability`)

Hi {{user_name}},

I’m sorry you’re experiencing a crash/ data loss. Could you provide the following information so we can reproduce the issue?
- Browser name and version
- Steps leading up to the problem
- Any error messages shown in the console (if you can open developer tools)

We’ll investigate as soon as possible.

Thanks,
Support Team

### Export Issue Follow‑up (`fulfillment`)

Hi {{user_name}},

I understand the export isn’t working for you. Please let me know:
- Which browser you’re using
- Whether you see any error dialogs when clicking **Export Summary**
- If the downloaded file is empty or fails to download entirely

With those details I can pinpoint the cause.

Best,
Support Team

### Data Privacy Clarification (`trust_privacy`)

Hi {{user_name}},

Your privacy is important to us. All data is stored locally in the browser’s localStorage and never sent to a server. This means the data is only as secure as the device you’re using. If you have specific concerns (e.g., about other sites accessing localStorage), let me know and I can share best‑practice tips.

Regards,
Support Team

### Scope of the Current Version (`offer_misunderstanding`)

Hi {{user_name}},

It looks like you expected {{misunderstood_feature}}. The current MVP is intentionally limited to local, single‑user tracking (see the Limitations doc). Features like cloud sync, multi‑user collaboration, or email notifications are not part of this release.

If you need those capabilities, we can discuss alternative tools or future roadmap plans.

Thanks,
Support Team

## Escalation rules

- Any ticket marked **critical** is escalated to the founder within 2 hours of receipt.
- A **high** severity ticket that is not resolved within the first‑response target (8 hours) and remains open after 24 hours is also escalated.
- Repeated tickets (≥3) of the same category and severity within a 7‑day window trigger escalation.
- A critical incident is defined as: data exposure (e.g., localStorage data accessible to other sites), the product becoming completely unusable for all users (e.g., app fails to load for any browser), or a wrong delivery that prevents the user from sending a client‑ready summary.

## Hours

- Targets are set in **calendar hours**.
- The gate measures first-response time in calendar hours from the ticket timestamps.

## How tickets are reported and measured

Submit tickets as a JSON list: `{category, severity, created_at, first_response_at, resolved_at}` (ISO 8601 times; mark practice tickets with `"drill": true`). Code computes the count, the median and maximum first-response hours and the critical issues open longer than 72 hours. Drills are excluded from the gate. With zero real tickets there is no observed response time, so the gate cannot be evaluated.

## Gaps in the user docs

- How to safely back up/export data before clearing the browser.
- Step‑by‑step guide for switching between multiple projects (currently not supported).
- What to do if localStorage is accidentally cleared – recovery options.
- Detailed FAQ on why cloud sync is not available and future roadmap.

## What I need from you

1. What is the expected volume of support tickets per week once the MVP launches?
2. Do you prefer escalation to be sent via email or a dedicated Slack channel?
3. Are there any planned timelines for adding cloud sync or multi‑user features that we should communicate to users?
