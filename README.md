# Logregartor

Хакатонный проект для анализа логов: поиск аномалий, связывание событий и объяснение вероятных причин сбоев на основе найденных записей.

Данные: [OpenStack из Loghub](https://github.com/logpai/loghub/tree/master/OpenStack). Задание: [AI-Powered Observability](docs/AI_Powered_Observability_Hackathon_1.pdf).

Реализован [LogParser](src/LogParser/README.md): пакетный разбор OpenStack на Go,
шаблоны через Python/Drain3 и повторяемая загрузка в ClickHouse с проверками
целостности. Аналитика, векторный поиск и dashboard находятся на этапе проектирования.
Компоненты проекта:

- **Загрузка и обработка** — чтение логов, нормализация и выделение шаблонов событий.
- **ClickHouse** — хранение логов, фильтрация и аналитические запросы.
- **Векторный поиск** — построение эмбеддингов и поиск похожих событий. Предварительно планируется отдельная векторная БД; выбор открыт.
- **Аналитика и AI** — обнаружение аномалий, корреляция событий и гипотезы о причинах сбоев с опорой на найденные логи (RAG).
- **Dashboard** — Next.js-модуль в `src/ui` со встроенным AI copilot. Модель может вернуть типизированную ссылку на incident, timeline, логи или сервис; по нажатию результат открывается в основной области.

Модули взаимодействуют через явные интерфейсы; подключения и параметры задаются конфигурацией. Границы модулей, модели и остальной стек уточняются по ходу хакатона. Компоненты и необходимые сервисы можно разворачивать в контейнерах.

Минимальная цель: воспроизводимое демо на OpenStack — загрузить логи, выделить шаблоны, обнаружить один класс аномалий и показать хронологию событий, вероятные причины со ссылками на логи и рекомендуемый следующий шаг.

Локальный ClickHouse (нужен Docker Compose):

```bash
docker compose up -d --wait clickhouse
```

HTTP: `http://localhost:8123`, native: `localhost:9000`. База: `logs`, пользователь: `logregartor`, пароль для локальной разработки: `localdev`. Другие сервисы в этой Compose-сети подключаются к `clickhouse:8123` или `clickhouse:9000`.

Версию образа, базу, учётные данные и порты можно переопределить переменными окружения `CLICKHOUSE_*`, указанными в [docker-compose.yml](docker-compose.yml). Данные хранятся в volume `clickhouse_data` и сохраняются после `docker compose down`.

Для AI researcher добавлен официальный `mcp-clickhouse` версии `0.6.0`.
После настройки двух секретов в локальном `.env` запустите:

```bash
docker compose --profile mcp up -d --build --wait mcp-clickhouse
docker compose exec -T mcp-clickhouse python /app/smoke.py
```

MCP endpoint: `http://127.0.0.1:8000/mcp`, транспорт Streamable HTTP,
авторизация `Authorization: Bearer <CLICKHOUSE_MCP_AUTH_TOKEN>`.
Сервер использует отдельного пользователя ClickHouse только для чтения.
Настройка, подключение researcher и примеры запросов: [MCP ClickHouse](docs/MCP_CLICKHOUSE.md).

UI можно запустить отдельно, без базы и MCP:

```bash
docker compose up -d --build --wait ui
```

Он будет доступен на `http://localhost:3000`. Без OpenAI-конфигурации работает демонстрационный переход из чат-карточки в dashboard. Для реального чата скопируйте `.env.example` в `.env` и задайте `OPENAI_API_KEY`; доступ к данным включается через `MCP_SERVER_URL` и опциональный `MCP_AUTHORIZATION`.

Все сервисы запускаются одной командой:

```bash
docker compose up -d --build --wait
```
