# FinScout report: https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12898&Mode=0

- Generated: 2026-10-06 23:16 with llama3:8b on Ollama
- Verdict: INCONSISTENT
- Code checks: the assessment rates a change that does not apply to FlexiPay as High, Medium or Low
- Verification agent said: CONSISTENT
- Status: draft for human review
- Warning: The verification agent said CONSISTENT, but the code checks found problems it missed.

## 1. Summary of the circular

Reserve Bank of India (Authentication mechanisms for digital payment transactions) Directions, 2025

Issuer: Reserve Bank of India

Reference Number: RBI/2025-26/79

Date: September 25, 2025

Applicability: All Payment System Providers and Payment System Participants, including banks and non-bank entities

Key Changes:

• Minimum two-factor authentication for digital payment transactions
• At least one factor to be dynamic
• Robust authentication mechanism
• Risk-based approach for high-risk transactions
• Cross-border transactions to be validated and authenticated separately

Effective Date: April 01, 2026

## 2. Impact on FlexiPay India

Change: Minimum two-factor authentication for digital payment transactions
- Applies to FlexiPay: Yes, FlexiPay India's UPI app and wallet require two-factor authentication for digital payment transactions.
- What FlexiPay does today: FlexiPay India uses an additional factor of authentication (card OTP) for wallet loads by card and a SIM-based verification for the FlexiUPI app.
- What FlexiPay must change: Implement a robust authentication mechanism that meets the RBI's minimum two-factor authentication requirement.
- Impact: Medium

Change: At least one factor to be dynamic
- Applies to FlexiPay: Yes, FlexiPay India's current authentication mechanism includes dynamic factors such as card OTP and SMS-based verification.
- What FlexiPay does today: FlexiPay India uses a combination of static and dynamic factors for authentication.
- What FlexiPay must change: Nothing, FlexiPay India's current authentication mechanism already meets this requirement.
- Impact: None

Change: Robust authentication mechanism
- Applies to FlexiPay: Yes, FlexiPay India's current authentication mechanism is considered robust, using a combination of static and dynamic factors.
- What FlexiPay does today: FlexiPay India uses a combination of static and dynamic factors for authentication.
- What FlexiPay must change: Nothing, FlexiPay India's current authentication mechanism already meets this requirement.
- Impact: None

Change: Risk-based approach for high-risk transactions
- Applies to FlexiPay: Yes, FlexiPay India's current fraud risk management policy uses a risk-based approach for high-risk transactions.
- What FlexiPay does today: FlexiPay India uses a risk-based approach for high-risk transactions, with additional verification steps for transactions exceeding ₹50,000 per month.
- What FlexiPay must change: Nothing, FlexiPay India's current fraud risk management policy already meets this requirement.
- Impact: None

Change: Cross-border transactions to be validated and authenticated separately
- Applies to FlexiPay: No, FlexiPay India does not currently support cross-border transactions.
- What FlexiPay does today: FlexiPay India's services are limited to domestic transactions.
- What FlexiPay must change: Develop a mechanism to validate and authenticate cross-border transactions separately.
- Impact: High

## 3. Action plan

Here is the revised action plan:

1. Implement a robust authentication mechanism that meets the RBI's minimum two-factor authentication requirement.
	* Owner: Compliance
	* Priority: High
	* Target Date: 60 days from the circular's effective date
	* Change: Minimum two-factor authentication for digital payment transactions

2. Develop a mechanism to validate and authenticate cross-border transactions separately.
	* Owner: Engineering
	* Priority: High
	* Target Date: 120 days from the circular's effective date
	* Change: Cross-border transactions to be validated and authenticated separately

1. Review the impact assessment and confirm that all changes with Impact High, Medium, or Low have been addressed.
2. Update the compliance records to reflect the actions taken to address the changes with Impact High, Medium, or Low.

## 4. Verification

Check 1: Coverage
PASS. The summary lists the key changes, which are also present in the impact assessment. The reason is that the impact assessment covers all the changes mentioned in the summary.

Check 2: Ratings
PASS. For each change in the impact assessment, the correct combinations are present. The reason is that the impact assessment provides the correct ratings for each change, including "Applies to FlexiPay", "What FlexiPay does today", "What FlexiPay must change", and "Impact".

Check 3: Plan
PASS. The plan lists actions for each change, and the actions are consistent with the impact assessment. The reason is that the plan addresses all the changes with Impact High, Medium, or Low, and the actions are correctly assigned to the owners and target dates.

Check 4: Facts
PASS. The summary, impact assessment, and action plan all agree on the applicability, effective date, and key changes. The reason is that the three outputs are consistent in their facts, including the applicability, effective date, and key changes.

VERDICT: CONSISTENT

## Appendix: knowledge-base searches

- "What authentication mechanisms does FlexiPay India use for digital payment transactions?" returned: fraud_risk_policy.md > Authentication; products.md > 1. FlexiUPI App; products.md > 2. FlexiWallet; infrastructure.md > Technical Stack
- "What products or services does FlexiPay India offer?" returned: products.md > 1. FlexiUPI App; fraud_risk_policy.md > Authentication; grievance_policy.md > Channels; kyc_policy.md > Who can be onboarded
- "What changes does the circular summarised above affect?" returned: kyc_policy.md > Periodic updation; kyc_policy.md > Records; kyc_policy.md > Identity verification; data_protection_policy.md > Incidents
- "What FlexiPay products, policies and systems does the circular affect?" returned: grievance_policy.md > Channels; fraud_risk_policy.md > Authentication; products.md > 1. FlexiUPI App; kyc_policy.md > Who can be onboarded
