import google.generativeai as genai

# BURAYA KENDİ API KEY'İNİZİ YAPIŞTIRIN
MY_API_KEY = "AIzaSyAIzaSyA2pcNFzC48cw-8xgY0QK44lzQ0u5C3qQE" 

genai.configure(api_key=MY_API_KEY)

print("--- Erisilebilir Modeller Listesi ---")
try:
    for m in genai.list_models():
        # Sadece içerik üretme (generateContent) yeteneği olanları filtreleyelim
        if 'generateContent' in m.supported_generation_methods:
            print(f"Model Adı: {m.name}")
except Exception as e:
    print(f"Hata oluştu: {e}")