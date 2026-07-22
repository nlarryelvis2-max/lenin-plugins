#!/usr/bin/env python3
"""
slow_read_gate — forcing-член против цикла №1 (read-before-infer).
UserPromptSubmit hook. Когда во входящем промпте есть ПРИЗНАКИ чужого текста
к разбору (длинная цитата, транскрипт, объявление, путь к .txt/.html, большой
объём) — ПРИНУДИТЕЛЬНО впрыскивает директиву: читать дословно ДО интерпретации
+ подсветить психологические аспекты, которые могут откликаться.

Реализация решения Фила (2026-06-20): «как hook запиши, что нужно читать
медленнее; пока читаешь медленнее — подсвечивай психологические аспекты».
Это floor V(t) в error_cycles_ode.md — держит R=V/S над порогом R*.
"""
import sys, json, re

THRESH_WORDS = 120          # длинный входящий текст
MARKERS = [
    "транскрипт", "объявлен", "переписк", "сообщени", "диалог", "цитат",
    "messages", "_chat", ".txt", ".html", "докум", "письмо", "отзыв",
    "speaker", "спикер", "вот текст", "разбери", "проанализируй текст",
]

def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    prompt = (data.get("prompt") or "")
    low = prompt.lower()
    words = len(prompt.split())

    has_marker = any(m in low for m in MARKERS)
    long_quote = bool(re.search(r'[«"“].{80,}', prompt))
    big = words >= THRESH_WORDS

    # СИГНАТУРА ВЫСОКОЙ ЭНТРОПИИ (эмпирика 2026-06-20: срывы коррелируют с диктовкой,
    # не с длиной). Срыв-режим Фила = поток без структуры.
    punct = prompt.count('.') + prompt.count(',') + prompt.count('?') + prompt.count('!')
    no_punct = words > 40 and punct < words / 25          # длинно и почти без пунктуации
    tak_dalee = bool(re.search(r'и так далее|и т\.?д|в этом роде|и тому подоб', low))
    multi_topic = low.count(' значит ') + low.count(' то есть ') >= 2
    entropy_sig = sum([no_punct, tak_dalee, multi_topic]) >= 2  # ≥2 признака = поток

    if not (has_marker or long_quote or big or entropy_sig):
        return  # обычный короткий структурный промпт — не мешаем

    directive = (
        "── ⏳ slow-read gate (forcing-член, цикл №1) ──\n"
        "Во входящем есть чужой текст к разбору. ПЕРЕД любым синтезом — три слоя, по порядку:\n"
        "1. ДОСЛОВНО: что буквально написано (каждое утверждение отдельно, без достройки).\n"
        "2. СВЕРКА: что написано vs что я думаю что написано (поймать раннюю интерпретацию).\n"
        "3. ПСИХО-АСПЕКТЫ: что здесь может откликаться у Фила — паттерн, перенос, скрытая динамика,\n"
        "   терапевтический/реляционный слой (synthesist + therapist). Подсветить, не диагностировать.\n"
        "Только после трёх слоёв — вывод. И параллельной линией — где это в ХРОНОЛОГИИ (правило explanation-forms §2).\n"
        "Не дочитал до конца предложения — не интерпретируй (feedback_read_before_infer)."
    )
    print(directive)

if __name__ == "__main__":
    main()
