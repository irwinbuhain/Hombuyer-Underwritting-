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
    .stTextInput label, .stNumberInput label, .stSelectbox label {
        font-size: 13px !important;
    }
    .stTextInput label p, .stNumberInput label p, .stSelectbox label p {
        font-size: 13px !important;
    }
    
    .stTextInput > div > div > input, 
    .stNumberInput > div > div > input,
    .stSelectbox > div > div > div {
        background-color: #1e242d;
        border: 1px solid #334155;
        border-radius: 8px;
        color: #f8fafc;
        padding: 8px 12px;
        font-size: 14px;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.2);
    }
    
    /* Hide standard number input spinners across all browsers */
    input[type="number"]::-webkit-inner-spin-button, 
    input[type="number"]::-webkit-outer-spin-button { 
        -webkit-appearance: none; 
        margin: 0; 
    }
    input[type="number"] {
        -moz-appearance: textfield;
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

arv_override = st.number_input("After Repair Value (ARV) ($)", min_value=0, value=None, step=5000)

col1, col2 = st.columns(2)
with col1:
    rehab_ff = st.number_input("Rehab Estimate (Fix & Flip)", min_value=0, value=None, step=5000)
with col2:
    rehab_bh = st.number_input("Rehab Estimate (Buy & Hold)", min_value=0, value=None, step=5000)

col_c, col_d, col_e, col_f, col_g = st.columns(5)
with col_c:
    rent = st.number_input("Rent ($)", min_value=0, value=None, step=50)
with col_d:
    manual_taxes = st.number_input("Taxes ($)", min_value=0, value=None, step=100)
with col_e:
    manual_ins = st.number_input("Ins. ($)", min_value=0, value=None, step=50)
with col_f:
    neighborhood_class_override = st.selectbox(
        "Grade",
        options=["Select", "A", "B", "C", "D", "F"],
        index=0
    )
with col_g:
    wholesale_fee_input = st.number_input("Wholesale Fee ($)", min_value=0, value=None, step=1000)

st.markdown("<br>", unsafe_allow_html=True)
calc_button = st.button("Calculate MAO")
st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------
# Main Calculation Block
# ---------------------------------------------------------
if calc_button:
    if arv_override is None or arv_override <= 0:
        st.error("Please enter an ARV greater than $0 to proceed.")
    elif rehab_ff is None or rehab_bh is None:
        st.error("Please enter Rehab Estimates to proceed.")
    elif rent is None or rent <= 0:
        st.error("Please enter a Monthly Rent greater than $0 to proceed.")
    elif manual_taxes is None or manual_taxes <= 0:
        st.error("Please enter Annual Taxes greater than $0 to proceed.")
    elif manual_ins is None or manual_ins <= 0:
        st.error("Please enter Annual Insurance greater than $0 to proceed.")
    elif neighborhood_class_override == "Select":
        st.error("Please pick an Area Grade (A, B, C, D, or F) to proceed.")
    else:
        with st.spinner("🔍 Calculating MAO..."):
            try:
                neighborhood = "Manual Entry"
                neighborhood_class = 'C'
                comps = []
                
                arv = arv_override
                final_address = "Manual Underwriting"
                
                # Apply map override for area grade
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
                    wholesale_fee=wholesale_fee_input,
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
                    wholesale_fee=wholesale_fee_input,
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
                

                        
            except Exception as e:
                st.error(f"Error calculating MAO: {e}")
