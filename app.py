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

    waived_gal = data.get("waivedFuelGallons") or data.get("fuelMinimum")
    if waived_gal is not None:
        return int(waived_gal)

    return None


def extract_length_of_stay_discount(data):
    """Parses length of stay discount from all potential locations in the JSON response."""
    if not isinstance(data, dict):
        return 0.0

    def find_discount_in_list(items):
        if not isinstance(items, list):
            return 0.0
        for item in items:
            if isinstance(item, dict):
                label = str(
                    item.get("label") or item.get("description") or item.get("name") or ""
                ).lower()
                # Clean up bullet characters or dots from label (e.g., "• length of stay discount")
                clean_label = re.sub(r"[^\w\s]", "", label)
                if "length" in clean_label or "stay" in clean_label:
                    amt = item.get("amount") or item.get("value") or item.get("discount") or 0.0
                    if amt:
                        return abs(float(amt))
        return 0.0

    # 1. Search in primary top-level arrays
    for key in ["discounts", "lineItems", "charges", "items", "breakdown"]:
        if key in data:
            found = find_discount_in_list(data[key])
            if found > 0:
                return found

    # 2. Search inside nested pricing objects (e.g. priceSummary)
    for nested_key in ["priceSummary", "pricingSummary", "summary"]:
        if nested_key in data and isinstance(data[nested_key], dict):
            nested_obj = data[nested_key]
            for key in ["discounts", "lineItems", "charges"]:
                found = find_discount_in_list(nested_obj.get(key, []))
                if found > 0:
                    return found
            # Check direct key inside nested summary
            if "lengthOfStayDiscount" in nested_obj:
                return abs(float(nested_obj["lengthOfStayDiscount"]))

    # 3. Direct top-level fields
    if "lengthOfStayDiscount" in data and data["lengthOfStayDiscount"]:
        return abs(float(data["lengthOfStayDiscount"]))

    # 4. Direct 'discount' field if it is explicitly labeled or standalone
    if "discount" in data and isinstance(data["discount"], (int, float)) and data["discount"] < 0:
        if data.get("fuelGallons", 0) == 0:
            return abs(float(data["discount"]))

    return 0.0


def extract_discount_amount(data):
    """Extracts fuel uplift discount amount from discounts list or residual price difference."""
    if not data:
        return 0.0

    # 1. Check discounts / lineItems array in payload for fuel uplift specifically
    discounts = data.get("discounts", []) or data.get("lineItems", [])
    total_disc = 0.0
    for item in discounts:
        if isinstance(item, dict):
            label = str(item.get("label", "") or item.get("description", "")).lower()
            clean_label = re.sub(r"[^\w\s]", "", label)
            amt = item.get("amount", 0)
            if amt < 0 and "length" not in clean_label and "stay" not in clean_label:
                total_disc += abs(amt)

    if total_disc > 0:
        return total_disc

    # 2. Fallback: Difference between initial rate and estimated total (minus length of stay discount)
    initial = float(data.get("initialRate", 0.0))
    total = float(data.get("estimatedTotal", 0.0))
    tax = float(data.get("tax", 0.0))
    los_disc = extract_length_of_stay_discount(data)
    
    if initial > 0 and (initial + tax - los_disc) > total:
        return (initial + tax - los_disc) - total

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
                est_total = data.get("estimatedTotal", 0.0)
                
                # Extract Length of Stay Discount from initial response
                los_discount_val = extract_length_of_stay_discount(data)
                
                # Fetch threshold quote to obtain the discounted rate & discount value
                est_total_at_threshold_str = "N/A"
                discount_amount_val = 0.0
                
                if threshold_gal is not None:
                    if fuel_gal >= threshold_gal:
                        est_total_at_threshold_str = f"${est_total:,.2f}"
                        discount_amount_val = extract_discount_amount(data)
                    else:
                        status.write(f"   ↳ Requesting threshold quote ({threshold_gal} gal) for **{tail}**...")
                        thresh_res = fetch_quote(
                            tail_num=tail,
                            customer_name=customer_name,
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
                            
                            # Extract length of stay discount if present in threshold response
                            if los_discount_val == 0.0:
                                los_discount_val = extract_length_of_stay_discount(thresh_data)

                            # Extract discount from the threshold response or calculate savings
                            discount_amount_val = extract_discount_amount(thresh_data)
                            if discount_amount_val == 0.0:
                                discount_amount_val = max(0.0, est_total - thresh_total)

                status.write(f"✅ **{tail}** — Quote retrieved successfully!")
                
                results_summary.append({
                    "Status": "🟢 Success",
                    "Tail Number": tail,
                    "Min Fuel for Discount": threshold_display,
                    "Fuel Purchased (gal)": f"{fuel_gal:,} gal",
                    "Current Estimated Total": f"${est_total:,.2f}",
                    "Length of Stay Discount": f"-${los_discount_val:,.2f}" if los_discount_val > 0 else "$0.00",
                    "Fuel Uplift Discount": f"-${discount_amount_val:,.2f}" if discount_amount_val > 0 else "$0.00",
                    "Est. Total if min fuel purchased": est_total_at_threshold_str,
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
                    "Current Estimated Total": "N/A",
                    "Length of Stay Discount": "N/A",
                    "Fuel Uplift Discount": "N/A",
                    "Est. Total if min fuel purchased": "N/A",
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
                "Current Estimated Total",
                "Length of Stay Discount",
                "Fuel Uplift Discount",
                "Est. Total if min fuel purchased"
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
                    c1, c2, c3, c4, c5, c6 = st.columns(6)
                    c1.metric("Min Fuel for Discount", item["Min Fuel for Discount"])
                    c2.metric("Fuel Purchased", item["Fuel Purchased (gal)"])
                    c3.metric("Current Total", item["Current Estimated Total"])
                    c4.metric("Length of Stay Discount", item["Length of Stay Discount"])
                    c5.metric("Fuel Uplift Discount", item["Fuel Uplift Discount"])
                    c6.metric("Est. Total if min fuel purchased", item["Est. Total if min fuel purchased"])
                
                st.write("**Raw Payload/Response:**")
                st.json(item["raw"])