"""Host persona: system prompts, leak-safety sanitizer, LLM fallback replies,
silence filler, prologue chat, batched word metadata."""
from __future__ import annotations

import json
import os
import random
import re

import nltk

from llm_client import LLMError
from .config import SILENCE_LLM_PROBABILITY
from .text_utils import UnicodeTr

LLM_DEBUG = os.environ.get("LEXICHAT_DEBUG") == "1"


# --------------------------------------------------------------------------
# Safe LLM call wrapper
# --------------------------------------------------------------------------


def safe_chat(llm, system, messages, max_tokens=80, fallback=""):
    """Wrapper that never raises — returns `fallback` on any LLM error.

    Empty responses are treated as failure (Gemini sometimes returns "" when
    content is filtered). Set LEXICHAT_DEBUG=1 to see raw errors.
    """
    if llm is None:
        return fallback
    try:
        resp = llm.chat(system=system, messages=messages, max_tokens=max_tokens)
        if resp and resp.strip():
            return resp
        if LLM_DEBUG:
            print(f"[debug] LLM returned empty; using fallback. messages={messages!r}")
        return fallback
    except LLMError as e:
        if LLM_DEBUG:
            print(f"[debug] LLMError: {e}")
        return fallback
    except Exception as e:
        if LLM_DEBUG:
            print(f"[debug] Unexpected LLM exception: {type(e).__name__}: {e}")
        return fallback


# --------------------------------------------------------------------------
# Pre-game word metadata (batched into ONE call instead of 42)
# --------------------------------------------------------------------------


def batch_word_metadata(llm, word_list):
    """One LLM call: get origin+structure+example for all words as JSON.

    Returns (origin_list, structure_list, example_list). Any item we can't
    parse becomes "None".
    """
    n = len(word_list)
    if llm is None:
        return ["None"] * n, ["None"] * n, ["None"] * n

    system = (
        "Sen Türkçe dilbilgisi yardımcısısın. Verilen kelime listesinin her biri için "
        "SADECE geçerli bir JSON dizisi üret. Her eleman şu alanları içersin:\n"
        '- "word": kelime\n'
        '- "origin": etimolojik köken, iki kelime. Örnek: "Arapça kökenli". Bilmiyorsan "None".\n'
        '- "structure": "Birleşik kelime" veya "Tek kelime".\n'
        '- "example": 3 kelimelik örnek cümle; kelimenin geçtiği yere _______ yaz.\n'
        "Yalnızca JSON dizisini döndür, başka açıklama YAZMA."
    )
    user_msg = "Kelimeler: " + ", ".join(word_list)
    raw = safe_chat(llm, system, [{"role": "user", "content": user_msg}], max_tokens=900)

    origins = ["None"] * n
    structures = ["None"] * n
    examples = ["None"] * n

    if not raw:
        return origins, structures, examples

    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        data = json.loads(cleaned)
    except Exception:
        if LLM_DEBUG:
            print(f"[debug] batch JSON parse failed. Raw: {raw[:200]!r}")
        return origins, structures, examples

    by_word = {}
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and "word" in item:
            by_word[str(item["word"]).lower()] = item

    for i, word in enumerate(word_list):
        item = by_word.get(word.lower())
        if not item:
            continue
        o = str(item.get("origin", "None")).strip()
        s = str(item.get("structure", "None")).strip()
        e = str(item.get("example", "None")).strip()
        origins[i] = o if o and o.lower() != "none" else "None"
        structures[i] = s if s and s.lower() != "none" else "None"
        examples[i] = e.lower().replace(word.lower(), "-------") if e and e.lower() != "none" else "None"

    return origins, structures, examples


# --------------------------------------------------------------------------
# Host persona system prompt and safety net
# --------------------------------------------------------------------------


HOST_SYSTEM_PROMPT_TEMPLATE = """Sen, "Kelime Oyunu"nun sunucusu Ali İhsan Varol tarzında konuşan Lexichat sunucususun. Oyun ZATEN devam ediyor — sen yalnızca oyuncuya KISA bir cevap veriyorsun. Oyunu sen YÜRÜTMÜYORSUN, sen sadece yorum yapıyorsun.

MUTLAK KURALLAR — ASLA İHLAL ETMEYECEKSİN:
- Bu turun cevabı: "{WORD}". Yanıtında bu kelimeyi VEYA eş anlamlılarını ASLA yazma.
- Eş anlamlılar (yasaklı): {SYNONYMS}
- ASLA yeni bir kelime sorusu sorma. ASLA yeni bir tanım/ipucu sun.
- ASLA "_ _ _ _" gibi harf kutucukları yazma.
- ASLA "Sıradaki kelime", "İlk soru", "Kelime 1", "Bir sonraki" gibi ifadeler kullanma.
- ASLA "Tebrikler, kazandınız!", "Doğru cevap!", "Yeni soruya geçelim" deme.
- Cevabın 1 ya da 2 kısa cümleyi geçmesin.

TARZ:
- Daima "siz" ve "efendim".
- Türkçe, sohbet havası, TV sunucusu.
- Oyuncu ipucundaki bir kelimenin anlamını sorarsa ("X ne demek?"), önce yumuşak bir geçiş ("Biliyorsunuz...", "Aa evet...", "Şöyle düşünün...") sonra TEK cümlelik açıklama yap.
- Oyuncu "bilmiyorum/zor/aklıma gelmiyor" derse, cesaretlendir ve "h" yazarak harf, "ipucu" yazarak yardım alabileceğini hatırlat. Direkt cevabı verme.
- Oyuncu sohbet ederse ("vay be", "hmm"), kısaca karşılık ver ve dikkatini ipucuna çek.

OYUN DURUMU (sen değiştirme, sadece bunu kullan):
- Mevcut ipucu metni: "{CLUE}"
- Oyuncunun açtığı harfler: "{REVEALED}"
- Toplam puan: {SCORE}
"""


def host_system_prompt(state, round_ctx):
    syns = round_ctx.get("synonyms") or []
    if isinstance(syns, str):
        syns = [] if syns == "None" else [syns]
    return HOST_SYSTEM_PROMPT_TEMPLATE.format(
        WORD=round_ctx["word"],
        SYNONYMS=", ".join(syns) if syns else "(yok)",
        CLUE=round_ctx["clue"],
        REVEALED=" ".join(state.revealed_letters) if state.revealed_letters else "(henüz yok)",
        SCORE=state.total_score,
    )


def sanitize_reply(text, word, synonyms):
    """Drop the reply if it leaks the target word OR tries to hijack the game flow."""
    if not text:
        return ""
    low = UnicodeTr(text).lower()
    forbidden = [UnicodeTr(word).lower()]
    if isinstance(synonyms, list):
        forbidden.extend(UnicodeTr(s).lower() for s in synonyms if isinstance(s, str))
    for bad in forbidden:
        if bad and re.search(rf'\b{re.escape(bad)}\b', low):
            return ""

    hijack_patterns = [
        r'kelime\s*\d',
        r'sıradaki\s+(kelime|soru)',
        r'ilk\s+(kelime|soru)',
        r'bir\s+sonraki\s+(kelime|soru)',
        r'doğru\s+cevap',
        r'yeni\s+soru',
        r'_\s*_\s*_',
        r'^\s*(?:#+\s*)?(kelime|soru)\s*\d*\s*[:：]',
    ]
    for pat in hijack_patterns:
        if re.search(pat, low):
            return ""

    return text.strip()


# --------------------------------------------------------------------------
# Scripted fallbacks
# --------------------------------------------------------------------------


def scripted_stuck_reply():
    return random.choice([
        "Efendim, hadi bir harf mi alsak..? \"h\" yazmanız yeter.",
        "\"ipucu\" derseniz size bir ipucu hazırlayabilirim...",
        "Yavaş yavaş... Bir harf açalım, bakın içiniz açılır...",
        "Vazgeçmek yok efendim, bir ipucu ile bulabilirsiniz...",
    ])


def scripted_silence_reply():
    return random.choice([
        "Zaman akıyor efendim...",
        "Hâlâ orada mısınız..?",
        "Bir harf mi alsak..?",
        "Düşünüyorsunuz, biliyorum... Yine de zaman akıyor...",
        "Hmm... İpucu ister misiniz?",
        "Bakalım, bir şey geldi mi aklınıza?",
        "Efendim, dalıp gittiniz sanırım...",
    ])


# --------------------------------------------------------------------------
# Host fallback (called when no keyword branch matched)
# --------------------------------------------------------------------------


def llm_host_reply(llm, state, round_ctx, user_input, history):
    """Free-form host reply for inputs that don't match any keyword branch.

    history: list of (role, text) for THIS round only.
    Returns a safe string, never None. Never leaks the target word.
    """
    if llm is None:
        return scripted_stuck_reply()

    messages = [{"role": role, "content": text} for role, text in history[-6:]]
    messages.append({"role": "user", "content": user_input})

    try:
        raw = llm.chat(
            system=host_system_prompt(state, round_ctx),
            messages=messages,
            max_tokens=70,
        )
    except (LLMError, Exception):
        return scripted_stuck_reply()

    clean = sanitize_reply(raw, round_ctx["word"], round_ctx.get("synonyms"))
    return clean if clean else scripted_stuck_reply()


def llm_silence_reply(llm, state, round_ctx):
    """Proactive line when player goes quiet. 70% scripted, 30% generated."""
    if random.random() > SILENCE_LLM_PROBABILITY or llm is None:
        return scripted_silence_reply()
    try:
        raw = llm.chat(
            system=host_system_prompt(state, round_ctx),
            messages=[{"role": "user", "content": "(Oyuncu sessiz kaldı, nazikçe dikkatini çek.)"}],
            max_tokens=60,
        )
    except Exception:
        return scripted_silence_reply()
    clean = sanitize_reply(raw, round_ctx["word"], round_ctx.get("synonyms"))
    return clean if clean else scripted_silence_reply()


# --------------------------------------------------------------------------
# Pre-game prologue prompt — strict, won't ad-lib a fake game
# --------------------------------------------------------------------------


PROLOGUE_SYSTEM_PROMPT = (
    "Sen 'Kelime Oyunu' yarışmasının sunucusu Ali İhsan Varol tarzında konuşan "
    "Lexichat sunucususun. ŞU ANDA YARIŞMA BAŞLAMADI — yalnızca yarışma öncesi "
    "kısa bir sohbet ediyorsun. Amacın: yarışmacıyı rahatlatmak.\n\n"
    "MUTLAK KURALLAR — ASLA İHLAL ETMEYECEKSİN:\n"
    "- ASLA bir kelime sorusu sorma. ASLA bir tanım/ipucu verme.\n"
    "- ASLA '_ _ _ _' gibi harf kutucukları yazma.\n"
    "- ASLA 'Kelime 1', 'Sıradaki kelime', 'İlk soru' gibi ifadeler kullanma.\n"
    "- ASLA yarışmaya başlama veya başlamış gibi yapma.\n"
    "- Yarışma kuralları zaten anlatıldı, tekrar anlatma.\n\n"
    "TARZ:\n"
    "- 1-2 kısa cümle, daima 'siz' ve 'efendim' ile.\n"
    "- Hava durumu, ruh hali, küçük sohbet — sadece bu kadar.\n"
    "- Sonunda 'Hazır mısınız?' / 'Hazırsanız başlayalım' DEMEK YOK — kullanıcı "
    "  'hazırım' yazdığında oyun otomatik olarak başlayacak."
)


READY_SIGNALS = frozenset({
    "hazırım", "hazir", "hazır", "başla", "basla", "başlayalım", "evet",
})


def is_ready_signal(text):
    """Check if user input means 'I'm ready to start'."""
    low = text.lower().strip()
    if low in READY_SIGNALS:
        return True
    toks = set(nltk.word_tokenize(low))
    return bool(toks & READY_SIGNALS)


def prologue_reply(llm, messages):
    """One turn of pre-game small talk. Returns the host's reply string."""
    return safe_chat(
        llm,
        PROLOGUE_SYSTEM_PROMPT,
        messages,
        max_tokens=70,
        fallback="Çok sevindim efendim.",
    )
