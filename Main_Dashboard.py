import streamlit as st
import pandas as pd
import numpy as np
import requests
from io import StringIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import plotly.express as px

# --- Page Config: Tab Title & Icon -------------------------------------------------------------------------------------
st.set_page_config(
    page_title="Axelar User Analytics",
    page_icon="https://axelarscan.io/logos/logo.png",
    layout="wide"
)

# --- Title with Logo ---------------------------------------------------------------------------------------------------
st.markdown(
    """
    <div style="display: flex; align-items: center; gap: 15px;">
        <img src="https://axelarscan.io/logos/logo.png" alt="axelar Logo" style="width:60px; height:60px;">
        <h1 style="margin: 0;">Axelar User Analytics</h1>
    </div>
    """,
    unsafe_allow_html=True
)

# --- Builder Info ---------------------------------------------------------------------------------------------------------
st.markdown(
    """
    <div style="margin-top: 20px; margin-bottom: 20px; font-size: 16px;">
        <div style="display: flex; align-items: center; gap: 10px;">
            <img src="https://pbs.twimg.com/profile_images/2060406047391559681/sA9zPNKM_400x400.jpg" style="width:25px; height:25px; border-radius: 50%;">
            <span>Built by: <a href="https://x.com/0xeman_raz" target="_blank">Eman Raz</a></span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# ==========================================================
# Plot-size guard
# ==========================================================
# Lorenz / Pareto charts are naturally one-point-per-user. With large user
# counts this can blow past Streamlit's websocket message-size limit
# (MessageSizeError). We cap the number of points actually sent to the
# browser by bucketing, while keeping exact math (Gini, cumulative %, etc.)
# computed on the full, un-bucketed data.
MAX_PLOT_POINTS = 2000


def downsample_curve(x: np.ndarray, y: np.ndarray, max_points: int = MAX_PLOT_POINTS):
    """Evenly subsample a monotonic curve for plotting only (keeps shape)."""
    n = len(x)
    if n <= max_points:
        return x, y
    idx = np.unique(np.linspace(0, n - 1, max_points).astype(int))
    return x[idx], y[idx]


def bucket_pareto(df: pd.DataFrame, value_col: str, max_points: int = MAX_PLOT_POINTS) -> pd.DataFrame:
    """Group a rank-sorted per-user Pareto table into <= max_points buckets.

    Bar height per bucket = sum of value_col within the bucket.
    CumPct per bucket = cumulative % at the bucket's last (highest) rank,
    taken from the already-computed exact cumulative column.
    """
    n = len(df)
    if n <= max_points:
        return df

    bin_size = int(np.ceil(n / max_points))
    bucketed = df.copy()
    bucketed["_bin"] = np.arange(n) // bin_size

    out = bucketed.groupby("_bin", as_index=False).agg(
        Rank=("Rank", "max"),
        **{value_col: (value_col, "sum")},
        CumPct=("CumPct", "last"),
    )
    return out


# ==========================================================
# GitHub Configuration
# ==========================================================

OWNER = "Emanoel91"
REPO = "Axelar-User-Analytics-Dashboard"
BRANCH = "main"
FOLDER = "User_Data_History"


# ==========================================================
# Load Data (parallel downloads, single cached pass)
# ==========================================================

@st.cache_data(ttl=3600, show_spinner="Loading on-chain data...")
def load_data():

    session = requests.Session()

    api_url = (
        f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{FOLDER}?ref={BRANCH}"
    )

    response = session.get(api_url, timeout=30)
    response.raise_for_status()
    files = response.json()

    # Build the list of (url, service, period) targets first, no network yet
    targets = []
    for item in files:
        if item.get("type") != "file":
            continue

        name = item["name"]
        if not name.endswith(".csv"):
            continue

        if name.startswith("gmp-"):
            service, period = "GMP", name[len("gmp-"):-4]
        elif name.startswith("tt-"):
            service, period = "Token Transfer", name[len("tt-"):-4]
        else:
            continue

        targets.append((item["download_url"], service, period))

    def _fetch_one(target):
        url, service, period = target
        try:
            r = session.get(url, timeout=60)
            if r.status_code != 200:
                return None

            df = pd.read_csv(StringIO(r.text))
            if df.empty or "key" not in df.columns:
                return None

            df["Month"] = period
            df["Service"] = service
            return df

        except Exception:
            return None

    # Download all files concurrently instead of one-by-one (main bottleneck)
    all_rows = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(_fetch_one, t) for t in targets]
        for f in as_completed(futures):
            df = f.result()
            if df is not None:
                all_rows.append(df)

    if not all_rows:
        empty = pd.DataFrame()
        return empty, empty, empty

    all_data = pd.concat(all_rows, ignore_index=True)

    all_data["Month"] = pd.to_datetime(all_data["Month"])
    all_data["Service"] = all_data["Service"].astype("category")
    all_data["key"] = all_data["key"].astype("string")

    for col in ("num_txs", "volume"):
        if col in all_data.columns:
            all_data[col] = pd.to_numeric(all_data[col], errors="coerce").fillna(0)

    # ------------------------------------------------------
    # Monthly Active Users (per service)
    # ------------------------------------------------------

    monthly_df = (
        all_data.groupby(["Month", "Service"], observed=True)["key"]
        .nunique()
        .reset_index(name="Users")
        .sort_values("Month")
    )
    monthly_df["Month"] = monthly_df["Month"].dt.strftime("%Y-%m")

    # ------------------------------------------------------
    # Donut (global unique users per service)
    # ------------------------------------------------------

    donut_df = (
        all_data.groupby("Service", observed=True)["key"]
        .nunique()
        .reindex(["GMP", "Token Transfer"])
        .fillna(0)
        .reset_index(name="Users")
    )

    return all_data, monthly_df, donut_df


all_data, monthly_df, donut_df = load_data()

if all_data.empty:
    st.error("No data could be loaded from the repository.")
    st.stop()


# ==========================================================
# All heavy derived tables computed ONCE, in one cached call
# (avoids recomputing on every widget interaction / rerun,
#  and avoids the previous O(n^2) history-rebuild loop)
# ==========================================================

@st.cache_data(show_spinner=False)
def compute_all_metrics(df: pd.DataFrame):

    monthly_users = df.groupby("Month")["key"].apply(set).sort_index()
    months = list(monthly_users.index)

    growth_rows = []
    lifecycle_rows = []

    seen = set()                 # all users seen through current month (growth)
    hist_before_prev = set()     # union of months[0 .. i-2]  (lifecycle)
    prev_users = set()           # monthly_users[months[i-1]]
    prev_active = None

    for i, month in enumerate(months):
        current = monthly_users[month]
        active = len(current)

        # ---- Growth metrics ----
        new = len(current - seen)
        returning = len(current & seen)

        if i == 0:
            churned = 0
            growth_rate = np.nan
        else:
            churned = len(prev_users - current)
            growth_rate = (
                (active - prev_active) / prev_active * 100
                if prev_active else np.nan
            )

        net_growth = new - churned
        seen |= current
        cumulative = len(seen)

        growth_rows.append(
            {
                "Month": month,
                "Active Users": active,
                "New Users": new,
                "Returning Users": returning,
                "Churned Users": churned,
                "Net User Growth": net_growth,
                "User Growth Rate": growth_rate,
                "Cumulative Users": cumulative,
            }
        )

        # ---- Lifecycle metrics (reactivation / resurrection) ----
        if i == 0:
            reactivated = set()
            lc_churned = set()
            resurrection_rate = 0.0
        else:
            reactivated = (current - prev_users) & hist_before_prev
            lc_churned = prev_users - current
            inactive = hist_before_prev - prev_users
            resurrection_rate = (
                len(reactivated) / len(inactive) * 100 if inactive else 0.0
            )

        lifecycle_rows.append(
            {
                "Month": month,
                "Reactivated Users": len(reactivated),
                "Churned Users": len(lc_churned),
                "Resurrection Rate": resurrection_rate,
            }
        )

        # roll state forward
        hist_before_prev = hist_before_prev | prev_users
        prev_users = current
        prev_active = active

    growth_df = pd.DataFrame(growth_rows)
    growth_df["Month"] = pd.to_datetime(growth_df["Month"]).dt.strftime("%Y-%m")

    lifecycle_df = pd.DataFrame(lifecycle_rows)
    lifecycle_df["Month"] = pd.to_datetime(lifecycle_df["Month"]).dt.strftime("%Y-%m")

    # ---- Per-user stats (used by KPIs, Lorenz, Pareto) ----
    user_stats = df.groupby("key", as_index=False, observed=True).agg(
        Total_Transactions=("num_txs", "sum"),
        Total_Volume=("volume", "sum"),
    )

    # ---- Monthly average / median volume & tx per user ----
    monthly_user_stats = df.groupby(["Month", "key"], as_index=False, observed=True).agg(
        Volume=("volume", "sum"),
        Transactions=("num_txs", "sum"),
    )
    monthly_metrics = monthly_user_stats.groupby("Month", as_index=False).agg(
        Avg_Volume=("Volume", "mean"),
        Median_Volume=("Volume", "median"),
        Avg_Tx=("Transactions", "mean"),
        Median_Tx=("Transactions", "median"),
    )
    monthly_metrics["Month"] = pd.to_datetime(monthly_metrics["Month"]).dt.strftime("%Y-%m")

    return growth_df, lifecycle_df, user_stats, monthly_metrics


growth_df, lifecycle_df, user_stats, monthly_metrics = compute_all_metrics(all_data)


def gini_coefficient(values: np.ndarray) -> float:
    """Vectorized Gini coefficient (values must be >= 0)."""
    v = np.sort(np.asarray(values, dtype=float))
    v = v[v >= 0]
    n = v.size
    if n == 0 or v.sum() == 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return (2 * np.sum(idx * v)) / (n * v.sum()) - (n + 1) / n


# ==========================================================
# KPI Row 1
# ==========================================================

latest_month = all_data["Month"].max()
latest_df = all_data[all_data["Month"] == latest_month]

first_month = all_data.groupby("key")["Month"].min()

total_unique_users = all_data["key"].nunique()
new_users = (first_month == latest_month).sum()

returning_users = latest_df[
    latest_df["key"].isin(first_month[first_month < latest_month].index)
]["key"].nunique()

kpi1, kpi2, kpi3 = st.columns(3)

with kpi1:
    st.metric("Total Unique Users", f"{total_unique_users:,}")

with kpi2:
    st.metric("New Users (30d)", f"{new_users:,}")

with kpi3:
    st.metric(
        "Returning Users (30d)",
        f"{returning_users:,}",
        help="Users who were active in the latest month and had at least one activity before the latest month.",
    )

st.markdown("---")

# ==========================================================
# Charts: Monthly Active Users (stacked) + Donut
# ==========================================================

col1, col2 = st.columns([3, 1])

with col1:
    fig = px.bar(
        monthly_df,
        x="Month",
        y="Users",
        color="Service",
        barmode="stack",
        text="Users",
        color_discrete_map={"GMP": "#ff7400", "Token Transfer": "#00a1f7"},
    )
    fig.update_layout(title="Monthly Active Users", height=500, hovermode="x unified")
    fig.update_traces(textposition="inside")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    fig2 = px.pie(
        donut_df,
        names="Service",
        values="Users",
        hole=0.65,
        color="Service",
        color_discrete_map={"GMP": "#ff7400", "Token Transfer": "#00a1f7"},
    )
    fig2.update_layout(title="Unique Users", height=500)
    fig2.update_traces(textinfo="percent+value")
    st.plotly_chart(fig2, use_container_width=True)

# ==========================================================
# User Growth Charts
# ==========================================================

col1, col2 = st.columns(2)

with col1:
    fig = px.bar(
        growth_df,
        x="Month",
        y=["New Users", "Returning Users"],
        barmode="stack",
        color_discrete_map={"New Users": "#58fd86", "Returning Users": "#9f58fd"},
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
    st.plotly_chart(fig, use_container_width=True)

with col2:
    fig2 = px.area(growth_df, x="Month", y="Cumulative Users")
    fig2.update_traces(line=dict(width=3))
    fig2.update_layout(
        title="Cumulative Unique Users",
        xaxis_title="Month",
        yaxis_title="Users",
        hovermode="x unified",
        height=500,
    )
    st.plotly_chart(fig2, use_container_width=True)

# ==========================================================
# KPI Row 2 (reuse growth_df / lifecycle_df last rows — no recompute)
# ==========================================================

last_growth = growth_df.iloc[-1]
last_lifecycle = lifecycle_df.iloc[-1]

reactivated_users = int(last_lifecycle["Reactivated Users"])
churned_users = int(last_lifecycle["Churned Users"])
user_growth = last_growth["User Growth Rate"]
user_growth = 0.0 if pd.isna(user_growth) else user_growth
mau = int(last_growth["Active Users"])



# ==========================================================
# KPI Row 3 — User-Level Statistics
# ==========================================================

avg_transactions = user_stats["Total_Transactions"].mean()
median_transactions = user_stats["Total_Transactions"].median()
avg_volume = user_stats["Total_Volume"].mean()
median_volume = user_stats["Total_Volume"].median()

kpi8, kpi9, kpi10, kpi11 = st.columns(4)

with kpi8:
    st.metric(
        "Average Transactions/User",
        f"{avg_transactions:,.2f}",
        help="Average number of transactions performed by each unique user across the entire dataset.",
    )

with kpi9:
    st.metric(
        "Median Transactions/User",
        f"{median_transactions:,.0f}",
        help="Median number of transactions per unique user across the entire dataset.",
    )

with kpi10:
    st.metric(
        "Average Volume/User",
        f"${avg_volume:,.2f}",
        help="Average transfer volume per unique user across the entire dataset.",
    )

with kpi11:
    st.metric(
        "Median Volume/User",
        f"${median_volume:,.2f}",
        help="Median transfer volume per unique user across the entire dataset.",
    )
# ==========================================================
# Lorenz Curve
# ==========================================================

st.subheader("📈 Lorenz Curve")
st.caption(
    "The Lorenz Curve visualizes how evenly activity is distributed across users. "
    "The farther the curve deviates from the line of perfect equality, "
    "the more concentrated the network activity becomes."
)

lorenz_metric = st.selectbox("Metric", ["Transactions", "Volume"], key="lorenz_metric_global")

if lorenz_metric == "Volume":
    lorenz_values = user_stats["Total_Volume"].clip(lower=0)
    x_title, y_title, lorenz_color = (
        "Cumulative Share of Users",
        "Cumulative Share of Volume",
        "#c58ce2",
    )
    lorenz_fill = "rgba(197,140,226,0.20)"
else:
    lorenz_values = user_stats["Total_Transactions"].clip(lower=0)
    x_title, y_title, lorenz_color = (
        "Cumulative Share of Users",
        "Cumulative Share of Transactions",
        "#e1fb43",
    )
    lorenz_fill = "rgba(225,251,67,0.20)"

lorenz_values = np.sort(lorenz_values[lorenz_values > 0].to_numpy())
n_lorenz = lorenz_values.size

if n_lorenz == 0:
    st.info("No users with positive activity found.")
else:
    cum_users = np.arange(1, n_lorenz + 1) / n_lorenz
    cum_values = np.cumsum(lorenz_values) / lorenz_values.sum()

    lorenz_x = np.insert(cum_users, 0, 0)
    lorenz_y = np.insert(cum_values, 0, 0)

    # Gini is computed on the FULL, exact data — only the plotted curve is
    # downsampled, so the metric stays accurate even for huge user counts.
    lorenz_gini = gini_coefficient(lorenz_values)

    plot_x, plot_y = downsample_curve(lorenz_x, lorenz_y)

    gap = plot_x - plot_y
    hover_text = [
        f"<b>Users:</b> {x * 100:.2f}%<br><b>Activity:</b> {y * 100:.2f}%"
        f"<br><b>Inequality Gap:</b> {g * 100:.2f}%"
        for x, y, g in zip(plot_x, plot_y, gap)
    ]

    if lorenz_gini < 0.30:
        interpretation = "Low Inequality"
    elif lorenz_gini < 0.60:
        interpretation = "Moderate Inequality"
    elif lorenz_gini < 0.80:
        interpretation = "High Inequality"
    else:
        interpretation = "Extreme Concentration"

    lorenz_fig = go.Figure()

    lorenz_fig.add_trace(
        go.Scatter(
            x=[0, 1],
            y=[0, 1],
            mode="lines",
            line=dict(color="gray", width=2, dash="dash"),
            name="Perfect Equality",
            hoverinfo="skip",
        )
    )

    lorenz_fig.add_trace(
        go.Scatter(
            x=np.concatenate([plot_x, plot_x[::-1]]),
            y=np.concatenate([plot_x, plot_y[::-1]]),
            fill="toself",
            fillcolor=lorenz_fill,
            line=dict(color="rgba(0,0,0,0)"),
            hoverinfo="skip",
            name="Inequality Area",
        )
    )

    lorenz_fig.add_trace(
        go.Scatter(
            x=plot_x,
            y=plot_y,
            mode="lines",
            line=dict(color=lorenz_color, width=4),
            customdata=hover_text,
            hovertemplate="%{customdata}<extra></extra>",
            name="Lorenz Curve",
        )
    )

    lorenz_fig.add_annotation(
        x=0.65,
        y=0.18,
        showarrow=False,
        align="left",
        bgcolor="rgba(255,255,255,0.92)",
        bordercolor=lorenz_color,
        borderwidth=1,
        text=f"<b>Gini Coefficient</b><br>{lorenz_gini:.3f}<br><br><b>{interpretation}</b>",
    )

    lorenz_fig.add_annotation(
        x=0.90, y=0.96, text="<b>Perfect Equality</b>", showarrow=False,
        font=dict(color="gray", size=12),
    )

    lorenz_fig.add_annotation(
        x=0.42, y=0.25, text="<b>Current Distribution</b>", showarrow=False,
        font=dict(color=lorenz_color, size=12),
    )

    lorenz_fig.update_layout(
        template="plotly_white",
        height=600,
        title=f"Lorenz Curve ({lorenz_metric}) — Gini = {lorenz_gini:.3f}",
        margin=dict(l=20, r=20, t=70, b=20),
        hovermode="closest",
        legend=dict(orientation="h", y=1.03, x=0),
        xaxis=dict(
            title=x_title, tickformat=".0%", range=[0, 1],
            showgrid=True, gridcolor="rgba(0,0,0,0.08)", zeroline=False,
        ),
        yaxis=dict(
            title=y_title, tickformat=".0%", range=[0, 1],
            showgrid=True, gridcolor="rgba(0,0,0,0.08)", zeroline=False,
        ),
    )

    st.plotly_chart(lorenz_fig, use_container_width=True, key="user_lorenz_curve")
    if len(plot_x) < len(lorenz_x):
        st.caption(
            f"Curve rendered from {len(plot_x):,} sampled points out of {len(lorenz_x):,} "
            "users to keep the chart lightweight. The Gini coefficient above is computed "
            "on the full, unsampled data."
        )

# ==========================================================
# User Activity Pareto Analysis
# ==========================================================

st.subheader("📊 User Activity Pareto Analysis")
st.caption(
    "Shows how Axelar's total user activity is distributed across wallets. "
    "Users are ranked from highest to lowest activity, while the cumulative "
    "line shows the percentage of total activity contributed by the top-ranked users."
)

pareto_metric = st.selectbox("Metric", ["Transactions", "Volume"], key="pareto_metric_global")

if pareto_metric == "Volume":
    value_col = "Total_Volume"
    color_bar, color_line = "#c58ce2", "#e1fb43"
    value_title = "Volume ($)"
    value_format = "$%{y:,.2f}"
    hover_value_label = "Volume"
else:
    value_col = "Total_Transactions"
    color_bar, color_line = "#e1fb43", "#c58ce2"
    value_title = "Transactions"
    value_format = "%{y:,}"
    hover_value_label = "Transactions"

pareto_df = user_stats.sort_values(value_col, ascending=False).reset_index(drop=True)
pareto_df["Rank"] = pareto_df.index + 1

total_activity = pareto_df[value_col].sum()
total_users = len(pareto_df)

pareto_df["CumPct"] = (
    pareto_df[value_col].cumsum() / total_activity * 100 if total_activity > 0 else 0
)

# Reference levels (50/80/95%) below are computed on the exact, full
# pareto_df. The traces themselves are bucketed to keep the payload sent
# to the browser small when there are many thousands of users.
pareto_plot_df = bucket_pareto(pareto_df, value_col)
bucketed = len(pareto_plot_df) < total_users

pareto_fig = go.Figure()

bar_hover = (
    "<b>Users up to Rank %{x:,}</b><br>" + hover_value_label + " (bucket sum): " + value_format + "<extra></extra>"
    if bucketed
    else "<b>User Rank %{x}</b><br>" + hover_value_label + ": " + value_format + "<extra></extra>"
)

pareto_fig.add_trace(
    go.Bar(
        x=pareto_plot_df["Rank"],
        y=pareto_plot_df[value_col],
        marker=dict(color=color_bar),
        name=value_title,
        hovertemplate=bar_hover,
    )
)

pareto_fig.add_trace(
    go.Scatter(
        x=pareto_plot_df["Rank"],
        y=pareto_plot_df["CumPct"],
        mode="lines",
        line=dict(color=color_line, width=4),
        yaxis="y2",
        name="Cumulative Share",
        hovertemplate="<b>User Rank %{x}</b><br>Cumulative Share: %{y:.2f}%<extra></extra>",
    )
)

levels = [50, 80, 95]
level_colors = {50: "#4CAF50", 80: "#FF9800", 95: "#F44336"}

if total_users > 0 and total_activity > 0:
    for level in levels:
        matching_rows = pareto_df.index[pareto_df["CumPct"] >= level]
        if len(matching_rows) == 0:
            continue

        idx = matching_rows[0]
        rank = int(pareto_df.loc[idx, "Rank"])
        pct_users = rank / total_users * 100

        pareto_fig.add_hline(y=level, line_dash="dot", line_color=level_colors[level], yref="y2")
        pareto_fig.add_vline(x=rank, line_dash="dot", line_color=level_colors[level])
        pareto_fig.add_annotation(
            x=rank,
            y=level,
            yref="y2",
            showarrow=True,
            arrowhead=2,
            bgcolor="white",
            bordercolor=level_colors[level],
            borderwidth=1,
            text=f"<b>{level}% of Activity</b><br>Top {pct_users:.2f}% Users",
        )

pareto_fig.update_layout(
    template="plotly_white",
    height=620,
    hovermode="x unified",
    margin=dict(l=20, r=20, t=80, b=20),
    title=(
        f"Pareto Analysis — {pareto_metric}"
        "<br><sup>Users ranked from highest to lowest activity with cumulative "
        "activity contribution shown on the secondary axis.</sup>"
    ),
    xaxis=dict(title="Users Ranked by Activity", showgrid=False, zeroline=False),
    yaxis=dict(title=value_title, gridcolor="rgba(0,0,0,0.08)"),
    yaxis2=dict(
        title="Cumulative Share (%)", overlaying="y", side="right",
        range=[0, 100], showgrid=False, ticksuffix="%",
    ),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0.5),
)

st.plotly_chart(pareto_fig, use_container_width=True, key="user_activity_pareto_chart")
if bucketed:
    st.caption(
        f"Bars grouped into {len(pareto_plot_df):,} rank buckets out of {total_users:,} users "
        "to keep the chart lightweight. The 50/80/95% reference markers above are computed "
        "on the full, unbucketed data."
    )

# ==========================================================
# USER RETENTION COHORT ANALYSIS
# ==========================================================

st.subheader("📊 User Retention Cohort Analysis")

st.caption(
    "Measures the percentage of users from each monthly cohort who remain active "
    "in subsequent months. A user is considered active if they perform at least "
    "one transaction during the month, regardless of the service used."
)


# ==========================================================
# PREPARE MONTHLY USER ACTIVITY
# ==========================================================

cohort_data = all_data[
    ["key", "Month"]
].copy()

cohort_data["Month"] = pd.to_datetime(
    cohort_data["Month"],
    format="%Y-%m",
    errors="coerce"
)

cohort_data = cohort_data.dropna(
    subset=["key", "Month"]
)

# One user = one activity record per month
cohort_data = (
    cohort_data[
        ["key", "Month"]
    ]
    .drop_duplicates()
)


# ==========================================================
# FIND FIRST ACTIVE MONTH FOR EACH USER
# ==========================================================

first_active = (
    cohort_data
    .groupby("key")["Month"]
    .min()
    .reset_index()
    .rename(
        columns={
            "Month": "Cohort Month"
        }
    )
)


# ==========================================================
# MERGE COHORT INFORMATION
# ==========================================================

cohort_data = cohort_data.merge(
    first_active,
    on="key",
    how="left"
)


# ==========================================================
# CALCULATE MONTH INDEX
# ==========================================================

cohort_data["Cohort Index"] = (

    (
        cohort_data["Month"].dt.year
        - cohort_data["Cohort Month"].dt.year
    ) * 12

    +

    (
        cohort_data["Month"].dt.month
        - cohort_data["Cohort Month"].dt.month
    )

)


# ==========================================================
# COHORT SIZE
# ==========================================================

cohort_sizes = (
    first_active
    .groupby("Cohort Month")["key"]
    .nunique()
    .rename("Cohort Users")
)


# ==========================================================
# ACTIVE USERS BY COHORT
# ==========================================================

cohort_activity = (

    cohort_data
    .groupby(
        [
            "Cohort Month",
            "Cohort Index"
        ]
    )["key"]
    .nunique()
    .reset_index(name="Active Users")
)


# ==========================================================
# CALCULATE RETENTION RATE
# ==========================================================

cohort_activity["Cohort Users"] = (

    cohort_activity["Cohort Month"]
    .map(cohort_sizes)

)

cohort_activity["Retention Rate"] = (

    cohort_activity["Active Users"]
    /
    cohort_activity["Cohort Users"]
    * 100

)


# ==========================================================
# COHORT RETENTION MATRIX
# ==========================================================

retention_matrix = (

    cohort_activity
    .pivot(
        index="Cohort Month",
        columns="Cohort Index",
        values="Retention Rate"
    )
)


# ==========================================================
# SORT COHORTS
# ==========================================================

retention_matrix = retention_matrix.sort_index()


# ==========================================================
# RENAME COLUMNS
# ==========================================================

retention_matrix.columns = [
    f"Month {int(x)}"
    for x in retention_matrix.columns
]


# ==========================================================
# HEATMAP
# ==========================================================

fig_cohort = px.imshow(

    retention_matrix,

    text_auto=".1f",

    aspect="auto",

    color_continuous_scale=[
        "#f5f5f5",
        "#c58ce2",
        "#8e44ad"
    ],

    labels={
        "x": "Months Since Cohort",
        "y": "Cohort Month",
        "color": "Retention (%)"
    }
)


fig_cohort.update_layout(

    template="plotly_white",

    height=1200,

    title=(
        "User Retention by Cohort"
        "<br>"
        "<sup>"
        "Percentage of users from each cohort who remained active "
        "in subsequent months."
        "</sup>"
    ),

    margin=dict(
        l=20,
        r=20,
        t=80,
        b=20
    ),

    xaxis=dict(
        title="Months Since Cohort"
    ),

    yaxis=dict(
        title="Cohort Month"
    ),

    coloraxis_colorbar=dict(
        title="Retention (%)"
    )
)


fig_cohort.update_traces(

    hovertemplate=
    "<b>Cohort:</b> %{y}<br>"
    "<b>Period:</b> %{x}<br>"
    "<b>Retention:</b> %{z:.2f}%"
    "<extra></extra>"
)


# ==========================================================
# DISPLAY HEATMAP
# ==========================================================

st.plotly_chart(

    fig_cohort,

    width="stretch",

    key="user_retention_cohort_heatmap"

)


# ==========================================================
# DETAILED COHORT TABLE
# ==========================================================

st.subheader("📋 Detailed Cohort Retention")

st.caption(
    "Detailed cohort-level retention data including cohort size, "
    "active users and retention rate for each subsequent month."
)


# ==========================================================
# PREPARE TABLE
# ==========================================================

cohort_table = cohort_activity.copy()


cohort_table["Cohort Month"] = (

    cohort_table["Cohort Month"]
    .dt.strftime("%Y-%m")

)


cohort_table["Period"] = (

    "Month "
    +
    cohort_table["Cohort Index"]
    .astype(int)
    .astype(str)

)


cohort_table = cohort_table[
    [
        "Cohort Month",
        "Period",
        "Cohort Index",
        "Cohort Users",
        "Active Users",
        "Retention Rate"
    ]
]


# ==========================================================
# FORMAT TABLE
# ==========================================================

cohort_table = cohort_table.rename(

    columns={
        "Cohort Month": "Cohort",
        "Cohort Index": "Month Index",
        "Cohort Users": "Cohort Size",
        "Active Users": "Active Users",
        "Retention Rate": "Retention (%)"
    }

)


cohort_table["Retention (%)"] = (

    cohort_table["Retention (%)"]
    .round(2)

)


cohort_table = cohort_table.sort_values(

    [
        "Cohort",
        "Month Index"
    ]

)


# ==========================================================
# DISPLAY TABLE
# ==========================================================

st.dataframe(

    cohort_table,

    width="stretch",

    hide_index=True,

    column_config={

        "Cohort": st.column_config.TextColumn(
            "Cohort",
            help="Month in which users first became active."
        ),

        "Period": st.column_config.TextColumn(
            "Period",
            help="Number of months since the cohort's first activity."
        ),

        "Month Index": st.column_config.NumberColumn(
            "Month Index",
            help="0 = cohort month, 1 = one month later, 2 = two months later, etc."
        ),

        "Cohort Size": st.column_config.NumberColumn(
            "Cohort Size",
            format="%d"
        ),

        "Active Users": st.column_config.NumberColumn(
            "Active Users",
            format="%d"
        ),

        "Retention (%)": st.column_config.NumberColumn(
            "Retention (%)",
            format="%.2f%%"
        )
    }
)
