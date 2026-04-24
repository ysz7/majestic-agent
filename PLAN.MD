# majestic-agent — PLAN.MD

> База: **Parallax** (ysz7/Parallax)  
> Ориентир по архитектуре: **Hermes Agent** (NousResearch/hermes-agent)
> Код, коментарии и тд для агента всегда на анг
---

## Идеология

majestic-agent — это **универсальный агент-исполнитель**. Не research tool, не чатбот с меню команд.

**Главный принцип:** дай задачу — агент сам разберётся как её выполнить.

- Запускается легко, настраивается минимально
- Агент сам выбирает нужные инструменты под задачу
- Новый функционал = новый файл в `tools/` — больше ничего не нужно менять
- Research, маркет, брифинги — это просто один из toolsets, не основа
- Slash команды (`/research`, `/briefing` и т.д.) — shortcuts, не обязательны
- Работает с любой задачей: research, файлы, веб, системные задачи, внешние программы
- Подключил новую интеграцию → агент автоматически умеет с ней работать

**Пример:**
```
"Сделай брифинг по крипто рынку и отправь мне в Telegram"  
→ агент сам вызывает нужные инструменты и выполняет
```
```
"Открой Excel и заполни колонку B данными из последнего отчёта"  
→ агент использует инструмент для работы с Excel
```

---

## Сравнение репозиториев

### Parallax — что есть сейчас

| Область | Детали |
|---|---|
| **Цель** | Personal research agent: сбор сигналов из 8 веб-источников, скоринг LLM, маркет-данные, брифинги |
| **Интерфейсы** | CLI (`cli.py`) + Telegram бот (`bot.py`) |
| **LLM** | Ollama (локально) или Anthropic API |
| **Хранилище** | ChromaDB (RAG), SQLite (маркет-история), файлы `data/exports/` |
| **Память** | Нет persistent memory между сессиями |
| **Сессии** | Нет хранения истории диалогов — каждый запуск с чистого листа |
| **Платформы** | Только Telegram + CLI |
| **Инструменты** | Жёстко зашитые: RSS, Reddit, HN, GitHub Trending и т.д. |
| **Навыки/Skills** | Отсутствуют |
| **Агент-луп** | Нет — каждая команда это отдельный вызов LLM |
| **Планировщик** | Auto-research interval + morning briefing (asyncio) |
| **Деплой** | Docker Compose |

### Hermes Agent — что есть там

| Область | Детали |
|---|---|
| **Цель** | Self-improving agent: grows with you, persistent memory, learning loop |
| **Интерфейсы** | Full TUI CLI + Telegram, Discord, Slack, WhatsApp, Signal и др. |
| **LLM** | Любой провайдер через OpenRouter, или напрямую Anthropic, OpenAI и др. |
| **База данных** | SQLite (`~/.hermes/state.db`) — WAL mode, FTS5, schema versioning |
| **Память** | MEMORY.md + USER.md, inter-session recall через FTS5 |
| **Сессии** | Полное хранение истории: sessions + messages + token costs + tool calls |
| **Платформы** | 15+ платформ из одного gateway процесса |
| **Инструменты** | 40+ инструментов, toolsets, MCP-серверы |
| **Навыки/Skills** | Skills system — агент создаёт навыки из опыта, они улучшаются при использовании |
| **Агент-луп** | Настоящий agentic loop с context compression и sub-агентами |
| **Планировщик** | Built-in cron с доставкой на любую платформу |
| **Деплой** | Local, Docker, SSH, Modal (serverless) |

---

## Хранилище данных

### Что использует Hermes
1. **SQLite** (`~/.hermes/state.db`) — сессии, история диалогов, FTS5 поиск
2. **Markdown файлы** — `MEMORY.md`, `USER.md`, навыки в `skills/*.md`
3. **Внешние memory провайдеры** (опционально) — Honcho, Mem0 и др.

ChromaDB в Hermes нет.

### Решение для majestic-agent — один файл, одна директория

**ChromaDB убираем.** Заменяем на `sqlite-vec` — векторный плагин для SQLite.  
Всё хранится в одном файле `state.db`. Один бэкап покрывает всё.

**Таблицы в `state.db`:**
```
state.db
├── sessions          # сессии: id, source, model, tokens, cost, parent_session_id
├── messages          # история диалогов: role, content, tool_calls, timestamp
├── messages_fts      # FTS5 — full-text search по всем сообщениям
├── market_history    # цены крипто/акций/форекс (из Parallax)
├── schedules         # cron расписания
├── vectors           # sqlite-vec — RAG вместо ChromaDB
└── schema_version    # версия схемы для миграций
```

**Директория `~/.majestic-agent/`:**
```
~/.majestic-agent/
├── state.db        # единая база данных — всё выше
├── memory/
│   ├── memory.md   # факты агента о себе и задачах
│   └── user.md     # профиль пользователя
├── skills/
│   └── *.md        # навыки агента
├── exports/        # брифинги, отчёты
├── .env            # секреты: API ключи, токены платформ
└── config.yaml     # настройки: модель, платформы, cron и т.д.
```

Бэкап одной командой:
```bash
tar -czf backup.tar.gz ~/.majestic-agent/
```

Все пути через одну переменную:
```bash
MAJESTIC_HOME=~/.majestic-agent  # default
```

### Конфиг — как у Hermes

Секреты и настройки разделены:
- **`~/.majestic-agent/.env`** — только секреты: API ключи, токены Telegram/Discord и т.д.
- **`~/.majestic-agent/config.yaml`** — все остальные настройки: модель, платформы, cron и т.д.

Пользователь никогда не редактирует файлы руками — всё через CLI:
```bash
majestic-agent setup              # полный wizard при первом запуске
majestic-agent model              # выбор провайдера и модели
majestic-agent config set key val # установить конкретное значение
```

### Деплой на сервере

Агент живёт на VPS как постоянный процесс. Пользователь подключается
с любого устройства через Telegram, Discord, WhatsApp и т.д.:

```
Телефон (Telegram/Discord/...) → VPS (majestic-agent gateway) → LLM API
```

При Docker деплое `~/.majestic-agent/` обязательно монтировать как volume:
```yaml
volumes:
  - ~/.majestic-agent:/root/.majestic-agent
```

---

## ПЛАН РАЗРАБОТКИ majestic-agent

---

### Фаза 0 — Подготовка и установка

**Цель:** Проект запускается одной командой `majestic` как у Hermes.

- [x] Очистить зависимости, убрать ChromaDB и лишнее из Parallax
- [x] Настроить структуру папок — `majestic/` пакет с `cli/`, `db/`, `constants.py`, `config.py`
- [x] `pyproject.toml` — entrypoint `majestic` (команда `majestic`, не `majestic-agent`)
- [x] `scripts/install.sh` — установочный скрипт: Python, зависимости, регистрация команды в PATH
- [x] Setup wizard `majestic setup` — интерактивная настройка при первом запуске:
  - выбор LLM провайдера и модели
  - ввод API ключей → сохраняются в `~/.majestic-agent/.env`
  - настройка платформ (Telegram и т.д.) → токены в `.env`
  - остальные настройки → `~/.majestic-agent/config.yaml`
- [x] Команды `majestic model`, `majestic config set/get`
- [x] Переменная `MAJESTIC_HOME`, все пути только через неё (`majestic/constants.py`)
- [x] `majestic doctor` — диагностика проблем конфига

---

### Фаза 1 — Persistent Storage (SQLite)

**Цель:** Единый `state.db` для всего — сессии, диалоги, векторы, маркет, расписания.

**Почему первое:** всё остальное зависит от наличия персистентного хранилища.

- [x] Установить `sqlite-vec` — векторный плагин для SQLite (замена ChromaDB)
- [x] Создать `majestic/db/state.py` — класс `StateDB`, таблицы:
  - `sessions`: id, source, user_id, model, started_at, ended_at, message_count, token_counts, estimated_cost_usd, parent_session_id, title
  - `messages`: id, session_id, role, content, tool_calls, tool_name, timestamp, finish_reason
  - `messages_fts`: FTS5 виртуальная таблица + триггеры автосинхронизации
  - `news` + `news_fts`: собранные новости с FTS5
  - `reports` + `reports_fts`: сохранённые отчёты с FTS5
  - `market_history`: symbol, price, volume, timestamp, source
  - `schedules`: id, name, cron_expr, prompt, delivery_target, last_run, next_run
  - `vector_chunks` + `vectors` (sqlite-vec): документы
  - `schema_version`: version
- [x] WAL mode + foreign keys + schema versioning + миграции (`majestic/db/migrations.py`)
- [x] Методы: `search_messages()`, `vector_search()`, `add_news_items()`, `search_news()`
- [ ] `export_session()`, `prune_sessions()` — добавить по мере необходимости

---

### Фаза 2 — Persistent Memory

**Цель:** Агент помнит пользователя и контекст между сессиями.

- [x] `~/.majestic-agent/memory/memory.md` — факты агента о задачах и знаниях
- [x] `~/.majestic-agent/memory/user.md` — профиль пользователя (предпочтения, привычки)
- [x] Загружать memory в system prompt при старте каждой сессии (`set_memory_context`)
- [x] LLM nudge после сессии — агент сам решает что запомнить (`majestic/memory/nudge.py`)
- [x] Команды: `/memory` (просмотр), `/forget <topic>` (удаление записи)

---

### Фаза 3 — Multi-Provider LLM

**Цель:** Anthropic напрямую + OpenRouter для всего остального (200+ моделей).

- [x] Абстракция `LLMProvider` с единым интерфейсом (`complete`, `stream`)
- [x] Провайдер **Anthropic** — напрямую (основной)
- [x] Провайдер **OpenRouter** — для всех остальных моделей (Ollama, OpenAI, Gemini и т.д.)
- [x] Команда `/model` — переключение без перезапуска
- [x] Подсчёт токенов и `estimated_cost_usd` — сохранять в `sessions`

---

### Фаза 4 — Agentic Loop

**Цель:** Настоящий агент-луп вместо "один запрос = один ответ".

- [x] Цикл `while not done`: LLM → tool calls → результаты → следующий turn
- [x] Tool call tracking — всё пишется в таблицу `messages`
- [x] `/stop` — прервать выполнение (Ctrl+C + stop_event)
- [ ] Context compression — при приближении к лимиту сжимать контекст, создавать дочернюю сессию через `parent_session_id`
- [x] Параллельные tool calls через `ThreadPoolExecutor`

---

### Фаза 5 — Skills System

**Цель:** Процедурная память — агент создаёт и переиспользует навыки.

- [x] `~/.majestic-agent/skills/*.md` — каждый навык отдельный файл
- [x] Структура навыка: название, описание, шаги, примеры
- [x] После сложной задачи — LLM предлагает сохранить навык
- [x] Навык улучшается при повторном использовании
- [x] Команды: `/skills` (список), `/<skill-name>` (вызов)

---

### Фаза 6 — Multi-Platform Gateway

**Цель:** Один процесс на VPS — все платформы одновременно.

```
Телефон → Telegram/Discord/... → VPS gateway → агент
```

- [x] `gateway/base.py` — абстракция платформы
- [x] `gateway/telegram.py` — рефакторинг из `bot.py` Parallax (первый, уже есть)
- [x] Команда `majestic gateway setup` — wizard подключения платформ
- [x] Команда `majestic gateway start` — запуск gateway процесса
- [x] Хранить `source` в таблице `sessions`
- [ ] Cross-platform continuity — начал в Telegram, продолжил в Discord, контекст сохранён
- [ ] Voice memo транскрипция через Whisper

---

### Фаза 6.5 — Команды и UX

**Принцип:**
- Свободный текст → основное общение с агентом, агент сам вызывает нужные tools
- Slash команды → управление агентом + shortcuts для тяжёлых research операций
- Research функции = Tools в `majestic/agent/tools.py` — агент видит их и вызывает по смыслу

**Команды управления агентом:**
```
/model       — сменить модель
/memory      — просмотр памяти
/forget      — удалить воспоминание
/skills      — список навыков
/stop        — прервать выполнение
/usage       — токены и стоимость сессии
```

**Shortcuts для research (bypass loop, прямой вызов tool):**
```
/research    — собрать сигналы из всех источников + CCW скоринг
/news [N]    — последние N новостей по скору
/briefing    — полный брифинг: сигналы + маркет + инвест направление
/market      — крипто + акции + форекс
/report      — глубокий репорт по теме
/reports     — список сохранённых репортов
/rss         — управление RSS лентами
/remind      — напоминание на естественном языке
/reminders   — список напоминаний
```

**Убрано из shortcuts (агент понимает из свободного текста):**
- `/predict`, `/flows` — часть briefing, агент вызывает `get_briefing` с нужным фокусом
- `/ideas` — агент вызывает `generate_ideas` tool по запросу
- `/background`, `/compress` — не реализованы, убраны

**Research tools в `majestic/tools/research/`:**
- [x] `get_market_data` — `research/market.py`
- [x] `run_research` — `research/news.py` (`collect_and_index`)
- [x] `get_briefing` — `research/briefing.py` (full / predictions / flows)
- [x] `get_news` — `research/news.py` (top by CCW)
- [x] `get_report` — `research/report.py`
- [x] `generate_ideas` — `research/ideas.py`

**Tool registry:** `majestic/tools/registry.py` — авторегистрация через `@tool` декоратор, `majestic/tools/__init__.py` импортирует все поддиректории.

---

### Фаза 7 — Cron & Automations

**Цель:** Scheduled задачи с доставкой на любую платформу.

- [ ] Таблица `schedules` уже в `state.db` (создана в Фазе 1)
- [ ] Natural language scheduling: "каждый понедельник в 9 утра делай X"
- [ ] Delivery target: куда доставлять результат (telegram/discord/cli)
- [ ] Команды: `/schedule add`, `/schedule list`, `/schedule remove`
- [ ] Расширить существующий cron Parallax (auto_research, morning_briefing)

---

### Фаза 8 — Sub-Agents

**Цель:** Делегировать сложные задачи изолированным под-агентам.

> ⚠️ Делать только после готовности всех предыдущих фаз.

- [ ] `agent/delegate.py` — инструмент `delegate_task`
- [ ] Каждый sub-агент получает свежую изолированную сессию
- [ ] Параллельный запуск через `ThreadPoolExecutor` (max 3 по дефолту)
- [ ] В контекст родителя возвращается только финальный summary
- [ ] Interrupt propagation — прерывание родителя прерывает всех детей
- [ ] Применить к параллельному сбору из 8 источников Parallax

---

## На будущее (не в активном плане)

### MCP Integration
Подключение внешних инструментов через MCP-серверы. Добавить когда появится конкретная потребность.

---

## Технологический стек

| Компонент | Технология |
|---|---|
| Язык | Python 3.11+ |
| Entrypoint | `majestic-agent` команда через `pyproject.toml` |
| Установка | `scripts/install.sh` — один скрипт, всё включено |
| Конфиг | `~/.majestic-agent/.env` (секреты) + `~/.majestic-agent/config.yaml` (настройки) |
| LLM | Anthropic (напрямую) + OpenRouter (всё остальное) |
| База данных | SQLite + FTS5 + sqlite-vec — единый `state.db` для всего |
| RAG | sqlite-vec (замена ChromaDB — всё в том же `state.db`) |
| Memory | Markdown файлы (`~/.majestic-agent/memory/`) |
| Skills | Markdown файлы (`~/.majestic-agent/skills/`) |
| Все данные | Единая директория `~/.majestic-agent/` — один бэкап, Docker volume |
| Messaging | aiogram (Telegram) + адаптеры под каждую платформу |
| Scheduling | APScheduler |
| Deploy | Docker Compose / VPS — агент всегда онлайн |

---

## Архитектура кода

### Принципы

- **Один файл = одна ответственность**
- **Максимум 300 строк на файл** — если больше, значит две ответственности, делить
- **Никаких файлов-монстров** — Hermes пришёл к `run_agent.py` в 10,700 строк через вайбкодинг без контроля
- **tools/registry.py** — каждый инструмент регистрируется сам при импорте, не нужен ручной список
- **gateway/base.py** — абстракция платформы, каждый адаптер просто реализует интерфейс
- **llm/base.py** — абстракция провайдера, `anthropic.py` и `openrouter.py` полностью независимы

### Структура папок

```
majestic-agent/
│
├── pyproject.toml              # entrypoint: majestic-agent
├── scripts/
│   └── install.sh
│
├── majestic/                   # основной пакет
│   ├── __init__.py
│   ├── constants.py            # MAJESTIC_HOME, пути — только константы
│   ├── config.py               # чтение config.yaml + .env
│   │
│   ├── agent/                  # агент-луп
│   │   ├── loop.py             # while not done — основной цикл
│   │   ├── prompt.py           # сборка system prompt
│   │   ├── compressor.py       # context compression
│   │   └── delegate.py         # sub-agents (Фаза 8)
│   │
│   ├── db/                     # единое хранилище
│   │   ├── state.py            # SessionDB — все таблицы, WAL, FTS5, sqlite-vec
│   │   └── migrations.py       # schema versioning + миграции
│   │
│   ├── memory/                 # память
│   │   ├── store.py            # чтение/запись memory.md + user.md
│   │   └── nudge.py            # LLM nudge — что запомнить после сессии
│   │
│   ├── llm/                    # провайдеры
│   │   ├── base.py             # абстракция LLMProvider
│   │   ├── anthropic.py        # Anthropic напрямую
│   │   └── openrouter.py       # OpenRouter
│   │
│   ├── tools/                  # инструменты — сердце агента
│   │   ├── registry.py         # авторегистрация: добавил файл → инструмент подхватился
│   │   ├── web/
│   │   │   ├── search.py       # web_search, HN, Reddit, RSS
│   │   │   └── extract.py      # web_extract, парсинг страниц
│   │   ├── research/           # toolset: research и аналитика
│   │   │   ├── news.py         # сбор и скоринг новостей
│   │   │   ├── briefing.py     # генерация брифингов
│   │   │   ├── market.py       # крипто, акции, форекс
│   │   │   └── report.py       # глубокие репорты
│   │   ├── files/              # toolset: работа с файлами
│   │   │   ├── read.py         # чтение файлов
│   │   │   ├── write.py        # запись файлов
│   │   │   └── index.py        # индексация в RAG
│   │   ├── system/             # toolset: системные задачи
│   │   │   └── terminal.py     # выполнение команд
│   │   └── db_search.py        # универсальный поиск по всей БД
│   │
│   ├── skills/                 # skills system
│   │   ├── loader.py           # загрузка .md навыков
│   │   └── creator.py          # создание навыка после задачи
│   │
│   ├── gateway/                # мессенджеры
│   │   ├── base.py             # абстракция платформы
│   │   ├── runner.py           # главный процесс gateway
│   │   ├── telegram.py
│   │   ├── discord.py
│   │   ├── slack.py
│   │   ├── whatsapp.py
│   │   └── signal.py
│   │
│   ├── cron/                   # планировщик
│   │   ├── scheduler.py        # APScheduler обёртка
│   │   └── jobs.py             # CRUD для расписаний
│   │
│   └── cli/                    # CLI точки входа
│       ├── main.py             # majestic-agent команда, роутинг субкоманд
│       ├── setup.py            # majestic-agent setup wizard
│       ├── commands.py         # /slash команды — реестр
│       └── display.py          # статус-бар, форматирование вывода
│
└── tests/
    ├── test_db.py
    ├── test_memory.py
    ├── test_llm.py
    └── test_tools.py
```

---

*Файл обновляется по мере выполнения фаз.*

---

## RAG — Universal Search

> Конкурентное преимущество над Hermes — у них RAG нет из коробки.  
> Не просто "поиск по документам" — агент ищет по **всей базе данных** через один инструмент.

### Концепция

Агент не знает где лежит нужная информация. Он просто вызывает `db_search` и получает релевантный результат из любого источника:

```
Агент → db_search("запрос")
            ↓
   Параллельный поиск по всем источникам:
   ├── messages_fts    → история диалогов
   ├── news_fts        → собранные новости (/research)
   ├── reports_fts     → сохранённые отчёты (/report)
   ├── market_history  → маркет данные (по символу, дате)
   └── vectors         → загруженные документы (семантически)
            ↓
   RRF — объединение результатов по релевантности
            ↓
   Агент получает топ чанков из любых источников
```

### Как работает каждый источник

**messages + news + reports → FTS5 (BM25)**
- Полнотекстовый keyword поиск — мгновенно
- Точные термины, имена, тикеры, даты

**vectors → sqlite-vec (семантический)**
- Эмбеддинги загруженных документов
- Поиск по смыслу, не по точному совпадению
- Модель `all-MiniLM-L6-v2` локально через `fastembed`, CPU, ~15ms

**market_history → SQL запрос**
- По символу (BTC, AAPL), диапазону дат, источнику
- Не нужны эмбеддинги — структурированные данные

**Объединение через RRF (Reciprocal Rank Fusion)**
- Стандартный алгоритм слияния результатов из разных источников
- Итог: единый ранжированный список по релевантности

### Индексация документов

Пользователь загружает файл или указывает директорию:
- Документ разбивается на чанки (~500 токенов, 10% overlap, по естественным границам)
- Каждый чанк эмбеддится локально через `fastembed`
- Сохраняется в таблицу `vectors` в `state.db`
- Оригинальный файл хранится в `~/.majestic-agent/workspace/`

Новости и отчёты индексируются автоматически при создании — FTS5 триггеры на insert.

### Поддерживаемые форматы документов
PDF, DOCX, MD, TXT, CSV

### Инструмент для агента
```python
db_search(query, sources=["all"])  # агент вызывает сам
# sources: "all" | "news" | "reports" | "messages" | "docs" | "market"
```

### Команды для пользователя
```
/index <path>   — индексировать файл или директорию
/kb             — статистика: файлы, чанков, размер
/kb remove <f>  — удалить файл из индекса
```

### Таблицы в state.db

```
messages      → messages_fts (FTS5, триггер)
news          → news_fts     (FTS5, триггер)
reports       → reports_fts  (FTS5, триггер)
market_history               (SQL запрос)
vectors                      (sqlite-vec, эмбеддинги)
```

### Файлы
```
majestic/tools/rag.py   — db_search: параллельный поиск + RRF fusion
~/.majestic-agent/state.db    — все таблицы включая vectors
~/.majestic-agent/workspace/  — оригинальные файлы пользователя
```

### Сравнение с Parallax
| | Parallax | majestic-agent |
|---|---|---|
| Что ищет | Только загруженные документы | Вся база: новости, отчёты, диалоги, документы, маркет |
| База | ChromaDB (отдельный процесс) | sqlite-vec в state.db |
| Поиск | Только векторный | Гибридный: FTS5 + векторный + SQL + RRF |
| Бэкап | Отдельная папка chroma/ | Всё в одном state.db |
| Embedding | Через Ollama или API | Локально CPU, без сервера |
