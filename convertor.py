import streamlit as st
import requests
import pandas as pd
from io import StringIO


# تنظیمات صفحه
st.set_page_config(
    page_title="API to CSV Dashboard",
    layout="wide"
)

st.title("📊 API JSON to CSV Dashboard")

st.write(
    "لینک API را وارد کنید تا داده‌ها دریافت و به CSV تبدیل شوند."
)


# دریافت URL از کاربر
api_url = st.text_input(
    "API URL:",
    placeholder="https://example.com/api/data"
)


if st.button("دریافت اطلاعات"):

    if not api_url:
        st.warning("لطفاً لینک API را وارد کنید.")
    
    else:
        try:
            # درخواست API
            response = requests.get(api_url, timeout=30)

            if response.status_code != 200:
                st.error(
                    f"خطا در دریافت API: {response.status_code}"
                )

            else:
                json_data = response.json()

                # استخراج data
                records = json_data.get("data", [])

                if not records:
                    st.warning("داده‌ای پیدا نشد.")

                else:
                    # تبدیل به DataFrame
                    df = pd.DataFrame(records)

                    # فقط ستون‌های مورد نظر
                    required_columns = [
                        "key",
                        "volume",
                        "num_txs"
                    ]

                    df = df[
                        [
                            col for col in required_columns
                            if col in df.columns
                        ]
                    ]


                    st.success(
                        f"{len(df)} رکورد دریافت شد."
                    )


                    # نمایش جدول
                    st.subheader("داده‌ها")
                    st.dataframe(
                        df,
                        use_container_width=True
                    )


                    # تبدیل به CSV
                    csv = df.to_csv(
                        index=False,
                        encoding="utf-8"
                    )


                    # دانلود CSV
                    st.download_button(
                        label="⬇️ دانلود CSV",
                        data=csv,
                        file_name="api_data.csv",
                        mime="text/csv"
                    )


                    # نمایش اطلاعات اضافی API
                    st.subheader("اطلاعات API")

                    col1, col2 = st.columns(2)

                    with col1:
                        st.metric(
                            "Total",
                            json_data.get("total", 0)
                        )

                    with col2:
                        st.metric(
                            "Time spent",
                            json_data.get("time_spent", 0)
                        )


        except requests.exceptions.RequestException as e:
            st.error(
                f"خطای ارتباط با API: {e}"
            )

        except Exception as e:
            st.error(
                f"خطای پردازش داده: {e}"
            )
