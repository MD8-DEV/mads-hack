# 4.2 Draft legal policies: Draft Terms, Privacy and Refund policies (not legal advice)

`[Phase 4: Commercial setup | Step 4.2 | Repeat 0/2 | Last gate: GO]`

Venture: **Revision Rounds - scope tracker for freelance web designers** | Run `20261117-193518-revision-rounds-scope-tracker-for-freela` | Attempt 0 | Generated 2026-11-17T19:49:30Z

**What I'm doing now:** Drafted Terms, Privacy and Refund policies tailored to the prototype's data. They are drafts, not legal advice: a qualified lawyer must review them before any real use.

**DRAFT, not legal advice. Must be reviewed by a qualified lawyer before use.**

Approving this step requires acknowledging that these are drafts and that a qualified lawyer must review them. Approval publishes the HTML versions to the local MOCKED site only.

Jurisdiction: **Egypt**

| Document | Markdown | Page |
|---|---|---|
| Terms of Service | terms.md | terms.html |
| Privacy Policy | privacy.md | privacy.html |
| Refund Policy | refund.md | refund.html |

## Data the prototype handles

| Data | Collected when | Stored as | Purpose | Recipients | Retention |
|---|---|---|---|---|---|
| Waitlist email address | A visitor joins the waitlist on the landing page | A one-way hash of the email, a consent flag and a timestamp (the plain email is not kept by the prototype) | Count real sign-ups and record consent | None (stored locally by the prototype) | Not set yet: founder to decide (TO CONFIRM WITH COUNSEL) |
| Page-view events | A visitor opens the landing, pricing or store page | Page name, timestamp and a random visitor id generated for the browser (not linked to a name or email) | Count unique visitors for the demand tests | None (stored locally by the prototype) | Not set yet: founder to decide (TO CONFIRM WITH COUNSEL) |
| Mock order requests (MOCKED) | A visitor clicks Buy on the store page | Order id, product id, timestamp and the random visitor id; no-charge, nothing is sold | Measure buy intent and test the MOCKED delivery flow | None (stored locally by the prototype) | Not set yet: founder to decide (TO CONFIRM WITH COUNSEL) |
| Payment data | Never | Not collected: no card, bank or payment details; no payment provider | - | - | - |

## Implementation checklist

- [ ] Have a qualified lawyer review all three drafts before any real use.
- [ ] Confirm that Egypt is the governing jurisdiction and where buyers are located.
- [ ] Set retention and deletion periods for waitlist hashes, page-view events and mock orders.
- [ ] Add a real support and privacy contact address to every policy.
- [ ] Link the policies from the landing, pricing and store pages.
- [ ] Replace the MOCKED refund section with counsel-reviewed terms before any real payment is introduced.
- [ ] Set and document retention periods for each data category (waitlist hash, page-view events, mock orders) and implement automated deletion.
- [ ] Add a support contact (email or form) and publish it in the Terms and Privacy Policy.
- [ ] Implement a user-facing way to request data access, rectification, and deletion (e.g., a "My Data" page or contact form).
- [ ] Add a cookie/consent banner if any non-essential localStorage usage is added (currently only essential).
- [ ] Create a Terms acceptance flow (checkbox on waitlist/sign-up) and record consent timestamp.
- [ ] Link Privacy Policy and Terms of Service in the website footer and on sign-up/purchase pages.
- [ ] Obtain legal review from a qualified Egyptian lawyer before launching any paid version.
- [ ] If integrating a payment processor later, update data inventory, privacy policy, and refund policy accordingly.
- [ ] Implement age verification if the service targets users under 18 (TO CONFIRM WITH COUNSEL).

## Questions for counsel

1. Which consumer-protection and data-protection rules apply to this product, founder and buyers?
2. Is a hashed email with a consent flag enough to show valid consent for a waitlist here?
3. What must change in these drafts before real payments or refunds are introduced?
4. What are the mandatory data retention periods for waitlist sign-ups and analytics events under Egyptian Law No. 151 of 2020 (Personal Data Protection Law)?
5. Does Egyptian consumer law require a 14-day cooling-off period for digital subscriptions, and can it be waived by terms?
6. What are the required elements for a valid electronic contract formation in Egypt (e.g., clickwrap acceptance)?
7. Are there specific rules for refunds of digital goods/services that cannot be returned (e.g., access to a SaaS tool)?
8. What age of consent applies for data processing of minors, and is parental consent required?
9. Must the Privacy Policy be in Arabic, or is English sufficient for a service targeting freelance designers?
10. Are there any registration or notification requirements for data controllers under the PDPL before processing begins?

## Discrepancies between the build and the drafts

- The prototype stores data only in localStorage (client-side), but the Privacy Policy describes the provider as a data controller. If no server-side processing occurs, the controller role may be ambiguous (TO CONFIRM WITH COUNSEL).
- No user accounts exist yet; the Terms refer to "user-provided data" but the only user-provided data is the waitlist email hash. The Terms should be updated when accounts are added.
- No payment processing is implemented, yet the pricing page shows prospective prices. The Terms and Refund Policy must clearly state that no purchase is possible today.
- No mechanism for users to exercise data subject rights (access, deletion) is built. The Privacy Policy mentions clearing browser data as a workaround, but a formal process is needed for compliance.
- The support contact is null; both Terms and Privacy Policy require a contact method.
- No cookie consent banner is present; if any third-party scripts are added later, consent management will be required.
- The mock order flow uses a "Buy" button that could be mistaken for a real purchase. The UI should label it clearly as a test (e.g., "Simulate Purchase").
- Privacy draft mentions 'Payment Data', which the data inventory does not list: verify it in the build or remove it.

## Checks applied in code

- Refund: the model omitted the draft banner; it was added.

## Full drafts

### terms.md

DRAFT, not legal advice. Must be reviewed by a qualified lawyer before use.

> Jurisdiction (from the founder's brief): Egypt. Every statement about a specific law is TO CONFIRM WITH COUNSEL.

#### Terms of Service

##### 1. Service Description
Revision Rounds ("the Service") is a digital scope-tracking tool for freelance web and UI designers working solo on fixed-price client projects. The Service helps designers track revision rounds against contracted limits. The current prototype is a static web application that stores data locally in the user's browser (localStorage) and does not process payments.

##### 2. Acceptance of Terms
By accessing or using the Service, you agree to these Terms. If you do not agree, do not use the Service.

##### 3. User Responsibilities
- You are responsible for the accuracy of any data you enter into the Service.
- You must not use the Service for any unlawful purpose or in any way that could damage, disable, or impair the Service.
- You acknowledge that the Service is a tracking aid only; it does not create, modify, or enforce legal contracts between you and your clients.

##### 4. Intellectual Property
All rights, title, and interest in the Service (excluding user-provided data) remain with the provider. You retain ownership of your project data.

##### 5. Disclaimer of Warranties
THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT. TO CONFIRM WITH COUNSEL: extent of permissible disclaimers under Egyptian consumer protection law.

##### 6. Limitation of Liability
TO THE MAXIMUM EXTENT PERMITTED BY LAW, THE PROVIDER SHALL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR ANY LOSS OF PROFITS, DATA, OR BUSINESS OPPORTUNITIES. TO CONFIRM WITH COUNSEL: enforceability of liability limitations under Egyptian law.

##### 7. Governing Law and Jurisdiction
These Terms shall be governed by the laws of Egypt. TO CONFIRM WITH COUNSEL: mandatory consumer protection provisions that may override choice of law.

##### 8. Changes to Terms
We may update these Terms from time to time. Continued use of the Service after changes constitutes acceptance. We will notify users of material changes via the Service or by email (if provided).

##### 9. Termination
You may stop using the Service at any time. We may suspend or terminate access if you breach these Terms.

##### 10. Contact
For questions about these Terms, contact the provider at the support address listed in the Privacy Policy (currently not set).


### privacy.md

DRAFT, not legal advice. Must be reviewed by a qualified lawyer before use.

> Jurisdiction (from the founder's brief): Egypt. Every statement about a specific law is TO CONFIRM WITH COUNSEL.

#### Privacy Policy

##### 1. Data Controller
The provider of Revision Rounds ("we", "us") is the data controller for personal data processed through the Service. Contact: [TO BE PROVIDED BY FOUNDER].

##### 2. Data We Collect
We only collect the following data, and only as described below:

###### 2.1 Waitlist Email Address
- **What**: A one-way hash of the email address, a consent flag, and a timestamp.
- **When**: When a visitor joins the waitlist on the landing page.
- **Purpose**: To count real sign-ups and record consent.
- **Storage**: Stored locally by the prototype (localStorage). The plain email is not kept.
- **Recipients**: None.
- **Retention**: Not set yet – founder to decide (TO CONFIRM WITH COUNSEL).

###### 2.2 Page-View Events
- **What**: Page name, timestamp, and a random visitor ID generated for the browser (not linked to a name or email).
- **When**: When a visitor opens the landing, pricing, or store page.
- **Purpose**: To count unique visitors for demand tests.
- **Storage**: Stored locally by the prototype.
- **Recipients**: None.
- **Retention**: Not set yet – founder to decide (TO CONFIRM WITH COUNSEL).

###### 2.3 Mock Order Requests
- **What**: Order ID, product ID, timestamp, and the random visitor ID.
- **When**: When a visitor clicks "Buy" on the store page.
- **Purpose**: To measure buy intent and test the mocked delivery flow.
- **Storage**: Stored locally by the prototype.
- **Recipients**: None.
- **Retention**: Not set yet – founder to decide (TO CONFIRM WITH COUNSEL).

###### 2.4 Payment Data
- **What**: Not collected. No card, bank, or payment details are gathered; no payment provider is integrated.

##### 3. Legal Basis for Processing (TO CONFIRM WITH COUNSEL)
Under Egyptian data protection law, the legal bases for the above processing must be identified (e.g., consent, legitimate interest).

##### 4. Data Subject Rights (TO CONFIRM WITH COUNSEL)
You may have rights to access, rectify, erase, restrict, or port your data, and to object to processing. Because the prototype stores data locally in your browser, you can clear it by clearing site data. A formal request process is not yet implemented.

##### 5. Data Retention
Retention periods for each data category are not yet defined (TO CONFIRM WITH COUNSEL).

##### 6. Third-Party Processors
None. The prototype does not use third-party analytics, hosting, or payment processors.

##### 7. International Transfers
Not applicable; data remains in the user's browser.

##### 8. Security
Data is stored locally in the user's browser (localStorage). No server-side storage or transmission occurs in the current prototype.

##### 9. Children's Privacy
The Service is not directed to individuals under 18. TO CONFIRM WITH COUNSEL: age of consent under Egyptian law.

##### 10. Changes to This Policy
We will post any changes on this page. Continued use constitutes acceptance.

##### 11. Contact
For privacy inquiries, contact [TO BE PROVIDED BY FOUNDER].

##### Data the prototype handles today (from the build)

| Data | Collected when | Stored as | Purpose | Recipients | Retention |
|---|---|---|---|---|---|
| Waitlist email address | A visitor joins the waitlist on the landing page | A one-way hash of the email, a consent flag and a timestamp (the plain email is not kept by the prototype) | Count real sign-ups and record consent | None (stored locally by the prototype) | Not set yet: founder to decide (TO CONFIRM WITH COUNSEL) |
| Page-view events | A visitor opens the landing, pricing or store page | Page name, timestamp and a random visitor id generated for the browser (not linked to a name or email) | Count unique visitors for the demand tests | None (stored locally by the prototype) | Not set yet: founder to decide (TO CONFIRM WITH COUNSEL) |
| Mock order requests (MOCKED) | A visitor clicks Buy on the store page | Order id, product id, timestamp and the random visitor id; no-charge, nothing is sold | Measure buy intent and test the MOCKED delivery flow | None (stored locally by the prototype) | Not set yet: founder to decide (TO CONFIRM WITH COUNSEL) |
| Payment data | Never | Not collected: no card, bank or payment details; no payment provider | - | - | - |

If anything above contradicts this table, the table describes the prototype as built: fix the text before use.


### refund.md

DRAFT, not legal advice. Must be reviewed by a qualified lawyer before use.

> Jurisdiction (from the founder's brief): Egypt. Every statement about a specific law is TO CONFIRM WITH COUNSEL.

#### Refund Policy

##### Today: no payments (MOCKED)

No payment is taken today. Any order placed through the prototype is a MOCKED, no-charge request that the prototype records to test delivery. No card, bank or other payment details are requested or stored, and no payment provider is connected. Because nothing is charged, there is nothing to refund.

##### Refund Policy – Current (Mocked Orders)

**No payment is taken.** All orders in the current prototype are MOCKED: clicking "Buy" records a mock order request (order ID, product ID, timestamp, visitor ID) but charges nothing and delivers nothing. Because no money changes hands, there is nothing to refund. If you have clicked "Buy" and wish to remove the mock order record, you can clear your browser site data for this domain.

This policy applies only to the current prototype. If and when real payments are introduced, a separate refund policy will apply (see below).

##### If real payments are introduced later (CONDITIONAL)

> CONDITIONAL: the terms in this section apply only if and when real payments are introduced, and only after a qualified lawyer has reviewed them. They do not apply today.

##### Refund Policy – Future Conditional (If Real Payments Are Introduced)

**The following terms would apply ONLY IF AND WHEN real payments are enabled.** They do not apply today.

1. **Eligibility**: Refund requests for digital subscriptions must be made within 14 days of the original purchase (TO CONFIRM WITH COUNSEL: mandatory cooling-off period under Egyptian consumer law for digital content).
2. **Condition**: Refunds are available only if the Service has not been substantially used (e.g., no projects created, no data entered). TO CONFIRM WITH COUNSEL: definition of "substantial use" and any statutory exceptions.
3. **Process**: Requests must be sent to the support contact with the order ID. Refunds will be issued to the original payment method within 30 days (TO CONFIRM WITH COUNSEL: statutory refund timelines).
4. **Exceptions**: No refunds for amounts below the payment processor's minimum refund threshold, or for purchases made more than 14 days prior (unless required by law).
5. **Subscription Cancellations**: Cancelling a subscription stops future billing; it does not generate a refund for the current period unless the above conditions are met.
6. **Changes**: This conditional policy will be finalised and published before any real payment integration.

## Claims and their evidence

- The policy drafts describe the data inventory of the prototype as built `ASSUMPTION` (inventory supplied by the build step or the default prototype inventory; verify against the code)

## What I need from you

1. What retention periods do you want for waitlist hashes, page-view events, and mock order records (e.g., 30 days, 90 days, until manual deletion)?
2. What support contact (email, form URL) should be published in the policies?
3. Do you plan to add user accounts or server-side storage before launching a paid version? This affects controller status and data subject rights implementation.
