# Ruff Life Retreat — Staff Knowledge Base
### Feature Updates — June 2026

---

## Article 1: Daycare Dashboard Calendar

**Category:** Daycare Operations  
**Audience:** Staff / Admin

### Overview

The Daycare Dashboard now includes a two-week calendar that shows which enrolled dogs are scheduled each day. It follows the same style as the Boarding Dashboard, making it easy to see occupancy at a glance and click into any day for details.

### Where to Find It

**Admin → Daycare Dashboard** — scroll past the Check-In/Check-Out section to the calendar.

### How to Use It

**Reading the calendar**

- The calendar displays two weeks at a time (Monday through Sunday), split into two side-by-side grids.
- **Green circle** — dogs are scheduled for daycare on that day.
- **Yellow highlight** — today's date.
- **Yellow highlight + green ring** — today has dogs scheduled.
- **Grey number, no circle** — weekend; daycare is not offered.
- **No circle on a weekday** — no dogs enrolled for that day, or the facility is closed.

**Navigating weeks**

- Use the **Previous** and **Next** buttons to move backward or forward by two weeks.
- The **Today** button returns to the current two-week window.

**Viewing a day's details**

Click any green circle to open a popup showing:
- Each dog's name, breed, and owner
- Any special (custom) daily rate, if applicable

### Notes

- The calendar reflects **daycare enrollment schedules** (recurring weekly days), not individual bookings. If a dog is enrolled Monday/Wednesday/Friday, they appear on every Monday, Wednesday, and Friday.
- Closure dates suppress the green circle for that day automatically.

---

## Article 2: Boarding Outlook (formerly Boarding Occupancy)

**Category:** Boarding Operations  
**Audience:** Staff / Admin

### Overview

The **Boarding Occupancy** report and dashboard section have been renamed to **Boarding Outlook** across the entire application. No functionality has changed — only the name.

### Where to Find It

- **Admin → Boarding Dashboard** — "Boarding Outlook" section
- **Reports → Boarding Outlook**
- **Admin Dashboard** → Quick-action card labeled "Boarding Outlook"

### Why the Change

The name "Boarding Outlook" better reflects that the view shows upcoming reservations and capacity over time, not just current occupancy.

---

## Article 3: Grooming Report — Prep Date Logic

**Category:** Grooming Operations  
**Audience:** Staff / Admin

### Overview

The Grooming Report now defaults to showing **tomorrow's pickups** when you open it today. This is because grooming prep happens the day before pickup — so the report is designed around your prep workflow, not the pickup date.

### Where to Find It

**Admin → Boarding Dashboard → Grooming Report** (or via Reports menu)

### How It Works

| What you select | What the report shows |
|---|---|
| Today (e.g. June 15) | Dogs checking out June 16 |
| June 17 | Dogs checking out June 18 |

- The **date picker** is labeled "Prep date" — this is the day you are doing the grooming.
- The report heading confirms both dates: *"Grooming Prep — [prep date] · pickups on [pickup date]"*
- The **Reset** button always returns to today as the prep date (showing tomorrow's pickups).

### Before 10 AM Filter

Click the **Before 10 AM** button to show only dogs whose owners are picking up before 10:00 AM. This is useful for prioritizing which dogs need to be groomed first thing in the morning.

- When active, the button is highlighted yellow and a note appears in the summary banner.
- Click it again to remove the filter.
- The filter persists with whatever prep date you have selected.

---

## Article 4: Homepage Photo Management

**Category:** Site Settings  
**Audience:** Admin

### Overview

Admins can now change the photo displayed on the Ruff Life Retreat homepage without restarting the server. The change goes live immediately after uploading.

### Where to Find It

**Admin Dashboard → Homepage Photo** (quick-action card in the second row)  
Or navigate directly to **Admin → Site → Homepage Photo**.

### How to Upload a New Photo

1. Go to **Admin → Site → Homepage Photo**.
2. You will see a preview of the current photo.
3. Under **Upload New Photo**, click **Choose File** and select your image.
   - Accepted formats: JPG, PNG, GIF, WebP.
   - No size limit is enforced, but smaller files (under 2 MB) load faster for visitors.
4. Click **Upload & Go Live**.
5. The new photo appears on the homepage immediately — no server restart needed.

### How to Revert to the Default Photo

If a custom photo is active, a **Revert to Default** section appears at the bottom of the page.

1. Click **Reset to Default**.
2. Confirm the prompt.
3. The original homepage photo (`img/homepage.jpg`) is restored immediately.

### Notes

- Only one custom photo is active at a time. Uploading a new photo automatically removes the previous one.
- The default photo is never deleted — reverting always restores it.

---

## Article 5: Kiosk — Phone Number Auto-Lookup

**Category:** Daycare Kiosk  
**Audience:** Staff / Front Desk

### Overview

The daycare check-in/check-out kiosk now looks up a customer's enrolled pets automatically when they enter their phone number. Staff and customers no longer need to type a pet name manually.

### How the New Flow Works

1. **Enter phone number** — The customer types their phone number into the kiosk.
   - After 10 digits are entered, the lookup runs automatically (after a brief half-second delay).
   - Alternatively, tap the **Find Pets** button to trigger it manually.

2. **Select a pet** — The kiosk displays the owner's name ("Hi, Sarah! 👋") and a large button for each enrolled dog.
   - If only one dog is enrolled, it is selected automatically.
   - Tap the correct dog's button to highlight it.

3. **Check In or Check Out** — Once a pet is selected, the **Check In** (green) and **Check Out** (dark) buttons appear. Tap the appropriate action.

### If the Phone Number Isn't Found

An error message appears in red below the phone field explaining the issue (e.g. "No account found for that number" or "No enrolled pets found"). The customer should speak with a staff member.

### Changing the Phone Number

Tap the **Change** button (top right of the pet selection area) to clear the lookup and start over.

### Notes

- Phone matching strips formatting — entering `9125551234`, `(912) 555-1234`, or `912-555-1234` all match the same account.
- Only **active daycare enrollments** are shown. If a pet's enrollment is inactive, they will not appear.
- Staff can process check-ins/outs from the admin Daycare Dashboard if the kiosk is unavailable.

---

## Article 6: Kiosk — SMS Notifications Removed

**Category:** Daycare Kiosk  
**Audience:** Staff / Admin

### Overview

SMS notifications for kiosk check-ins and check-outs have been removed. Customers will no longer receive a text message when their dog checks in or out via the kiosk.

### What Changed

- **Previously:** A text message was automatically sent to the owner's phone when a dog checked in ("🐾 Buddy has checked in…") and again at check-out ("🐾 Buddy has checked out…").
- **Now:** No SMS is sent at check-in or check-out from the kiosk.

### What Was Not Changed

- Play group auto-assignment still runs at check-in.
- The daycare milestone survey check still runs at check-out.
- SMS notifications from other parts of the application (inbox messages, balance reminders, etc.) are unaffected.

---

## Article 7: Waiver Management

**Category:** Customer Management  
**Audience:** Staff / Admin

### Overview

The waiver system has been updated with better reporting, admin controls to correct waiver status, and an automatic prompt for customers who haven't signed.

---

### 7a. Understanding the Waiver Report

**Where to find it:** Reports → Waiver Acceptance Report

The report lists all active customers and their waiver status. Use the tabs at the top to filter:

- **All Customers** — full list with a Accepted / Not Accepted badge per customer
- **Accepted** — customers who have signed (includes the date signed)
- **Not Accepted** — customers whose waiver is on file as unsigned

**What "Backfilled" means**

Some older customers may show a yellow **Backfilled** badge on their customer detail page. This means their waiver was automatically marked as accepted when the waiver feature was first introduced (based on having completed onboarding), not because they actually clicked through and signed it. These customers should be reviewed — see section 7b for how to handle them.

---

### 7b. Resetting a Waiver (Backfilled or Incorrect Records)

Use this when a customer's waiver is marked as accepted but they haven't actually signed it.

1. Go to **Admin → Customers** and open the customer's record.
2. Find the **Waiver** card (between Customer Info and Pets).
3. Click **Reset Waiver**.
4. Confirm the prompt.

The customer's waiver status is cleared. The next time they log in, they will be redirected to sign the waiver before accessing their account.

---

### 7c. Marking a Waiver as Accepted (Paper Copy Collected)

Use this when a customer has signed a paper waiver in person and you need to record it in the system.

1. Go to **Admin → Customers** and open the customer's record.
2. Find the **Waiver** card.
3. If the waiver shows **Not Accepted**, click **Mark Accepted**.
4. Confirm the prompt.

The waiver is recorded as accepted with today's date and time.

---

### 7d. Customer Waiver Signing (Online)

When a customer logs into their account and their waiver is not on file, they are automatically redirected to a waiver signing page before they can access anything else.

The page shows:
- The full Ruff Life Retreat Doggy Daycare & Boarding Waiver text
- A field for their pet name(s) and today's date
- A checkbox to confirm they have read and agree
- A **Sign Waiver & Continue** button

Once signed, they are taken to their dashboard as normal. They will not be shown the waiver again unless an admin resets it.

**Customers cannot bypass this step** — all pages in their account redirect to the waiver signing page until it is completed.

---

*Last updated: June 2026 — Ruff Life Retreat internal documentation*
