import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

st.set_page_config(
    page_title="Axelar User Analytics",
    layout="wide"
)

st.title("📊 Axelar User Analytics Dashboard")

# مسیر پوشه فایل‌های CSV
DATA_FOLDER = Path("User_Data_History")


@st.cache_data
def load_data():

    monthly_rows = []

    gmp_users = set()
    tt_users = set()

    for file in sorted(DATA_FOLDER.glob("*.csv")):

        name = file.stem

        # فقط فایل‌هایی با فرمت gmp-YYYY-MM یا tt-YYYY-MM
        parts = name.split("-")
        if len(parts) != 3:
            continue

        service = parts[0]
        year = parts[1]
        month = parts[2]

        period = f"{year}-{month}"

        # خواندن فایل با مدیریت خطا
        try:
            df = pd.read_csv(file)

            # اگر فایل خالی باشد یا ستون key نداشته باشد
            if df.empty or "key" not in df.columns:
                continue

        except pd.errors.EmptyDataError:
            continue

        except Exception as e:
            st.warning(f"⚠️ Could not read {file.name}: {e}")
            continue

        users = set(df["key"].dropna())

        monthly_rows.append(
            {
                "Month": period,
                "Service": "GMP" if service == "gmp" else "Token Transfer",
                "Users": len(users),
            }
        )

        if service == "gmp":
            gmp_users.update(users)
        elif service == "tt":
            tt_users.update(users)

    monthly_df = pd.DataFrame(monthly_rows)

    donut_df = pd.DataFrame(
        {
            "Service": ["GMP", "Token Transfer"],
            "Users": [len(gmp_users), len(tt_users)],
        }
    )

    return monthly_df, donut_df


monthly_df, donut_df = load_data()

col1, col2 = st.columns([3, 1])

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
            "Token Transfer": "#00a1f7",
        },
    )

    fig.update_traces(textposition="inside")

    fig.update_layout(
        title="Monthly Active Users",
        xaxis_title="Month",
        yaxis_title="Users",
        hovermode="x unified",
        height=500,
    )

    st.plotly_chart(fig, use_container_width=True)

with col2:

    fig2 = px.pie(
        donut_df,
        names="Service",
        values="Users",
        hole=0.6,
        color="Service",
        color_discrete_map={
            "GMP": "#ff7400",
            "Token Transfer": "#00a1f7",
        },
    )

    fig2.update_traces(
        textposition="inside",
        textinfo="percent+value",
    )

    fig2.update_layout(
        title="Unique Users by Service",
        height=500,
    )

    st.plotly_chart(fig2, use_container_width=True)
