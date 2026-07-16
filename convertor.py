import streamlit as st
import requests
import pandas as pd
from datetime import datetime


# تنظیمات صفحه
st.set_page_config(
    page_title="API to CSV Dashboard",
    layout="wide"
)


st.title("📊 API JSON to CSV Dashboard")

st.write(
    "لینک API را وارد کنید، داده‌ها دریافت شده و به فایل CSV تبدیل می‌شوند."
)


# دریافت URL API
api_url = st.text_input(
    "🔗 API URL:",
    placeholder="https://example.com/api/data"
)


if st.button("🚀 دریافت اطلاعات"):

    if not api_url:
        st.warning("لطفاً لینک API را وارد کنید.")

    else:
        try:

            # ارسال درخواست به API
            response = requests.get(
                api_url,
                timeout=30
            )


            if response.status_code != 200:
                st.error(
                    f"خطا در دریافت API: {response.status_code}"
                )

            else:

                # تبدیل پاسخ به JSON
                json_data = response.json()


                # گرفتن بخش data
                records = json_data.get(
                    "data",
                    []
                )


                if not records:
                    st.warning(
                        "هیچ داده‌ای در API وجود ندارد."
                    )

                else:

                    # تبدیل JSON به DataFrame
                    df = pd.DataFrame(records)


                    # انتخاب ستون‌های مورد نیاز
                    columns = [
                        "key",
                        "volume",
                        "num_txs"
                    ]


                    df = df[
                        [
                            col for col in columns
                            if col in df.columns
                        ]
                    ]


                    st.success(
                        f"✅ تعداد {len(df)} رکورد دریافت شد."
                    )


                    # نمایش داده‌ها
                    st.subheader(
                        "📋 جدول اطلاعات"
                    )

                    st.dataframe(
                        df,
                        use_container_width=True
                    )


                    # اطلاعات اضافی API
                    st.subheader(
                        "ℹ️ اطلاعات API"
                    )


                    col1, col2 = st.columns(2)


                    with col1:
                        st.metric(
                            "Total",
                            json_data.get(
                                "total",
                                0
                            )
                        )


                    with col2:
                        st.metric(
                            "Time spent",
                            json_data.get(
                                "time_spent",
                                0
                            )
                        )



                    # ==========================
                    # بخش خروجی CSV
                    # ==========================

                    st.subheader(
                        "⬇️ خروجی CSV"
                    )


                    # ساخت نام پیش‌فرض با تاریخ
                    default_filename = (
                        f"api_export_"
                        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    )


                    filename = st.text_input(
                        "نام فایل CSV:",
                        value=default_filename
                    )


                    # اضافه کردن پسوند csv
                    if not filename.endswith(".csv"):
                        filename += ".csv"



                    # تبدیل به CSV
                    csv_data = df.to_csv(
                        index=False,
                        encoding="utf-8"
                    )


                    # دکمه دانلود
                    st.download_button(
                        label="📥 دانلود فایل CSV",
                        data=csv_data,
                        file_name=filename,
                        mime="text/csv"
                    )



        except requests.exceptions.Timeout:

            st.error(
                "⏳ زمان دریافت API تمام شد."
            )


        except requests.exceptions.RequestException as e:

            st.error(
                f"خطای ارتباط با API:\n{e}"
            )


        except Exception as e:

            st.error(
                f"خطای پردازش اطلاعات:\n{e}"
            )
