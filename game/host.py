"""Host persona: system prompts, leak-safety sanitizer, LLM fallback replies,
silence filler, prologue chat, batched word metadata."""
from __future__ import annotations

import json
import logging
import os
import random
import re

import nltk

from llm_client import LLMError
from .config import SILENCE_LLM_PROBABILITY
from .mood import (
    MOOD_DESCRIPTIONS, MOOD_PLAYFUL, MOOD_TEASING, MOOD_WARM,
)
from .text_utils import UnicodeTr

LLM_DEBUG = os.environ.get("LEXICHAT_DEBUG") == "1"

# Silence google-genai's INFO logs ("AFC is enabled...") and httpx request
# logs ("HTTP Request: POST..."). They bleed into game output unhelpfully.
# Set LEXICHAT_DEBUG=1 to keep them visible for debugging.
if not LLM_DEBUG:
    for name in ("google_genai", "google_genai.models", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


# --------------------------------------------------------------------------
# Safe LLM call wrapper
# --------------------------------------------------------------------------


def _chat_maybe_low_priority(llm, *, system, messages, max_tokens):
    """Call llm.chat, passing low_priority=True when the client supports it.

    Only BudgetedClient (the web app's session-cap wrapper) understands
    low_priority — it cuts these calls earlier to reserve budget for
    high-value banter. Raw provider clients and the CLI driver don't accept
    the kwarg, so fall back to a plain call for them.
    """
    try:
        return llm.chat(system=system, messages=messages,
                        max_tokens=max_tokens, low_priority=True)
    except TypeError:
        return llm.chat(system=system, messages=messages, max_tokens=max_tokens)


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

OYUN MODU: {MODE_DESCRIPTION}
{MODE_RULES}

TARZ:
- Daima "siz" ve "efendim".
- Türkçe, sohbet havası, TV sunucusu.
- Oyuncu ipucundaki bir kelimenin anlamını sorarsa ("X ne demek?"), önce yumuşak bir geçiş ("Biliyorsunuz...", "Aa evet...", "Şöyle düşünün...") sonra TEK cümlelik açıklama yap.
- Oyuncu sohbet ederse ("vay be", "hmm"), kısaca karşılık ver ve dikkatini ipucuna çek.

OYUN DURUMU (sen değiştirme, sadece bunu kullan):
- Mevcut ipucu metni: "{CLUE}"
- Oyuncunun açtığı harfler: "{REVEALED}"
- Toplam puan: {SCORE}
"""

_HINT_PHASE_RULES = (
    "- Oyuncu \"bilmiyorum/zor/aklıma gelmiyor\" derse, cesaretlendir ve "
    "\"h\" yazarak harf, \"ipucu\" yazarak yardım alabileceğini hatırlat. "
    "Direkt cevabı verme."
)
_ANSWER_PHASE_RULES = (
    "- DİKKAT: Oyuncu cevap verme moduna girdi (\"bb\" tuşuna bastı). "
    "Bu modda HARF ALAMAZ. ASLA \"h yazın\" veya \"harf alın\" deme. "
    "Sadece \"ipucu\" yazarak yardım alabileceğini hatırlat. Direkt cevabı verme."
)
_HINT_PHASE_DESC = "İpucu fazı (oyuncu serbestçe harf alabilir veya tahmin yapabilir)."
_ANSWER_PHASE_DESC = "Cevap fazı (oyuncu \"bb\" dedi, 45 saniyesi var, harf alamaz)."


def host_system_prompt(state, round_ctx, in_answer_mode: bool = False,
                       mood: str = MOOD_WARM):
    syns = round_ctx.get("synonyms") or []
    if isinstance(syns, str):
        syns = [] if syns == "None" else [syns]
    base = HOST_SYSTEM_PROMPT_TEMPLATE.format(
        WORD=round_ctx["word"],
        SYNONYMS=", ".join(syns) if syns else "(yok)",
        CLUE=round_ctx["clue"],
        REVEALED=" ".join(state.revealed_letters) if state.revealed_letters else "(henüz yok)",
        SCORE=state.total_score,
        MODE_DESCRIPTION=_ANSWER_PHASE_DESC if in_answer_mode else _HINT_PHASE_DESC,
        MODE_RULES=_ANSWER_PHASE_RULES if in_answer_mode else _HINT_PHASE_RULES,
    )
    mood_line = MOOD_DESCRIPTIONS.get(mood, MOOD_DESCRIPTIONS[MOOD_WARM])
    return base + f"\nRUH HALİ:\n- {mood_line}"


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


# Scripted bank structure:
#   _STUCK_BANKS[phase][mood] = [lines...]
#   phase ∈ {"answer", "hint"}; mood ∈ {warm, playful, teasing}.
#
# Warm = default voice (large bank, used when no specific signal).
# Playful = fires when state.last_was_close is true — player is near the
#           answer and the host noticed, so the tone is "almost there!"
# Teasing = fires after 3+ wrong real-word guesses in the round — light
#           Ali İhsan Varol-style ribbing, never mean.
_STUCK_BANKS = {
    "answer": {
        MOOD_WARM: [
            "\"ipucu\" derseniz size bir ipucu hazırlayabilirim...",
            "Vazgeçmek yok efendim, bir ipucu ile bulabilirsiniz...",
            "Bir ipucu mu istesek..? Yardımı dokunabilir...",
            "Düşünmeye devam edelim efendim, ipucu da isteyebilirsiniz...",
            "İpucu isteyin, belki tek kelime yeter dilinizin ucundakini çözmeye...",
            "Şöyle bir ipucu fena olmaz mı sizce? Yazmanız yeter, getireyim...",
            "Henüz vakit var, bir ipucu sizi toparlayabilir efendim...",
            "İpucu silahınız hâlâ elinizde, kullanmaktan çekinmeyin...",
            "Pes etmeyin efendim, bir ipucu yetebilir...",
            "Bir ipucu daha mı istesek..? Belki çözülür düğüm...",
        ],
        MOOD_PLAYFUL: [
            "Bu kadar yaklaşmışken pes yok efendim, bir ipucu yetebilir...",
            "Dilinizin ucundayken bırakmak olmaz, ipucu mu istesek?",
            "Az kaldı, az... Bir ipucu son perdeyi açar efendim...",
            "Çok yakın olduğunuzu söylemiştim, ipucu son sayfayı çevirir...",
            "Bir ipucu hâlâ elinizde efendim, son adımı atmak için...",
            "Saniyeler önemli, ama bir ipucu sizi tam oraya götürebilir...",
        ],
        MOOD_TEASING: [
            "Birkaç farklı yön denediniz, bir ipucu ile dalga geçmeyi keselim mi?",
            "Hadi efendim, bu sefer ipucu ile çözmeyi şereflendirin...",
            "Israrcılık güzel, ama ipucu daha güzel — vakit varken...",
            "Tamam tamam, sizi anlıyorum — ipucu ile yardım edeyim ben...",
            "Şu kapıyı zorlamayı bırakın efendim, ipucu ile yan kapıdan girelim...",
            "Bu kadar yanlıştan sonra ipucu hak ettiniz desem yeridir...",
        ],
    },
    "hint": {
        MOOD_WARM: [
            "Efendim, hadi bir harf mi alsak..? \"h\" yazmanız yeter.",
            "\"ipucu\" derseniz size bir ipucu hazırlayabilirim...",
            "Yavaş yavaş... Bir harf açalım, bakın içiniz açılır...",
            "Vazgeçmek yok efendim, bir ipucu ile bulabilirsiniz...",
            "Bir harf açın efendim, bazen tek bir harf her şeyi anlatır...",
            "İsterseniz harf alalım, isterseniz ipucu — siz seçin...",
            "Bir harf daha, bir adım daha... \"h\" yazın efendim...",
            "Hadi bir harf daha açalım, içinize doğan ne varsa söyleyiverin...",
            "Ufak bir ipucu mu istesek, belki dilinizin ucuna geliyor...",
            "Bir harf, sonra bir nefes, sonra bir tahmin... Olur mu efendim?",
        ],
        MOOD_PLAYFUL: [
            "Dilinizin ucunda efendim — yine bir harf alsak mı?",
            "Az kaldı, biliyorum hissediyorum... Bir harf daha mı..?",
            "Çok yakınız efendim, bir ipucu ile tamamen çözebilirsiniz...",
            "Vazgeçmek yok — kelime burnunuzun dibinde...",
            "Şöyle bir ipucu, son bir tık kadar uzaktayız efendim...",
            "Tam olacakken duruyorsunuz — hadi bir ipucu daha...",
        ],
        MOOD_TEASING: [
            "Hadi efendim, biraz daha farklı bir yön deneyelim...",
            "Şu kadar yanlış cevaptan sonra bir harf cidden işinize yarar...",
            "İnatçılığınızı sevdim ama yön değiştirmenin vakti — bir ipucu?",
            "Daha bir süre böyle gidecek galiba, bir ipucu ile rahatlasak mı?",
            "Cesur tahminler güzel ama cesarete ipucu eklenince... iyi olur efendim...",
            "Ne yapsanız oluyor, bir ipucu ile başka kapı arayalım mı?",
        ],
    },
}


def scripted_stuck_reply(in_answer_mode: bool = False, mood: str = MOOD_WARM):
    """Reply when the player signals they're stuck.

    in_answer_mode = True means the player has pressed 'bb' and is now in
    the 45s answer phase, where letter requests are NOT allowed. We must
    NOT suggest pressing 'h' in that case.
    """
    bucket = _STUCK_BANKS["answer" if in_answer_mode else "hint"]
    bank = bucket.get(mood, bucket[MOOD_WARM])
    return random.choice(bank)


_SILENCE_BANKS = {
    "answer": {
        MOOD_WARM: [
            "Zaman akıyor efendim...",
            "Hâlâ orada mısınız..?",
            "Düşünüyorsunuz, biliyorum... Yine de zaman akıyor...",
            "Hmm... İpucu ister misiniz?",
            "Bakalım, bir şey geldi mi aklınıza?",
            "Efendim, dalıp gittiniz sanırım...",
            "Saniyeler ilerliyor, bir tahmin yetebilir...",
            "Sessizlik bozulsun, ne dersiniz efendim?",
            "İçinize doğan bir şey var mı acaba?",
            "Aklınıza ilk geleni söyleyin bakalım, belki tutar...",
            "Şu an aklınızdan geçeni duysam ne iyi olurdu...",
            "İpucu mu, yoksa cesur bir tahmin mi?",
        ],
        MOOD_PLAYFUL: [
            "Çok yakındaydınız efendim, hatırlayın...",
            "Dilinizin ucunda, vakit akıyor...",
            "Az kaldı, son bir tık daha...",
            "Söylemek üzereydiniz sanki, çıkarın bakalım...",
            "Hatırlayın o kelimeyi, az önce yakındaydı...",
            "Geliyor mu efendim, geliyor mu?",
        ],
        MOOD_TEASING: [
            "Sessizlik mi, yoksa yeni bir yön mü düşünüyorsunuz?",
            "Şu kadar farklı tahminden sonra biraz mola fena değil...",
            "Hadi efendim, son bir hamle...",
            "Israrla yanlış kelimeleri bırakıp gerçek olanı düşünelim mi?",
            "Belki gerçek cevap aklınızdadır da söylemiyorsunuz..?",
            "Vazgeçmemenizi seviyorum, ama saatler döndü efendim...",
        ],
    },
    "hint": {
        MOOD_WARM: [
            "Zaman akıyor efendim...",
            "Hâlâ orada mısınız..?",
            "Bir harf mi alsak..?",
            "Düşünüyorsunuz, biliyorum... Yine de zaman akıyor...",
            "Hmm... İpucu ister misiniz?",
            "Bakalım, bir şey geldi mi aklınıza?",
            "Efendim, dalıp gittiniz sanırım...",
            "Bir harf açın, görsel hafıza güçlüdür efendim...",
            "Saatler işliyor, bir adım atalım mı?",
            "İçinize doğan bir kelime var mı acaba?",
            "Şöyle bir harf daha, sonra ne diyeceğinize bakarız...",
            "Tek bir harf bazen perdeyi aralar efendim...",
            "Sessizlik bozulsun istesek mi acaba?",
        ],
        MOOD_PLAYFUL: [
            "Çok yakınız efendim, biraz daha düşünün...",
            "Dilinizin ucunda, hissediyorum — şöyle bir nefes alın...",
            "Vurmak üzeresiniz, son düşünce...",
            "Bir tık kaldı efendim, sabırla...",
            "Az ötede duruyor o kelime, biraz daha...",
            "Saniyeler değerli, ama düşünceniz iyi yöne gidiyor — devam...",
        ],
        MOOD_TEASING: [
            "Belki başka bir açıdan bakmak gerek efendim?",
            "Aynı yolda gitmeyelim, yeni bir tahmin?",
            "Sessizlik düşünce mi, yoksa şaşkınlık mı..?",
            "Hadi farklı bir şey deneyin, ne çıkacağına bakalım...",
            "Israrınıza hayranım, ama yön değişikliği iyi gelir...",
            "Tam olacakken durduk galiba — başka bir açıdan?",
        ],
    },
}


def scripted_silence_reply(in_answer_mode: bool = False, mood: str = MOOD_WARM):
    """Proactive line when the player goes quiet. Phase-aware: never
    suggest 'h' (letter request) during the 45s answer phase."""
    bucket = _SILENCE_BANKS["answer" if in_answer_mode else "hint"]
    bank = bucket.get(mood, bucket[MOOD_WARM])
    return random.choice(bank)


# --------------------------------------------------------------------------
# Host fallback (called when no keyword branch matched)
# --------------------------------------------------------------------------


def llm_host_reply(llm, state, round_ctx, user_input, history,
                   in_answer_mode: bool = False, mood: str = MOOD_WARM):
    """Free-form host reply for inputs that don't match any keyword branch.

    history: list of (role, text) for THIS round only.
    in_answer_mode: True when the player has pressed 'bb' (cannot request letters).
    mood: tone signal (warm/playful/teasing) used both for the LLM system
          prompt and the scripted fallback.
    Returns a safe string, never None. Never leaks the target word.
    """
    if llm is None:
        return scripted_stuck_reply(in_answer_mode, mood=mood)

    messages = [{"role": role, "content": text} for role, text in history[-6:]]
    messages.append({"role": "user", "content": user_input})

    try:
        raw = llm.chat(
            system=host_system_prompt(state, round_ctx, in_answer_mode, mood=mood),
            messages=messages,
            max_tokens=150,
        )
    except (LLMError, Exception):
        return scripted_stuck_reply(in_answer_mode, mood=mood)

    clean = sanitize_reply(raw, round_ctx["word"], round_ctx.get("synonyms"))
    return clean if clean else scripted_stuck_reply(in_answer_mode, mood=mood)


def llm_silence_reply(llm, state, round_ctx, in_answer_mode: bool = False,
                      mood: str = MOOD_WARM):
    """Proactive line when player goes quiet. 70% scripted, 30% generated.

    in_answer_mode: True when player has pressed 'bb'. Scripted/LLM lines
    will not suggest 'h' (letter request) in that mode.
    mood: tone signal — colors both the LLM prompt and scripted fallback.
    """
    if random.random() > SILENCE_LLM_PROBABILITY or llm is None:
        return scripted_silence_reply(in_answer_mode, mood=mood)
    try:
        raw = _chat_maybe_low_priority(
            llm,
            system=host_system_prompt(state, round_ctx, in_answer_mode, mood=mood),
            messages=[{"role": "user", "content": "(Oyuncu sessiz kaldı, nazikçe dikkatini çek.)"}],
            max_tokens=120,
        )
    except Exception:
        return scripted_silence_reply(in_answer_mode, mood=mood)
    clean = sanitize_reply(raw, round_ctx["word"], round_ctx.get("synonyms"))
    return clean if clean else scripted_silence_reply(in_answer_mode, mood=mood)


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


# --------------------------------------------------------------------------
# Scripted prologue bank — keyword-bucketed fallback for demo mode
# --------------------------------------------------------------------------

# Buckets of intent → matching tokens. First bucket whose tokens overlap the
# last user message wins. Order matters: more specific intents come first so
# generic greetings don't swallow "nasılsınız" / "teşekkür ederim".
_PROLOGUE_BUCKETS: list[tuple[str, frozenset[str]]] = [
    ("ready", frozenset({
        "hazırım", "hazirim", "hazır", "hazir", "başlayalım", "baslayalim",
        "başla", "basla", "haydi", "hadi",
    })),
    ("thanks", frozenset({
        "teşekkür", "tesekkur", "teşekkürler", "tesekkurler", "sağol",
        "sagol", "sağolun", "sagolun", "mersi", "eyvallah",
    })),
    ("how_are_you", frozenset({
        "nasılsın", "nasilsin", "nasılsınız", "nasilsiniz", "naber",
        "neyin", "keyifler",
    })),
    ("nervous_excited", frozenset({
        "heyecan", "heyecanlı", "heyecanliyim", "heyecanlıyım", "gergin",
        "stres", "stresli", "korkuyorum", "merak", "sabırsız", "sabirsiz",
        "sabırsızlanıyorum",
    })),
    ("weather", frozenset({
        "hava", "soğuk", "soguk", "sıcak", "sicak", "yağmur", "yagmur",
        "kar", "güneş", "gunes", "rüzgar", "ruzgar",
    })),
    ("location", frozenset({
        "istanbul", "ankara", "izmir", "bursa", "antalya", "adana",
        "trabzon", "nereden", "neredesin", "nerelisin", "şehir", "sehir",
    })),
    ("rules", frozenset({
        "kural", "nasıl", "oynanıyor", "oynanir", "oynanır",
        "puan", "süre", "sure", "yapacağız", "yapacagiz",
    })),
    ("greeting", frozenset({
        "merhaba", "selam", "selamlar", "selamlar", "hoş", "iyi",
        "günler", "akşamlar", "geceler", "kolay", "gelsin", "selamünaleyküm",
    })),
]

_PROLOGUE_REPLIES: dict[str, list[str]] = {
    "ready": [
        "Aferin efendim, ben de tam başlamak üzereydim...",
        "İşte bu cesaret hoşuma gitti, başlıyoruz...",
        "Çok güzel — birazdan ilk soruyu açıyorum, hazır olun...",
    ],
    "thanks": [
        "Rica ederim efendim, asıl ben teşekkür ederim...",
        "Estağfurullah, daha bir şey yapmadık ki...",
        "Ne demek efendim, sizi ağırlamak benim için zevk...",
        "Estağfurullah, asıl bana keyif veriyor sizinle olmak...",
    ],
    "how_are_you": [
        "Çok iyiyim efendim, hele sizi karşımda görünce daha da iyi oldum...",
        "Keyfimiz yerinde efendim, sahnemiz hazır, sıra sizde...",
        "İyiyim efendim, soluk soluğa hazırlandık bu yarışmaya...",
        "Çok şükür, gayet iyiyim... Siz nasılsınız bakalım?",
    ],
    "nervous_excited": [
        "Heyecanı bırakın efendim, sahne ışıkları sıcacık, korkacak bir şey yok...",
        "Heyecan iyidir efendim, sahneye o lezzeti katar...",
        "Derin bir nefes alın efendim, beraber yürüyeceğiz bu yolu...",
        "Sakin olun efendim, ben de buradayım... Birlikte halledeceğiz...",
    ],
    "weather": [
        "Hava nasıl olursa olsun, içeride bizim sahnemiz hep ılık efendim...",
        "Aman havayı boş verin, biz burada kelimelerle ısınırız...",
        "Hava güzel ya da değil, biraz Türkçe ile başımızı dağıtalım...",
    ],
    "location": [
        "Nereden olursanız olun efendim, sahnemiz size açık...",
        "Türkçe konuştuğumuz her yer bizim memleketimiz efendim...",
        "Memleketin neresi olursa olsun, biz hep aynı kelime sevdasındayız...",
    ],
    "rules": [
        "Detaylara takılmayın efendim, ilerledikçe oturacak her şey...",
        "Önce bir başlayalım, gerisi gelir... Yanınızdayım nasılsa...",
        "Aklınızda soru kalsın efendim, ilk soruda gösterirken anlatırım...",
    ],
    "greeting": [
        "Merhabalar efendim, hoş geldiniz sahnemize...",
        "Selam olsun size de efendim, sefa getirdiniz...",
        "Hoş geldiniz efendim, sizi burada görmek ne güzel...",
        "Merhaba efendim, aramıza katıldığınıza çok sevindim...",
    ],
    "fallback": [
        "Anladım efendim, hadi yavaş yavaş ısınalım...",
        "Hmm, güzel söylediniz... Hazır olduğunuzda başlayalım...",
        "Öyle mi efendim... Sahnemiz hazır, biz sizi bekliyoruz...",
        "Tamamdır efendim, vaktiniz olunca başlayabiliriz...",
        "Çok güzel... Ne zaman isterseniz başlarız efendim...",
        "Sizi dinlemek güzel efendim, hadi keyifle başlayalım...",
    ],
}

_PROLOGUE_OPENERS = [
    "Çok sevindim sizi burada görmeye efendim, hadi biraz Türkçe ile haşır neşir olalım...",
    "Hoş geldiniz efendim, sahnemiz sizinle daha da bir güzelleşti...",
    "Buyrun efendim, oturun bir kahve içelim — sonra ilk soruya geçelim...",
    "Hoş geldiniz, sefa getirdiniz... Hazır olduğunuzda başlıyoruz efendim...",
]


def _classify_prologue(text: str) -> str:
    """Pick the first prologue bucket whose keywords match `text`.

    Keywords of length ≥4 match by prefix on any token (so `kural` catches
    `kuralları`, `istanbul` catches `istanbul'dan`); shorter keywords must
    match a token exactly (so `kar` doesn't fire on `karanlık`).
    """
    if not text:
        return "fallback"
    low = UnicodeTr(text).lower()
    try:
        toks = set(nltk.word_tokenize(low))
    except Exception:
        toks = set(low.split())
    for label, keywords in _PROLOGUE_BUCKETS:
        for kw in keywords:
            if len(kw) >= 4:
                if any(t.startswith(kw) for t in toks):
                    return label
            elif kw in toks:
                return label
    return "fallback"


def scripted_prologue_reply(messages) -> str:
    """Bucket-based scripted prologue reply for demo mode (and as a safety
    net when the LLM returns nothing). Reacts loosely to the last user
    message instead of repeating one canned line."""
    # Opener path: only the seeded "Merhaba" is present.
    if len(messages) == 1 and messages[0].get("role") == "user":
        first = (messages[0].get("content") or "").strip().lower()
        if first in {"merhaba", "selam", "selamlar"}:
            return random.choice(_PROLOGUE_OPENERS)

    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = m.get("content") or ""
            break

    bucket = _classify_prologue(last_user)
    return random.choice(_PROLOGUE_REPLIES.get(bucket, _PROLOGUE_REPLIES["fallback"]))


def prologue_reply(llm, messages):
    """One turn of pre-game small talk. Returns the host's reply string.

    In demo mode (llm is None) and on any LLM failure, returns a
    keyword-bucketed scripted line based on the last user message — so
    the host stays varied and responsive instead of repeating one canned
    sentence.
    """
    scripted = scripted_prologue_reply(messages)
    return safe_chat(
        llm,
        PROLOGUE_SYSTEM_PROMPT,
        messages,
        max_tokens=150,
        fallback=scripted,
    )
