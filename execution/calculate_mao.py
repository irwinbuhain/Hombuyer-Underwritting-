import argparse
import json
import os
import re
import builtins

def calculate_mortgage_factor(rate, years=30):
    """
    Calculates the annual mortgage payment factor (Annual Payment = Loan Amount * Factor).
    Formula: M = P [ r(1 + r)^n ] / [ (1 + r)^n - 1 ]
    """
    if rate == 0:
        return 1.0 / years
    
    r = rate / 12.0
    n = years * 12
    monthly_factor = (r * (1 + r)**n) / ((1 + r)**n - 1)
    return monthly_factor * 12

def get_neighborhood_grade(neighborhood_name):
    """Parses the HomeBuyer+ neighborhood reference file to find a grade."""
    file_path = "redfin-comps/references/neighborhoods.md"
    if not os.path.exists(file_path):
        return None
        
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
            
        search_target = neighborhood_name.lower().strip()
        for line in lines:
            if not line.startswith('|'):
                continue
            
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 3:
                name_val = parts[1].lower()
                grade_val = parts[2]
                
                # Check for an exact or substring match in the neighborhood name column
                if search_target in name_val or name_val in search_target:
                    return grade_val
        return None
    except Exception as e:
        return None

def standardize_grade(raw_grade):
    """
    Standardize raw grades containing +/-, splits (C/F), or ranges.
    Returns A, B, C, D, or F. Uses conservative lower bounds.
    """
    if not raw_grade:
        return None
        
    grade = raw_grade.upper()
    
    # Strip plus/minus
    grade = grade.replace('+', '').replace('-', '')
    
    # Handle splits or ranges by taking the lowest grade (most conservative)
    if '/' in grade:
        parts = grade.split('/')
        if 'F' in parts: return 'F'
        if 'D' in parts: return 'D'
        if 'C' in parts: return 'C'
        if 'B' in parts: return 'B'
        if 'A' in parts: return 'A'
        
    # Standard 1-letter extraction
    match = re.search(r'[ABCDF]', grade)
    if match:
        return match.group(0)
        
    return None

def calculate_mao(args):
    # Determine the strict Neighborhood Class letter
    if args.neighborhood_name:
        raw_grade = get_neighborhood_grade(args.neighborhood_name)
        if raw_grade:
            strict_class = standardize_grade(raw_grade)
            print(f"[INFO] Found '{args.neighborhood_name}' mapped to grade: {raw_grade} -> {strict_class} Class")
            resolved_class = strict_class if strict_class else 'C'
        else:
            print(f"[WARN] Neighborhood '{args.neighborhood_name}' not found in references. Defaulting to C Class.")
            resolved_class = 'C'
    else:
        resolved_class = args.neighborhood_class.upper()

    # ---------------------------------------------------------
    # Universal Lending Assumptions
    # ---------------------------------------------------------
    origination_fee_pct = 0.02
    title_escrow_fee = 1000
    
    # ---------------------------------------------------------
    # Fix and Flip Calculation
    # ---------------------------------------------------------
    # F&F Loan = 80% of (Purchase Price + Rehab)
    # F&F Down Payment = 20% of (Purchase Price + Rehab)
    # Holding Period = 6 months
    # F&F Interest Rate = 10% annual -> 5% over 6 months
    # Closing/Selling Costs = 7.5% of ARV
    
    # Use the 70% Rule for Fix and Flip per User Request
    # MAO = (ARV * 0.70) - Rehab - Wholesale Fee
    
    effective_rehab = args.rehab
    
    ff_end_buyer_price = (args.arv * 0.75) - effective_rehab
    ff_mao = ff_end_buyer_price - args.wholesale_fee
    
    # Calculate detailed flip metrics
    # DealCheck uses MAO (Purchase Price to Seller) for the primary loan/down payment basis, not the gross end-buyer price.
    ff_loan = 0.80 * (ff_mao + effective_rehab)
    ff_monthly_payment = (ff_loan * 0.10) / 12
    
    # DealCheck origination is 2% of Purchase Price (MAO)
    origination_fee = 0.02 * ff_mao
    
    # Cash needed includes down payment, origination, title, and the wholesale fee paid in cash
    ff_cash_needed = (0.20 * (ff_mao + effective_rehab)) + title_escrow_fee + origination_fee + args.wholesale_fee
    
    # Holding costs (simplified to interest + 6 months of taxes/insurance)
    ff_holding_costs = (ff_monthly_payment * 6) + (args.taxes / 2) + (args.insurance / 2)
    ff_selling_costs = args.arv * 0.075
    
    ff_total_costs = ff_cash_needed + ff_loan + ff_holding_costs + ff_selling_costs
    ff_total_profit = args.arv - ff_total_costs
    
    # DealCheck ROI denominator includes Cash Needed AND Holding Costs
    ff_total_invested = ff_cash_needed + ff_holding_costs
    ff_roi = ff_total_profit / ff_total_invested if ff_total_invested > 0 else 0
    ff_annualized_roi = ff_roi * 2
    
    # ---------------------------------------------------------
    # Buy and Hold Calculation
    # ---------------------------------------------------------
    # B&H Loan = 80% of Purchase Price + Rehab
    
    # New Rule: DealCheck Default Template uses 7% interest rate strictly.
    bh_interest_rate = 0.07
    
    # 1. Determine Target COC based on neighborhood class
    coc_targets = {
        'A': 0.08,
        'B': 0.10,
        'C': 0.14,
        'D': 0.20,
        'F': 0.30
    }
    target_coc = coc_targets.get(resolved_class, 0.14) # Default to C if unknown
    
    # 2. Calculate Annual Revenue & Expenses
    annual_rent = args.rent * 12
    maint = annual_rent * 0.05
    vacancy = annual_rent * 0.05
    capex = annual_rent * 0.05
    
    # Property Management is typically calculated as a percentage of COLLECTED rent (Gross - Vacancy)
    pm_fee = (annual_rent - vacancy) * 0.10
    
    total_expenses = pm_fee + maint + vacancy + capex + args.taxes + args.insurance
    noi = annual_rent - total_expenses
    
    # 3. Calculate max allowable offer (MAO) algebraically
    factor = calculate_mortgage_factor(bh_interest_rate, 30)
    effective_rehab_bh = args.rehab
    
    # Based on DealCheck, the "Purchase Price" inputted into the platform is the Seller's acquisition cost (MAO).
    # The Wholesale Fee is separated out entirely as a Cash Purchase Cost.
    # Therefore:
    # Base_Loan = MAO * 0.80
    # Financed 2% Origination = (MAO * 0.80) * 0.02 = MAO * 0.016
    # Total_Loan = MAO * 0.816
    # Annual_Debt_Service = Total_Loan * factor = MAO * 0.816 * factor
    
    # Total_Cash_Invested = Down_Payment + Rehab + Title + Wholesale_Fee
    # Total_Cash_Invested = (MAO * 0.20) + effective_rehab_bh + title_escrow_fee + args.wholesale_fee
    
    # Target Cash Flow = Total_Cash_Invested * target_coc
    # Target Cash Flow = NOI - Annual_Debt_Service
    # NOI - (MAO * 0.816 * factor) = ((MAO * 0.20) + effective_rehab_bh + title_escrow_fee + args.wholesale_fee) * target_coc
    
    # Algebraic Solve for MAO:
    # NOI - (effective_rehab_bh + title_escrow_fee + args.wholesale_fee) * target_coc = MAO * ((0.816 * factor) + (0.20 * target_coc))
    
    denominator = (0.20 * target_coc) + (0.816 * factor)
    numerator = noi - ((effective_rehab_bh + title_escrow_fee + args.wholesale_fee) * target_coc)
    
    bh_mao = numerator / denominator
    bh_end_buyer_price = bh_mao + args.wholesale_fee
    
    # Calculate resultant loan terms
    bh_loan_amount = bh_mao * 0.816
    bh_monthly_payment = (bh_loan_amount * factor) / 12
    
    # Calculate resultant cash flow for B&H based on the algebraic target
    bh_down_payment = bh_mao * 0.20
    # Wholesale fee paid in cash upfront
    bh_cash_needed = bh_down_payment + effective_rehab_bh + title_escrow_fee + args.wholesale_fee
    
    bh_annual_cash_flow = noi - (bh_monthly_payment * 12)
    bh_monthly_cash_flow = bh_annual_cash_flow / 12
    bh_cap_rate = noi / (bh_mao + effective_rehab_bh) if (bh_mao + effective_rehab_bh) > 0 else 0
    bh_coc_return = bh_annual_cash_flow / bh_cash_needed if bh_cash_needed > 0 else 0
    
    # Safety Check: Appraisal Cap
    appraisal_cap = args.arv - effective_rehab_bh
    capped_mao = min(bh_mao, appraisal_cap)
    appraisal_capped_bh_mao = capped_mao
    
    # ---------------------------------------------------------
    # BRRRR Calculation (Buy, Rehab, Rent, Refinance, Repeat)
    # ---------------------------------------------------------
    # Target: Investor pulls $20,000 CASH OUT of the deal after refinance.
    # Refinance Loan amount = 80% of ARV
    # Refinance Costs = 3% of ARV
    effective_rehab_brrrr = args.rehab
    
    cash_out_target = 20000
    
    # All-In Cost = Purchase Price + effective_rehab_brrrr + title_escrow_fee + holding_costs + refinance_costs
    # To pull $20k cash out: All-In Cost + $20,000 <= Refinance Loan
    # Purchase Price = (ARV * 0.80) - effective_rehab - Title/Escrow - holding_costs - Refinance Costs - $20,000
    refinance_amount = args.arv * 0.80
    refinance_costs = args.arv * 0.03
    brrrr_end_buyer_price = (args.arv * 0.75) - effective_rehab_brrrr
    
    brrrr_mao = brrrr_end_buyer_price - args.wholesale_fee
    brrrr_annual_debt_service = refinance_amount * factor
    brrrr_monthly_payment = brrrr_annual_debt_service / 12
    brrrr_annual_cash_flow = noi - brrrr_annual_debt_service
    brrrr_monthly_cash_flow = brrrr_annual_cash_flow / 12
    
    # ---------------------------------------------------------
    # BRRRR Override: Minimum 5% Cash-on-Cash (Yield on $20k)
    # ---------------------------------------------------------
    # The investor has $20,000 trapped/pulled equity. We want a 5% yield minimum on that $20k.
    # Required annual cash flow = $20,000 * 0.05 = $1,000/yr.
    required_annual_cf = cash_out_target * 0.05
    
    # If the property does not cash flow at least $1,000/yr naturally:
    # We must lower the Refinance Loan amount until the debt service drops enough to hit that $1,000 CF mark.
    # New Max Debt Service = NOI - $1,000
    if brrrr_annual_cash_flow < required_annual_cf:
        max_allowable_debt_service = noi - required_annual_cf
        # If the property can't even carry debt (NOI < $1,000), deal is dead
        if max_allowable_debt_service <= 0:
            brrrr_mao = -999999
            brrrr_annual_cash_flow = max_allowable_debt_service
            brrrr_monthly_cash_flow = brrrr_annual_cash_flow / 12
            brrrr_coc = "Dead Deal (Negative NOI)"
        else:
            # Drop the loan amount down to fit the new max debt service
            reduced_refinance_amount = max_allowable_debt_service / factor
            # Because the loan amount drops, the investor has less cash to buy the house with upfront.
            # We penalize the MAO dollar-for-dollar by the difference between the 80% ARV loan and this new reduced loan.
            loan_shortfall = refinance_amount - reduced_refinance_amount
            brrrr_end_buyer_price -= loan_shortfall
            brrrr_mao -= loan_shortfall
            
            # Recalculate cashflow which will now exactly equal the 5% target
            brrrr_annual_cash_flow = required_annual_cf
            brrrr_monthly_cash_flow = brrrr_annual_cash_flow / 12
            
    # Calculate True Cash on Cash (Yield on $20k minimum)
    actual_coc = brrrr_annual_cash_flow / cash_out_target if cash_out_target > 0 else 0
    brrrr_coc = actual_coc
    # Wholesale fee paid in cash upfront
    brrrr_cash_needed = (brrrr_end_buyer_price * 0.20) + effective_rehab_brrrr + title_escrow_fee + (0.02 * (brrrr_end_buyer_price * 0.8)) + args.wholesale_fee
    brrrr_cap_rate = noi / (brrrr_end_buyer_price + effective_rehab_brrrr) if (brrrr_end_buyer_price + effective_rehab_brrrr) > 0 else 0
    
    return {
        "inputs": vars(args),
        "financials": {
            "annual_gross_rent": annual_rent,
            "annual_expenses": total_expenses,
            "expenses_breakdown": {
                "property_management_fee": pm_fee,
                "maintenance": maint,
                "vacancy": vacancy,
                "capex": capex,
                "taxes": args.taxes,
                "insurance": args.insurance
            },
            "net_operating_income": noi,
            "target_coc_return": target_coc
        },
        "results": {
            "fix_and_flip": {
                "end_buyer_max_purchase_price": round(ff_end_buyer_price, 2),
                "mao": round(ff_mao, 2),
                "cash_needed": round(ff_cash_needed, 2),
                "total_profit": round(ff_total_profit, 2),
                "roi": round(ff_roi, 4),
                "annualized_roi": round(ff_annualized_roi, 4),
                "costs_breakdown": {
                    "rehab": effective_rehab,
                    "holding_costs": round(ff_holding_costs, 2),
                    "selling_costs": round(ff_selling_costs, 2),
                    "title_escrow_fee": title_escrow_fee,
                    "wholesale_fee": args.wholesale_fee
                },
                "lending_breakdown": {
                    "loan_amount": round(ff_loan, 2),
                    "interest_rate": 0.10,
                    "monthly_payment": round(ff_monthly_payment, 2)
                },
                "formula": "Purchase = (ARV * 0.75) - Effective Rehab - Wholesale Fee",
                "assumptions": {
                    "down_payment": "20%",
                    "interest_rate": "10%",
                    "hold_time_months": 6,
                    "origination_fee": "2%",
                    "rehab_overrun": "10%",
                    "closing_costs_on_sale": "7.5%",
                    "title_escrow_fee": "$1000"
                }
            },
            "buy_and_hold_yield_based": {
                "end_buyer_max_purchase_price": round(bh_end_buyer_price, 2),
                "mao": round(bh_mao, 2),
                "cash_needed": round(bh_cash_needed, 2),
                "monthly_cash_flow": round(bh_monthly_cash_flow, 2),
                "coc_return": round(target_coc, 4),
                "cap_rate": round(bh_cap_rate, 4),
                "lending_breakdown": {
                    "loan_amount": round(bh_loan_amount, 2),
                    "interest_rate": bh_interest_rate,
                    "monthly_payment": round(bh_monthly_payment, 2)
                },
                "is_capped_by_appraisal": bh_end_buyer_price > appraisal_cap,
                "mao_after_appraisal_cap": round(appraisal_capped_bh_mao, 2),
                "assumptions": {
                    "down_payment": "20%",
                    "interest_rate": f"{int(bh_interest_rate * 100)}%",
                    "amortization_years": 30,
                    "origination_fee": "2% (Financed into Loan)",
                    "title_escrow_fee": "$1000",
                    "rehab_overrun": "10%",
                    "property_management_fee": "10%",
                    "vacancy_maint_capex": "5% Vacancy, 5% Maint, 5% CapEx"
                }
            },
            "brrrr": {
                "end_buyer_max_purchase_price": round(brrrr_end_buyer_price, 2),
                "mao": round(brrrr_mao, 2),
                "cash_needed": round(brrrr_cash_needed, 2),
                "cash_out_profit": round(cash_out_target, 2),
                "monthly_cash_flow": round(brrrr_monthly_cash_flow, 2),
                "coc_return": brrrr_coc if isinstance(brrrr_coc, str) else round(brrrr_coc, 4),
                "cap_rate": round(brrrr_cap_rate, 4),
                "lending_breakdown": {
                    "loan_amount": round(refinance_amount, 2),
                    "interest_rate": bh_interest_rate,
                    "monthly_payment": round(brrrr_monthly_payment, 2)
                },
                "formula": "Purchase = (ARV * 0.75) - Effective Rehab - Wholesale Fee",
                "assumptions": {
                    "refinance_ltv": "80%",
                    "refinance_costs": "3% of ARV",
                    "rehab_overrun": "10%",
                    "cash_left_in_deal_target": "$0",
                    "title_escrow_fee": "$1000"
                }
            }
        }
    }

def main():
    parser = argparse.ArgumentParser(description="Calculate Max Allowable Offer (MAO)")
    parser.add_argument("--arv", type=float, required=True, help="After Repair Value")
    parser.add_argument("--rehab", type=float, required=True, help="Estimated Rehab Cost")
    parser.add_argument("--rent", type=float, required=True, help="Monthly Gross Rent")
    
    # Allow either a direct class letter or a neighborhood name lookup
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--neighborhood-class", type=str, choices=['A', 'B', 'C', 'D', 'F', 'a', 'b', 'c', 'd', 'f'], help="Direct Neighborhood Grade (A, B, C, D, F)")
    group.add_argument("--neighborhood-name", type=str, help="Neighborhood name to auto-lookup from references/neighborhoods.md")
    
    parser.add_argument("--wholesale-fee", type=float, default=10000, help="Target Wholesale Assignment Fee (Default: 10000)")
    parser.add_argument("--realtor-commission", type=float, default=0.0, help="Realtor Commission as a Decimal %% (Default: 0.0)")
    parser.add_argument("--interest-rate", type=float, default=0.07, help="30-yr Mortgage Rate (Default: 0.07)")
    parser.add_argument("--taxes", type=float, default=1200, help="Annual Property Taxes (Default: 1200, but should be passed from DealCheck)")
    parser.add_argument("--insurance", type=float, default=1000, help="Annual Landlord Insurance (Default: 1000, but should be passed from DealCheck)")
    
    args = parser.parse_args()
    
    results = calculate_mao(args)
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
