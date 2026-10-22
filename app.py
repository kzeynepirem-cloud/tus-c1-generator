
import os
import re
import json
from io import BytesIO
from typing import List, Dict, Any

import streamlit as st
from openai import OpenAI

# Optional parsers
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    from docx import Document
except Exception:
    Document = None


st.set_page_config(
    page_title="TUS C1 Cloze Üretici",
    page_icon="🧠",
    layout="wide",
)

SYSTEM_PROMPT = r"""
Sen TUS'a hazırlanan bir tıp öğrencisinin "metindeki hiçbir bilgiyi kaçırmama" amacıyla
kullandığı ileri düzey bir Anki C1 cloze üretim motorusun.

TEMEL GÖREV:
Kullanıcının verdiği kaynak metni satır satır / cümle cümle incele. Kaynakta bulunan
TÜM sınanabilir bilgileri atomik bilgi parçalarına ayır. Ardından bu bilgilerin her biri
için TUS hocasının sorabileceği C1 cloze kartları üret.

ÇOK ÖNEMLİ:
- Kaynak dışından bilgi ekleme. Genel tıbbi bilginle "düzeltme" yapma.
- Kaynakta bir bilgi açıkça veya anlamlı biçimde verilmişse onu atlama.
- Aynı bilgi farklı cümlelerde tekrar ediyorsa gereksiz kopya üretme; fakat iki farklı
  sınama biçimi gerçekten faydalıysa ayrı kart üretebilirsin.
- "Her detay" hedefleniyor: sayılar, eşikler, süreler, oranlar, sınıflamalar, tanımlar,
  neden-sonuç ilişkileri, istisnalar, karşılaştırmalar, yerleşimler, mekanizmalar,
  ilaç/etken madde ilişkileri, yan etkiler, kontrendikasyonlar, risk faktörleri,
  laboratuvar bulguları, görüntüleme bulguları, klinik ipuçları ve "özellikle", "en sık",
  "en önemli", "ilk", "tek", "altın standart" gibi vurgu sözcükleri taranmalıdır.

C1 KURALININ EN ÖNEMLİ KISMI:
- {{c1::...}} içine mümkün olduğunca TEK bir cevap veya en fazla 1-2 kısa öğe koy.
- Uzun cümleleri veya paragrafı C1 içine alma.
- C1, sorunun asıl ölçtüğü kritik kelime/terim/sayı/ilaç/bulgu olmalı.
- Örnek: "İlaç etkileşimine {{c1::Farmakokinetik}} denir."
- Kötü örnek: "{{c1::Farmakokinetik ilaç etkileşimleri, emilim, dağılım, metabolizma ve atılımı...}}"
- C1 cevabı bir liste ise mümkünse listeyi tek blok yerine sınanabilir küçük parçalara böl.
- C1 dışındaki metin, cevabı tahmin ettirmeyecek kadar iyi bir soru bağlamı sağlamalı.
- Kaynakta birden fazla kritik öğe varsa her biri için ayrı kart üret.
- Gerektiğinde aynı cümleden farklı atomik bilgiler için birden fazla kart üret.
- Her {{c1::...}} alanının cevabı EN FAZLA 2 kelime olmalıdır.
- İki kelime sınırını aşan cevaplar kullanma; bilgiyi anlamlı ve ayrı kartlara böl.
- Cevap olarak mümkün olduğunda tek bir tıbbi terim, sayı, ilaç adı veya kısa ifade kullan.
- Cevabın iki kelimeden uzun olmaması için tıbbi anlamı bozma ve kaynakta olmayan bilgi ekleme.
- Uzun bir listeyi tek bir C1 alanına koyma; listedeki her öğeyi ayrı kartlarda sınamaya çalış.
- C1 alanına tam cümle, açıklama, gerekçe veya paragraf koyma.
- C1 dışındaki cümle, cevabın anlaşılması için yeterli klinik veya bilimsel bağlamı sağlamalıdır.
- Her kartta yalnızca bir temel bilgi sınanmalıdır.
- Son kontrolde tüm {{c1::...}} alanlarını incele. İki kelimeden uzun olanları anlamı koruyarak yeniden düzenle.
- Çıktıdaki her kartın C1 cevabının en fazla 2 kelime olduğunu kontrol et.


TUS HOCA BAKIŞI:
Her kart için "Bu noktayı TUS hocası neden sorar?" mantığıyla öncelik belirle:
1 = kaynakta mutlaka bilinmesi gereken / klasik yüksek getirili / ince nokta,
2 = önemli,
3 = destekleyici ayrıntı.
Öncelik verirken kaynağın kendi vurgularını dikkate al.

ÇIKTI:
Sadece geçerli JSON üret. Markdown üretme.
Şema:
{
  "facts": [
    {
      "id": "F001",
      "source_text": "Kaynakta bu bilgiyi destekleyen kısa ifade",
      "fact": "Atomik sınanabilir bilgi",
      "importance": 1,
      "reason": "TUS açısından neden önemli"
    }
  ],
  "cards": [
    {
      "id": "C001",
      "fact_id": "F001",
      "cloze": "Tam cümle ve {{c1::KISA CEVAP}}",
      "importance": 1,
      "type": "tanım|mekanizma|klinik|ilaç|lab|sayı|eşik|süre|karşılaştırma|istisna|diğer",
      "reason": "TUS hocasının bunu neden vurgulayacağı"
    }
  ]
}

KAPSAM:
- Önce metni atomik "facts" listesine ayır.
- Sonra facts listesindeki HER sınanabilir bilgi için en az bir kart üret.
- Bir fact tek bir C1 ile düzgün ölçülemiyorsa, aynı fact için birden fazla kısa kart üret.
- "facts" ve "cards" arasında fact_id bağlantısı zorunludur.
"""

AUDIT_PROMPT = r"""
Sen bir TUS içerik denetçisisin. Aşağıda kaynak metin, çıkarılmış atomik facts ve
üretilmiş C1 kartları var.

Amaç: Kaynaktaki SINANABİLİR hiçbir bilgiyi kaçırmamak.

Şunları kontrol et:
- Her sayısal bilgi / süre / eşik / oran / sınıflama kapsanmış mı?
- Her neden-sonuç ilişkisi kapsanmış mı?
- Her "en sık / en önemli / ilk / altın standart / tek / özellikle" vurgusu kapsanmış mı?
- İstisnalar ve karşılaştırmalar kapsanmış mı?
- İlaç-etki, hastalık-bulgu, test-sonuç, mekanizma-sonuç ilişkileri kapsanmış mı?
- C1'ler kısa mı; cevabın içine uzun bilgi yığılmış mı?
- C1 cevabı gerçekten tek bir bilgi parçasını mı ölçüyor?
- Kaynakta olup kartlarda olmayan atomik bilgiler var mı?

Sadece JSON döndür:
{
  "missing": [
    {
      "fact": "Eksik bilgi",
      "source_text": "Kaynak desteği",
      "importance": 1,
      "suggested_cloze": "Cümle {{c1::Kısa cevap}}",
      "reason": "Neden mutlaka kapsanmalı"
    }
  ],
  "quality_issues": [
    {
      "card_id": "C001",
      "issue": "Sorun",
      "fix": "Düzeltilmiş cloze"
    }
  ]
}
"""

def extract_text(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    data = uploaded_file.getvalue()

    if name.endswith(".txt") or name.endswith(".md"):
        return data.decode("utf-8", errors="ignore")

    if name.endswith(".docx"):
        if Document is None:
            raise RuntimeError("DOCX için python-docx kurulmamış.")
        doc = Document(BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    if name.endswith(".pdf"):
        if PdfReader is None:
            raise RuntimeError("PDF için pypdf kurulmamış.")
        reader = PdfReader(BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    raise ValueError("Desteklenen dosyalar: .txt, .md, .docx, .pdf")

def clean_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    # Find the outermost JSON object if the model added stray text.
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Model geçerli JSON döndürmedi.")
    return json.loads(text[start:end+1])

def _groq_json_completion(client: OpenAI, model: str, system_prompt: str, prompt: str, max_output_tokens: int = 8192) -> Dict[str, Any]:
    # Groq's OpenAI-compatible endpoint uses Chat Completions.
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt + "\n\nYanıtın geçerli JSON olsun; Markdown kod çiti kullanma."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=max_output_tokens,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    return clean_json(content)

def call_model(client: OpenAI, model: str, prompt: str, max_output_tokens: int = 8192) -> Dict[str, Any]:
    return _groq_json_completion(client, model, SYSTEM_PROMPT, prompt, max_output_tokens)

def audit_model(client: OpenAI, model: str, prompt: str, max_output_tokens: int = 8192) -> Dict[str, Any]:
    return _groq_json_completion(client, model, AUDIT_PROMPT, prompt, max_output_tokens)

def chunk_text(text: str, max_chars: int = 18000) -> List[str]:
    # Keep chunks sentence-aware.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, current = [], ""
    for p in paragraphs:
        if len(current) + len(p) + 2 <= max_chars:
            current = (current + "\n\n" + p).strip()
        else:
            if current:
                chunks.append(current)
            if len(p) <= max_chars:
                current = p
            else:
                # Hard split very long paragraph.
                for i in range(0, len(p), max_chars):
                    piece = p[i:i+max_chars]
                    if piece:
                        chunks.append(piece)
                current = ""
    if current:
        chunks.append(current)
    return chunks

def normalize_cards(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for c in cards:
        cloze = str(c.get("cloze", "")).strip()
        if not cloze or "{{c1::" not in cloze:
            continue
        # Exact duplicate cloze removal.
        key = re.sub(r"\s+", " ", cloze)
        if key in seen:
            continue
        seen.add(key)
        c["cloze"] = cloze
        out.append(c)
    for i, c in enumerate(out, 1):
        c["id"] = f"C{i:04d}"
    return out

def make_tsv(cards: List[Dict[str, Any]]) -> str:
    rows = ["Text\tTags"]
    for c in cards:
        text = c["cloze"].replace("\t", " ").replace("\n", " ")
        tag = f"TUS_C1::{c.get('type','diger')}::P{c.get('importance',3)}"
        rows.append(f"{text}\t{tag}")
    return "\n".join(rows)

st.title("🧠 TUS C1 Cloze Üretici")
st.caption("Metindeki sınanabilir bilgileri atomik parçalara ayırır → C1 üretir → kapsam denetimi yapar.")

with st.sidebar:
    st.header("Ayarlar")
    api_key = st.text_input("Groq API Key", type="password", value=os.getenv("GROQ_API_KEY", ""))
    model = st.text_input("Model", value=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"))
    chunk_size = st.slider("Parça boyutu", 8000, 24000, 18000, 1000)
    do_audit = st.checkbox("Kapsam denetimi + eksik kart tamamlama", value=True)
    st.info("Groq API anahtarını uygulamaya kaydetmiyorum; yalnızca bu oturumda kullanıyorum. Ücretsiz kullanım limitleri geçerlidir.")

uploaded = st.file_uploader("Metni yükle", type=["txt", "md", "docx", "pdf"])
pasted = st.text_area("veya metni buraya yapıştır", height=220, placeholder="TUS çalıştığın paragrafı buraya bırak...")

if st.button("🚀 Tüm TUS noktalarını çıkar ve C1 üret", type="primary", use_container_width=True):
    if not api_key:
        st.error("Önce Groq API Key gir.")
        st.stop()

    source = pasted.strip()
    if uploaded is not None:
        try:
            source = extract_text(uploaded).strip()
        except Exception as e:
            st.error(f"Dosya okunamadı: {e}")
            st.stop()

    if not source:
        st.warning("Bir metin yükle veya yapıştır.")
        st.stop()

    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    chunks = chunk_text(source, chunk_size)

    all_facts, all_cards = [], []
    progress = st.progress(0)
    status = st.empty()

    for idx, chunk in enumerate(chunks, 1):
        status.write(f"Parça {idx}/{len(chunks)} analiz ediliyor…")
        prompt = f"""
KAYNAK METİN — PARÇA {idx}/{len(chunks)}
----------------
{chunk}
----------------

Bu parçadaki TÜM sınanabilir bilgileri facts olarak çıkar ve her fact için C1 kart(lar)ı üret.
Metinde "sadece ayrıntı" gibi görünen fakat TUS'ta sorulabilecek noktaları da dahil et.
"""
        try:
            result = call_model(client, model, prompt)
            all_facts.extend(result.get("facts", []))
            all_cards.extend(result.get("cards", []))
        except Exception as e:
            st.error(f"Parça {idx} sırasında hata: {e}")
            st.stop()

        progress.progress(idx / len(chunks))

    # Global deduplication of facts and cards.
    # Facts are kept because they form the audit trail; exact duplicates are removed.
    fact_seen = set()
    facts = []
    for f in all_facts:
        key = re.sub(r"\s+", " ", str(f.get("fact", "")).strip()).lower()
        if key and key not in fact_seen:
            fact_seen.add(key)
            facts.append(f)

    cards = normalize_cards(all_cards)

    # Reconnect fact ids where possible.
    fact_map = {}
    for i, f in enumerate(facts, 1):
        old = f.get("id")
        f["id"] = f"F{i:04d}"
        if old:
            fact_map[old] = f["id"]

    for c in cards:
        if c.get("fact_id") in fact_map:
            c["fact_id"] = fact_map[c["fact_id"]]

    audit = {"missing": [], "quality_issues": []}

    if do_audit:
        status.write("🔎 Kapsam denetimi yapılıyor…")
        # Audit in one call when possible. Truncate source only if enormous; the facts preserve coverage.
        audit_prompt = f"""
KAYNAK METİN:
{source}

ATOMİK FACTS:
{json.dumps(facts, ensure_ascii=False, indent=2)}

ÜRETİLEN C1 KARTLARI:
{json.dumps(cards, ensure_ascii=False, indent=2)}

Şimdi eksik sınanabilir bilgileri bul. Özellikle sayılar, eşikler, süreler,
istisnalar, karşılaştırmalar ve tek/ilk/en önemli gibi ifadeleri denetle.
"""
        try:
            audit = audit_model(client, model, audit_prompt)
        except Exception as e:
            st.warning(f"Denetim çalışmadı; ilk üretim sonucu gösteriliyor. Hata: {e}")

        missing = audit.get("missing", [])
        if missing:
            status.write(f"🛠️ {len(missing)} eksik nokta için düzeltme kartları üretiliyor…")
            repair_prompt = f"""
Aşağıdaki eksik noktaların HER BİRİ için kısa, TUS tarzı bir C1 cloze üret.
C1 içine yalnızca tek bir kısa cevap veya en fazla 1-2 kısa öğe koy.
Kaynak dışı bilgi ekleme.

EKSİKLER:
{json.dumps(missing, ensure_ascii=False, indent=2)}

Sadece JSON:
{{"cards":[
  {{"fact_id":"", "cloze":"...", "importance":1, "type":"...", "reason":"..."}}
]}}
"""
            try:
                repaired = call_model(client, model, repair_prompt)
                cards.extend(repaired.get("cards", []))
                cards = normalize_cards(cards)
            except Exception as e:
                st.warning(f"Eksik kart tamamlama çalışmadı: {e}")

    status.success(f"Tamamlandı: {len(cards)} benzersiz C1 kartı / {len(facts)} atomik bilgi.")

    st.session_state["facts"] = facts
    st.session_state["cards"] = cards
    st.session_state["audit"] = audit

if "cards" in st.session_state:
    cards = st.session_state["cards"]
    facts = st.session_state["facts"]
    audit = st.session_state.get("audit", {})

    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Atomik bilgi", len(facts))
    c2.metric("C1 kartı", len(cards))
    c3.metric("Eksik bulunan", len(audit.get("missing", [])))
    c4.metric("Kalite sorunu", len(audit.get("quality_issues", [])))

    tab1, tab2, tab3 = st.tabs(["🧠 C1 Kartları", "🔬 Bilgi Kapsamı", "⚠️ Denetim"])

    with tab1:
        importance_filter = st.multiselect(
            "Öncelik",
            [1, 2, 3],
            default=[1, 2, 3],
            format_func=lambda x: {1:"1 — MUTLAKA BİL",2:"2 — ÖNEMLİ",3:"3 — DESTEK"}[x]
        )
        filtered = [c for c in cards if int(c.get("importance", 3)) in importance_filter]
        for i, card in enumerate(filtered, 1):
            imp = int(card.get("importance", 3))
            label = {1:"🔴 MUTLAKA BİL", 2:"🟠 ÖNEMLİ", 3:"🟢 DESTEK"}[imp]
            with st.container(border=True):
                st.markdown(f"**{i}. {label} · {card.get('type','diğer')}**")
                st.markdown(card["cloze"])
                if card.get("reason"):
                    st.caption("TUS vurgusu: " + str(card["reason"]))

        st.download_button(
            "⬇️ Anki TSV indir",
            data=make_tsv(cards),
            file_name="tus_c1_cards.tsv",
            mime="text/tab-separated-values",
            use_container_width=True,
        )

        raw = "\n".join(c["cloze"] for c in cards)
        st.download_button(
            "⬇️ Sadece C1 metni indir",
            data=raw,
            file_name="tus_c1_clozes.txt",
            mime="text/plain",
            use_container_width=True,
        )

    with tab2:
        st.write("Her atomik bilgi en az bir kartla ilişkilendirilmeye çalışılır.")
        linked = {c.get("fact_id") for c in cards if c.get("fact_id")}
        for f in facts:
            state = "✅" if f.get("id") in linked else "❌"
            st.write(f"{state} **{f.get('id')}** — {f.get('fact','')}")
            if f.get("source_text"):
                st.caption("Kaynak: " + str(f["source_text"]))

    with tab3:
        missing = audit.get("missing", [])
        issues = audit.get("quality_issues", [])
        if not missing and not issues:
            st.success("Denetimde eksik nokta veya kalite sorunu raporlanmadı.")
        if missing:
            st.subheader("Denetimde bulunan eksikler")
            for m in missing:
                st.write(f"🔴 **{m.get('fact','')}**")
                st.caption(m.get("reason",""))
                if m.get("suggested_cloze"):
                    st.code(m["suggested_cloze"])
        if issues:
            st.subheader("Kalite sorunları")
            for q in issues:
                st.write(f"**{q.get('card_id','')}** — {q.get('issue','')}")
                if q.get("fix"):
                    st.code(q["fix"])

st.divider()
st.caption("Not: Bu uygulama kaynak metni kapsama odaklı işler; tıbbi doğruluğu bağımsız olarak garanti etmez. Sınav çalışmasında ders notu / kaynak kitapla çapraz kontrol et.")
