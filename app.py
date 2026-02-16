import streamlit as st
from google import genai
from google.genai import types
from pdf417gen import encode, render_image
from PIL import Image, ImageOps
from io import BytesIO
import zipfile
import json
import re

GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]

# Sayfa Ayarları
st.set_page_config(
    page_title="AI Barkod (v3.1 Stable)",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS Stil ---
st.markdown("""
<style>
.block-container { padding-top: 1rem; }
h1 { text-align: center; margin-bottom: 2rem; }
[data-testid='stFileUploader'] section > button { color: transparent !important; }
[data-testid='stFileUploader'] section > button::after { content: "Dosya Seç"; position: absolute; color: white; left: 50%; transform: translate(-50%, -50%); }
</style>
""", unsafe_allow_html=True)

# --- Fonksiyonlar ---

@st.cache_data(show_spinner=False)
def get_gemini_response_smart(file_content, mime_type):
    """
    Sadece listenizde MEVCUT olan modelleri dener.
    gemini-1.5-flash kaldırıldı.
    """
    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
    except Exception as e:
        st.error(f"API Anahtarı Hatası: {e}")
        return [], None
    
    # SENİN LİSTENE GÖRE GÜNCELLENMİŞ MODEL SIRALAMASI
    # 1.5-flash'ı kaldırdık çünkü sende yok.
    models_to_try = [
        "gemini-2.5-flash",         # En yeni ve hızlı
        "gemini-2.0-flash",       # Çok hızlı alternatif
        "gemini-3.0-flash",         # En zeki model (Yedek)
        "gemini-2.0-flash-lite",  # En hafif model (Yedek)s
        "gemini-flash-latest"     # Google'ın önerdiği son sürüm
    ]
    
    prompt_text = """
    Sen uzman bir lojistik veri asistanısın. Bu belgedeki barkod/etiket numaralarını analiz et.
    Kodlar genellikle şu harflerle başlar: DT, EA, CY, TW, DK, DG, GC, GU, MD.

    İKİ FARKLI SENARYO VARDIR, BELGEYE GÖRE HAREKET ET:

    SENARYO 1 (Açıkça Gruplanmış):
    Eğer metinde kodların önünde "1.BAĞ", "2.BAĞ" (veya Bundle, Paket) gibi ifadeler V A R S A:
    - Kodları aynen o grup adının altında topla.

    SENARYO 2 (Düz Liste):
    Eğer metinde kodların önünde "BAĞ" ifadesi Y O K S A (Sadece virgül/boşlukla ayrılmışsa):
    - Her bir kodu sırasıyla "1. BAĞ", "2. BAĞ", "3. BAĞ" şeklinde isimlendirerek tek tek grupla.

    ÇIKTI FORMATI (SADECE JSON LISTESI):
    [
      {"name": "1. BAĞ", "codes": ["KOD1", "KOD2"]},
      {"name": "2. BAĞ", "codes": ["KOD3"]}
    ]
    Lütfen sadece JSON döndür, açıklama yazma.
    """

    last_error = ""

    for model_name in models_to_try:
        try:
            # API İsteği
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_bytes(data=file_content, mime_type=mime_type),
                            types.Part.from_text(text=prompt_text)
                        ]
                    )
                ]
            )
            
            text = response.text.strip()
            
            # JSON Temizliği
            match = re.search(r'\[.*\]', text, re.DOTALL)
            
            if match:
                json_str = match.group(0)
                result = json.loads(json_str)
                return result, model_name
            else:
                last_error = f"{model_name} JSON döndürmedi."
                continue

        except Exception as e:
            error_msg = str(e)
            # Eğer model bulunamadıysa (404) veya kota doluysa (429) pas geç
            if "404" in error_msg or "429" in error_msg or "503" in error_msg:
                continue 
            else:
                last_error = f"{model_name} Hatası: {error_msg}"
                continue
    
    st.error(f"❌ Hiçbir model çalışmadı. Son hata: {last_error}")
    return [], None

def generate_barcode_image(code_text):
    try:
        # DEĞİŞİKLİK 1: columns=5 yerine 8-10 arası yapın (Barkodu genişletir)
        # DEĞİŞİKLİK 2: security_level=5 ekleyin (Okuma hatasını tolere eder)
        codes = encode(code_text, columns=8, security_level=5)
        
        # DEĞİŞİKLİK 3: scale'i 6'dan 8'e çıkarın (Daha büyük pikseller)
        # ratio=3 (Satır yüksekliği standarda daha yakın olsun, 4 bazen fazla uzun kalabilir)
        image = render_image(codes, scale=8, ratio=3)
        
        base_border = 50  # Kenar boşluğunu biraz daha rahatlatın
        img_padded = ImageOps.expand(image, border=base_border, fill="white")
        
        # ... geri kalan kod aynı ...
        w, h = img_padded.size
        final_square_size = max(w, h)
        white_box = Image.new("RGB", (final_square_size, final_square_size), "white")
        offset_x = (final_square_size - w) // 2
        offset_y = (final_square_size - h) // 2
        white_box.paste(img_padded, (offset_x, offset_y))
        
        buffer = BytesIO()
        white_box.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
    except Exception:
        return None

# --- Ana Uygulama ---

def main():
    st.markdown("<h1>✅ AI Barkod (2.5 Flash / Pro)</h1>", unsafe_allow_html=True)
    
    col_left, col_middle, col_right = st.columns([3, 5, 4], gap="medium")

    # --- Sol: Yükleme ---
    with col_left:
        st.subheader("📂 Yükleme")
        uploaded_file = st.file_uploader("İrsaliye Yükle", type=["pdf", "png", "jpg", "jpeg"])
        
        extracted_groups = []
        used_model = None
        
        if uploaded_file:
            bytes_data = uploaded_file.getvalue()
            mime_type = uploaded_file.type
            
            with st.spinner('AI (Gemini 2.5) Analiz Ediyor...'):
                extracted_groups, used_model = get_gemini_response_smart(bytes_data, mime_type)
            
            if extracted_groups:
                count = sum(len(g['codes']) for g in extracted_groups)
                st.success(f"✅ Başarılı! {count} barkod bulundu.")
                st.caption(f"🤖 Çalışan Model: **{used_model}**")
            elif not extracted_groups and used_model is None:
                st.warning("Etiket bulunamadı.")

    if 'selected_group' not in st.session_state:
        st.session_state.selected_group = None

    # --- Orta: Liste ---
    with col_middle:
        if extracted_groups:
            st.subheader(f"📦 Paket Listesi")
            
            for i, group in enumerate(extracted_groups):
                group_name = group.get("name", f"Bağ {i+1}")
                codes = group.get("codes", [])
                code_count = len(codes)
                
                if code_count == 1:
                    info_text = f" - {codes[0]}"
                else:
                    info_text = f" ({code_count} Barkod)"
                
                label = f"📦 {group_name}{info_text}"
                
                is_selected = (st.session_state.selected_group == group)
                btn_type = "primary" if is_selected else "secondary"
                
                if st.button(label, key=f"btn_{i}", use_container_width=True, type=btn_type):
                    st.session_state.selected_group = group
                    st.rerun()
            
            st.divider()
            
            # ZIP İndirme
            if st.button("💾 Tümünü İndir (ZIP)", type="primary", use_container_width=True):
                with st.spinner("ZIP hazırlanıyor..."):
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w") as zf:
                        for group in extracted_groups:
                            safe_name = group.get("name", "Grup").replace(".", "").replace(" ", "_")
                            for code in group.get("codes", []):
                                img_buff = generate_barcode_image(code)
                                if img_buff:
                                    filename = f"{safe_name}_{code}.png"
                                    zf.writestr(filename, img_buff.read())
                    
                    zip_buffer.seek(0)
                    st.download_button("⬇️ İndir", zip_buffer, "barkodlar_v3.zip", "application/zip", use_container_width=True)

    # --- Sağ: Önizleme ---
    with col_right:
        if st.session_state.selected_group:
            group = st.session_state.selected_group
            g_name = group.get("name", "Grup")
            codes = group.get("codes", [])
            
            st.info(f"Seçilen: **{g_name}**")
            
            if not codes:
                st.warning("Kod yok.")
            else:
                for code in codes:
                    st.markdown(f"**🏷️ {code}**")
                    img_buffer = generate_barcode_image(code)
                    if img_buffer:
                        st.image(img_buffer, width=350)
                    st.divider()

if __name__ == "__main__":
    main()