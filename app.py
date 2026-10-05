from datetime import datetime, timedelta
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="Aircraft Parking Fee Estimator", page_icon="✈️", layout="centered"
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
    
    # Fuel Minimum input above Fuel Purchased
    fuel_min = st.number_input(
        "Fuel Minimum (Gallons)", min_value=0, value=0, step=10,
        help="Minimum required fuel uplift to qualify for waived fees or discounts"
    )
    
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

    response = requests.post(api_url, json=payload, headers=headers, timeout=10)
    
    if response.status_code == 200:
        res_data = response.json()
        if "error" in res_data[0]:
            return {"error": res_data[0]["error"]}
        data = res_data[0].get("result", {}).get("data", {}).get("json", {})
        return {"data": data}
    else:
        return {"error": f"HTTP {response.status_code}: {response.text}"}


if submitted:
    # Format dates to YYYY-MM-DD
    now = datetime.utcnow()
    dept = now + timedelta(days=duration_days)
    arrival_str = now.strftime("%Y-%m-%d")
    departure_str = dept.strftime("%Y-%m-%d")

    # Determine list of tail numbers to query
    target_tails = TAIL_NUMBERS if selected_tail == "All Tail Numbers" else [selected_tail]

    results_summary = []
    
    with st.spinner("Fetching estimate(s) from API..."):
        for tail in target_tails:
            res = fetch_quote(
                tail_num=tail,
                customer_name=customer_name,
                aircraft_model=aircraft_make_model,
                fbo_id=fbo_base_id,
                arrival_str=arrival_str,
                departure_str=departure_str,
                fuel=fuel_gal
            )

            if "error" in res:
                st.error(f"Error fetching quote for {tail}:")
                st.json(res["error"])
            else:
                data = res["data"]
                
                # Retrieve fuel minimum from API response if present, otherwise fallback to form input
                api_fuel_min = data.get("fuelMinimum", data.get("minimumFuelGallons", fuel_min))
                
                results_summary.append({
                    "Tail Number": tail,
                    "Fuel Minimum (gal)": f"{api_fuel_min:,} gal",
                    "Fuel Purchased (gal)": f"{fuel_gal:,} gal",
                    "Initial Rate": f"${data.get('initialRate', 0):,.2f}",
                    "Total Tax": f"${data.get('tax', 0):,.2f}",
                    "Estimated Total": f"${data.get('estimatedTotal', 0):,.2f}",
                    "raw": data
                })

    # Render results
    if results_summary:
        st.success("Quote(s) retrieved successfully!")

        # Display comparison table
        if len(results_summary) > 1:
            st.subheader("Summary Table")
            df = pd.DataFrame(results_summary)[
                ["Tail Number", "Fuel Minimum (gal)", "Fuel Purchased (gal)", "Initial Rate", "Total Tax", "Estimated Total"]
            ]
            st.table(df)

        st.subheader("Detailed Breakdown")
        for item in results_summary:
            data = item["raw"]
            with st.expander(f"Quote Details: {item['Tail Number']}", expanded=(len(results_summary) == 1)):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Fuel Minimum", item["Fuel Minimum (gal)"])
                c2.metric("Initial Rate", item["Initial Rate"])
                c3.metric("Total Tax", item["Total Tax"])
                c4.metric("Estimated Total", item["Estimated Total"])
                
                st.json(data)