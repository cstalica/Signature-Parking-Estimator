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
    customer_name = st.text_input("Customer Name", value="Koch Industries Inc.")
    tail_number = st.text_input("Tail Number", value="N730K")
    aircraft_make_model = st.text_input(
        "Aircraft Make & Model", value="Bombardier Learjet - 75"
    )
    fbo_base_id = st.text_input(
        "FBO Base Code / ID", value="KICT", help="ICAO Code (e.g., KICT, KAPA)"
    )
    duration_days = st.number_input(
        "Duration of Stay (Days)", min_value=1, max_value=30, value=1, step=1
    )
    fuel_gal = st.number_input(
        "Fuel Purchased (Gallons)", min_value=0, value=0, step=10
    )

    submitted = st.form_submit_button("Calculate Estimate")

if submitted:
    # Format dates to YYYY-MM-DD as required by the backend regex schema
    now = datetime.utcnow()
    dept = now + timedelta(days=duration_days)

    arrival_str = now.strftime("%Y-%m-%d")
    departure_str = dept.strftime("%Y-%m-%d")

    # Payload matching the exact backend Zod validation schema
    payload = {
        "0": {
            "json": {
                "customerName": customer_name,
                "tailNumber": tail_number,
                "aircraftMakeModel": aircraft_make_model,
                "fboBaseId": fbo_base_id,
                "arrivalDate": arrival_str,
                "departureDate": departure_str,
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
            "url?id=7"
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

                # Handle tRPC Error Object
                if "error" in res_data[0]:
                    st.error("API returned a validation error:")
                    st.json(res_data[0]["error"])

                # Safe extraction of results
                else:
                    data = (
                        res_data[0]
                        .get("result", {})
                        .get("data", {})
                        .get("json", {})
                    )

                    if data:
                        st.success("Quote retrieved successfully!")

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