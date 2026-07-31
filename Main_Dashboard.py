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

# ==========================================================
# User Growth Data
# ==========================================================

# هر کاربر فقط یک بار در هر ماه شمرده شود
monthly_users = (
    all_data.groupby("Month")["key"]
    .apply(set)
    .sort_index()
)

months = list(monthly_users.index)

growth_rows = []

seen_users = set()

for i, month in enumerate(months):

    current_users = monthly_users[month]

    # Active Users
    active_users = len(current_users)

    # New Users
    new_users = len(current_users - seen_users)

    # Returning Users
    returning_users = len(current_users & seen_users)

    # بروزرسانی کاربران دیده شده
    seen_users.update(current_users)

    # Cumulative Users
    cumulative_users = len(seen_users)

    growth_rows.append(
        {
            "Month": month,
            "New Users": new_users,
            "Returning Users": returning_users,
            "Active Users": active_users,
            "Cumulative Users": cumulative_users,
        }
    )

growth_df = pd.DataFrame(growth_rows)

growth_df["Month"] = growth_df["Month"].dt.strftime("%Y-%m")

# ==========================================================
# User Growth Charts
# ==========================================================

col1, col2 = st.columns(2)

# ----------------------------------------------------------
# Active / New / Returning Users
# ----------------------------------------------------------

with col1:

    fig = px.bar(
        growth_df,
        x="Month",
        y=["New Users", "Returning Users"],
        barmode="stack",
        color_discrete_map={
            "New Users": "#00a1f7",
            "Returning Users": "#ff7400",
        },
    )

    fig.add_scatter(
        x=growth_df["Month"],
        y=growth_df["Active Users"],
        mode="lines+markers",
        name="Active Users",
        line=dict(color="black", width=3),
    )

    fig.update_layout(
        title="Monthly Active Users",
        xaxis_title="Month",
        yaxis_title="Users",
        hovermode="x unified",
        legend_title="",
        height=500,
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

# ----------------------------------------------------------
# Cumulative Users
# ----------------------------------------------------------

with col2:

    fig2 = px.area(
        growth_df,
        x="Month",
        y="Cumulative Users",
    )

    fig2.update_traces(
        line=dict(width=3)
    )

    fig2.update_layout(
        title="Cumulative Unique Users",
        xaxis_title="Month",
        yaxis_title="Users",
        hovermode="x unified",
        height=500,
    )

    st.plotly_chart(
        fig2,
        use_container_width=True,
    )
