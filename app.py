from datetime import datetime, timedelta
import requests
import streamlit as st

st.set_page_config(
    page_title="Aircraft Parking Fee Estimator", page_icon="✈️", layout="centered"
)

st.title("✈️ Aircraft Parking Fee Estimator")
st.write(
    "Calculate estimated aircraft parking charges using the live Signature Aviation tRPC API."
)

# Inputs
with st.form("parking_estimator_form"):
    company_name = st.text_input("Company Name", value="Koch Industries Inc.")
    tail_number = st.text_input("Tail Number", value="N730K")
    aircraft_model = st.text_input(
        "Aircraft Model", value="Bombardier Learjet - 75"
    )
    fbo_code = st.text_input(
        "FBO Airport Code", value="KICT", help="ICAO Code (e.g., KICT, KAPA)"
    )
    duration_days = st.number_input(
        "Duration of Stay (Days)", min_value=1, max_value=30, value=1, step=1
    )
    fuel_gal = st.number_input(
        "Fuel Purchased (Gallons)", min_value=0, value=0, step=10
    )

    submitted = st.form_submit_button("Calculate Estimate")

if submitted:
    # Generate arrival and departure timestamps
    now = datetime.utcnow()
    dept = now + timedelta(days=duration_days)

    # Payload structured for tRPC batching
    payload = {
        "0": {
            "json": {
                "companyName": company_name,
                "tailNumber": tail_number,
                "aircraftModel": aircraft_model,
                "fboCode": fbo_code,
                "arrivalDate": now.isoformat() + "Z",
                "departureDate": dept.isoformat() + "Z",
                "fuelGallons": fuel_gal,
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
        "Referer": (
            "https://www.signatureaviation.com/simplified-parking#parking-estimator"
        ),
    }

    api_url = "https://new-prod-api.signatureaviation.com/api/trpc/parkingQuote.create?batch=1"

    with st.spinner("Fetching estimate from API..."):
        try:
            response = requests.post(
                api_url, json=payload, headers=headers, timeout=10
            )

            if response.status_code == 200:
                res_data = response.json()

                # Safety Check 1: Check if response array is empty
                if not isinstance(res_data, list) or len(res_data) == 0:
                    st.error("Unexpected response structure from server.")
                    st.json(res_data)

                # Safety Check 2: Handle tRPC Error Object
                elif "error" in res_data[0]:
                    st.error("API returned a validation error:")
                    st.json(res_data[0]["error"])

                # Safety Check 3: Extract data safely using .get() to prevent KeyErrors
                else:
                    data = (
                        res_data[0]
                        .get("result", {})
                        .get("data", {})
                        .get("json", {})
                    )

                    if data:
                        st.success("Quote retrieved successfully!")

                        # Metrics grid
                        col1, col2, col3 = st.columns(3)
                        col1.metric(
                            "Initial Rate",
                            f"${data.get('initialRate', 0):,.2f}",
                        )
                        col2.metric(
                            "Total Tax", f"${data.get('tax', 0):,.2f}"
                        )
                        col3.metric(
                            "Estimated Total",
                            f"${data.get('estimatedTotal', 0):,.2f}",
                        )

                        # Expandable raw output
                        with st.expander("View Full API Response Details"):
                            st.json(data)
                    else:
                        st.warning(
                            "Unable to parse pricing data from response."
                        )
                        st.json(res_data)

            else:
                st.error(
                    f"HTTP Request failed with status code: {response.status_code}"
                )
                st.text(response.text)

        except Exception as e:
            st.error(f"An exception occurred while querying the API: {str(e)}")