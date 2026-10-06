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


def fetch_quote(customer_name, tail_num, aircraft_model, fbo_id, arrival_str, departure_str, fuel):
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

    waived_gal = data.get("waivedFuelGallons") or data.get("fuelMinimum")
    if waived_gal is not None:
        return int(waived_gal)

    return None


def extract_all_discounts(data):
    """
    Parses the response object to find Total Discount, Fuel Uplift Discount, 
    and Length of Stay Discount.
    """
    discounts_breakdown = {
        "total_discount": 0.0,
        "fuel_uplift_discount": 0.0,
        "length_of_stay_discount": 0.0
    }

    if not isinstance(data, dict):
        return discounts_breakdown

    discount_items = []
    
    def collect_items(obj):
        if isinstance(obj, dict):
            if "label" in obj or "description" in obj:
                discount_items.append(obj)
            for v in obj.values():
                collect_items(v)
        elif isinstance(obj, list):
            for item in obj:
                collect_items(item)

    collect_items(data)

    for item in discount_items:
        label = str(item.get("label") or item.get("description") or "").lower()
        amt_val = item.get("amount") or item.get("value") or item.get("discount")
        
        if amt_val is not None:
            try:
                numeric_val = abs(float(amt_val))
                if numeric_val > 0:
                    if "length" in label and "stay" in label:
                        discounts_breakdown["length_of_stay_discount"] = numeric_val
                    elif "fuel" in label and "uplift" in label:
                        discounts_breakdown["fuel_uplift_discount"] = numeric_val
                    elif label in ["discount", "discount applied", "total discount"]:
                        discounts_breakdown["total_discount"] = numeric_val
            except (ValueError, TypeError):
                pass

    if discounts_breakdown["total_discount"] == 0.0:
        sub_sum = (
            discounts_breakdown["fuel_uplift_discount"] 
            + discounts_breakdown["length_of_stay_discount"]
        )
        if sub_sum > 0:
            discounts_breakdown["total_discount"] = sub_sum
        else:
            direct_disc = data.get("discount") or data.get("totalDiscount")
            if direct_disc:
                try:
                    discounts_breakdown["total_discount"] = abs(float(direct_disc))
                except (ValueError, TypeError):
                    pass

    return discounts_breakdown


if submitted:
    now = datetime.utcnow()
    dept = now + timedelta(days=duration_days)
    arrival_str = now.strftime("%Y-%m-%d")
    departure_str = dept.strftime("%Y-%m-%d")

    # Hardcode customer name for the API call while keeping it hidden from the UI
    customer_name = "Koch"

    target_tails = TAIL_NUMBERS if selected_tail == "All Tail Numbers" else [selected_tail]
    results_summary = []
    
    with st.status("Fetching estimate(s) from Signature Aviation API...", expanded=True) as status:
        for idx, tail in enumerate(target_tails, 1):
            status.write(f"⏳ **[{idx}/{len(target_tails)}]** Requesting initial quote for **{tail}**...")
            
            res = fetch_quote(
                customer_name=customer_name,
                tail_num=tail,
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
                est_total = data.get("estimatedTotal", 0.0)
                
                disc_info = extract_all_discounts(data)
                
                est_total_at_threshold_str = "N/A"
                
                if threshold_gal is not None:
                    if fuel_gal >= threshold_gal:
                        est_total_at_threshold_str = f"${est_total:,.2f}"
                    else:
                        status.write(f"   ↳ Requesting threshold quote ({threshold_gal} gal) for **{tail}**...")
                        thresh_res = fetch_quote(
                            customer_name=customer_name,
                            tail_num=tail,
                            aircraft_model=aircraft_make_model,
                            fbo_id=fbo_base_id,
                            arrival_str=arrival_str,
                            departure_str=departure_str,
                            fuel=threshold_gal
                        )
                        if thresh_res["success"]:
                            thresh_data = thresh_res["data"]
                            thresh_total = thresh_data.get("estimatedTotal", 0.0)
                            est_total_at_threshold_str = f"${thresh_total:,.2f}"
                            
                            thresh_disc_info = extract_all_discounts(thresh_data)
                            for k in disc_info:
                                if disc_info[k] == 0.0 and thresh_disc_info[k] > 0.0:
                                    disc_info[k] = thresh_disc_info[k]

                status.write(f"✅ **{tail}** — Quote retrieved successfully!")
                
                results_summary.append({
                    "Status": "🟢 Success",
                    "Tail Number": tail,
                    "Min Fuel for Discount": threshold_display,
                    "Fuel Purchased (gal)": f"{fuel_gal:,} gal",
                    "Fuel Uplift Discount": f"-${disc_info['fuel_uplift_discount']:,.2f}" if disc_info['fuel_uplift_discount'] > 0 else "$0.00",
                    "Length of Stay Discount": f"-${disc_info['length_of_stay_discount']:,.2f}" if disc_info['length_of_stay_discount'] > 0 else "$0.00",
                    "Total Discount": f"-${disc_info['total_discount']:,.2f}" if disc_info['total_discount'] > 0 else "$0.00",
                    "Est. Total if min fuel purchased": est_total_at_threshold_str,
                    "Estimated Total Charge": f"${est_total:,.2f}",
                    "raw": data,
                    "is_error": False
                })
            else:
                status.write(f"❌ **{tail}** — Request failed: {res.get('error')}")
                results_summary.append({
                    "Status": "🔴 Failed",
                    "Tail Number": tail,
                    "Min Fuel for Discount": "N/A",
                    "Fuel Purchased (gal)": f"{fuel_gal:,} gal",
                    "Fuel Uplift Discount": "N/A",
                    "Length of Stay Discount": "N/A",
                    "Total Discount": "N/A",
                    "Est. Total if min fuel purchased": "N/A",
                    "Estimated Total Charge": "N/A",
                    "raw": res.get("raw") or res.get("error"),
                    "is_error": True,
                    "error_msg": res.get("error")
                })

        status.update(label="Data retrieval complete!", state="complete", expanded=False)

    # Render results
    if results_summary:
        st.subheader("Summary Table")
        df = pd.DataFrame(results_summary)[
            [
                "Status",
                "Tail Number",
                "Min Fuel for Discount",
                "Fuel Purchased (gal)",
                "Fuel Uplift Discount",
                "Length of Stay Discount",
                "Total Discount",
                "Est. Total if min fuel purchased",
                "Estimated Total Charge"
            ]
        ]
        st.table(df)

        st.subheader("Detailed Breakdown")
        for item in results_summary:
            status_text = "ERROR" if item["is_error"] else "SUCCESS"
            expander_title = f"{item['Tail Number']} — [{status_text}]"
            
            with st.expander(expander_title, expanded=(len(results_summary) == 1)):
                if item["is_error"]:
                    st.error(f"Data Retrieval Failed: {item.get('error_msg')}")
                else:
                    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
                    c1.metric("Min Fuel for Discount", item["Min Fuel for Discount"])
                    c2.metric("Fuel Purchased", item["Fuel Purchased (gal)"])
                    c3.metric("Fuel Uplift Discount", item["Fuel Uplift Discount"])
                    c4.metric("Length of Stay Discount", item["Length of Stay Discount"])
                    c5.metric("Total Discount", item["Total Discount"])
                    c6.metric("Est. Total if min fuel", item["Est. Total if min fuel purchased"])
                    c7.metric("Estimated Total Charge", item["Estimated Total Charge"])
                
                st.write("**Raw Payload/Response:**")
                st.json(item["raw"])