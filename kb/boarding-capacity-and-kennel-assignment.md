# Boarding Capacity & Kennel Assignment

**Date:** June 23, 2026
**Applies to:** Admin staff

---

## Overview

Three improvements were made to the boarding management workflow:

1. A new **Boarding Capacity** page with a live pie chart showing daily kennel occupancy
2. Kennel assignment is now **required** when approving a boarding request
3. An **Assign Kennel** button lets staff quickly assign a kennel to any existing reservation that doesn't have one yet

---

## Boarding Capacity Page

**Where:** Navigation → Services → Boarding Capacity

This page gives a visual snapshot of how full the facility is on any given day. Use it to plan ahead, check availability before quoting a customer, or review occupancy for a past date.

### What the chart shows

The doughnut chart divides the day's kennels into four segments:

| Segment | Color | Meaning |
|---|---|---|
| Staying Overnight | Dark navy | Pets mid-stay (checked in before today, checking out after today) |
| Arriving Today | Green | Pets whose check-in date is the selected day |
| Departing Today | Amber | Pets whose check-out date is the selected day |
| Available | Light gray | Remaining kennel capacity |

The percentage shown in the center of the chart is total occupancy (all boarding pets as a percentage of your kennel capacity setting).

### Navigating dates

- Use the **← / →** arrows to step forward or back one day at a time
- Use the date picker to jump to a specific date
- Click **Today** to return to the current date

The page loads data via AJAX — switching dates is instant with no page reload.

### Summary cards

Four stat cards above the chart show at a glance:

- **Total Guests** — all pets boarding on the selected day
- **Available Kennels** — remaining capacity
- **Arriving Today** — drop-offs
- **Departing Today** — pick-ups

### Pet detail tables

Below the chart, three tables list every pet in each category with their owner name, BOARD-N reference number, kennel/suite assignment, and check-in or check-out time.

### Capacity setting

The total kennel count comes from the **Kennel Capacity** setting on the Boarding Dashboard. If that number needs to change, update it there and the capacity page will reflect it immediately.

---

## Kennel Assignment Required at Approval

**Where:** Boarding Dashboard → Approve (modal)

The kennel/suite number field in the approval modal is now a required field. The form will not submit without it, and the server will also reject the request if it somehow arrives without one.

### How to approve

1. From the Boarding Dashboard, click **Approve** on a pending request
2. Confirm or adjust the check-in and check-out dates and times
3. Select **Kennel** or **Suite** from the accommodation type dropdown
4. Enter the kennel or suite number (e.g., `4`, `4A`, `12`)
5. For pets sharing a space, use the same number for both
6. Add any special notes, then click **Approve & Create Reservation**

If you try to submit without a kennel number, the form will stop you with a validation error.

---

## Assign Kennel Button (Existing Reservations)

**Where:** Boarding Dashboard → Checked In or Upcoming Reservations tables

Any active or upcoming reservation that was created without a kennel number shows a small **Assign** button (yellow outline) in the Location column instead of a blank dash.

### How to assign

1. Click the **Assign** button on any unassigned reservation row
2. In the modal that appears, select **Kennel** or **Suite**
3. Enter the number
4. Click **Save**

The page reloads and the Location column now shows the assigned kennel badge. The assignment is also reflected on the Boarding Capacity page immediately.

---

## Tips

- Reservations created before kennel assignment was required may still show as unassigned. Use the Assign button to fill those in.
- The Boarding Capacity page is a good morning check — open it to today's date before the facility opens to see who is arriving, who is staying, and how many spots remain.
- The **Boarding Outlook** page (Navigation → Services → Boarding Outlook) still shows the two-week calendar view with drop-off and pick-up lists if you need that broader range.
