# LogParser

Пакетный конвейер OpenStack: **Go → JSONL → Python/Drain3 → ClickHouse**.
Модуль сохраняет исходные строки, извлекает поля и числовые признаки,
назначает шаблоны из зафиксированного словаря и публикует завершённые загрузки.
Описание проекта — в [корневом README](../../README.md), правила разработки —
в [AGENTS.md](../../AGENTS.md).

## Быстрый запуск

Нужны Go 1.26.3, Python 3.11+ и Docker Compose. Python-адаптер использует
локальную файловую блокировку `fcntl` и рассчитан на Linux/macOS.
Из корня репозитория запустите БД:

```bash
docker compose up -d --wait clickhouse
```

Остальные команды выполняются из `src/LogParser`:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
go build -o bin/logparser .
python -m pipeline prepare --output-dir data/openstack
python -m pipeline run \
  --input data/openstack/openstack_normal1.log \
  --input data/openstack/openstack_normal2.log \
  --input data/openstack/openstack_abnormal.log \
  --reference data/openstack/openstack_normal1.log \
  --dataset-id openstack \
  --state-dir state/openstack-v1 \
  --work-dir output/openstack
```

`prepare` скачивает полный архив, сырой образец 2k и эталонный CSV, проверяет
закреплённые SHA-256 и извлекает только три известных `.log`. Существующие
загрузки можно передать через `--cache-dir /path/to/downloads`. Метки из
`anomaly_labels.txt` не извлекаются в каталог входных логов.

Повтор той же команды `run` проверяет и использует существующий словарь,
повторно создаёт локальные артефакты, а завершённые версии файлов в БД
пропускает. Результат загрузки записывается в `output/openstack/ingestion.json`.
Сырые данные, словари, JSONL и Python-окружение исключены из Git.

## Отдельные этапы и артефакты

```bash
go run . parse --input data/openstack/openstack_normal1.log \
  --dataset-id openstack --timezone UTC --output output/reference.jsonl
python -m pipeline fit --input output/reference.jsonl --state-dir state/reference-v1
python -m pipeline transform --input output/reference.jsonl \
  --state-dir state/reference-v1 --output output/events.jsonl
python -m pipeline load --input output/events.jsonl --state-dir state/reference-v1
```

Перед отдельным `parse` создайте каталог результата. `--input` у Go-парсера
повторяемый; один JSONL может содержать несколько файлов. Команды Python
`fit`, `transform`, `load` и `evaluate` принимают `--report`; по умолчанию
отчёт расположен в `INPUT.report.json`.
`transform` поддерживает `--output-report`, по умолчанию `OUTPUT.report.json`.
Ошибки конфигурации, чтения, записи и БД завершают команду ненулевым кодом.

| Артефакт | Содержимое |
| --- | --- |
| `normalized.jsonl` | Все физические строки, разобранные Go-парсером |
| `events.jsonl` | Те же события с `template_id/version/status` |
| `*.report.json` | Источники, хеши, счётчики, версии, длительность этапа |
| `state/.../templates.json` | Каталог окончательных шаблонов |
| `state/.../snapshot.bin` | Зафиксированное состояние Drain3 |
| `state/.../manifest.json` | Настройки, reference-хеши, зависимости и контрольные суммы словаря |

JSONL сопровождается обязательным отчётом с хешем артефакта. Python проверяет
каждое событие по [JSON Schema v1](schema/log-event.v1.json), последовательность
номеров строк, идентификаторы и восстановленный хеш каждого исходного файла.
Запись локальных результатов идёт через временные файлы. При сбое между
публикацией JSONL и отчёта несовпадение хешей блокирует последующую загрузку.

## Контракт события

Одна физическая строка — одно событие, включая traceback, пустые и повреждённые
записи. `raw_text` не содержит разделитель строки; `line_ending` сохраняет
`\n`, `\r\n` или пустое окончание последней строки. Их конкатенация восстанавливает
исходные UTF-8 байты. Не-UTF-8 вход завершает обработку файла ошибкой.

`event_id = SHA-256(source_sha256 + ":" + line_start)`, где SHA-256 представлен
строчными hex-символами, номер строки начинается с 1. Перемещение файла,
новый запуск и новый словарь не изменяют ID. Идентичные по содержимому файлы
в одном импорте отклоняются как повтор одного источника.

Сохраняются заголовок, необязательный context, исходный timestamp, UTC-время,
уровень, компонент, PID, request ID и явный `[instance: UUID]`. Отсутствующие
значения остаются `null`; имя источника не становится hostname. `host`
извлекается только из явного `Final resource view: name=...`. HTTP URL сохраняется,
но UUID из него не считается явным instance ID.

Перед шаблонизацией извлекаются `build/spawn/destroy_duration_seconds`,
`http_duration_seconds`, HTTP-метод, URL, статус и размер ответа. В `parameters`
сохраняются числовые параметры claim, total/used/limit/free, RAM/disk и vCPU;
суффиксы `mb`, `gb` и `count` задают единицу измерения.

`parse_status`: `ok`, `partial` (распознан заголовок, есть ошибки полей),
`unparsed` (нет заголовка), `empty` (пустая физическая строка).
Отсутствующий context и пустое тело с корректным заголовком допустимы.
Повреждённые строки сохраняются в БД; они не обучают словарь.

UTC — явное предположение для timestamp без зоны. Его можно изменить через
`--timezone Europe/Berlin` или другую IANA-зону. Исходное значение и выбранная
зона сохраняются. Сортировку для хронологии выполняет потребитель, чтение
сохраняет исходный порядок даже при обратном ходе timestamp.

## Шаблоны и оценка

`fit` обучается на явно заданном reference JSONL. Основной сценарий использует
только `normal1`. `transform` вызывает `match` с полным поиском по зафиксированным
шаблонам и никогда не дообучает словарь, в том числе на `normal2` и `abnormal`.

Настройки находятся в [config/drain.json](config/drain.json): `depth=5`,
`sim_th=0.5`, маски UUID, IP (включая список адресов прокси), HEX и чисел.
Уже извлечённый начальный `[instance: UUID]` удаляется только из копии сообщения
для Drain3; `message`, `raw_text` и признаки остаются исходными. Это позволяет
группировать сообщения по их содержанию. Маски не являются средством удаления
персональных данных: исходные логи сохраняются локально без редактирования.

`template_id` — SHA-256 окончательного текста шаблона. `template_version`
учитывает каталог, настройки, версии runtime, парсера и reference-источники.
Новый словарь пишется в новый каталог; `fit` не перезаписывает существующий.
Snapshot загружается только при совпадении зависимостей и хешей. Используйте
только доверенные локально созданные snapshots: Drain3 десериализует их через
`jsonpickle`.

Статусы шаблона: `pending` до обработки, `matched`, `unknown` при отсутствии
совпадения, `skipped` для пустых/повреждённых сообщений. Неизвестные события
остаются видимыми, их `template_id` равен `null`.

Отдельный эксперимент на 2k не изменяет основной словарь:

```bash
go run . parse --input data/openstack/OpenStack_2k.log \
  --dataset-id openstack-2k-evaluation --output output/2k.jsonl
python -m pipeline fit --input output/2k.jsonl --state-dir state/2k-evaluation
python -m pipeline transform --input output/2k.jsonl \
  --state-dir state/2k-evaluation --output output/2k-events.jsonl
python -m pipeline evaluate --input output/2k-events.jsonl \
  --reference-csv data/openstack/OpenStack_2k.log_structured.csv
```

Оценщик сверяет поля с CSV и считает pairwise precision/recall/F1 и grouping
accuracy (долю строк в точно совпавших группах). Непохожие неизвестные сообщения
не объединяются в один фиктивный кластер. Метрики относятся к группировке
шаблонов, а не к обнаружению аномалий; 43 эталонных группы не являются требованием
к числу полученных шаблонов. Настройки проверялись на этом же 2k-наборе,
поэтому его результаты не являются независимой оценкой обобщения.

Проверенный результат для закреплённого 2k и настроек v1: 2 000/2 000 сообщений
получили шаблон, 42 полученные группы против 43 эталонных; pairwise
precision **0,998982**, recall **1,0**, F1 **0,999491**, grouping accuracy **0,9785**.

## ClickHouse: публикация и восстановление

По умолчанию: `http://localhost:8123`, база `logs`, пользователь `logregartor`,
пароль `localdev` для локальной разработки. Переопределение через переменные
окружения `CLICKHOUSE_URL`, `CLICKHOUSE_DB`, `CLICKHOUSE_USER`,
`CLICKHOUSE_PASSWORD`, `CLICKHOUSE_TIMEOUT` (60 секунд). Python читает экспортированное
окружение; `.env` автоматически читает только Compose. Секреты не передавайте
в URL или аргументах команд.

Первый `load` применяет [SQL v1](sql/001_initial.sql) к выбранной базе.
`log_events_raw` и `event_templates_raw` содержат изолированные попытки загрузки;
`ingestion_runs` хранит записи `started` и `completed`. Представление
`current_ingestions` выбирает последнюю завершённую попытку на
`(dataset_id, source_sha256)`. Для потребителей предназначены `log_events` и
`event_templates` — незавершённые попытки в них не видны.

Загрузка синхронная, через HTTP `JSONEachRow`, по 5 000 событий на запрос
(`--batch-size`). Перед публикацией проверяются число и уникальность событий,
наличие каталога и контрольные суммы всего источника. Новая версия парсера,
зоны или шаблонов получает новую попытку; прежняя остаётся видимой до её завершения.
Публикация выполняется отдельно для каждого файла, общей транзакции на три файла нет.

При таймауте INSERT автоматически не повторяется: сервер мог уже принять данные.
Повторный `load` пропускает завершённые версии и начинает новые попытки для
незавершённых файлов. Если потерян ответ на `completed`, повтор обнаруживает
готовую попытку и пропускает её. Частичные попытки остаются только в `*_raw`
для диагностики и занимают место; автоматической очистки в MVP нет.

Импорт рассчитан на одного писателя на одном хосте. Общая файловая блокировка
для endpoint/базы предотвращает совпадающие локальные запуски; распределённая
загрузка с нескольких хостов не поддерживается. Выбор разных написаний одного
endpoint (`localhost`/`127.0.0.1`) не должен использоваться для параллельных импортов.

Примеры SQL для будущего API:

```sql
SELECT event_id, raw_text, source_file, line_start
FROM log_events
WHERE dataset_id = {dataset:String} AND event_id = {event:String};

SELECT event_time, event_id, message, build_duration_seconds, spawn_duration_seconds
FROM log_events
WHERE dataset_id = {dataset:String}
  AND source_sha256 = {source:String}
  AND instance_id = {instance:String}
ORDER BY event_time, line_start;
```

`source_sha256` разделяет независимые записи экспериментов. Уровень ERROR,
HTTP 404 и имя файла не превращаются в признаки целевой аномалии. Детектор,
корреляция, API, RAG и dashboard остаются отдельными компонентами проекта.
Изменение содержимого `.log` создаёт новый источник с новым хешем; совпадение
имени файла не заменяет ранее загруженный источник. MVP рассчитан на неизменяемые
снимки файлов, а не на дописываемые журналы.

## Проверки

```bash
go build ./...
go test ./...
go vet ./...
python -m unittest discover -s tests -v
LOGPARSER_DATA_DIR=data/openstack python -m unittest tests.test_openstack_dataset -v
LOGPARSER_CLICKHOUSE_TEST=1 python -m unittest tests.test_clickhouse_integration -v
```

Python-тесты автоматически собирают Go-бинарник; можно передать готовый путь
через `LOGPARSER_BINARY`. Проверка архива сопоставляет все 207 820 строк с
независимым аудитом, закреплённым в `tests/fixtures/openstack_audit.json`, включая 184 записи без context,
8 пустых сообщений и четыре контрольные длительности.

Интеграционные тесты используют настройки `CLICKHOUSE_*`, создают уникальную
базу `logparser_test_<UUID>` и удаляют только эту базу после выполнения. Нужны
права CREATE/DROP DATABASE. Проверяются повторы, частичная загрузка, потеря
подтверждения публикации и смена версии при сохранении предыдущих данных.
Обычный `unittest discover` пропускает проверки архива и БД без переменных выше.

Остановить локальный ClickHouse с сохранением данных: `docker compose down`
из корня репозитория. Не добавляйте `-v`, если данные нужно сохранить.

## OpenSpec

Контекст модуля и правила подготовки изменений заданы в
[openspec/config.yaml](openspec/config.yaml), схема — `spec-driven`.
Основные спецификации описывают фактическое поведение реализации:

| Спецификация | Контракт |
| --- | --- |
| [openstack-parsing](openspec/specs/openstack-parsing/spec.md) | Физические строки, нормализация и целостность JSONL |
| [template-mining](openspec/specs/template-mining/spec.md) | Обучение Drain3, версии и замороженное сопоставление |
| [clickhouse-ingestion](openspec/specs/clickhouse-ingestion/spec.md) | Публикация завершённых загрузок, повторы и восстановление |
| [pipeline-cli](openspec/specs/pipeline-cli/spec.md) | Команды, подготовка данных, сквозной запуск и оценка |

Артефакты пишутся по-русски; структурные заголовки OpenSpec, `SHALL`/`MUST`
и технические идентификаторы сохраняются на английском. Новые предложения
размещаются в `openspec/changes/`, завершённые — в `openspec/changes/archive/`.

Проверено с OpenSpec CLI 1.13.0. Команды выполняются из `src/LogParser/`:

```bash
openspec context --json
openspec list --specs
openspec validate --all --strict --no-interactive
```
