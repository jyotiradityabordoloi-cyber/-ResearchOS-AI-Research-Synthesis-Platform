# Trial conversion research — interview notes (sample dataset, Test 1)
# Eight consistently formatted interviews with recurring themes.

---
Participant ID: P01
Participant Role: Head of Data
Company Size: 200-500
Plan Tier: Trial (Business)
Pain: Connecting our Postgres warehouse took three days because the connector kept timing out. Once data was in, dashboards with more than a million rows took over a minute to load.
Behavior: Gave up on the live connector and uploaded nightly CSV exports instead. Pre-aggregates data in dbt so dashboards stay small.
Verbatim Quote: "I spent most of the trial fighting the connector instead of actually evaluating the product."

---
Participant ID: P02
Participant Role: Product Manager
Company Size: 50-200
Plan Tier: Trial (Team)
Pain: Setting up the HubSpot integration needed an admin who was on holiday, so we lost a week. Sharing a dashboard with leadership is awkward because they need their own seat to view it.
Behavior: Takes screenshots of charts and pastes them into the weekly Slack update.
Verbatim Quote: "My CEO is never going to create an account just to look at one chart."

---
Participant ID: P03
Participant Role: Marketing Operations Lead
Company Size: 50-200
Plan Tier: Starter
Pain: Exporting a report to PDF breaks the layout, so I can't send it to clients. I also can't tell what the next plan costs once we add more viewers.
Behavior: Rebuilds key charts in Google Slides every month for client reviews.
Verbatim Quote: "The pricing page made me feel like I'd need a spreadsheet to work out our bill."

---
Participant ID: P04
Participant Role: Analytics Engineer
Company Size: 500-1000
Plan Tier: Trial (Business)
Pain: The Snowflake connector required permissions our security team would not grant during a trial. There is no way to give a contractor access to only one dashboard.
Behavior: Created a separate sandbox Snowflake account with sample data just to test the tool.
Verbatim Quote: "We couldn't connect real data, so we never saw real value."

---
Participant ID: P05
Participant Role: Customer Success Manager
Company Size: 10-50
Plan Tier: Team
Pain: Dashboards are slow to refresh on Monday mornings when everyone opens them. Scheduled email reports arrive as links, and customers won't log in to see them.
Behavior: Downloads the data to Excel every Monday and emails a summary table to each customer.
Verbatim Quote: "If I have to wait two minutes for a chart in a customer call, I've already lost them."

---
Participant ID: P06
Participant Role: Founder
Company Size: 1-10
Plan Tier: Trial (Team)
Pain: I couldn't get Stripe data connected without writing an API script. Seat-based pricing is hard to justify when only two of us build dashboards and everyone else just reads them.
Behavior: Uses a free spreadsheet template for revenue metrics and checks it weekly.
Verbatim Quote: "Paying for ten seats so people can read a dashboard feels wrong for a team our size."

---
Participant ID: P07
Participant Role: BI Analyst
Company Size: 1000+
Plan Tier: Enterprise pilot
Pain: The Redshift connector failed on tables with JSON columns and support took two days to reply. Heavy dashboards time out during month-end reporting.
Behavior: Writes SQL views that flatten JSON before connecting, and runs month-end reports overnight.
Verbatim Quote: "Every new data source turned into a support ticket."

---
Participant ID: P08
Participant Role: VP Operations
Company Size: 200-500
Plan Tier: Business
Pain: There's no simple way to share a read-only dashboard with our board. Role permissions are all-or-nothing, and the price jumps a lot when we add viewer seats.
Behavior: Exports board metrics to PDF and fixes the formatting by hand before each board meeting.
Verbatim Quote: "I want the board to see the numbers without me becoming the PDF department."
