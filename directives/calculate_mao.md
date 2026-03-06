# Calculate Max Allowable Offer (MAO)

**Goal:** Quickly and deterministically determine the Max Allowable Offer (MAO) for a wholesale property for both Fix & Flip and Buy & Hold strategies.

## Inputs Required

Whenever you are asked to provide an offer price or MAO, ensure you have the following information:
**Provided directly by the User:**
- **Property Address**
- **Rehab Cost for Fix & Flip** 
- **Rehab Cost for Buy & Hold**
- **Target Monthly Rent**

**Gathered by the Agent:**
- **ARV (After Repair Value)** (Calculate by averaging the top 3 highest-priced sold comparable properties, unless the user provides it)
- **Neighborhood Class Grade** (A, B, C, D, or F). To find the area grade, you MUST input the address into this exact Google Map: `https://www.google.com/maps/d/u/1/viewer?mid=1KHa6DtnMDjMTGy2hbWfyRaHWrLPqCg0&ll=41.503002278238796%2C-81.57685790079529&z=12`. The color-coded zones will dictate the Neighborhood Class.
- **Annual Property Taxes** (Must be retrieved from DealCheck: Go to `https://app.dealcheck.io/`, search for the property address, and navigate to "Operating Expenses" to find the exact tax figure)
- **Annual Insurance** (Must be retrieved from DealCheck: Go to `https://app.dealcheck.io/`, search for the property address, and navigate to "Operating Expenses" to find the exact insurance figure)

*Optional overrides (use defaults unless specified):*
- Wholesale Assignment Fee (Default: $10,000)
- Interest Rate (Default: 7.0%)

## DealCheck Math Alignment Rules
When running the MAO calculation, the script uses the following strict rules perfectly aligned with DealCheck:
1. **Buy & Hold (Rental) Defaults:** 30-yr Amortizing Loan at strict 7% interest. Operating expenses universally assume: 10% Property Management, 5% Maintenance, 5% CapEx, 5% Vacancy.
2. **Fix & Flip Defaults:** 20% down, 10% Interest-Only loan for a 6-month hold. Selling costs are 7.5%.
3. **Universally Applied Rules:** A **10% cost overrun penalty** is attached to all rehab estimates (Buy & Hold, BRRRR, and Flips).
4. **BRRRR Defaults:** Refinance at 80% LTV, 30-year amortizing at 7% interest. Refinance costs are 3% of ARV.
5. **Closing Costs:** For all strategies, standard purchase closing costs assume a $10,000 wholesale fee and $1,000 Title & Escrow fee ($11,000 Total Purchase Costs).
6. **Buy & Hold Loan Terms:** The 2% origination fee is FINANCED into the loan, not paid in cash upfront. The wholesale fee is baked directly into the buyer's Total Cash Invested metric to strictly calculate their cash-on-cash yield.

## Execution Command

Run the deterministic Python script securely built into the `execution` directory. You can either provide a strict class letter OR a neighborhood name string to auto-lookup:

```bash
# Option A: With a direct class letter
python execution/calculate_mao.py \
  --arv <value> \
  --rehab <value> \
  --rent <value> \
  --neighborhood-class <A, B, C, D, or F> \
  --wholesale-fee 10000

# Option B: With auto-lookup from Redfin Comps Map (PREFERRED)
python execution/calculate_mao.py \
  --arv <value> \
  --rehab <value> \
  --rent <value> \
  --neighborhood-name "Glenville" \
  --wholesale-fee 10000
```

*Note: You can override `--taxes`, `--insurance`, and `--interest-rate` if you have specific data.*

## Interpreting and Presenting the Results

The script will output a JSON object. Present the findings to the user using this format:

1. **The Fix & Flip Scenario:**
   - Summarize the math: `(ARV * 0.70) - Effective Rehab (1.10x) - Wholesale Fee`
   - State the MAO clearly. If it's negative or dangerously low, note that it's a "Dead Deal" for flippers.

2. **The Buy & Hold Scenario:**
   - Note the NOI (accounting for 5% Vacancy, 5% Maint, 5% CapEx, 10% PM, Taxes & Insurance) and the Target Cash-on-Cash Return used (automatically chosen based on Neighborhood Class).
   - Provide the **Yield-Based MAO**.
   - **Crucial Check:** Look at `is_capped_by_appraisal`. If true, emphasize that the property's immense cash flow supports a higher purchase price, but the bank's LTV limits against the ARV cap it lower. Present the `mao_after_appraisal_cap` as the safest, most realistic MAO for a financed buyer.

3. **Final Recommendation:**
   - Tell the user specific negotiation ranges (e.g., "Aim to lock it up between X and Y to secure your fee easily").
