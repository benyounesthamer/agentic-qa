# User story: online banking transfers

As a NovaBank customer, I want to log in, send money to my beneficiaries and follow my accounts,
so that I can manage my money safely online.

The demo customer logs in with username `demo` and password `demo123`. The current account starts
with a balance of 3,250.750 TND. Amounts are in Tunisian dinars with 3 decimals.

Acceptance criteria:
1. After logging in, the accounts page shows each account with its balance.
2. A transfer goes through a confirmation step; once confirmed, the balance of the debited account
   decreases by exactly the transferred amount (for example 100.900 TND, to the millime).
3. A completed transfer appears in the statement of the debited account.
4. The amount must be greater than zero: zero or negative amounts are refused with an error message.
5. A transfer larger than the account balance is refused with an error message.
6. The total transferred in one day cannot exceed 5,000 TND: a transfer above the remaining daily
   limit is refused with an error message (the savings account has enough money to test this).
7. A beneficiary can only be added with a valid Tunisian IBAN: an IBAN with wrong check digits
   (for example TN5904001234567890123457) is refused with an error message.
8. Deleting a beneficiary removes it from the list.
9. After logging out, the accounts page can no longer be opened without logging in again.
