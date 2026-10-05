from datetime import datetime, timedelta
import re
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="Aircraft Parking Fee Estimator", page_icon="✈️", layout="wide"
)

st.title("✈️ Aircraft Parking Fee Estimator")
st.write(
    "Calculate estimated aircraft parking charges using the live Signature Aviation tRPC API."
)

# List of pre-configured Tail Numbers
TAIL_NUMBERS = ["N265K", "N316K", "N681K", "N730K"]

# List of all available FBO codes from Signature Aviation
FBO_CODES = [
    "ANC", "AVL", "BCT", "BFM", "BKL", "BNA", "CHO", "CHS", "CID", "DSM",
    "EFD", "F45", "FAT", "FOK", "FSD", "FXE", "GEG", "GSO", "HHH", "HOU",
    "HWD", "IAH", "ICT", "INT", "ISM", "JAX", "JCI", "LAX", "LEX", "LFT",
    "LGB", "LIT", "LUK", "MAF", "MCI", "MCO", "MEM", "MHT", "MKC", "MKE",
    "MOB", "MSP", "OAK", "OMA", "ORF", "PHK", "PSP", "RDU", "ROA", "SAV",
    "SBA", "SCF", "SHV", "SJC", "STP", "TXK"
]

# Form Inputs
with st.form("parking_estimator_form"):
    customer_name = st.text_input("Customer Name", value="Koch Industries Inc.")
    
    # Dropdown with "All Tail Numbers" option
    tail_options = ["All Tail Numbers"] + TAIL_NUMBERS
    selected_tail = st.selectbox("Tail Number", options=tail_options, index=0)
    
    aircraft_make_model = st.text_input(
        "Aircraft Make & Model", value="Bombardier Learjet - 75"
    )
    
    fbo_base_id = st.selectbox(
        "FBO Base Code / Airport",
        options=FBO_CODES,
        index=FBO_CODES.index("ICT")  # Default to ICT
    )
    
    duration_days = st.number_input(
        "Duration of Stay (Days)", min_value=1, max_value=30, value=1, step=1
    )
    
    # Fuel Purchased Input
    fuel_gal = st.number_input(
        "Fuel Purchased (Gallons)", min_value=0, value=0, step=10
    )

    submitted = st.form_submit_button("Calculate Estimate")


def fetch_quote(tail_num, customer_name, aircraft_model, fbo_id, arrival_str, departure_str, fuel):
    """Helper function to execute the tRPC API request for a single tail number."""
    payload = {
        "0": {
            "json": {
                "customerName": customer_name,
                "tailNumber": tail_num,
                "aircraftMakeModel": aircraft_model,
                "fboBaseId": fbo_id,
                "arrivalDate": arrival_str,
                "departureDate": departure_str,
                "fuelGallons": fuel,
            }
        }
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Origin": "https://www.signatureaviation.com",
        "Referer": "https://www.signatureaviation.com/simplified-parking",
    }

    api_url = "https://new-prod-api.signatureaviation.com/api/trpc/parkingQuote.create?batch=1"

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            res_data = response.json()
            if "error" in res_data[0]:
                err_msg = res_data[0]["error"].get("json", {}).get("message", "API Error")
                return {"success": False, "error": err_msg, "raw": res_data[0]["error"]}
            
            data = res_data[0].get("result", {}).get("data", {}).get("json", {})
            return {"success": True, "data": data}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}", "raw": response.text}
            
    except Exception as e:
        return {"success": False, "error": str(e), "raw": None}


def parse_threshold_gallons(data):
    """Extracts numeric threshold gallon value from response."""
    if not data:
        return None
        
    fuel_desc = data.get("fuelDescription", "")
    if fuel_desc:
        match = re.search(r"(\d+)\s*gal", fuel_desc)
        if match:
            return int(match.group(1))

    waived_gal = data.get("waivedFuelGallons")
    if waived_gal is not None:
        return int(waived_gal)

    return None


def extract_discount_amount(data):
    """Extracts discount amount from discounts list or by comparing initial rate and total."""
    if not data:
        return 0.0

    # 1. Check discounts / lineItems array in payload
    discounts = data.get("discounts", []) or data.get("lineItems", [])
    total_disc = 0.0
    for item in discounts:
        if isinstance(item, dict):
            amt = item.get("amount", 0)
            if amt < 0:
                total_disc += abs(amt)

    if total_disc > 0:
        return total_disc

    # 2. Fallback: Difference between initial rate and estimated total
    initial = data.get("initialRate", 0)
    total = data.get("estimatedTotal", 0)
    tax = data.get("tax", 0)
    
    if initial > 0 and (initial + tax) > total:
        return (initial + tax) - total

    return 0.0


if submitted:
    # Format dates to YYYY-MM-DD
    now = datetime.utcnow()
    dept = now + timedelta(days=duration_days)
    arrival_str = now.strftime("%Y-%m-%d")
    departure_str = dept.strftime("%Y-%m-%d")

    target_tails = TAIL_NUMBERS if selected_tail == "All Tail Numbers" else [selected_tail]
    results_summary = []
    
    # Status block for live updates during retrieval
    with st.status("Fetching estimate(s) from Signature Aviation API...", expanded=True) as status:
        for idx, tail in enumerate(target_tails, 1):
            status.write(f"⏳ **[{idx}/{len(target_tails)}]** Requesting initial quote for **{tail}**...")
            
            # Fetch initial quote based on user input
            res = fetch_quote(
                tail_num=tail,
                customer_name=customer_name,
                aircraft_model=aircraft_make_model,
                fbo_id=fbo_base_id,
                arrival_str=arrival_str,
                departure_str=departure_str,
                fuel=fuel_gal
            )

            if res["success"]:
                data = res["data"]
                threshold_gal = parse_threshold_gallons(data)
                threshold_display = f"{threshold_gal:,} gal" if threshold_gal is not None else "N/A"
                est_total = data.get("