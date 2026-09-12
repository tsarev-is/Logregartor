# Проверка базовых компонентов UI

## Исполнители

Три отдельных subagents, каждый `gpt-5.6-terra`, reasoning effort `medium`:

- UI-01: incident_analysis — аномалия, гипотезы, следующие проверки.
- UI-02: evidence_browser — timeline, логи, шаблоны, inspector.
- UI-03: workspace_integration — существующий shell, chat actions, состояния и навигация.

Координатор независимо просмотрел код и проверяет итоговую интеграцию. Изменения не закоммичены.

## Регрессионные проверки

Из `src/ui`:

```bash
npm test
npm run typecheck
npm run build
```

`npm test` использует встроенный Node test runner и native TypeScript imports (Node >= 22.18; проверено на Node 26.5.0). Новые зависимости не устанавливались.

15 тестов покрывают UTC formatting (включая невалидную дату), корректность синтетической фикстуры, стабильные IDs и source pointers, ссылки на evidence, соответствие демонстрационного правила событиям, неизвестные/неверного типа actions и отсутствие мутаций resolver.

## Найдено и возвращено исполнителям

1. Runtime TypeError у Intl.DateTimeFormat: смешивались dateStyle/timeStyle и timeZoneName. Исправлено, formatter вынесен и покрыт тестами.
2. Двойной callback при выборе шаблона мог терять фильтр и создавать лишнюю историю. Оставлен один управляемый переход.
3. Unavailable action до открытия demo скрывался empty state. Изменён приоритет состояний.
4. Return из unavailable мог оставлять пользователя в том же состоянии и расходовать историю. Возврат теперь очищает unavailable отдельно.
5. Скрытие workspace размонтировало EvidenceBrowser и теряло локальный поиск. Компонент сохраняется смонтированным.
6. Повторный заголовок инцидента, недоступная кнопка Back на overview, подпись textarea и закрытие mobile navigation.
7. Перекрытие log-фильтрами copilot при ширине viewport 1024px. Панель адаптируется по своей ширине, не только viewport.

## Итоговая приёмка

Проверено координатором 2026-09-12:

| Проверка | Результат |
| --- | --- |
| `npm test` | 15/15 pass |
| `npm run typecheck` | Pass |
| `npm run build` | Pass, включая появившийся параллельно `/api/logs` |
| `git diff --check` | Pass |
| Прямое открытие synthetic demo без API-ключа | Pass |
| Гипотеза / аномалия → точный DEMO-E-103 → raw/source/fields | Pass |
| DEMO-T-3 → ровно 2 matching records, Back → Patterns | Pass |
| Timeline: 6 событий по UTC, оговорка о причинности | Pass |
| Поиск без совпадений при открытом evidence inspector | Pass: пустой результат, выбранный источник остаётся доступен |
| Live `open_incident` с ID демо до и после открытия demo | Pass: unavailable, без подстановки synthetic records |
| Return из unavailable сохраняет поиск `timeout` и историю | Pass |
| Demo/localOnly сообщения исключаются из chat request | Pass, проверено по перехваченному request body |
| Невалидный JSON-контракт ответа AI | Pass: видимая ошибка, без падения UI |
| Панель логов на 375, 768, 901, 1024, 1440px | Нет горизонтального переполнения страницы/перекрытия copilot |
| Mobile navigation | Закрывается после выбора; закрытый sidebar невидим и исключён из Tab; Escape поддерживается |
| Accessibility snapshot — evidence + inspector, mobile | 100/100 после исправления контраста |
| Accessibility snapshot — incident analysis, mobile | 100/100 после исправления иерархии заголовков |

Проверки accessibility — автоматические снимки конкретных состояний, не полная сертификация всего продукта. У всех проверенных input/select/textarea есть доступная подпись; задан язык документа и разрешено масштабирование.

Использовались dev preview на 3100 с отключёнными OpenAI/MCP и production preview на 3101 с фиктивным ключом. `/api/chat` в production-браузере был перехвачен локальным mock, реальные запросы к AI не выполнялись. Production preview после приёмки остановлен. Помимо временного 404 браузерного ресурса, runtime-ошибок в проверенной production-версии не обнаружено; промежуточные ошибки HMR во время параллельного редактирования не считаются финальным результатом.

Неблокирующие предупреждения окружения: npm `always-auth`, Node MODULE_TYPELESS_PACKAGE_JSON при native TS imports; существующий `next start` предупреждает об `output: standalone` (deployment-конфигурация не менялась).

Координатор дополнительно исправил оставшийся CSS override `panel-kicker`, контраст severity badges и сделал названия гипотез настоящими h3.

## Параллельные изменения

В ходе проверки другой процесс добавил `LiveLogExplorer`, `/api/logs`, `lib/clickhouse.ts`, `logs-contract.ts`, изменения env/Docker/README и интеграцию live logs в workspace. Эти изменения сохранены. Они включены в последнюю сборку, но достоверность live-данных и server-side ClickHouse queries не проверялась в рамках этих трёх задач. Внешняя начальная страница также содержит фиксированное количество событий; наша проверка не подтверждает его актуальность.

## Границы результата

- Демо — шесть синтетических OpenStack-inspired событий, а не обработанный Loghub.
- UI не реализует ingestion, production anomaly detection или обучение/калибровку confidence.
- Live MCP chat сохранён. Для `open_incident`, `show_timeline`, `show_service` нужен server-side investigation loader; до его появления UI показывает unavailable. Live `show_logs` после параллельных изменений открывает отдельный обозреватель, а не синтетическую панель.
- End-to-end запросы к реальному OpenAI/ClickHouse не входят в эту локальную UI-приёмку. В браузерном тесте chat responses могут подменяться; это не проверка backend AI.
- Источник `sample`, baseline отсутствует, причины не подтверждены. Эти ограничения видны в UI.
