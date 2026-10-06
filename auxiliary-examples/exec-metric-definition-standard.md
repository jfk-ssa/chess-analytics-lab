# Executive Metric Definition Standard — Public Example

> **Portfolio example.** This document adapts a business-metric communication
> standard for public sharing. Every amount, count, date, and worked scenario
> below is **synthetic and illustrative**, not a disclosure of actual company
> performance. Names, email addresses, customer records, internal tickets, and
> production change history have been removed. The definitions demonstrate how
> an executive metric contract can prevent different dashboards from giving
> different answers.

The executive growth model depends on **MRR, paying customer, churn, NRR,
activation, engagement, currently engaged, signups, and CAC**. Each term has a
source, grain, clock, inclusion rule, and owner. A dashboard, semantic measure,
and transformation should implement the same contract. If they disagree, trace
the variance to the definition before changing a number.

## Contents

1. [How to read the standard](#1-how-to-read-the-standard)
2. [MRR](#2-mrr)
3. [Paying and active customers](#3-paying-and-active-customers)
4. [Churn](#4-churn)
5. [NRR, expansion, and contraction](#5-nrr-expansion-and-contraction)
6. [Activation and engagement](#6-activation-and-engagement)
7. [Signups](#7-signups)
8. [CAC](#8-cac)
9. [Implementation map](#9-implementation-map)
10. [Changing a definition](#10-changing-a-definition)

## 1. How to read the standard

**Source of record.** Billing owns money facts: subscription state, recurring
amount, discounts, and the effective end of service. The CRM owns qualitative
facts such as stage, owner, and renewal risk. CRM fields can be joined for
context but cannot override billing facts. A manually entered revenue value is
useful for variance reporting, not as the source of MRR.

**Conventions that apply everywhere:**

- **Grain.** MRR, paying customer, churn, NRR, and CAC are organization-grain.
  Signups, activation, and engagement are user-grain. A lifecycle view may roll
  user activity up to an organization, but the funnel should retain the user
  denominator.
- **Monthly clock.** Each monthly money metric is a point-in-time snapshot at
  the end of the last calendar day in UTC. Sample at the exclusive upper bound
  of the month; a transition on the last day belongs to that month.
- **Daily funnel clock.** Date a user stage by the business's declared local
  timezone. Label any visitor series that uses a different source timezone.
- **Net of discounts.** The headline recurring amount is net. Carry list
  amount beside it so promotional subsidy is visible.
- **Marketplace volume is not subscription revenue.** Keep payment flow between
  customers and their partners outside MRR unless the business actually earns
  that amount.
- **Small denominators.** Publish numerator and denominator with every rate.
  A large-looking percentage move can represent one account.

## 2. MRR

> **MRR** is the month-end sum of normalized **net** recurring amounts across
> subscriptions in a paying state. It is a run-rate snapshot, not cash
> collected and not a time-weighted monthly average.

| Rule | Definition |
|---|---|
| Interval normalization | Monthly: `unit_amount / 100 × quantity`. Annual: divide by 12. Respect any interval count greater than one. |
| Net versus list | Apply the discount effective at month-end to the list amount. Carry both values. |
| Trial | Contributes zero until the trial ends. |
| Pause | Contributes zero while paused. |
| Partial month | No proration in this illustrative policy; the month-end state wins. |
| Plan change | Use the historical price effective at month-end rather than a mutable current subscription item. |
| Currency | One reporting currency. Add an explicit FX policy before mixing currencies. |

A point-in-time rule makes each snapshot reproducible. A time-weighted metric
may be valid for another question, but it needs a separate name and calculation.
**ARR** is `MRR × 12`; it is neither bookings nor cash collected.

### Synthetic example

Suppose an annual subscription lists at **$360 per year** and has a temporary
100%-off coupon. The list run rate is **$30 per month** (`360 / 12`).

| Illustrative month-end | State | List MRR | Net MRR |
|---|---|--:|--:|
| January | Trial | $0 | $0 |
| July | Paying, fully discounted | $30 | $0 |
| Following April | Paying, coupon expired | $30 | $30 |

The July logo is active but not paying under the net-MRR definition. The $30
list-to-net difference is visible discount leakage.

## 3. Paying and active customers

> **Paying customer:** organization with net MRR greater than zero at month-end.
>
> **Active customer:** organization with a subscription in a paying state at
> month-end, including a fully discounted subscription.

These are distinct counts. Trialing and paused accounts are neither active nor
paying under this contract. Count organizations, not subscription rows; an
unmapped subscription cannot become an invented organization.

### Synthetic example

| Measure | Definition | Illustrative count |
|---|---|--:|
| Paying customers | Organizations with net MRR > 0 | 8 |
| Active customers | Organizations in a paying state | 12 |
| Trialing accounts | Organizations still in trial | 3 |
| Paying-state subscriptions | Subscription rows, including one unmapped row | 13 |

Four active organizations are fully discounted. A bare **“customer count”**
would obscure whether the speaker means revenue-bearing logos or supported
logos. Label the count at the point of use. A GTM funnel's “Paid” stage may
instead mean the first paying-state checkout, including a $0 promotional
checkout; if so, call it **checkout intent**, not `paying_customer_count`.

## 4. Churn

> An organization **churns** in month *M* if it held a subscription in a paying
> state at the end of *M−1* and does not at the end of *M*.

A cancellation during trial is a **trial abandonment**, not customer churn.
Record both `churn_requested_at` and the authoritative `churned_at` when access
and billing actually end. A future cancellation belongs to the effective month,
not the request month.

| Class | Rule |
|---|---|
| Involuntary | Payment failure ended the subscription. |
| Voluntary | Other customer-initiated cancellation. |
| Downgrade to free | Use only if an actual free tier exists. |

Always split involuntary from voluntary churn. One suggests a payment-recovery
problem; the other may suggest a value or fit problem. A 100%-off coupon is not
churn because the logo retains access.

**Churned MRR** in *M* is the organization's **net MRR at the end of *M−1***.
Do not value a departed account at its list price or the price visible after
cancellation.

| Rate | Calculation |
|---|---|
| Paying-logo churn | Churned logos that had net MRR > 0 at end of *M−1* ÷ paying logos then |
| Active-logo churn | All churned active logos in *M* ÷ active logos at end of *M−1* |
| Gross MRR churn | Prior-month net MRR of churned logos ÷ prior-month net MRR |

### Synthetic example

Suppose a month starts with **10 paying logos**, **12 active logos**, and
**$1,200 net MRR**. Two paying logos cancel after carrying $70 and $50 net
MRR; one fully discounted logo also cancels. A fourth account leaves during
trial and is excluded.

| Rate | Calculation | Illustrative result |
|---|---|--:|
| Paying-logo churn | 2 / 10 | 20% |
| Active-logo churn | 3 / 12 | 25% |
| Gross MRR churn | ($70 + $50) / $1,200 | 10% |

The comped logo affects active-logo churn but not churned MRR. The trial
abandonment affects neither.

## 5. NRR, expansion, and contraction

> **NRR** is current-month net MRR from the customers who had positive net MRR
> last month, divided by those same customers' prior-month net MRR. New
> customers are excluded from both sides.

```text
NRR (M) = (starting_mrr + expansion − contraction − churned) / starting_mrr
GRR (M) = (starting_mrr − contraction − churned) / starting_mrr
```

| Component | Definition |
|---|---|
| `starting_mrr` | Net MRR of the prior-month paying cohort. |
| `new_mrr` | Net MRR from an organization with no earlier paying month. |
| `expansion_mrr` | Increase for an organization already retained in the cohort, including a discount expiring. |
| `contraction_mrr` | Decrease for an organization still paying, including a new discount. |
| `churned_mrr` | Prior-month net MRR of a paying organization now at zero. |
| `reactivation_mrr` | Net MRR from an organization that paid before, went to zero, and returned. |

The movement ledger must reconcile:

```text
starting_mrr + new + expansion − contraction − churned + reactivation = ending_mrr
```

A coupon expiry on an **already retained active logo** is expansion, not new
business. Present it as discount movement beside genuine upgrade expansion.
An upsell rate should count expanding organizations over the prior-month paying
organizations; do not silently equate every expansion dollar with an upgrade.

### Synthetic example

| Quantity | Illustrative value |
|---|--:|
| Starting net MRR from prior-month cohort | $1,200 |
| Expansion within that cohort | $60 |
| Contraction within that cohort | $30 |
| Churned MRR | $120 |
| Ending MRR from that cohort | $1,110 |
| NRR | $1,110 / $1,200 = **92.5%** |
| New MRR outside the cohort | $90 |
| Total ending net MRR | $1,200 |

The final total reconciles, while NRR still describes only the retained cohort.

## 6. Activation and engagement

These are **user-grain** metrics. Activation and engagement are monotonic
funnel milestones. Currently engaged is a rolling health state.

> **Activation:** first qualifying user-created referral deal, including a
> deal later deleted from the application if the event remains in the audit
> spine.
>
> **Engagement:** at least **3** qualifying referrals within **14 days** of
> activation.
>
> **Currently engaged:** at least **3** qualifying referrals in the trailing
> **14 days**.

These thresholds are example policy, not claims about a particular product.
Define the qualifying event before counting it; exclude CRM imports and sync
jobs that did not represent user action. Use the same event spine for all
three states.

| Measure | Denominator |
|---|---|
| Activation rate | Confirmed user signups in the signup cohort |
| Engagement rate | Activated users |
| Currently-engaged rate | Activated users |

Exclude staff, test identities, and system accounts from the funnel under a
maintained classification rule. Keep uncertain classifications in a review
queue rather than quietly discarding them. A user-level exclusion must also
apply to the user drill behind an executive tile or the two views will not
reconcile. A lifecycle view can roll activity to an organization with an
explicit **any-user** rule.

### Synthetic example

A user signs up on day 1, creates a qualifying referral on day 5, then creates
referrals on days 10 and 12. They activate on day 5 and engage on day 12. A
session-start on day 2 is not activation. If the user makes fewer than three
qualifying referrals in the last 14 days at a later snapshot, they remain
**engaged historically** but are **not currently engaged**.

## 7. Signups

> **Funnel Signups:** non-deleted, authenticated platform users, timestamped at
> the first confirmed signup or identity link under a declared rule. Grain is
> one row per user. A second organization membership for the same person does
> not make another signup.

A CRM person creation is not a product signup. A Slack notification is an
operational event, not the definition. Record the business timezone for daily
funnel dates and keep it distinct from monthly UTC money snapshots. If an
identity graph supplies the signup clock, specify the fallback for a user with
no graph row and preserve the source timestamp.

### Synthetic example

| Event | Funnel signup? | Why |
|---|---|---|
| New authenticated person joins an organization | Yes | New platform user |
| Existing person joins a second organization | No | Same user identity |
| CRM contact is created | No | No authenticated platform account |
| User creates a first referral | No | Activation event, not signup |

Keep visitors, signups, activation, and payment clocks separately. When a
source changes, restate the affected series and explain the definition change
rather than quietly replacing a historical dashboard line.

## 8. CAC

> **CAC (external GTM spend)** = external go-to-market spend in month *M* /
> organizations whose net MRR first exceeds zero in month *M*.

| Included | Excluded |
|---|---|
| Paid media | Internal salaries and fully loaded headcount |
| GTM tooling and software | Product and engineering cost |
| GTM contractors and retainers | General administration and hosting |
| Events, content, and sponsorships | Marketplace payment flow |

Name the measure **“CAC (external GTM spend)”** when salary is absent. A fully
loaded CAC is a separate measure with an explicit allocation policy. Do not
present a narrower measure as plain CAC in an external readout.

Reactivations are not new customers. A fully discounted logo enters the
CAC denominator only when its net MRR first becomes positive, even if the
same movement is **expansion MRR** under the retained-logo movement contract.
That divergence should be explicit at the point of use. The spend that won a
coupon-funded logo may have been incurred long before its first net payment;
flag this timing caveat.

**Presentation rules:**

- CAC is **null** when there are zero new paying customers. Zero is incorrect.
- Show monthly numerator and denominator. Use a rolling three-month CAC as the
  executive default when volume is small, but do not let smoothing hide a real
  acquisition halt.
- State whether spend and acquisition are matched in the same month or with a
  lag. A lag is a policy choice, not an automatic correction.
- Per-channel CAC stays null if attribution is unavailable. Do not allocate
  unattributed acquisitions pro rata merely to fill a chart.
- Payback months = CAC / average monthly net MRR of new paying customers.

### Synthetic example

Suppose a month has **$7,200 external GTM spend**, **3 new paying customers**,
and their average initial net MRR is **$120**.

| Measure | Calculation | Illustrative value |
|---|---|--:|
| CAC (external GTM spend) | $7,200 / 3 | $2,400 |
| Payback | $2,400 / $120 | 20 months |
| Per-channel CAC | No reliable attribution | Null |

## 9. Implementation map

The names below are **generic illustrative interfaces**, not production model
names. This table makes the definition discoverable by both analytics engineers
and dashboard authors.

| Term | Illustrative model or measure | Grain |
|---|---|---|
| MRR and ARR | `fact_monthly_recurring_revenue`; ARR measure = net MRR × 12 | Organization × month |
| Paying and active customer | `fact_account_lifecycle` | Organization × month |
| Churn event and churned MRR | `fact_account_lifecycle` plus revenue movement | Organization × month |
| NRR and GRR | Semantic measures over monthly movement columns | Monthly cohort |
| Activation and engagement | `fact_user_activation` | User |
| Signups | `fact_people_signups` | User |
| CAC | `fact_monthly_acquisition_cost` | Month; channel only when attributed |

Keep ratios as measures over published numerators and denominators when
possible. Storing multiple versions of a ratio creates another place for a
metric definition to drift.

## 10. Changing a definition

1. Change the metric contract first and date the decision.
2. Update the transformation, semantic measure, dashboard label, and AI context
   that consume it in the same release.
3. Do not redefine a metric by editing one dashboard tile or model description.
4. Record which historical periods were restated, why, and how the old and new
   values differ. Retain the validation query and reviewer decision.
5. Recheck the clock, source, grain, exclusions, and denominator whenever a
   product event or billing flow changes.

A useful executive readout states the decision-relevant number, its denominator,
its date and source, and the caveat that changes its interpretation. The metric
contract exists so those words remain stable as implementation changes.
