import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from io import StringIO

# ==========================================================
# Page Config
# ==========================================================

st.set_page_config(
    page_title="Axelar User Analytics",
    layout="wide"
)

st.title("📊 Axelar User Analytics Dashboard")

# ==========================================================
# GitHub Configuration
# ==========================================================

OWNER = "Emanoel91"
REPO = "Axelar-User-Analytics-Dashboard"
BRANCH = "main"
FOLDER = "User_Data_History"

# ==========================================================
# Load Data
# ==========================================================

@st.cache_data(ttl=3600)
def load_data():

    api_url = (
        f"https://api.github.com/repos/"
        f"{OWNER}/{REPO}/contents/{FOLDER}?ref={BRANCH}"
    )

    response = requests.get(api_url, timeout=30)
    response.raise_for_status()

    files = response.json()

    all_rows = []

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

            csv_response = requests.get(
                item["download_url"],
                timeout=60
            )

            if csv_response.status_code != 200:
                continue

            df = pd.read_csv(StringIO(csv_response.text))

            if df.empty:
                continue

            if "key" not in df.columns:
                continue

        except Exception:
            continue

        df = df.copy()

        df["Month"] = period
        df["Service"] = service

        all_rows.append(df)

        users = set(df["key"].dropna())

        if service == "GMP":
            gmp_users.update(users)
        else:
            tt_users.update(users)

    # ------------------------------------------------------

    all_data = pd.concat(all_rows, ignore_index=True)

    all_data["Month"] = pd.to_datetime(all_data["Month"])

    # ------------------------------------------------------
    # Monthly Active Users
    # ------------------------------------------------------

    monthly_df = (
        all_data
        .groupby(["Month", "Service"])["key"]
        .nunique()
        .reset_index(name="Users")
        .sort_values("Month")
    )

    monthly_df["Month"] = monthly_df["Month"].dt.strftime("%Y-%m")

    # ------------------------------------------------------
    # Donut
    # ------------------------------------------------------

    donut_df = pd.DataFrame(
        {
            "Service": [
                "GMP",
                "Token Transfer"
            ],
            "Users": [
                len(gmp_users),
                len(tt_users)
            ]
        }
    )

    return all_data, monthly_df, donut_df

# ==========================================================
# Load
# ==========================================================

all_data, monthly_df, donut_df = load_data()

# ==========================================================
# KPI Calculation
# ==========================================================

latest_month = all_data["Month"].max()

latest_df = all_data[
    all_data["Month"] == latest_month
]

first_month = (
    all_data
    .groupby("key")["Month"]
    .min()
)

total_unique_users = all_data["key"].nunique()

new_users = (
    first_month == latest_month
).sum()

returning_users = latest_df[
    latest_df["key"].isin(
        first_month[
            first_month < latest_month
        ].index
    )
]["key"].nunique()

# ==========================================================
# KPI Row
# ==========================================================

kpi1, kpi2, kpi3 = st.columns(3)

with kpi1:
    st.metric(
        label="Total Unique Users",
        value=f"{total_unique_users:,}"
    )

with kpi2:
    st.metric(
        label="New Users (30d)",
        value=f"{new_users:,}"
    )

with kpi3:
    st.metric(
        label="Returning Users (30d)",
        value=f"{returning_users:,}",
        help="Users who were active in the latest month and had at least one activity before the latest month."
    )

st.markdown("---")

# ==========================================================
# Charts
# ==========================================================

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
            "GMP":"#ff7400",
            "Token Transfer":"#00a1f7"
        }
    )

    fig.update_layout(
        title="Monthly Active Users",
        height=500,
        hovermode="x unified"
    )

    fig.update_traces(
        textposition="inside"
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
            "GMP":"#ff7400",
            "Token Transfer":"#00a1f7"
        }
    )

    fig2.update_layout(
        title="Unique Users",
        height=500
    )

    fig2.update_traces(
        textinfo="percent+value"
    )

    st.plotly_chart(
        fig2,
        use_container_width=True
    )
