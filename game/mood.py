"""Host mood — same persona, different energy.

Pure function `compute_mood(state)` returns one of MOOD_WARM / MOOD_PLAYFUL /
MOOD_TEASING based on per-round signals on GameState. The mood label feeds
both the LLM system prompt (`MOOD_DESCRIPTIONS`) and the scripted bank
selectors in `game.host` so demo mode benefits too.

MOOD_CELEBRATORY is used directly by the win celebration path (not picked
by compute_mood), since the win signal is unambiguous and one-shot.
"""
from __future__ import annotations

MOOD_WARM = "warm"
MOOD_PLAYFUL = "playful"
MOOD_TEASING = "teasing"
MOOD_CELEBRATORY = "celebratory"

ALL_MOODS = (MOOD_WARM, MOOD_PLAYFUL, MOOD_TEASING, MOOD_CELEBRATORY)

# Wrong-guess attempts in current round needed to flip into teasing.
# 3 lets first-pass exploration breathe but catches the "ben yine de
# tahmin ediyorum" loop.
TEASING_THRESHOLD = 3


def compute_mood(state) -> str:
    """Return the mood that should color the host's next line.

    Reads state.wrong_streak and state.last_was_close — both updated by
    `_handle_input` after each player turn. Teasing wins over playful so
    repeated wrong guesses don't get over-encouraged.
    """
    if state.wrong_streak >= TEASING_THRESHOLD:
        return MOOD_TEASING
    if state.last_was_close:
        return MOOD_PLAYFUL
    return MOOD_WARM


# One-paragraph mood description injected into the LLM system prompt so
# the model can color its tone without needing a separate prompt per mood.
MOOD_DESCRIPTIONS = {
    MOOD_WARM: (
        "Şu an varsayılan modundasın — sıcak, destekleyici ve cömert bir TV "
        "sunucusu gibi konuş."
    ),
    MOOD_PLAYFUL: (
        "Oyuncu cevaba çok yakın! Onaylayıcı ve oyunbaz ol — "
        "\"yaklaştınız\", \"az bir şey kaldı\", \"dilinizin ucunda\" gibi "
        "nüanslarla cesaretlendir, ama doğru cevabı açıkça verme."
    ),
    MOOD_TEASING: (
        "Oyuncu üst üste birkaç yanlış cevap verdi. Sevecen bir şekilde "
        "takıl, Ali İhsan Varol gibi hafif şakacı bir tonla nazikçe iğnele — "
        "asla küçük düşürme, hep \"siz\" ve \"efendim\" diyerek."
    ),
    MOOD_CELEBRATORY: (
        "Oyuncu doğru cevabı verdi! Coşkulu, alkışlayan, gerçekten sevinen "
        "bir sunucu gibi tepki ver — ama yine kısa kal."
    ),
}
