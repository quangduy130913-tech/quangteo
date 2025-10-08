# python.py

import streamlit as st
import pandas as pd
from google import genai
from google.genai.errors import APIError
from google.genai import types # IMPORT MỚI: Cần thiết để cấu hình Chat

# --- Cấu hình Trang Streamlit ---
st.set_page_config(
    page_title="App Phân Tích Báo Cáo Tài Chính",
    layout="wide"
)

st.title("Ứng dụng Phân Tích Báo Cáo Tài chính 📊")

# --- Hàm tính toán chính (Sử dụng Caching để Tối ưu hiệu suất) ---
@st.cache_data
def process_financial_data(df):
    """Thực hiện các phép tính Tăng trưởng và Tỷ trọng."""
    
    # Đảm bảo các giá trị là số để tính toán
    numeric_cols = ['Năm trước', 'Năm sau']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # 1. Tính Tốc độ Tăng trưởng
    df['Tốc độ tăng trưởng (%)'] = (
        (df['Năm sau'] - df['Năm trước']) / df['Năm trước'].replace(0, 1e-9)
    ) * 100

    # 2. Tính Tỷ trọng theo Tổng Tài sản
    tong_tai_san_row = df[df['Chỉ tiêu'].str.contains('TỔNG CỘNG TÀI SẢN', case=False, na=False)]
    
    if tong_tai_san_row.empty:
        raise ValueError("Không tìm thấy chỉ tiêu 'TỔNG CỘNG TÀI SẢN'.")

    tong_tai_san_N_1 = tong_tai_san_row['Năm trước'].iloc[0]
    tong_tai_san_N = tong_tai_san_row['Năm sau'].iloc[0]

    divisor_N_1 = tong_tai_san_N_1 if tong_tai_san_N_1 != 0 else 1e-9
    divisor_N = tong_tai_san_N if tong_tai_san_N != 0 else 1e-9

    df['Tỷ trọng Năm trước (%)'] = (df['Năm trước'] / divisor_N_1) * 100
    df['Tỷ trọng Năm sau (%)'] = (df['Năm sau'] / divisor_N) * 100
    
    return df

# --- Hàm gọi API Gemini (Dùng cho Chức năng 5 - Nhận xét) ---
def get_ai_analysis(data_for_ai, api_key):
    """Gửi dữ liệu phân tích đến Gemini API và nhận nhận xét."""
    try:
        client = genai.Client(api_key=api_key)
        model_name = 'gemini-2.5-flash' 

        prompt = f"""
        Bạn là một chuyên gia phân tích tài chính chuyên nghiệp. Dựa trên các chỉ số tài chính sau, hãy đưa ra một nhận xét khách quan, ngắn gọn (khoảng 3-4 đoạn) về tình hình tài chính của doanh nghiệp. Đánh giá tập trung vào tốc độ tăng trưởng, thay đổi cơ cấu tài sản và khả năng thanh toán hiện hành.
        
        Dữ liệu thô và chỉ số:
        {data_for_ai}
        """

        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        return response.text

    except APIError as e:
        return f"Lỗi gọi Gemini API: Vui lòng kiểm tra Khóa API hoặc giới hạn sử dụng. Chi tiết lỗi: {e}"
    except KeyError:
        return "Lỗi: Không tìm thấy Khóa API 'GEMINI_API_KEY'. Vui lòng kiểm tra cấu hình Secrets trên Streamlit Cloud."
    except Exception as e:
        return f"Đã xảy ra lỗi không xác định: {e}"

# --- Hàm xử lý Khung Chat (SỬA LỖI ĐÃ XONG) ---
def get_chat_response(prompt_input):
    """Gửi tin nhắn trong khung chat và nhận phản hồi, có duy trì ngữ cảnh."""
    # Lấy API Key từ Streamlit Secrets
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        return "Lỗi API: Vui lòng cấu hình Khóa 'GEMINI_API_KEY' trong Streamlit Secrets."

    try:
        # 1. Khởi tạo Client và Chat Session nếu chưa có
        if "chat_client" not in st.session_state:
            st.session_state.chat_client = genai.Client(api_key=api_key)
            
            # Khởi tạo System Instruction và Config để sửa lỗi 'unexpected keyword argument'
            system_instruction = (
                "Bạn là một chuyên gia phân tích tài chính am hiểu. "
                "Hãy trả lời các câu hỏi về tài chính của người dùng, sử dụng dữ liệu Báo cáo Tài chính đã được tải lên và phân tích. "
                "Tuyệt đối không trả lời các câu hỏi ngoài phạm vi phân tích tài chính và dữ liệu đã cung cấp."
            )
            
            config = types.GenerateContentConfig(
                system_instruction=system_instruction
            )
            
            # Khởi tạo chat session
            st.session_state.chat_session = st.session_state.chat_client.chats.create(
                model='gemini-2.5-flash',
                config=config # SỬA LỖI: Truyền cấu hình qua tham số 'config'
            )
        
        # 2. Gửi tin nhắn
        chat = st.session_state.chat_session
        response = chat.send_message(prompt_input)
        return response.text

    except APIError as e:
        return f"Lỗi gọi Gemini API: {e}"
    except Exception as e:
        return f"Lỗi không xác định: {e}"


# *******************************************************************
# --- Logic Chính của Ứng dụng ---
# *******************************************************************

# --- Chức năng 1: Tải File ---
uploaded_file = st.file_uploader(
    "1. Tải file Excel Báo cáo Tài chính (Chỉ tiêu | Năm trước | Năm sau)",
    type=['xlsx', 'xls']
)

if uploaded_file is not None:
    try:
        df_raw = pd.read_excel(uploaded_file)
        
        # Tiền xử lý
        df_raw.columns = ['Chỉ tiêu', 'Năm trước', 'Năm sau']
        
        # Xử lý dữ liệu
        df_processed = process_financial_data(df_raw.copy())

        if df_processed is not None:
            
            # --- Chức năng 2 & 3: Hiển thị Kết quả ---
            st.subheader("2. Tốc độ Tăng trưởng & 3. Tỷ trọng Cơ cấu Tài sản")
            st.dataframe(df_processed.style.format({
                'Năm trước': '{:,.0f}',
                'Năm sau': '{:,.0f}',
                'Tốc độ tăng trưởng (%)': '{:.2f}%',
                'Tỷ trọng Năm trước (%)': '{:.2f}%',
                'Tỷ trọng Năm sau (%)': '{:.2f}%'
            }), use_container_width=True)
            
            # --- Khởi tạo dữ liệu và Session State cho Chat (Chức năng 6) ---
            if "messages" not in st.session_state:
                st.session_state.messages = []
                initial_message = (
                    "Chào mừng bạn đến với chuyên gia phân tích tài chính AI! "
                    "Tôi đã phân tích Bảng Cân đối Kế toán của bạn. "
                    "Hãy hỏi tôi bất kỳ điều gì về tốc độ tăng trưởng, tỷ trọng cơ cấu tài sản, hoặc các chỉ số tài chính đã tính toán."
                )
                st.session_state.messages.append({"role": "assistant", "content": initial_message})
            
            # Gán dữ liệu phân tích vào session state để dùng cho Chatbot
            st.session_state.financial_data_markdown = df_processed.to_markdown(index=False)
            
            
            # --- Chức năng 4: Tính Chỉ số Tài chính ---
            st.subheader("4. Các Chỉ số Tài chính Cơ bản")
            
            try:
                # Lấy Tài sản ngắn hạn & Nợ ngắn hạn
                tsnh_n = df_processed[df_processed['Chỉ tiêu'].str.contains('TÀI SẢN NGẮN HẠN', case=False, na=False)]['Năm sau'].iloc[0]
                tsnh_n_1 = df_processed[df_processed['Chỉ tiêu'].str.contains('TÀI SẢN NGẮN HẠN', case=False, na=False)]['Năm trước'].iloc[0]

                no_ngan_han_N = df_processed[df_processed['Chỉ tiêu'].str.contains('NỢ NGẮN HẠN', case=False, na=False)]['Năm sau'].iloc[0]  
                no_ngan_han_N_1 = df_processed[df_processed['Chỉ tiêu'].str.contains('NỢ NGẮN HẠN', case=False, na=False)]['Năm trước'].iloc[0]

                # Tính toán
                thanh_toan_hien_hanh_N = tsnh_n / no_ngan_han_N
                thanh_toan_hien_hanh_N_1 = tsnh_n_1 / no_ngan_han_N_1
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(
                        label="Chỉ số Thanh toán Hiện hành (Năm trước)",
                        value=f"{thanh_toan_hien_hanh_N_1:.2f} lần"
                    )
                with col2:
                    st.metric(
                        label="Chỉ số Thanh toán Hiện hành (Năm sau)",
                        value=f"{thanh_toan_hien_hanh_N:.2f} lần",
                        delta=f"{thanh_toan_hien_hanh_N - thanh_toan_hien_hanh_N_1:.2f}"
                    )
                    
            except IndexError:
                 st.warning("Thiếu chỉ tiêu 'TÀI SẢN NGẮN HẠN' hoặc 'NỢ NGẮN HẠN' để tính chỉ số.")
                 thanh_toan_hien_hanh_N = "N/A"
                 thanh_toan_hien_hanh_N_1 = "N/A"
            
            # --- Chức năng 5: Nhận xét AI ---
            st.subheader("5. Nhận xét Tình hình Tài chính (AI)")
            
            # Chuẩn bị dữ liệu để gửi cho AI
            data_for_ai = pd.DataFrame({
                'Chỉ tiêu': [
                    'Toàn bộ Bảng phân tích (dữ liệu thô)', 
                    'Tăng trưởng Tài sản ngắn hạn (%)', 
                    'Thanh toán hiện hành (N-1)', 
                    'Thanh toán hiện hành (N)'
                ],
                'Giá trị': [
                    st.session_state.financial_data_markdown,
                    f"{df_processed[df_processed['Chỉ tiêu'].str.contains('TÀI SẢN NGẮN HẠN', case=False, na=False)]['Tốc độ tăng trưởng (%)'].iloc[0]:.2f}%", 
                    f"{thanh_toan_hien_hanh_N_1}", 
                    f"{thanh_toan_hien_hanh_N}"
                ]
            }).to_markdown(index=False) 

            if st.button("Yêu cầu AI Phân tích"):
                api_key = st.secrets.get("GEMINI_API_KEY") 
                
                if api_key:
                    with st.spinner('Đang gửi dữ liệu và chờ Gemini phân tích...'):
                        ai_result = get_ai_analysis(data_for_ai, api_key)
                        st.markdown("**Kết quả Phân tích từ Gemini AI:**")
                        st.info(ai_result)
                else:
                     st.error("Lỗi: Không tìm thấy Khóa API. Vui lòng cấu hình Khóa 'GEMINI_API_KEY' trong Streamlit Secrets.")

            
            # --- CHỨC NĂNG 6: KHUNG CHAT (Đã sửa lỗi) ---
            st.subheader("6. Khung Chat Hỏi đáp Chuyên sâu")
            st.info("Để bắt đầu cuộc trò chuyện, bạn có thể hỏi: 'Đánh giá chung về tình hình tài sản ngắn hạn?' hoặc 'Tốc độ tăng trưởng của tổng tài sản là bao nhiêu?'")
            
            # 1. Hiển thị lịch sử tin nhắn
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

            # 2. Xử lý đầu vào từ người dùng
            if prompt := st.chat_input("Hỏi Gemini về báo cáo tài chính..."):
                
                # Thêm tin nhắn của người dùng vào lịch sử
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)

                # Chuẩn bị prompt: Gửi cả dữ liệu phân tích kèm theo câu hỏi
                full_prompt_to_gemini = (
                    f"Dữ liệu Báo cáo Tài chính đã phân tích:\n\n"
                    f"{st.session_state.financial_data_markdown}\n\n"
                    f"Câu hỏi của tôi: {prompt}"
                )
                
                # 3. Gọi API Gemini
                with st.chat_message("assistant"):
                    with st.spinner("Gemini đang phân tích và phản hồi..."):
                        response_text = get_chat_response(full_prompt_to_gemini)
                        st.markdown(response_text)
                
                # 4. Thêm phản hồi của AI vào lịch sử
                st.session_state.messages.append({"role": "assistant", "content": response_text})
            
    except ValueError as ve:
        st.error(f"Lỗi cấu trúc dữ liệu: {ve}")
        # Xóa chat session để bắt đầu lại khi file mới được tải lên
        if "messages" in st.session_state: del st.session_state.messages
        if "chat_session" in st.session_state: del st.session_state.chat_session
        if "chat_client" in st.session_state: del st.session_state.chat_client
    except Exception as e:
        st.error(f"Có lỗi xảy ra khi đọc hoặc xử lý file: {e}. Vui lòng kiểm tra định dạng file.")
        if "messages" in st.session_state: del st.session_state.messages
        if "chat_session" in st.session_state: del st.session_state.chat_session
        if "chat_client" in st.session_state: del st.session_state.chat_client

else:
    st.info("Vui lòng tải lên file Excel để bắt đầu phân tích.")
    # Đảm bảo xóa chat history khi không có file
    if "messages" in st.session_state: del st.session_state.messages
    if "chat_session" in st.session_state: del st.session_state.chat_session
    if "chat_client" in st.session_state: del st.session_state.chat_client
