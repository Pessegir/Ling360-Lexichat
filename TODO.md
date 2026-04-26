# LEXI-CHAT — Modernization & Refinement TODO

Project survey and refinement plan. Built 2023 as a computational linguistics course project (Sabancı Üniversitesi, LING 360). Original authors: Fatma Müge Akcan, Nurullah Ertaş, Stenai Nuh.

---

## 1. Security (urgent — addressed but still needs cleanup)

- [x] **Exposed OpenAI API key** in `datakey.json` committed to public GitHub. User confirmed the key has been revoked.
- [ ] Remove `datakey.json` from the working tree; add it to `.gitignore`.
- [ ] Replace with `datakey.example.json` showing the expected shape, plus instructions to copy → rename → fill in.
- [ ] *(Optional but recommended)* Purge the key from git history with `git filter-repo` or BFG, then force-push. Otherwise anyone can recover the key by looking at old commits.

---

## 2. Broken / outdated code (won't run as-is today)

### 2.1 OpenAI SDK
The code uses the pre-1.0 API that no longer exists:
```python
openai.api_key = ...
openai.ChatCompletion.create(...)
response["choices"][0]["message"]["content"]
```
Must be migrated to the `openai>=1.x` client pattern:
```python
from openai import OpenAI
client = OpenAI(api_key=...)
client.chat.completions.create(...)
response.choices[0].message.content
```

Called in: `origin_of_the_words`, `Structure_of_Word`, `Gpt_Prologue`, `example_sentence`.

### 2.2 Retired model
- `gpt-3.5-turbo-0301` has been retired. `gpt-3.5-turbo` still routes somewhere but is legacy.
- Recommend upgrading to `gpt-4o-mini` or `gpt-4.1-mini` — cheaper, better Turkish, much better at following the "two words only" / "compound or not" style prompts.

### 2.3 Colab-isms inside the `.py` file
The `.py` was exported from a Colab notebook and still contains:
- `!pip install openai`, `!pip install zemberek-python`, `!pip install git+...`
- `from IPython.display import clear_output, display, HTML`
- Hard-coded path `/content/gts (1).json` inside `compound_function` and `example_sentences_function`

None of these run outside Colab. Needs to be split:
- Real `requirements.txt` for installs
- Replace `clear_output()` with a cross-platform screen clear (or drop it)
- Replace `display(HTML(...))` for the survey link with a plain `print(link)`
- Use a config-driven data path instead of `/content/...`

### 2.4 Filename with space
`gts (1).json` — renamed to `gts.json` (referenced everywhere with the space, which breaks on some shells/paths).

### 2.5 Runtime download of the Bilkent corpus
`lexichat_game.py:65` downloads a 22 MB CSV from GitHub every launch. If the URL breaks, the game breaks. Options:
- Cache it locally on first run (download → save → reuse).
- Or replace with a smaller pre-built frequency list we ship with the repo (much smaller than 22 MB).

### 2.6 Giant data file in repo
`gts (1).json` is 91 MB. It's the Turkish dictionary. Two loads of it happen in `compound_function` and `example_sentences_function`, each parsing the full file from disk. Plan:
- Load once at startup into a dict keyed by `madde` (headword).
- Either strip it down to only what the game actually uses (compound forms + example sentences) to shrink the repo, or keep it full but document that it's large.

---

## 3. Correctness bugs I spotted

- **`lexichat_game.py:347`** — `random.randint(0, (len(negative_phrases)))` is off-by-one; upper bound should be `len(...) - 1`. Will occasionally throw `IndexError`.
- **`lexichat_game.py:413, 1105`** — references `phrases_list_else` inside a branch that only defines `phrases_list_empty`. Will `NameError` when the user submits empty input before any other branch has set `phrases_list_else`.
- **`lexichat_game.py:456`** — malformed string `"...\Moral bozmak..."` (backslash-M instead of `\n`). Cosmetic but ugly.
- **`lexichat_game.py:877`** — `example_gts = example_sentences_function(word_list)` but `word_list` isn't defined yet at that point (only `selected_words` is). This is a latent bug shadowed by the `while True: try/except` — it silently retries on `NameError`.
- **`Round_Time`** — uses a **blocking** `input()` inside a thread while the main thread counts down. On Windows this is especially flaky: `input()` can't be interrupted cleanly, so if the timer expires, the input thread stays blocked until the user hits Enter. Needs a rethink (either `msvcrt` on Windows, `select` on Unix, or — better — a single event loop with `prompt_toolkit` or a small Tk/web UI).
- **Mutable global `revealed_letters`** shared across rounds; sometimes cleared, sometimes not. Sources of subtle bugs.
- **`clean_string` computed but unused** in several GPT functions — leftover dead code.

---

## 4. Architecture / refactor

- **All module-level side effects**: the file downloads corpus, loads 91 MB JSON, calls GPT, runs `select_words_and_meanings`, etc. as soon as you `import` it. None of this should happen at import time.
- **Single 1243-line file**. Suggested split:
  ```
  lexichat/
    __init__.py
    config.py          # API key loading, model name, paths
    data_loader.py     # word lists, gts.json, corpus
    host_gpt.py        # all OpenAI calls (origin, structure, prologue, example)
    nlp.py             # POS, synonyms, morphology, edit-distance helpers
    game_state.py      # round, score, revealed letters (no globals)
    hints.py           # hint selection logic
    ui_cli.py          # input/output, timer, threading
    main.py            # run()
  ```
- **Globals**: `total_score`, `word`, `username`, `start_com`, `is_paused`, `total_time`, `resume_time`, `active_input_bb`, `chosen_phrase`, `revealed_letters`. Replace with a `GameState` dataclass passed explicitly.
- **Pre-compute all GPT calls upfront**: currently the game calls GPT for origin/structure/example *before* round 1 starts, serially (28+ API calls). Easy win: parallelize with `asyncio` + `AsyncOpenAI`, or drop to a single batched prompt ("for these 14 words, return origin+structure+example as JSON"). Cuts startup from ~30 s to ~3 s and costs less.

---

## 5. UX & gameplay refinements (ideas — want your input)

The README mentions you want "some important updates" — here are candidate areas. Tell me which matter:

- **Difficulty levels**: today it's always 14 words, 4→10 letters, 5 min. Could add Easy/Normal/Hard.
- **Replay without re-selecting words**: right now each `run()` re-fetches GPT hints. Cache hints per word.
- **Score history**: save to a local `scores.json` so players can see their best.
- **Better timer UX**: the current countdown overwrites in place with `\r`, and input lines collide with the countdown. Looks messy. A proper TUI (Rich/Textual) would clean this up a lot.
- **Offline mode**: let the game run without an API key (skip GPT prologue, use pre-generated hints only).
- **Host persona tuning**: the prompts mimic Ali İhsan Varol. With `gpt-4o-mini` we can get much more in-character responses.
- **Skip question / give up**: no way to skip a word you really don't know beyond letting the timer tick.
- **Logging**: keep a log of each session (word, guesses, time taken, score) for analysis — useful since this started as a linguistics project.

---

## 6. Proposed order of work

1. **Safety net**: `.gitignore` + `datakey.example.json`, rename `gts (1).json` → `gts.json`.
2. **Make it run**: requirements.txt, migrate to `openai>=1.x`, upgrade model, remove Colab-isms, fix the off-by-one bugs.
3. **Data layer**: load gts.json once; cache corpus locally.
4. **Refactor**: split into modules, kill globals, pre-compute hints in parallel.
5. **UX pass**: pick from §5 based on what you care about.
6. **Tests**: a few sanity tests for `select_words_and_meanings`, `LetterRequest`, hint logic.

---

## Open questions for you

1. **Keep it as a CLI Python app**, or would you rather turn it into a small web app (Streamlit / FastAPI + tiny frontend) so it's easier to share?
2. **Stay on OpenAI**, or open to an alternative (Anthropic Claude / a local Turkish LLM)? Turkish quality differs noticeably between providers.
3. **Which items from §5 matter most to you?** You mentioned "important updates" — name them and we'll prioritize.
4. **Windows vs. Mac/Linux** for running it? Affects the threading/input decision.
5. **Are the other two contributors still involved?** Matters for whether we preserve git history style, whether force-pushing to clean secrets is OK, etc.
