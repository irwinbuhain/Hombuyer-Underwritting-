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
    
    # We still use the effective_rehab to account for 10% overrun safety padding
    effective_rehab = args.rehab * 1.10
    
    ff_end_buyer_price = (args.arv * 0.70) - effective_rehab
    ff_mao = ff_end_buyer_price - args.wholesale_fee
    
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
    pm_fee = annual_rent * 0.10
    maint = annual_rent * 0.05
    vacancy = annual_rent * 0.05
    capex = annual_rent * 0.05
    
    total_expenses = pm_fee + maint + vacancy + capex + args.taxes + args.insurance
    noi = annual_rent - total_expenses
    
    # 3. Calculate max allowable End-Buyer Purchase Price algebraically
    factor = calculate_mortgage_factor(bh_interest_rate, 30)
    
    # Universal 10% Rehab Cost Overrun
    effective_rehab_bh = args.rehab * 1.10
    
    # In DealCheck, the rehab is NOT financed. The Base Loan is just 80% of Purchase Price.
    # Base_Loan = Purchase_Price * 0.80
    # The 2% origination fee is FINANCED into the loan.
    # Total_Loan = Base_Loan * 1.02 = Purchase_Price * 0.816
    # Annual_Debt_Service = Total_Loan * factor = Purchase_Price * 0.816 * factor
    
    # Total_Cash_Invested = Down_Payment + Rehab + Title_Escrow + Wholesale_Fee
    # Down_Payment = MAO * 0.20
    # Total_Cash_Invested = MAO * 0.20 + effective_rehab_bh + title_escrow_fee + args.wholesale_fee
    
    # Target Cash Flow = Total_Cash_Invested * target_coc
    
    # Target Cash Flow = NOI - Annual_Debt_Service
    # (MAO * 0.20 + effective_rehab_bh + title_escrow_fee + args.wholesale_fee) * target_coc = noi - (MAO * 0.816 * factor)
    
    # Algebra:
    # MAO * 0.20 * target_coc + (effective_rehab_bh + title_escrow_fee + args.wholesale_fee) * target_coc = noi - MAO * 0.816 * factor
    # MAO * (0.20 * target_coc + 0.816 * factor) = noi - (effective_rehab_bh + title_escrow_fee + args.wholesale_fee) * target_coc
    
    denominator = (0.20 * target_coc) + (0.816 * factor)
    numerator = noi - ((effective_rehab_bh + title_escrow_fee + args.wholesale_fee) * target_coc)
    
    bh_mao = numerator / denominator
    bh_end_buyer_price = bh_mao + args.wholesale_fee
    
    # Calculate resultant cash flow for B&H based on the algebraic target
    bh_down_payment = bh_end_buyer_price * 0.20
    bh_total_cash_invested = bh_down_payment + effective_rehab_bh + title_escrow_fee + args.wholesale_fee
    bh_annual_cash_flow = bh_total_cash_invested * target_coc
    bh_monthly_cash_flow = bh_annual_cash_flow / 12
    
    # Safety Check: Appraisal Cap
    appraisal_cap = args.arv - effective_rehab_bh
    capped_end_buyer_price = min(bh_end_buyer_price, appraisal_cap)
    appraisal_capped_bh_mao = capped_end_buyer_price - args.wholesale_fee
    
    # ---------------------------------------------------------
    # BRRRR Calculation (Buy, Rehab, Rent, Refinance, Repeat)
    # ---------------------------------------------------------
    # Target: Investor pulls $20,000 CASH OUT of the deal after refinance.
    # Refinance Loan amount = 80% of ARV
    # Refinance Costs = 3% of ARV
    # Universal 10% Rehab Cost Overrun
    effective_rehab_brrrr = args.rehab * 1.10
    
    cash_out_target = 20000
    
    # All-In Cost = Purchase Price + Effective Rehab + Title/Escrow + Holding Costs + Refinance Costs
    # To pull $20k cash out: All-In Cost + $20,000 <= Refinance Loan
    # Therefore: Purchase Price = (ARV * 0.80) - Effective Rehab - Title/Escrow(1000) - holding_costs(5% of rehab) - Refinance Costs - $20,000
    refinance_amount = args.arv * 0.80
    refinance_costs = args.arv * 0.03
    brrrr_end_buyer_price = refinance_amount - effective_rehab_brrrr - title_escrow_fee - (0.05 * effective_rehab_brrrr) - refinance_costs - cash_out_target
    brrrr_mao = brrrr_end_buyer_price - args.wholesale_fee
    
    brrrr_annual_debt_service = refinance_amount * factor
    brrrr_annual_cash_flow = noi - brrrr_annual_debt_service
    brrrr_monthly_cash_flow = brrrr_annual_cash_flow / 12
    brrrr_coc = "Infinite"
    
    return {
        "inputs": vars(args),
        "financials": {
            "annual_gross_rent": annual_rent,
            "annual_expenses": total_expenses,
            "net_operating_income": noi,
            "target_coc_return": target_coc
        },
        "results": {
            "fix_and_flip": {
                "end_buyer_max_purchase_price": round(ff_end_buyer_price, 2),
                "mao": round(ff_mao, 2),
                "formula": "Purchase = [ARV - 7.5% Selling - 15% Profit Target - Effective Rehab(1.10x) - 5.6% F&F Loan Costs - $1000 Title/Escrow] / 1.056",
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
                "monthly_cash_flow": round(bh_monthly_cash_flow, 2),
                "coc_return": f"{int(target_coc * 100)}%",
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
                "monthly_cash_flow": round(brrrr_monthly_cash_flow, 2),
                "coc_return": brrrr_coc,
                "formula": "Purchase = (ARV * 80%) - Effective Rehab(1.10x) - $1000 Title/Escrow - 5% Holding Costs - 3% ARV Refi Costs",
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
    parser.add_argument("--interest-rate", type=float, default=0.07, help="30-yr Mortgage Rate (Default: 0.07)")
    parser.add_argument("--taxes", type=float, default=1200, help="Annual Property Taxes (Default: 1200, but should be passed from DealCheck)")
    parser.add_argument("--insurance", type=float, default=1000, help="Annual Landlord Insurance (Default: 1000, but should be passed from DealCheck)")
    
    args = parser.parse_args()
    
    results = calculate_mao(args)
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
