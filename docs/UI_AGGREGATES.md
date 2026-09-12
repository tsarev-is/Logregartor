# ClickHouse: агрегаты для UI

Агрегаты покрывают метрики, графики, сервисы, шаблоны и инциденты. Данные
карточки `INC-2048` из исходного UI — демонстрационные, а не целевые значения
для наполнения базы. Реальные показатели вычисляются по OpenStack. Подключение
виджетов к этим представлениям выполняется через серверный адаптер или MCP.

Счётчики текущего списка инцидентов — Incidents, Completed VMs, Incomplete VMs
и Events analyzed — доступны в `ui_analysis_summary`. Полные карточки, baseline,
этапы и исходные строки также доступны через существующий Analytics API.

Идентификаторы и хеши в новых представлениях возвращаются как `String`:
MCP передаёт их обычным текстом, без Python bytes-обёртки `b'...'` у `FixedString`.

## Покрытие экранов

| Данные UI | Представление | Срез / назначение |
| --- | --- | --- |
| Диапазон данных, Error rate, p95, число сервисов | `ui_dataset_summary` | Набор целиком, включая счётчики пропусков |
| Service details | `ui_service_summary` | Набор + наблюдаемый компонент |
| Графики ошибок, задержек, неизвестных шаблонов | `ui_service_metrics_1m` | Набор + источник + минута UTC + компонент |
| HTTP-запросы, статусы и p95 | `ui_http_metrics_1m` | Тот же срез + метод + статус |
| Patterns и переход к исходной строке | `ui_template_metrics_1m` | Тот же срез + версия/ID/статус шаблона, `sample_event_id` |
| Anomalies и полнота наблюдений VM | `ui_analysis_summary` | Последний завершённый запуск на набор, включая нулевой результат |
| Карточка инцидента | `ui_incident_details` | Типизированные поля карточки, порог, наблюдение, evidence IDs |
| Affected services и число доказательств | `ui_incident_evidence_summary` | Инцидент и зафиксированный запуск анализа |
| График аномалий | `ui_incident_metrics_1m` | Запуск + минута UTC + детектор |
| Timeline / Log explorer | `incident_evidence`, `log_events` | Исходные записи с устойчивыми ID, а не агрегаты |

Здесь **service = component** из OpenStack. Это наблюдаемый компонент, а не
подтверждённая топология. `affected_service_count` — число разных компонентов
в доказательствах инцидента; `error_service_count` — число компонентов с ERROR,
CRITICAL или FATAL в логах. Это разные показатели.

## Семантика

- `log_error_rate` — доля ERROR/CRITICAL/FATAL среди записей с известным `level`.
  `http_server_error_rate` — доля HTTP-статусов >= 500 среди известных статусов.
  Доли имеют диапазон 0–1; UI умножает их на 100. HTTP 4xx и ERROR не являются
  автоматически аномалиями VM.
- `http_p95_seconds` / `p95_seconds` — приближённый t-digest p95 измеренных
  HTTP-длительностей в секундах. Нулевой замер входит в выборку. При отсутствии
  замеров или знаменателя возвращается `NULL`, а не искусственный ноль.
- Счётчики складываются по непересекающимся срезам. Доли пересчитываются из
  суммы числителей и знаменателей. **Нельзя усреднять или складывать p95**.
  Общий p95 за произвольное окно вычисляется ограниченным запросом к `log_events`.
  Сводки по набору/сервису считают p95 сразу по всей соответствующей выборке.
- Минутные представления содержат только минуты с событиями. Пустые интервалы
  графика заполняет потребитель. Записи без времени учитываются в общих счётчиках
  и `undated_event_count`, но не получают вымышленную дату в графике.
- Строки с `template_status='unknown'` и `template_id=NULL` — счётчик неизвестных
  сообщений, а не один новый шаблон. Каталог присоединяется по паре
  `(template_version, template_id)`.
- `anomaly_count` относится к детектору медленной сборки VM. `bucket` аномалии —
  время выбранного завершения build. В данных нет lifecycle active/resolved,
  severity, вероятности причины, runbook или доказанной топологии: значения
  «4 critical» и «87% confidence» из демо не вычисляются.
- `ui_analysis_summary` без строки означает отсутствие завершённого анализа;
  строка с `anomaly_count=0` — завершённый анализ без срабатываний. Снимок анализа
  может быть старше текущего импорта. Передавайте `analysis_run_id` из карточки
  в Analytics API, чтобы расследование сохраняло её доказательства.

## Публикация и установка

Это обычные агрегирующие `VIEW` поверх `log_events`, `incidents` и
`incident_evidence`, выбирающих только завершённые публикации. Они сразу покрывают
уже загруженные данные и не удваивают статистику при повторной обработке.
Инкрементальные materialized views непосредственно на `*_raw` посчитали бы также
незавершённые и заменённые попытки. Если объём потребует предрасчёта, его нужно
версионировать вместе с публикациями. Текущие VIEW сканируют данные при запросе;
используйте фильтры набора/времени и ограничение результата.

SQL находится в миграциях `002_ui_aggregates.sql` модулей LogParser и Analytics.
Их `migrate()` применяют все SQL-файлы в порядке имени. Compose создаёт обе схемы
через `clickhouse-init`, а подготовка MCP ожидает его успешного завершения.
Для существующего volume из корня репозитория:

```bash
docker compose up -d --wait clickhouse
docker compose run --rm clickhouse-init
```

Повторный запуск безопасен. Используется `CLICKHOUSE_DB`, по умолчанию `logs`.
Установка схемы не загружает данные: выполните `pipeline run` по
[инструкции LogParser](../src/LogParser/README.md), затем `log_analytics run` по
[инструкции Analytics](../src/Analytics/README.md). Рабочий набор должен находиться
в той же базе, на которую выдан доступ MCP.

## Запросы для адаптера и MCP

Сначала определите диапазон набора: OpenStack содержит исторические логи, поэтому
`now() - INTERVAL 30 MINUTE` даст пустой результат.

```sql
SELECT * FROM ui_dataset_summary WHERE dataset_id = {dataset:String};
SELECT * FROM ui_analysis_summary WHERE dataset_id = {dataset:String};

SELECT bucket, sum(error_count) AS errors, sum(leveled_event_count) AS measured,
       errors / nullIf(measured, 0) AS log_error_rate
FROM ui_service_metrics_1m
WHERE dataset_id = {dataset:String}
  AND bucket >= toDateTime({start:String}, 'UTC')
  AND bucket < toDateTime({end:String}, 'UTC')
GROUP BY bucket ORDER BY bucket LIMIT 1440;

-- Окно [start, end), включая неполные минуты.
SELECT countIf(level IN ('ERROR', 'CRITICAL', 'FATAL'))
           / nullIf(countIf(level IS NOT NULL), 0) AS log_error_rate,
       countIf(http_duration_seconds IS NOT NULL) AS latency_sample_count,
       quantileTDigestOrNullIf(0.95)(assumeNotNull(http_duration_seconds),
                                  http_duration_seconds IS NOT NULL) AS http_p95_seconds
FROM log_events
WHERE dataset_id = {dataset:String}
  AND event_time >= toDateTime64({start:String}, 9, 'UTC')
  AND event_time < toDateTime64({end:String}, 9, 'UTC');

SELECT i.*, e.affected_service_count, e.affected_services, e.evidence_count
FROM ui_incident_details AS i
LEFT JOIN ui_incident_evidence_summary AS e
  USING (analysis_run_id, dataset_id, incident_id)
WHERE dataset_id = {dataset:String}
ORDER BY excess_seconds DESC, incident_id LIMIT 20;
```

Для delta повторите расчёт на предыдущем окне той же длины. Отсутствующие
замеры оставляйте неизвестными. Разность долей показывайте в процентных пунктах,
разность задержек — в секундах.

## Проверки

Интеграционные тесты используют уникальные временные базы и удаляют только их:

```bash
# Из src/LogParser, с установленными requirements.txt:
LOGPARSER_CLICKHOUSE_TEST=1 python -m unittest tests.test_ui_aggregates -v
# Из src/Analytics, с окружением LogParser и Go:
ANALYTICS_CLICKHOUSE_TEST=1 python -m unittest discover -s tests -p test_clickhouse_integration.py -v
```

Проверяются данные до миграции, повторная миграция, изоляция наборов, нулевые и
отсутствующие HTTP-замеры, некорректные и недатированные записи, незавершённая
попытка, замена и повтор публикации, снимок инцидента и нулевой результат анализа.
