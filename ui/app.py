import streamlit as st
import sys
import os
import subprocess
import json
import pandas as pd
# Add the parent directory to the path so we can import the execution scripts
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from execution.calculate_mao import calculate_mao
import argparse

st.set_page_config(page_title="MAO Calculator", page_icon="🏢", layout="centered")

# Custom CSS to mimic a sleek, modern, RentCast-inspired aesthetic
st.markdown("""
    <style>
    /* Main Background */
    .stApp {
        background-color: #0f1115;
        font-family: 'Inter', sans-serif;
        color: #e2e8f0;
    }
    
    /* Headers & Markdown Text */
    h1 {
        color: #f8fafc;
        font-weight: 800 !important;
        text-align: center;
        padding-bottom: 20px;
    }
    h2, h3, h4, p, li, span, div {
        color: #cbd5e1;
    }
    h3 {
        color: #f1f5f9;
        font-weight: 600 !important;
        margin-top: 1rem;
    }
    
    /* Input Fields Container Styling */
    .stTextInput > div > div > input, 
    .stNumberInput > div > div > input,
    .stSelectbox > div > div > div {
        background-color: #1e242d;
        border: 1px solid #334155;
        border-radius: 8px;
        color: #f8fafc;
        padding: 12px 16px;
        font-size: 16px;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.2);
    }
    
    /* Input Focus */
    .stTextInput > div > div > input:focus, 
    .stNumberInput > div > div > input:focus,
    .stSelectbox > div > div > div:focus {
        border-color: #3b82f6;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.4);
    }
    
    /* Dropdown elements */
    ul[data-testid="stSelectboxVirtualDropdown"] {
        background-color: #1e242d;
    }
    li[data-testid="stSelectboxVirtualDropdownItem"] {
        color: #f8fafc;
    }
    
    /* Primary Button Styling (RentCast Blue) */
    .stButton > button {
        background-color: #2563eb !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 14px 24px !important;
        font-weight: 600 !important;
        font-size: 16px !important;
        width: 100% !important;
        transition: all 0.2s ease;
        box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2);
    }
    
    .stButton > button:hover {
        background-color: #3b82f6 !important;
        box-shadow: 0 6px 8px -1px rgba(59, 130, 246, 0.3);
        transform: translateY(-1px);
    }
    
    /* Custom Cards for Results */
    .result-card {
        background: #171d25;
        padding: 24px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2);
        border: 1px solid #2a3340;
        margin-top: 16px;
        text-align: center;
    }
    
    .price-value {
        font-size: 36px;
        font-weight: 800;
        color: #60a5fa;
        margin: 10px 0;
    }
    
    .price-label {
        color: #94a3b8;
        font-size: 16px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    /* Override Streamlit's default info/success/warning boxes */
    .stAlert {
        background-color: #1e242d;
        color: #f8fafc;
        border: 1px solid #334155;
    }
    
    /* Override Streamlit Tabs */
    button[data-baseweb="tab"] {
        color: #94a3b8 !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #f8fafc !important;
    }
    
    </style>
    """, unsafe_allow_html=True)

st.markdown("<h1>Underwriting Engine</h1>", unsafe_allow_html=True)

# ---------------------------------------------------------
# Centered Clean Inputs
# ---------------------------------------------------------

address = st.text_input("Property Address", placeholder="123 Main St, Cleveland, OH")

arv_override = st.number_input("ARV ($)", min_value=0, value=0, step=5000, format="%d", help="Leave 0 to auto-calculate via Redfin")

col1, col2 = st.columns(2)
with col1:
    rehab_ff = st.number_input("Rehab Estimate (Fix & Flip)", min_value=0, value=50000, step=5000, format="%d")
with col2:
    rehab_bh = st.number_input("Rehab Estimate (Buy & Hold)", min_value=0, value=50000, step=5000, format="%d")

col_c, col_d, col_e, col_f = st.columns(4)
with col_c:
    rent = st.number_input("Monthly Rent ($)", min_value=0, value=2000, step=50, format="%d")
with col_d:
    manual_taxes = st.number_input("Annual Taxes ($)", min_value=0, value=1500, step=100, format="%d")
with col_e:
    manual_ins = st.number_input("Annual Ins. ($)", min_value=0, value=800, step=50, format="%d")
with col_f:
    neighborhood_class_override = st.selectbox(
        "Area Grade",
        options=["Auto", "A", "B", "C", "D", "F"],
        index=0
    )

st.markdown("<br>", unsafe_allow_html=True)
calc_button = st.button("Calculate MAO")
st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------
# Main Calculation Block
# ---------------------------------------------------------
if calc_button:
    final_address = address
    if not final_address:
        st.error("Please enter a property address to proceed.")
    else:
        with st.spinner("🔍 Analyzing property metrics and calculating MAO..."):
            try:
                neighborhood = "Unknown"
                neighborhood_class = 'C'
                comps = []
                
                # 1. Fetch Comps & Neighborhood Data dynamically ONLY if ARV wasn't provided
                if arv_override > 0:
                     arv = arv_override
                     st.info(f"Using User-Provided ARV: ${arv:,.0f}")
                else:
                     comps_script_path = os.path.join(parent_dir, 'redfin-comps', 'scripts', 'fetch_redfin_comps.py')
                     tmp_dir = os.path.join(parent_dir, ".tmp")
                     os.makedirs(tmp_dir, exist_ok=True)
                     json_path = os.path.join(tmp_dir, "streamlit_comps.json")
                     
                     lookbacks = [180, 365, 730]
                     for days in lookbacks:
                         st.toast(f"Searching for matching comps ({days} days back)...")
                         search_address = final_address if ", OH" in final_address or "Ohio" in final_address else f"{final_address}, Cleveland, OH"
                         cmd = [
                             sys.executable, comps_script_path,
                             "--address", search_address,
                             "--lookback-days", str(days),
                             "--property-type", "any",
                             "--output", json_path
                         ]
                         
                         subprocess.run(cmd, capture_output=True, text=True)
                         
                         if os.path.exists(json_path):
                             with open(json_path, 'r') as f:
                                 comps_data = json.load(f)
                             if len(comps_data.get('comps', [])) >= 3:
                                 break # found enough comps
                             
                     if os.path.exists(json_path):
                          with open(json_path, 'r') as f:
                              comps_data = json.load(f)
                          
                          # Extract neighborhood metadata regardless of comp count
                          neighborhood = comps_data.get('filters', {}).get('neighborhood', 'Unknown')
                          neighborhood = neighborhood if neighborhood else "Unknown"
                          neighborhood_class = comps_data.get('filters', {}).get('neighborhood_class', 'C')
                          
                          if len(comps_data.get('comps', [])) == 0:
                              st.warning("⚠️ Could not find exact Redfin Comps even after extending search to 2 years. Defaulting to an estimated $150k ARV floor. Please override manually if needed.")
                              arv = 150000
                          else:
                              # Calculate ARV based on top 3 comps
                              top_comps = sorted(comps_data['comps'], key=lambda x: x.get('price', 0), reverse=True)[:3]
                              arv = sum(c.get('price', 0) for c in top_comps) / len(top_comps)
                              comps = top_comps
                     else:
                          st.error("Backend error: No comps data returned from the engine.")
                          arv = 150000
                              
                     st.success(f"📍 **Neighborhood identified:** {neighborhood} (API Class {neighborhood_class})")
                
                # Apply map override for area grade if provided
                if neighborhood_class_override != "Auto":
                    neighborhood_class = neighborhood_class_override
                
                # Use precise DealCheck input values
                estimated_taxes = manual_taxes
                estimated_ins = manual_ins
                
                args_ff = argparse.Namespace(
                    address=final_address,
                    arv=arv,
                    rehab=rehab_ff,
                    rent=rent,
                    neighborhood_class=neighborhood_class,
                    neighborhood_name=None,
                    taxes=estimated_taxes,
                    insurance=estimated_ins,
                    wholesale_fee=10000,
                    interest_rate=0.07 
                )
                
                args_bh = argparse.Namespace(
                    address=final_address,
                    arv=arv,
                    rehab=rehab_bh,  
                    rent=rent,
                    neighborhood_class=neighborhood_class,
                    neighborhood_name=None,
                    taxes=estimated_taxes,
                    insurance=estimated_ins,
                    wholesale_fee=10000,
                    interest_rate=0.07 
                )

                res_ff = calculate_mao(args_ff)
                res_bh = calculate_mao(args_bh)
                
                st.markdown("### Underwriting Results")
                
                # Render Sleek Custom Cards
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown(f"""
                    <div class="result-card">
                        <div class="price-label">Fix & Flip MAO</div>
                        <div class="price-value">${res_ff['results']['fix_and_flip']['mao']:,.0f}</div>
                        <div style="color: #94a3b8; font-size: 14px;">Rehab budget: ${rehab_ff:,.0f}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col2:
                    bh_mao_val = res_bh['results']['buy_and_hold_yield_based']['mao']
                    
                    if bh_mao_val < 0:
                        st.markdown(f"""
                        <div class="result-card" style="border-color: #7f1d1d; background-color: #450a0a;">
                            <div class="price-label" style="color: #fca5a5;">Buy & Hold MAO</div>
                            <div class="price-value" style="color: #f87171; font-size: 24px; padding: 10px 0;">Dead Deal</div>
                            <div style="color: #fca5a5; font-size: 14px;">Rent cannot cover debt service</div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        bh_cf = res_bh['results']['buy_and_hold_yield_based']['monthly_cash_flow']
                        st.markdown(f"""
                        <div class="result-card">
                            <div class="price-label">Buy & Hold MAO</div>
                            <div class="price-value">${bh_mao_val:,.0f}</div>
                            <div style="color: #94a3b8; font-size: 14px;">Rehab budget: ${rehab_bh:,.0f}</div>
                            <div style="color: #10b981; font-size: 14px; font-weight: bold; margin-top: 5px;">Cash Flow: ${bh_cf:,.0f}/mo</div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                with col3:
                    brrrr_mao_val = res_bh['results']['brrrr']['mao']
                    
                    if brrrr_mao_val < 0:
                        st.markdown(f"""
                        <div class="result-card" style="border-color: #7f1d1d; background-color: #450a0a;">
                            <div class="price-label" style="color: #fca5a5;">BRRRR MAO</div>
                            <div class="price-value" style="color: #f87171; font-size: 24px; padding: 10px 0;">Dead Deal</div>
                            <div style="color: #fca5a5; font-size: 14px;">Cannot hit 80% LTV</div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class="result-card">
                            <div class="price-label">BRRRR MAO</div>
                            <div class="price-value">${brrrr_mao_val:,.0f}</div>
                            <div style="color: #94a3b8; font-size: 14px;">Rehab budget: ${rehab_bh:,.0f}</div>
                        </div>
                        """, unsafe_allow_html=True)
                
                st.markdown("---")
                
                # Mathematical Breakdown Section
                st.markdown("### 📊 The Breakdown")
                
                t_col1, t_col2 = st.tabs(["Calculation Logic", "ARV & Comps Data"])
                
                with t_col1:
                    scol1, scol2, scol3 = st.columns(3)
                    with scol1:
                        st.markdown("**Fix & Flip Math (15% Net Profit Target)**")
                        st.write(f"- **ARV Used:** ${arv:,.0f}")
                        st.write(f"- Selling Costs (7.5%): -${(arv * 0.075):,.0f}")
                        st.write(f"- Investor Profit (15%): -${(arv * 0.15):,.0f}")
                        st.write(f"- Effective Rehab (+10% overrun): -${(rehab_ff * 1.10):,.0f}")
                        st.write(f"- Your Wholesale Fee: -$10,000")
                        st.write("- Minus 6-month hard money holding costs")
                        
                    with scol2:
                        target_coc = res_bh['financials']['target_coc_return'] * 100
                        st.markdown(f"**Buy & Hold Math ({target_coc:,.0f}% Cash-on-Cash)**")
                        st.write(f"- **Gross Rent:** ${rent:,.0f}/mo (${rent*12:,.0f}/yr)")
                        st.write(f"- **Operating Expenses:** -${res_bh['financials']['annual_expenses']:,.0f}/yr (Taxes, Ins, 10% PM, 5% Vac/Maint/CapEx)")
                        st.write(f"- **NOI:** ${res_bh['financials']['net_operating_income']:,.0f}/yr")
                        st.info(f"Calculates exact Purchase Price allowing {target_coc:,.0f}% ROI on all cash left in the deal (Down Payment + Effective Rehab + Fees).")
                        
                    with scol3:
                        st.markdown("**BRRRR Math ($0 Left in Deal)**")
                        st.write(f"- **Refinance Loan (80% ARV):** ${(arv * 0.80):,.0f}")
                        st.write(f"- ARV Refinance Costs (3%): -${(arv * 0.03):,.0f}")
                        st.write(f"- Title/Escrow Costs: -$1,000")
                        st.write(f"- 5% Holding Costs: -${(rehab_bh * 0.05):,.0f}")
                        st.write(f"- Effective Rehab (+10% overrun): -${(rehab_bh * 1.10):,.0f}")
                        st.write(f"- Your Wholesale Fee: -$10,000")
                        brrrr_cf = res_bh['results']['brrrr']['monthly_cash_flow']
                        st.write(f"- **Yield-Based Cash Flow:** ${brrrr_cf:,.0f}/mo")
                        st.info("Calculates MAO capped entirely by the allowable Refinance Loan minus all rehab, holding, and closing costs.")
                    
                with t_col2:
                    st.markdown(f"**Calculated ARV: ${arv:,.0f}**")
                    if len(comps) > 0:
                        st.write("Based on these top comparable sales sourced from **Redfin.com** in the exact neighborhood polygon:")
                        for idx, c in enumerate(comps):
                            st.markdown(f"**{idx+1}. {c.get('address')}**")
                            st.write(f"- **Sold For:** ${c.get('price', 0):,.0f} on {c.get('sale_date', 'Unknown')}")
                            st.write(f"- **Specs:** {c.get('beds')} Bed | {c.get('baths')} Bath | {c.get('sqft')} Sqft | {c.get('condition', 'Unknown')} Condition")
                            st.markdown(f"[View on Redfin]({c.get('url')})")
                            st.divider()
                    else:
                        st.warning("No perfect 1-to-1 comps were found via the API. An estimated floor ARV of $150k was used.")
                        
            except Exception as e:
                st.error(f"Error calculating MAO: {e}")
