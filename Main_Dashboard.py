import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from io import StringIO

st.set_page_config(
    page_title="Axelar User Analytics",
    layout="wide"
)

st.title("📊 Axelar User Analytics Dashboard")

# -----------------------------
# GitHub Configuration
# -----------------------------

OWNER = "Emanoel91"
REPO = "Axelar-User-Analytics-Dashboard"
BRANCH = "main"
FOLDER = "User_Data_History"

# -----------------------------
# Load Data
# -----------------------------

@st.cache_data(ttl=3600)
def load_data():

    api_url = (
        f"https://api.github.com/repos/"
        f"{OWNER}/{REPO}/contents/{FOLDER}?ref={BRANCH}"
    )

    response = requests.get(api_url, timeout=30)
    response.raise_for_status()

    files = response.json()

    monthly_rows = []

    gmp_users = set()
    tt_users = set()

    for item in files:

        if item["type"] != "file":
            continue

        filename = item["name"]

        if not filename.endswith(".csv"):
            continue

        if not (
            filename.startswith("gmp-")
            or filename.startswith("tt-")
        ):
            continue

        service = "GMP" if filename.startswith("gmp-") else "Token Transfer"

        period = filename.replace(".csv", "")

        if service == "GMP":
            period = period.replace("gmp-", "")
        else:
            period = period.replace("tt-", "")

        try:

            csv_url = item["download_url"]

            csv_response = requests.get(csv_url, timeout=60)

            if csv_response.status_code != 200:
                continue

            df = pd.read_csv(StringIO(csv_response.text))

            if df.empty:
                continue

            if "key" not in df.columns:
                continue

        except Exception:
            continue

        users = set(df["key"].dropna())

        monthly_rows.append(
            {
                "Month": period,
                "Service": service,
                "Users": len(users),
            }
        )

        if service == "GMP":
            gmp_users.update(users)
        else:
            tt_users.update(users)

    monthly_df = pd.DataFrame(monthly_rows)

    monthly_df = monthly_df.sort_values("Month")

    donut_df = pd.DataFrame(
        {
            "Service": ["GMP", "Token Transfer"],
            "Users": [
                len(gmp_users),
                len(tt_users),
            ],
        }
    )

    return monthly_df, donut_df

# -----------------------------
# Load
# -----------------------------

monthly_df, donut_df = load_data()

# -----------------------------
# Charts
# -----------------------------

col1, col2 = st.columns([3,1])

with col1:

    fig = px.bar(
        monthly_df,
        x="Month",
        y="Users",
        color="Service",
        barmode="stack",
        text="Users",
        color_discrete_map={
            "GMP": "#ff7400",
            "Token Transfer": "#00a1f7"
        }
    )

    fig.update_traces(textposition="inside")

    fig.update_layout(
        title="Monthly Active Users",
        xaxis_title="Month",
        yaxis_title="Users",
        legend_title="Service",
        hovermode="x unified",
        height=500
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

with col2:

    fig2 = px.pie(
        donut_df,
        names="Service",
        values="Users",
        hole=0.65,
        color="Service",
        color_discrete_map={
            "GMP": "#ff7400",
            "Token Transfer": "#00a1f7"
        }
    )

    fig2.update_traces(
        textposition="inside",
        textinfo="percent+value"
    )

    fig2.update_layout(
        title="Unique Users",
        height=500
    )

    st.plotly_chart(
        fig2,
        use_container_width=True
    )
