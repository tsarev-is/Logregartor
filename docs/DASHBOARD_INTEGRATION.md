# Dashboard: интеграция с модулями

Dashboard находится в `src/ui` (Next.js). Рабочий срез: выбор набора → список
медленных VM → карточка → этапы и хронология → точная строка из снимка анализа.
Просмотр данных работает без OpenAI и MCP. Отдельного HTTP-интерфейса у LogParser
не требуется: он публикует данные в ClickHouse, Analytics читает эти публикации.

```text
LogParser → опубликованные события ClickHouse → Analytics run → снимок анализа
                                                                  ↑
Браузер → Next.js /api/analytics/* → Analytics serve ────────────────┘
        → Next.js /api/chat → OpenAI Agents SDK + ClickHouse MCP
```

## Что потребляет Dashboard

| Dashboard endpoint | Analytics endpoint | Назначение |
| --- | --- | --- |
| `GET /api/analytics/health` | `GET /health` | Доступность БД и схемы Analytics |
| `GET /api/analytics/datasets` | `GET /v1/datasets` | Наборы, наличие анализа, устаревший снимок |
| `GET /api/analytics/incidents?dataset_id=…` | `GET /v1/incidents?dataset_id=…` | Текущий отчёт и ранжированные инциденты |
| `GET /api/analytics/incidents/{id}?analysis_run_id=…` | `GET /v1/incidents/{id}` с тем же параметром | Карточка конкретной публикации |
| `GET /api/analytics/incidents/{id}/timeline?analysis_run_id=…` | `GET /v1/incidents/{id}/timeline` с тем же параметром | Датированные и недатированные события |
| `GET /api/analytics/events/{id}?analysis_run_id=…` | `GET /v1/events/{id}` с тем же параметром | Исходная строка и ID загрузки |

Контракт discovery: `{datasets: [{dataset_id, ingested_sources, analysis_run_id,
incident_count, analysis_stale}]}`. `analysis_run_id=null` и `incident_count=null`
означают импорт без завершённого анализа. `incident_count=0` — завершённый анализ
без срабатываний. `analysis_stale=true` означает, что текущие загрузки LogParser
отличаются от входного снимка анализа. Список включает опубликованные наборы
LogParser, в том числе пустые файлы, и наборы с сохранёнными анализами.
До первого импорта discovery возвращает пустой массив.

Карточки, baseline, этапы, полнота и строки описаны в
[README Analytics](../src/Analytics/README.md). TypeScript-типы и проверка данных
во время исполнения находятся в `src/ui/lib/analytics-contract.ts`; тесты UI
получают JSON от настоящего Python runner Analytics. Добавочные поля API сохраняются
прокси, несовместимый обязательный контракт возвращает `502`.

ID инцидентов и событий — SHA-256 в нижнем регистре. **Любая навигация после списка
сохраняет `analysis_run_id`**. Обновление списка не переключает уже открытую карточку
на новый анализ. Переносить `event_id` на текущий импорт нельзя: доказательство —
копия записи из завершённого снимка, включая `raw_text`, `line_ending` и
`ingestion_run_id`. `GET /events` не является универсальным поиском всех логов.

## Состояния и ошибки

- Нет наборов: предложить импорт LogParser и запуск Analytics.
- Набор импортирован, но анализа нет: показать это состояние; порог задаётся CLI.
- Анализ с нулём инцидентов: показать фактический порог и нулевой результат.
- Неполная карточка: показать отсутствующие этапы, записи без времени и ошибки
  парсинга; срабатывание по завершённому build сохраняется.
- `404`: публикация/карточка/строка не найдена; `422`: неверные параметры;
  `503`: сервис, БД или схема недоступны; `502`: нарушен контракт upstream.
- Кнопка Refresh повторяет загрузку, сохраняя ID открытого снимка. Запоздавшие ответы
  отменяются при смене выбора. Ошибка AI не закрывает данные Analytics.

Next.js проксирует только перечисленные маршруты и параметры, с `no-store`,
таймаутом 10 секунд и запретом redirect. Произвольные SQL, URL и заголовки браузера
не передаются в upstream. `ANALYTICS_API_URL` хранится только на сервере, поэтому
отдельный CORS между браузером и Analytics не нужен. `/api/health` — liveness UI;
`/api/status` раздельно сообщает доступность Analytics и MCP и наличие настройки AI.

## Контекст чата и ссылки

`POST /api/chat` принимает 1–20 сообщений `{role: user|assistant, content}` и
необязательный `context: {datasetId, incidentId, analysisRunId, eventId?}`.
`incidentId` и `analysisRunId` могут быть `null` только для контекста набора;
для конкретной строки передаётся `eventId`, `incidentId=null` и ID запуска.
Контекст сервер повторно получает из Analytics. Изменившаяся публикация набора
требует обновить список; открытая карточка остаётся привязана к прежнему запуску.
Имена исходных файлов и raw-текст не добавляются в автоматический контекст модели.

Ответ: `{message, actions: [{kind, label, title, description, targetId, datasetId,
analysisRunId}]}`. Доступны только действия с рабочим обработчиком:

| kind | targetId | Результат |
| --- | --- | --- |
| `open_incident` | `incident_id` | Карточка и этапы |
| `show_timeline` | `incident_id` | Хронология карточки |
| `show_logs` | один `event_id` из evidence | Точная исходная запись |

Сервер проверяет наличие каждой ссылки в завершённом анализе и соответствие
набора, ID объекта и запуска. Неверные ссылки удаляются из `actions`.
Эта проверка доказывает существование записи, а не правильность гипотезы модели.
`show_service` исключён из контракта, пока нет отдельного API и экрана компонента.
MCP остаётся инструментом дополнительного исследования. Доступные SQL-агрегаты
описаны в [UI_AGGREGATES.md](UI_AGGREGATES.md); они доступны researcher через MCP.

## Запуск

Из корня репозитория, после настройки ClickHouse через локальный `.env`:

```bash
docker compose up -d --build --wait clickhouse analytics ui
# После импорта LogParser: явный порог, приведённый здесь только как пример.
docker compose exec analytics python -m log_analytics run \
  --dataset-id openstack --threshold-seconds 27.91
```

Открыть `http://localhost:3000`. `run` не запускается автоматически и не вызывается
через HTTP: выбор порога/baseline остаётся явным. Запускайте писателя в одном
контейнере `analytics` через `exec`, чтобы процессы использовали общую локальную
блокировку; одновременные `run` с разных хостов не поддерживаются.

Для разработки без контейнера UI:

```bash
cd src/ui
npm ci
cp .env.example .env.local
# ANALYTICS_API_URL=http://127.0.0.1:8080
npm run dev
```

В Compose используется `ANALYTICS_API_URL=http://analytics:8080`; host-порт задаётся
через `ANALYTICS_PORT` (по умолчанию 8080). MCP и OpenAI подключаются отдельно по
[инструкции MCP](MCP_CLICKHOUSE.md). Секреты остаются в игнорируемых `.env`.

## Проверки и границы среза

```bash
# src/ui, Node.js 22.18+ и Python 3.11+ для генератора контрактов
npm test
npm run typecheck
npm run build
# src/Analytics
python3 -m unittest discover -s tests -v
# С зависимостями LogParser, Go и работающим ClickHouse, только временная БД:
ANALYTICS_CLICKHOUSE_TEST=1 python -m unittest discover -s tests \
  -p test_clickhouse_integration.py -v
```

Контракты покрывают нулевой результат, ошибки upstream, снимки, проверку ссылок
и несовпадение контекста. Интеграционные тесты проверяют импорт → анализ → discovery,
карточку, timeline и исходную строку, повтор публикации и чтение прежнего снимка.

Сохранённые структурированные гипотезы, отдельный retrieval API, отчёт evaluation,
граф компонентов и графики агрегатов остаются отдельными возможностями из
исследования. Текущий Dashboard показывает детерминированное наблюдение; он не
подставляет вымышленные severity, состояние active/resolved, confidence или runbook.
Чат может сформулировать гипотезу, но отдельного модуля сохранённых объяснений пока нет.
