# What's new in DEVTech

These features were copied from the RMTech project (Laravel) into DEVTech (Flask). Only the features
and how they work were copied; every screen keeps DEVTech's own design. RMTech itself was not changed.

Before adding anything, each RMTech feature was compared with DEVTech. Features DEVTech already had
were left as they were.

---

## New features

### 1. A service fee for each service

**Before:** DEVTech had one "service fee percentage" setting that nothing used.
**Now:** every service has its own service fee, charged on top of its starting price.

- **Suggested fee:** 10% of the starting price, rounded to the nearest ₱50, kept between ₱50 and ₱500.
  Services start with this fee.
- **Change one service:** Admin > Services > Edit. Leave the fee blank to use the suggested fee; enter 0 for no fee.
- **Change many at once:** Admin > Services > **Set service fees**. Apply one amount to every service or to
  one category, or reset each service to its suggested fee.
- **Where customers see it:**
  - the Services list ("From ₱700 + ₱50 service fee")
  - each service on the booking form, plus a "Service fee" line in the booking summary
  - booking details
  - the home page repair readout
  - the service API
- **The bill includes it:** the booking's amount due is now starting price + service fee − booking fee
  (if one was paid).
- **The FAQ chatbot knows it:** it answers "how much is the service fee?" (also in Tagalog, for example
  "magkano ang service fee") with the real lowest and highest fees.
- The unused percentage setting was removed from Settings. A **Set service fees** button there now opens
  Services.

### 2. "Amount to be paid" on the service report

The service report PDF now has a bill section:

- the service's starting price ("Set on diagnosis" if it has none yet)
- the service fee
- **additional work fees: only the extra work the customer approved.** Declined, pending and withdrawn
  requests are not charged.
- **Total amount to be paid by the customer**
- the booking fee already paid, subtracted, and the balance due at the shop

### 3. The customer confirms they received their device

When a repair is **Ready for Collection**:

- **Customer:** their Monitor Device page shows **"I received my device"**. After pressing it, the page
  shows "You confirmed you received your device", and later "Device returned".
- **Technician:** the job page lists "Customer confirmed they received the device" as a requirement and
  says "Waiting for the customer to confirm they received the device." The **Release** button stays
  disabled until the customer confirms, and the server refuses a release before that.
- **What gets recorded:** the confirmation is written to the job's activity log, and the technician gets a
  notification ("Customer received the device").
- **Safeguards:** a customer can confirm only their own booking, only once it is ready, and only once.

### 4. Photos at device intake (photo record)

**Before:** the Device Intake form had only a text field, with the placeholder
"Photo upload arrives with the Flask backend".
**Now:** technicians add real photos to the intake record.

- **How:** take photos with the phone camera, choose files, drag and drop, or paste a screenshot.
  Up to 12 photos, each with its own note (for example "Crack on the top-left corner").
- **When:** photos can be added or removed only while the job is active. Once the job moves on, they are
  kept as a record and can no longer be removed.
- **Where they show:** on the technician's job page, and in the admin's Service Requests > booking details
  (with the intake condition and notes).

### 5. Technicians must add a profile photo of themselves

So customers can recognise who handles their device:

- **The notice:** a verified technician without a photo gets a notice with a **2-day deadline**.
  It appears as a banner in the technician portal and as a notification.
- **When it starts:** approving a technician who has no photo starts the notice straight away.
- **When it ends:** the notice ends as soon as they add a photo.
- **If the deadline passes:**
  - the banner says "Your profile photo is overdue."
  - the admins are told once
  - Technician Verification lists the overdue technicians
  - each technician's page shows the photo status, with **Send another notice** (a new 2-day deadline)
    and **Suspend**

### 6. Settings > Danger Zone now works

**Before:** the four Danger Zone buttons only showed "not available yet".
**Now:** they work, with strong safeguards:

- **Locked by default:** press **Unlock to edit**. It locks itself again after 2 minutes.
- **Three confirmations per action:** "Are you sure?", then what exactly will happen, then the action's
  name typed exactly (for example `CLEAR ALL DATA`) together with the admin's own password.
  The server checks the phrase and the password again.
- **Reset All Settings:** puts the shop details, hours, booking fee and map location back to their defaults.
- **Clear All Data:** permanently deletes every booking, payment, order, message, notification, support
  chat, report, intake record and uploaded photo. Accounts, services, products, the technician roster and
  settings are kept.
- **Deactivate System (maintenance mode):**
  - Customers, technicians and visitors see a "We'll be right back" page.
  - Admins keep full access, and every admin page shows a banner.
  - Settings shows the system status as Deactivated.
  - **Reactivate System** turns it back on.
- **Logged:** every action, and every wrong password, is written to the activity log.

### 7. Technician Roster: read any valid ID, not only PhilSys

The "Add a hired technician" form already read the QR code on a PhilSys National ID.

- **New:** for other IDs there is a **Read the printed text instead** button. The admin's own browser reads
  the text off the photo, and DEVTech picks out the name, birth date, ID type and ID number.
- **Supported IDs:** PhilSys, Driver's License, UMID, Passport (from its machine-readable lines), PhilHealth,
  SSS, TIN, Postal, PRC and Voter's ID.
- **Warnings:** the admin is warned when the card doesn't match the chosen ID type, or when the middle name
  couldn't be read.
- **Privacy:** the photo never leaves the admin's computer. Only the text that was read is sent to the server.
- **Requires internet:** the text reader is downloaded the first time it is used.

### 8. A proper "Are you sure?" dialog everywhere

The browser's plain confirm boxes were replaced with one confirmation dialog. It matches each portal:
light for customers, navy for admins, dark with yellow for technicians.

New confirmations were added before:

- a customer submits a repair request ("Are you sure you want to submit this repair request?")
- a technician submits their registration ("Are you sure you want to submit your information?")
- a customer confirms receiving the device, approves or declines extra work, or submits a rating
- a technician releases a device to the customer
- an admin adds, edits or hides a service or category, changes service fees, or adds or removes a
  technician on the roster
- an admin sends a profile-photo notice or suspends a technician

### 9. Monitor Device: a section for the technician's certificates

- **Where:** the technician's certificates and achievements now have their own section on the customer's
  Monitor Device page, with a count and a "View certificates" link on the technician card.
- **Viewing:** images open in a viewer on the page; PDFs open in a new tab.
- **None yet:** if there are none, it says so.

### 10. Pages update live when someone edits their profile

- When a technician changes their profile (name, photo, phone...), their customers' pages refresh by
  themselves. The same happens the other way round, and on admin pages.
- Being online or signing in does not count as a profile change, so pages don't refresh for nothing.
- The technician's job page now shows the **customer's profile photo**, to recognise them at drop-off,
  pickup or a home visit.

### 11. Smaller changes

- **Home page:** no longer links to the technician and admin sign-in pages. Staff still reach them with
  the keyboard shortcuts.
- **Customer dashboard:** the **Support** quick action now opens the Support page; before, it opened Messages.
- **Admin "session ended" banner:** it now appears only when the session has really ended (checked twice).
  A slow server or a network hiccup no longer shows it by mistake.

---

## Kept as they were in DEVTech

- **The FAQ chatbot answers FAQs only.** RMTech's bot hands unanswered questions to a person; DEVTech's
  stays FAQ-only, as requested earlier. It only learned the service fee answer.
- **The customer sidebar.** RMTech renamed "Service Request" to "Support" there; DEVTech's sidebar was
  left as it is.
- **Design.** Every new screen uses DEVTech's own look.

---

## For whoever runs the website

The new features need five new database columns:

- `services.service_fee`
- `bookings.customer_received_at`
- `technicians.photo_notice_at`, `photo_notice_count` and `photo_overdue_reported_at`

**On this PC:** the local database is already updated, and its 166 services have suggested fees from ₱50
to ₱300. A backup of the services from before the change is in `instance/backup_services_20261119_102755.json`.

**On the live site (Supabase):** run this once, the same way as Part 4 of `DEPLOY_FREE.md`, with the Session
pooler address set as `DATABASE_URL`:

```
.venv\Scripts\flask --app app init-db
```

Do this **before** pushing the new code. The new code expects these columns and will show errors until
they exist.

---

## Tests

45 new automated tests cover the features above. Together with the existing tests, all 376 pass.

---

# Update: payments, ID photos, orders and sign-in (November 20, 2026)

## Booking fee: paid before the request is sent

1. The customer fills in the form and presses **Book Now**.
2. PayMongo's QR Ph code for the booking fee opens. They scan it with GCash, Maya or their bank app and pay.
   PayMongo confirms the payment by itself.
3. Only then does the next step open: they attach a **screenshot of the receipt** (required) and an optional
   reference number.
4. Only then can they press **Submit booking**. The request is refused on the server too if the fee isn't paid
   or the screenshot is missing.

- The paid fee is attached to the booking and deducted from the final bill. If they go back to change the form,
  the payment is kept and used for this booking; one payment can't be used for two bookings.
- Fee payments started but never paid don't appear under Payments or in the customer's Transactions.
- **Nothing typed is lost if the payment doesn't go through.** If the QR code expires, the payment fails, the
  customer closes it, the page reloads, they use PayMongo's card/e-wallet page, or the server sends them back
  with a message, the form comes back filled in (device, service, description, date and time, address and map
  pin, payment choice), with a note "We kept what you entered". They press Book Now and pay again as many times
  as needed; an expired code is replaced with a new one. Only the screenshot has to be attached again (browsers
  can't keep files). The kept form lives in that browser tab only and is cleared once the booking is sent, or
  with "Start over".
- Admins see the receipt screenshot with the fee under Payments. A booking can't be approved until its fee is paid.
- **Without PayMongo** (keys not set), the shop's own QR code from Admin > Settings > Payment Settings is shown
  instead, and an admin confirms the screenshot under Payments.

## The repair bill is paid after the repair

- **Two choices on the booking form:** GCash / online, or C.A.R (Cash After Repair). Both are paid after the repair.
- **GCash / online:** the bill can only be paid once the repair is done (Ready for Collection). Until then
  Transactions says so. The customer scans the QR and sends a screenshot (required).
- **Release needs a checked payment.** At release the technician sees the customer's screenshot, checks the
  money reached the shop account, and ticks "I checked..." before the device can be released. For C.A.R the
  technician ticks "I collected ₱… cash", as before. If no payment was sent yet, release is refused.

## Transactions page

- **Screenshot upload** for any payment ("Pay with GCash"), with a preview before sending.
- **Approved extra work is added to the total.** The bill shows the service, service fee, each extra the
  customer approved, less the booking fee already paid, and the total to pay.
- **View Details opens at once.** It used to stay on "Loading…" (a script error) and always read the first
  transaction. Each transaction's details are now already on the page.

## Technician Roster and registration

- **Front and back of the ID.** The roster form needs a photo of the front, and of the back for IDs with details
  on the back (PhilSys National ID, Driver's License, UMID, PRC ID, Postal ID). The front is still read to fill
  in the fields. Technician registration asks for the same two photos.
- **Address.** Both the roster and the registration form have a home address field.
- Admins see both sides (and the address) on the verification page and in the roster list. Every view of an ID
  photo is logged.

## Services & Prices: edit a whole category

Each category has **Edit category & prices**: rename it, change its icon and description, and edit the name,
starting price, service fee and hours of every service in it in one table. A "fill every row" tool sets one
service fee for all, or raises all prices by a percentage, before saving.

## Shop orders

- **Admin > Shop Orders** is now one card per order: a progress rail (placed, preparing, out for delivery,
  delivered), customer, items, address and payment side by side, and the actions at the bottom. A search box
  finds an order, customer or product on the page.
- **My Orders (customer):** each card shows the progress tracker, the first items, the payment state and the
  delivery time, with counts of orders being prepared, on the way and delivered at the top.

## Customer sign-in

The customer sign-in page now uses the same layout as the admin and technician sign-in pages, in its own
colour (green circuit board with mint accents).

## One click per action

Every button that sends something now locks after the first click and shows "Please wait…" until the server
answers: sign-in, registration, booking, payments, checkout, settings and every other form. Pressing Enter or
clicking again in the meantime does nothing, so an order, booking or payment can't be sent twice. If the server
sends the person back (a wrong password, a field to fix), the page comes back with the button usable again; the
browser's Back button unlocks it too. Buttons that work without reloading the page (add to cart, cancel, approve)
stay locked until the answer arrives. This is `static/js/busy-guard.js`, loaded on every page. The server still
refuses duplicates on its own (one booking per time slot, one use of a fee payment, one checkout per cart).

## For whoever runs the website

New database columns: `technicians.id_back_file`, `id_back_mime`, and `technician_employees.address`,
`id_front_file`, `id_front_mime`, `id_back_file`, `id_back_mime`. Run `init-db` (or `upgrade-db`) on Supabase
before pushing, as above. Then upload the payment QR code in Admin > Settings.

## Tests

15 new tests (`tests/test_payments_and_ids.py` and two in `tests/test_paymongo.py`) plus updated ones cover this update. All 405 tests pass.

# Update: automatic refresh, booking fee in Services & Prices, device-specific troubleshooting

## Customer pages refresh by themselves

- When something changes (a repair moves to the next stage, a payment is confirmed, an order is sent out, a reply
  arrives, the shop changes a price or the booking fee), the page updates by itself. There is no Refresh button to press.
- If the customer is in the middle of something (typing, a dialog open, a form with unsaved changes), a small notice
  says "New updates · this page refreshes when you finish", and the page refreshes the moment they're done.
- Before, typing anything in any box (even a search box) made the page wait for a manual "Refresh" click from then on.
  Now a form only counts as unsaved while it really differs from how the page loaded.
- Monitor Device updates the repair in place the instant it changes, without reloading. Its refresh button, and the one
  on Notifications, were replaced by a "Live" badge.

## Booking fee in Services & Prices

Admin > Services & Prices has a **Booking fee** box at the top: enter the amount in whole pesos (0 to 5,000; 0 turns
it off) and save. It is the same setting as in Admin > Settings, so both pages always show the same amount. New
bookings pay the new amount; bookings already made keep what they paid.

## Troubleshooting fits the chosen device

After the customer picks a device, the "likely cause" and "What you can try on your laptop / desktop PC / smartphone /
tablet" only show steps for that device. Before, a laptop owner also saw desktop steps ("check the switch on the back
of the power supply") and phone steps. Every problem has its own steps written for each device it applies to.

## Sidebar numbers show what's new

The numbers next to Notifications, Service Requests, Payments, Support, Refunds, Technician Verification, Technician
Activity (admin), My Jobs and Notifications (technician), and Monitor Device and Notifications (customer) now count
what is new since that page was last opened:

- Opening the page clears its number straight away, also in other open tabs.
- Anything new afterwards (a booking, a payment screenshot, a support message, a notification...) makes it appear again.
- Messages still count unread messages: opening the conversation clears them.

Before, Service Requests, Payments and the others kept counting everything still waiting, so the number never went
away by looking at the page. New table: `nav_seen` (run `init-db` on Supabase before pushing).

## Transactions: pay with GCash through PayMongo

On the customer's Transactions page there is now one **Pay with GCash** button, which works like the booking fee
and the shop:

1. PayMongo's QR Ph code opens with the exact amount; the customer scans it with GCash, Maya or a bank app and
   PayMongo confirms the payment by itself.
2. For a repair bill (or extra work), the next step asks for a screenshot of the receipt as proof. If they close it,
   an "Attach receipt screenshot" button stays on the payment until they add one. Shop orders stop after step 1, as
   in the shop.

The separate "Pay online (instant)" button was removed. A repair bill can still only be paid once the repair is done.
Without PayMongo keys, the shop's own QR code and a screenshot checked by an admin are used, as before.
