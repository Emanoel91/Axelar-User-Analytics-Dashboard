import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from io import StringIO
from plotly.subplots import make_subplots
import plotly.graph_objects as go

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
            "New Users": "#58fd86",
            "Returning Users": "#9f58fd",
        },
    )

    fig.add_scatter(
        x=growth_df["Month"],
        y=growth_df["Active Users"],
        mode="lines",
        name="Active Users",
        line=dict(color="black", width=2),
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

# ==========================================================
# Additional KPI Calculation
# ==========================================================

# مرتب‌سازی ماه‌ها
months = sorted(all_data["Month"].unique())

latest_month = months[-1]
previous_month = months[-2]

# کاربران آخرین ماه
latest_users = set(
    all_data.loc[
        all_data["Month"] == latest_month,
        "key"
    ]
)

# کاربران ماه قبل
previous_users = set(
    all_data.loc[
        all_data["Month"] == previous_month,
        "key"
    ]
)

# کاربران قبل از ماه قبل
historical_users = set(
    all_data.loc[
        all_data["Month"] < previous_month,
        "key"
    ]
)

# Reactivated Users
reactivated_users = len(
    (latest_users - previous_users) & historical_users
)

# Churned Users
churned_users = len(
    previous_users - latest_users
)

# Monthly Active Users
mau = len(latest_users)

# User Growth %
previous_mau = len(previous_users)

if previous_mau > 0:
    user_growth = (mau - previous_mau) / previous_mau * 100
else:
    user_growth = 0

# ==========================================================
# KPI Row 2
# ==========================================================

kpi4, kpi5, kpi6, kpi7 = st.columns(4)

with kpi4:
    st.metric(
        label="Reactivated Users",
        value=f"{reactivated_users:,}",
        help=(
            "Users who were active in the latest month, "
            "inactive in the previous month, "
            "but had activity before that."
        )
    )

with kpi5:
    st.metric(
        label="Churned Users",
        value=f"{churned_users:,}",
        help=(
            "Users who were active in the previous month "
            "but were not active in the latest month."
        )
    )

with kpi6:
    st.metric(
        label="User Growth %",
        value=f"{user_growth:.2f}%",
        help=(
            "Percentage change in Monthly Active Users (MAU) "
            "compared with the previous month."
        )
    )

with kpi7:
    st.metric(
        label="Monthly Active Users",
        value=f"{mau:,}",
        help=(
            "Total number of unique users "
            "who were active in the latest month."
        )
    )

# ==========================================================
# User-Level Statistics
# ==========================================================

user_stats = (
    all_data
    .groupby("key", as_index=False)
    .agg(
        Total_Transactions=("num_txs", "sum"),
        Total_Volume=("volume", "sum"),
    )
)

avg_transactions = user_stats["Total_Transactions"].mean()
median_transactions = user_stats["Total_Transactions"].median()

avg_volume = user_stats["Total_Volume"].mean()
median_volume = user_stats["Total_Volume"].median()

# ==========================================================
# KPI Row 3
# ==========================================================

kpi8, kpi9, kpi10, kpi11 = st.columns(4)

with kpi8:
    st.metric(
        label="Average Transactions/User",
        value=f"{avg_transactions:,.2f}",
        help="Average number of transactions performed by each unique user across the entire dataset."
    )

with kpi9:
    st.metric(
        label="Median Transactions/User",
        value=f"{median_transactions:,.0f}",
        help="Median number of transactions per unique user across the entire dataset."
    )

with kpi10:
    st.metric(
        label="Average Volume/User",
        value=f"${avg_volume:,.2f}",
        help="Average transfer volume per unique user across the entire dataset."
    )

with kpi11:
    st.metric(
        label="Median Volume/User",
        value=f"${median_volume:,.2f}",
        help="Median transfer volume per unique user across the entire dataset."
    )

# ==========================================================
# Advanced Distribution Metrics
# ==========================================================

# Total Volume
total_volume = user_stats["Total_Volume"].sum()

# -------------------------------
# Top 100 Users Share
# -------------------------------

top100_volume = (
    user_stats
    .nlargest(100, "Total_Volume")["Total_Volume"]
    .sum()
)

top100_share = (
    top100_volume / total_volume * 100
    if total_volume > 0 else 0
)

# -------------------------------
# Whale Dominance
# Top 1% users by volume
# -------------------------------

n_whales = max(1, int(len(user_stats) * 0.01))

whale_volume = (
    user_stats
    .nlargest(n_whales, "Total_Volume")["Total_Volume"]
    .sum()
)

whale_dominance = (
    whale_volume / total_volume * 100
    if total_volume > 0 else 0
)

# -------------------------------
# Gini Coefficient
# -------------------------------

volumes = (
    user_stats["Total_Volume"]
    .fillna(0)
    .values
)

volumes = volumes[volumes >= 0]

volumes.sort()

n = len(volumes)

if n == 0 or volumes.sum() == 0:

    gini = 0

else:

    index = range(1, n + 1)

    gini = (
        (
            2 * sum(i * x for i, x in zip(index, volumes))
        ) / (n * volumes.sum())
    ) - (n + 1) / n

# -------------------------------
# Herfindahl Index (HHI)
# -------------------------------

shares = volumes / volumes.sum()

hhi = (shares ** 2).sum()

# ==========================================================
# KPI Row 4
# ==========================================================

kpi12, kpi13, kpi14, kpi15 = st.columns(4)

with kpi12:
    st.metric(
        "Top 100 Users Share",
        f"{top100_share:.2f}%",
        help="Percentage of the total transfer volume contributed by the top 100 users."
    )

with kpi13:
    st.metric(
        "Whale Dominance",
        f"{whale_dominance:.2f}%",
        help="Percentage of the total transfer volume contributed by the top 1% highest-volume users."
    )

with kpi14:
    st.metric(
        "Gini Coefficient",
        f"{gini:.3f}",
        help="Measures inequality in transfer volume distribution across users. Values closer to 1 indicate higher concentration."
    )

with kpi15:
    st.metric(
        "Herfindahl Index",
        f"{hhi:.4f}",
        help="Measures concentration of transfer volume among users. Higher values indicate greater concentration."
    )

# ==========================================================
# User Growth Metrics
# ==========================================================

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

    # Churned Users
    if i == 0:
        churned_users = 0
    else:
        previous_users = monthly_users[months[i-1]]
        churned_users = len(previous_users - current_users)

    # Net User Growth
    net_growth = new_users - churned_users

    # User Growth Rate
    if i == 0:
        growth_rate = 0
    else:
        previous_active = len(monthly_users[months[i-1]])
        growth_rate = (
            (active_users - previous_active)
            / previous_active * 100
            if previous_active > 0 else 0
        )

    seen_users.update(current_users)

    growth_rows.append(
        {
            "Month": month,
            "Active Users": active_users,
            "New Users": new_users,
            "Returning Users": returning_users,
            "Churned Users": churned_users,
            "Net User Growth": net_growth,
            "User Growth Rate": growth_rate,
        }
    )

growth_metrics_df = pd.DataFrame(growth_rows)

growth_metrics_df["Month"] = (
    growth_metrics_df["Month"]
    .dt.strftime("%Y-%m")
)

# ==========================================================
# Growth Charts
# ==========================================================

col1, col2 = st.columns(2)

# ==========================================================
# User Growth Metrics
# ==========================================================

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

    # Churned Users
    if i == 0:
        churned_users = 0
    else:
        previous_users = monthly_users[months[i - 1]]
        churned_users = len(previous_users - current_users)

    # Net User Growth
    net_growth = new_users - churned_users

    # User Growth Rate
    if i == 0:
        growth_rate = None
    else:
        previous_active = len(monthly_users[months[i - 1]])

        growth_rate = (
            (active_users - previous_active)
            / previous_active
            * 100
            if previous_active > 0 else None
        )

    seen_users.update(current_users)

    growth_rows.append(
        {
            "Month": month,
            "Active Users": active_users,
            "New Users": new_users,
            "Returning Users": returning_users,
            "Churned Users": churned_users,
            "Net User Growth": net_growth,
            "User Growth Rate": growth_rate,
        }
    )

growth_metrics_df = pd.DataFrame(growth_rows)

growth_metrics_df["Month"] = pd.to_datetime(
    growth_metrics_df["Month"]
)

# فقط از فوریه 2022 به بعد
growth_rate_df = growth_metrics_df[
    growth_metrics_df["Month"] >= "2022-02-01"
].copy()

growth_rate_df["Month"] = (
    growth_rate_df["Month"]
    .dt.strftime("%Y-%m")
)

growth_metrics_df["Month"] = (
    growth_metrics_df["Month"]
    .dt.strftime("%Y-%m")
)

# ==========================================================
# Growth Charts
# ==========================================================

col1, col2 = st.columns(2)

# ----------------------------------------------------------
# Monthly User Growth Rate
# ----------------------------------------------------------

with col1:

    growth_rate_df["Color"] = growth_rate_df[
        "User Growth Rate"
    ].apply(
        lambda x: "#16a34a" if x >= 0 else "#dc2626"
    )

    fig = px.bar(
        growth_rate_df,
        x="Month",
        y="User Growth Rate",
        text="User Growth Rate",
    )

    fig.update_traces(
        marker_color=growth_rate_df["Color"],
        texttemplate="%{y:.1f}%",
        textposition="outside",
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Growth Rate: %{y:.2f}%<extra></extra>"
        ),
    )

    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="gray",
    )

    fig.update_layout(
        title="Monthly User Growth Rate",
        xaxis_title="Month",
        yaxis_title="Growth Rate (%)",
        hovermode="x unified",
        height=500,
        showlegend=False,
    )

    st.plotly_chart(
        fig,
        width="stretch",
    )

# ----------------------------------------------------------
# Net User Growth
# ----------------------------------------------------------

with col2:

    growth_metrics_df["Color"] = growth_metrics_df[
        "Net User Growth"
    ].apply(
        lambda x: "#16a34a" if x >= 0 else "#dc2626"
    )

    fig2 = px.bar(
        growth_metrics_df,
        x="Month",
        y="Net User Growth",
        text="Net User Growth",
    )

    fig2.update_traces(
        marker_color=growth_metrics_df["Color"],
        textposition="outside",
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Net Growth: %{y:,}<extra></extra>"
        ),
    )

    fig2.add_hline(
        y=0,
        line_dash="dash",
        line_color="gray",
    )

    fig2.update_layout(
        title=(
            "Net User Growth"
            "<br><sup>"
            "Net User Growth = New Users − Churned Users "
            "(Churned Users are users who were active in the previous month "
            "but not in the current month.)"
            "</sup>"
        ),
        xaxis_title="Month",
        yaxis_title="Users",
        hovermode="x unified",
        height=500,
        showlegend=False,
    )

    st.plotly_chart(
        fig2,
        width="stretch",
    )

# ==========================================================
# Monthly User Statistics
# ==========================================================

# هر کاربر در هر ماه فقط یک بار در نظر گرفته شود
monthly_user_stats = (
    all_data
    .groupby(["Month", "key"], as_index=False)
    .agg(
        Volume=("volume", "sum"),
        Transactions=("num_txs", "sum"),
    )
)

monthly_metrics = (
    monthly_user_stats
    .groupby("Month", as_index=False)
    .agg(
        Avg_Volume=("Volume", "mean"),
        Median_Volume=("Volume", "median"),
        Avg_Tx=("Transactions", "mean"),
        Median_Tx=("Transactions", "median"),
    )
)

monthly_metrics["Month"] = (
    pd.to_datetime(monthly_metrics["Month"])
    .dt.strftime("%Y-%m")
)

# ==========================================================
# Monthly User Statistics Charts
# ==========================================================

col1, col2 = st.columns(2)

# ----------------------------------------------------------
# Monthly Average & Median Volume per User
# ----------------------------------------------------------

with col1:

    fig = make_subplots(
        specs=[[{"secondary_y": True}]]
    )

    # Average Volume
    fig.add_trace(
        go.Scatter(
            x=monthly_metrics["Month"],
            y=monthly_metrics["Avg_Volume"],
            mode="lines+markers",
            name="Average",
            line=dict(
                color="#00a1f7",
                width=3,
            ),
        ),
        secondary_y=False,
    )

    # Median Volume
    fig.add_trace(
        go.Scatter(
            x=monthly_metrics["Month"],
            y=monthly_metrics["Median_Volume"],
            mode="lines+markers",
            name="Median",
            line=dict(
                color="#ff7400",
                width=3,
            ),
        ),
        secondary_y=True,
    )

    fig.update_layout(

        title="Monthly Average & Median Volume per User",

        hovermode="x unified",

        height=500,

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
        ),
    )

    fig.update_xaxes(
        title_text="Month"
    )

    fig.update_yaxes(
        title_text="Average Volume",
        secondary_y=False,
    )

    fig.update_yaxes(
        title_text="Median Volume",
        secondary_y=True,
    )

    st.plotly_chart(
        fig,
        width="stretch",
    )

# ----------------------------------------------------------
# Monthly Average & Median Transactions per User
# ----------------------------------------------------------

with col2:

    fig2 = make_subplots(
        specs=[[{"secondary_y": True}]]
    )

    # Average Tx
    fig2.add_trace(
        go.Scatter(
            x=monthly_metrics["Month"],
            y=monthly_metrics["Avg_Tx"],
            mode="lines+markers",
            name="Average",
            line=dict(
                color="#00a1f7",
                width=3,
            ),
        ),
        secondary_y=False,
    )

    # Median Tx
    fig2.add_trace(
        go.Scatter(
            x=monthly_metrics["Month"],
            y=monthly_metrics["Median_Tx"],
            mode="lines+markers",
            name="Median",
            line=dict(
                color="#ff7400",
                width=3,
            ),
        ),
        secondary_y=True,
    )

    fig2.update_layout(

        title="Monthly Average & Median Transactions per User",

        hovermode="x unified",

        height=500,

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
        ),
    )

    fig2.update_xaxes(
        title_text="Month"
    )

    fig2.update_yaxes(
        title_text="Average Transactions",
        secondary_y=False,
    )

    fig2.update_yaxes(
        title_text="Median Transactions",
        secondary_y=True,
    )

    st.plotly_chart(
        fig2,
        width="stretch",
    )

# ==========================================================
# Reactivated Users / Churn / Resurrection Rate
# ==========================================================

monthly_users = (
    all_data.groupby("Month")["key"]
    .apply(set)
    .sort_index()
)

months = list(monthly_users.index)

history = set()

lifecycle_rows = []

for i, month in enumerate(months):

    current = monthly_users[month]

    # Previous month
    previous = monthly_users[months[i-1]] if i > 0 else set()

    # Users active before previous month
    active_before_previous = history - previous

    # Reactivated
    reactivated = current & active_before_previous

    # Churned
    churned = previous - current if i > 0 else set()

    # Resurrection Rate
    inactive_last_month = history - previous

    resurrection_rate = (
        len(reactivated) / len(inactive_last_month) * 100
        if len(inactive_last_month) > 0
        else 0
    )

    lifecycle_rows.append(
        {
            "Month": month,
            "Reactivated Users": len(reactivated),
            "Churned Users": len(churned),
            "Resurrection Rate": resurrection_rate,
        }
    )

    history.update(current)

lifecycle_df = pd.DataFrame(lifecycle_rows)

lifecycle_df["Month"] = (
    pd.to_datetime(lifecycle_df["Month"])
    .dt.strftime("%Y-%m")
)

# ==========================================================
# User Lifecycle Charts
# ==========================================================

col1, col2, col3 = st.columns(3)

# ----------------------------------------------------------
# Monthly Reactivated Users
# ----------------------------------------------------------

with col1:

    fig = px.bar(
        lifecycle_df,
        x="Month",
        y="Reactivated Users",
        text="Reactivated Users",
    )

    fig.update_traces(
        marker_color="#16a34a",
        textposition="outside",
    )

    fig.update_layout(
        title=(
            "Monthly Reactivated Users"
            "<br><sup>"
            "Users who became active again after being inactive "
            "during the previous month."
            "</sup>"
        ),
        xaxis_title="Month",
        yaxis_title="Users",
        hovermode="x unified",
        height=500,
    )

    st.plotly_chart(
        fig,
        width="stretch",
    )

# ----------------------------------------------------------
# Monthly Churned Users
# ----------------------------------------------------------

with col2:

    fig2 = px.bar(
        lifecycle_df,
        x="Month",
        y="Churned Users",
        text="Churned Users",
    )

    fig2.update_traces(
        marker_color="#dc2626",
        textposition="outside",
    )

    fig2.update_layout(
        title=(
            "Monthly Churned Users"
            "<br><sup>"
            "Users who were active in the previous month "
            "but not in the current month."
            "</sup>"
        ),
        xaxis_title="Month",
        yaxis_title="Users",
        hovermode="x unified",
        height=500,
    )

    st.plotly_chart(
        fig2,
        width="stretch",
    )

# ----------------------------------------------------------
# Resurrection Rate
# ----------------------------------------------------------

with col3:

    fig3 = px.line(
        lifecycle_df,
        x="Month",
        y="Resurrection Rate",
        markers=True,
    )

    fig3.update_traces(
        line=dict(width=3, color="#00a1f7"),
    )

    fig3.update_layout(
        title=(
            "Monthly Resurrection Rate"
            "<br><sup>"
            "Percentage of previously inactive users "
            "who became active again during the month."
            "</sup>"
        ),
        xaxis_title="Month",
        yaxis_title="Rate (%)",
        hovermode="x unified",
        height=500,
    )

    st.plotly_chart(
        fig3,
        width="stretch",
    )
