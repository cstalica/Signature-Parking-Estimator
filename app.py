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
    # Dropdown with "All Tail Numbers" option
    tail_options = ["All Tail Numbers"] + TAIL_NUMBERS
    selected_tail = st.selectbox("Tail Number", options=tail_options, index=0)
    
    aircraft_make_model = st.text_input(
        "Aircraft Make & Model", value="Bombardier Learjet - 75"
    )
    
    fbo_base_id = st.selectbox(
        "FBO Base Code / Airport",
        options=FBO_CODES,
        index=FBO_CODES.index("CHO")  # KCHO
    )
    
    duration_days = st.number_input(
        "Duration of Stay (Days)", min_value=1, max_value=30, value=2, step=1
    )
    
    # Fuel Purchased Input
    fuel_gal = st.number_input(
        "Fuel Purchased (Gallons)", min_value=0, value=0, step=10
    )

    submitted = st.form_submit_button("Calculate Estimate")


def fetch_quote(tail_num, aircraft_model, fbo_id, arrival_str, departure_str, fuel):
    """Helper function to execute the tRPC API request for a single tail number."""
    payload = {
        "0": {
            "json": {
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
            
    except Exception as e