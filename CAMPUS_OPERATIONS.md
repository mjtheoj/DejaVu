# LostLink — Campus Operations and Integration

This document defines the intended campus process around the prototype. It is not a substitute for an approved CVR College lost-property policy.

## 1. Found-item custody: report, receive, tag and store

A student's found-item report is a notification to the office, not proof that the item has been handed over.

1. The student submits the report. The report is set to **Awaiting office intake**, remains out of public search, and notifies office staff.
2. The finder physically delivers the item to the designated campus lost-and-found custodian/desk. Staff confirm that the physical item is actually in custody.
3. Staff record a specific storage location used on campus (for example, the authorised room plus cabinet/shelf reference), an internal verification detail or approved method, and sensitivity/value fields appropriate to the item.
4. LostLink assigns a unique private Tag ID, records the storage location and makes the item available for matching. Public student search does not expose the tag or exact storage location.
5. The office console shows the **Campus storage register** for tagged items still in custody. If an item is physically moved, staff use **Update storage location** after the move; the app records the previous location, new location, Tag ID, timestamp and optional internal note in its audit log.

The college must designate the real intake desk, storage rooms, cabinets and shelves. The location typed into LostLink is a custody record; it does not itself move or physically secure an object. Staff must not confirm intake until the item is received and placed at the recorded location.

Older local database records whose storage location was never recorded are marked **Location needs confirmation** during migration and should be physically checked by staff.

## 2. Claim review and Tag ID handover

1. The claimant selects an available item and submits private ownership evidence. They can optionally link one of their own open lost reports. The evidence is shown to the office reviewer, not public search.
2. Authorised office staff review distinctive features/owner-only details, time and location consistency, physical inspection and independent evidence as relevant. The app requires identity confirmation and a minimum number of checks based on item risk. Restricted/high-sensitivity items also require an authorised-record/custodian check.
3. Competing claims must be resolved before any claim is approved. Approval changes the claim to **Ready for physical handover**; the physical item remains in campus custody.
4. Staff use the inventory's private storage location to retrieve the item. At collection, staff compare the physical label with the Tag ID on the approved claim, check the claimant's identity under campus policy and hand the physical item to that claimant.
5. Staff confirm physical handover in LostLink and enter the exact Tag ID. A mismatched tag, a claim that is not approved, or a duplicate handover is rejected. A successful handover records the claimant, office staff, item/tag and timestamp; marks the claim and item **Returned**; and triggers an in-app notification. If the claimant linked an open lost report, LostLink closes that report in the same database transaction and notifies the claimant. A linked lost report cannot be closed manually while its claim is active.

The Tag ID establishes which inventory record is being released; it does not, by itself, prove who owns the item. Identity and claim verification remain mandatory.

## 3. Report closure, withdrawal and status handling

Student-owned reports have controlled exit paths so stale reports do not stay active forever:

- An **open lost report** can be closed by its owner with a reason: recovered elsewhere, no longer searching, or duplicate. Its record stays visible to its owner, but candidate matching stops.
- A **found report awaiting office intake** can be withdrawn by its owner only before physical custody is accepted. The withdrawal is logged and office staff are notified.
- Once staff physically accept and tag a found item, the original reporter cannot withdraw it from the inventory. Campus staff must use the custody/return process.
- Repeating a closure or trying to close a report in a later state returns a conflict instead of silently changing history.
- Optional public characteristics include brand/make, primary colour and safe-to-share visible characteristics. These support search and matching. Private proof-of-ownership clues belong in claim evidence, not the public report description.
- An optional date must be a valid ISO date/time. A block/building **or** a nearby area is required; room and floor are optional.

### Key state transitions

| Record | From | To | Actor / condition |
|---|---|---|---|
| Lost report | **Open** | **Closed** | Owner closes the search with a reason |
| Found report | **Awaiting intake** | **Withdrawn** | Owner withdraws before office intake |
| Found report | **Awaiting intake** | **Available** | Office confirms receipt, records location and assigns Tag ID |
| Found report | **Available** | **Claim verified** | Office approves a claim after verification checks |
| Found report | **Claim verified** | **Returned** | Office checks the exact tag and confirms identity plus physical handover |
| Claim | Active review state | **Ready for handover** | Office approves after required checks and resolution of competing active claims |
| Claim | Active review state | **Not approved** | Office rejects the claim |
| Rejected claim | **Not approved** | **Disputed / review requested** | Claimant requests one review with a reason |
| Claim | **Ready for handover** | **Returned** | Office records actual physical handover |
| Linked lost report | **Open** | **Closed** | The linked claim’s verified physical handover is recorded |

The **Disputed** claim state can mean either competing claims or a claimant-requested review. The prototype stores the review request separately in the appeal note, so office staff can distinguish the reason. A rejected claim can be reviewed once; a completed handover and a closed report are final states in the current prototype.

## 4. Follow-up and accountability

- Found reports waiting for intake generate notifications to the office and reporter.
- Intake, storage-location changes, claim decisions, handovers and verified rewards are audited.
- Students see status/notifications for their own reports and claims. Exact storage locations, physical Tag IDs, private evidence, verification details and internal notes are restricted to authorised office staff.
- The office storage register includes items in custody that are available or approved for collection. Returned items are removed from current inventory and remain represented in the handover record and audit trail.
- Reward points are only awarded for office-confirmed actions. A student-submitted found item receives +10 on physical intake/tagging and +5 is recorded for a successful verified return. The points are recognition for the finder/contributor, not ownership evidence.

## 5. Campus Sync integration plan

The GitHub repository currently runs as a standalone web prototype. Campus Sync integration has **not** been implemented because the repository does not contain the college's Campus Sync API/SDK, institutional sign-in contract or deployment credentials.

An approved integration should be done through a documented boundary rather than direct access to Campus Sync's internal database:

1. **Confirm the integration contract:** obtain Campus Sync vendor/administrator documentation, supported embedded-web or deep-link options, API endpoints, test environment, authentication method, app review process and operational owner.
2. **Institutional identity:** replace demo email/password authentication with college-approved SSO (the exact protocol and claims depend on Campus Sync), map authenticated users to campus identities and enforce the student/office role on the server. Office access must be assigned explicitly, not inferred from a client-side field.
3. **Hosting and data:** deploy the API to college-approved infrastructure over HTTPS, choose an institution-approved production database and image store, configure backups and access controls, and decide record retention/deletion, incident logging and data ownership.
4. **Launch from Campus Sync:** add an approved LostLink entry in the Campus Sync user interface. Use a signed/delegated session or secure SSO handoff if the platform supports it; do not place passwords, long-lived bearer tokens or secrets in a URL.
5. **Operational integration:** agree the authoritative campus building/room directory, designated intake location, custodians, restricted-item rules, tag-label format, lost-property retention period and escalation path. Test the full report → intake/store → claim verification → exact-tag handover path with campus staff.
6. **Security and acceptance:** review role permissions, session management, CSRF protections, upload handling, rate limiting, audit-log access, backups, privacy notice and certificate/reward policy before accepting real student data.

Until this contract is supplied and approved, describe Campus Sync as the **intended integration target**, not a live connection.
