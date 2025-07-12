import streamlit as st
import pandas as pd
from fuzzywuzzy import process, fuzz
import pdfplumber
import pytesseract
from PIL import Image
import io

st.set_page_config(layout="wide")

# --- Utility Functions ---
def extract_items_from_pdf(file):
    items = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            lines = text.split('\n')
            for line in lines:
                parts = line.split("CASE")
                if len(parts) > 1:
                    try:
                        name_rate = parts[0].strip()
                        name_part = name_rate.rsplit(' ', 1)[0]
                        rate = float(name_rate.rsplit(' ', 1)[1].replace('/-', '').replace(',', ''))
                        items.append({"Vendor Item": name_part, "Vendor Rate": rate})
                    except:
                        continue
    return pd.DataFrame(items)

def extract_items_from_image(image_file):
    image = Image.open(image_file)
    text = pytesseract.image_to_string(image)
    lines = text.split('\n')
    items = []
    for line in lines:
        if any(c.isdigit() for c in line):
            try:
                parts = line.split()
                rate = float([p for p in parts if p.replace('.', '', 1).isdigit()][-1])
                name = line.replace(str(rate), '').strip()
                items.append({"Vendor Item": name, "Vendor Rate": rate})
            except:
                continue
    return pd.DataFrame(items)

def fuzzy_match(vendor_name, choices, threshold=75):
    match, score = process.extractOne(vendor_name, choices, scorer=fuzz.token_sort_ratio)
    return (match, score) if score >= threshold else (None, score)

# --- Streamlit Interface ---
st.title("🧾 Step 1: Vendor File Extractor")

if 'extracted_data' not in st.session_state:
    st.session_state['extracted_data'] = pd.DataFrame()

extract_tab, match_tab = st.tabs(["1️⃣ Extractor", "2️⃣ Matcher"])

with extract_tab:
    st.header("Upload Vendor Price Sheet (PDF or Image)")
    vendor_files = st.file_uploader("Upload vendor files", type=["pdf", "jpeg", "jpg", "png"], accept_multiple_files=True)

    if vendor_files:
        all_vendor_data = []
        for file in vendor_files:
            if file.type == "application/pdf":
                vendor_df = extract_items_from_pdf(file)
                vendor_df['Source'] = 'PDF'
            else:
                vendor_df = extract_items_from_image(file)
                vendor_df['Source'] = 'Image'
            all_vendor_data.append(vendor_df)

        combined_vendor_df = pd.concat(all_vendor_data, ignore_index=True)
        st.session_state['extracted_data'] = combined_vendor_df

        st.subheader("Extracted Items")
        st.dataframe(combined_vendor_df)

with match_tab:
    st.header("Upload Master Stock Sheet")
    stock_file = st.file_uploader("Upload Master Stock Sheet (Excel)", type=["xlsx"], key="stock")

    if stock_file and not st.session_state['extracted_data'].empty:
        stock_df = pd.read_excel(stock_file, sheet_name='STOCK')
        stock_items = stock_df[['Item', 'Balance Cases  after minus order cases']].copy()
        stock_items.rename(columns={'Balance Cases  after minus order cases': 'Stock (Balance Cases)'}, inplace=True)

        matched = []
        unmatched = []

        for _, row in st.session_state['extracted_data'].iterrows():
            vendor_item = row['Vendor Item']
            vendor_rate = row['Vendor Rate']
            source = row['Source']

            match, score = fuzzy_match(vendor_item, stock_items['Item'].tolist())
            if match:
                stock_row = stock_items[stock_items['Item'] == match].iloc[0]
                matched.append({
                    'Vendor Item': vendor_item,
                    'Vendor Rate': vendor_rate,
                    'Matched Stock Item': match,
                    'Stock (Balance Cases)': stock_row['Stock (Balance Cases)'],
                    'Match Score': score,
                    'Source': source
                })
            else:
                unmatched.append({
                    'Vendor Item': vendor_item,
                    'Vendor Rate': vendor_rate,
                    'Source': source
                })

        matched_df = pd.DataFrame(matched)
        unmatched_df = pd.DataFrame(unmatched)

        st.subheader("Matched Items")
        st.dataframe(matched_df)

        st.subheader("Unmatched Items")
        st.dataframe(unmatched_df)

        st.download_button("Download Matched Items", matched_df.to_csv(index=False), "matched_items.csv")
        st.download_button("Download Unmatched Items", unmatched_df.to_csv(index=False), "unmatched_items.csv")
    elif st.session_state['extracted_data'].empty:
        st.warning("Please upload and extract vendor data in Step 1 first.")
