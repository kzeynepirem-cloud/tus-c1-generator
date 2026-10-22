# TUS C1 Cloze Üretici

Metin/PDF/DOCX/TXT yükleyip TUS odaklı C1 Anki cloze kartları üretir.

## Özellikler
- Metni atomik sınanabilir bilgilere ayırma
- Her atomik bilgi için C1 üretme
- C1 içine uzun cevap koymama
- TUS hocası gibi önem derecesi verme
- Sayı, eşik, süre, istisna, karşılaştırma ve "en önemli/ilk/en sık" noktaları tarama
- İkinci geçişte kapsam denetimi
- Eksik bulunan bilgileri otomatik tamamlama
- Anki TSV ve düz TXT çıktısı
- TXT, MD, DOCX, PDF desteği

## Kurulum

Python 3.10+ önerilir.

```bash
pip install -r requirements.txt
```

API anahtarını ortam değişkeni olarak verebilirsin:

```bash
export OPENAI_API_KEY="sk-..."
```

Windows PowerShell:

```powershell
$env:OPENAI_API_KEY="sk-..."
```

Uygulamayı çalıştır:

```bash
streamlit run app.py
```

Tarayıcıda açılan sayfaya metni yükle.

## Model

Varsayılan model `gpt-6-luna` olarak ayarlanmıştır. Hesabında farklı bir model erişimi varsa sol menüden model adını değiştirebilirsin.

## Mantık

1. Kaynak metin parçalara ayrılır.
2. Her parçada atomik facts çıkarılır.
3. Her fact için bir veya daha fazla C1 üretilir.
4. Kartlar deduplikasyondan geçirilir.
5. Tüm kaynak + facts + kartlar ikinci bir TUS denetiminden geçirilir.
6. Eksik görülen bilgiler için ilave C1 kartları üretilir.

Bu nedenle tek seferlik "özetle" yaklaşımı yerine kapsam odaklı iki aşamalı üretim kullanılır.
