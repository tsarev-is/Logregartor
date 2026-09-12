# UI-02: timeline, log explorer и шаблоны

## Зачем

Закрывает Must have «Evidence timeline», проверку разбора на шаблоны и DoD «evidence-linked output». Должен позволять доказать каждое существенное наблюдение исходными строками.

## Реализация и интерфейс

Создать `src/ui/components/investigation/evidence-browser.tsx`, `evidence.module.css`.
Экспорт `EvidenceBrowser({ investigation, view, selectedEvidenceId, templateId, service, onViewChange, onSelectEvidence, onSelectTemplate, onSelectService })`.
Типы из `@/lib/investigation-contract`: `view: EvidenceView`, `selectedEvidenceId: string | null`, `templateId: string | null`, `service: string | null`.
Callbacks: `onViewChange(view: EvidenceView)`, `onSelectEvidence(id: string | null)`, `onSelectTemplate(id: string | null)`, `onSelectService(service: string | null)`.
Прочитать общий README. Не менять shell/контракт/фикстуру/глобальный CSS.

## Представления

1. `timeline`: сортировка evidence по timestamp, связь по entity/request, role (observation/symptom/possible_trigger), пояснение correlationBasis. UTC-время. Нажатие открывает raw-event inspector. Линия времени НЕ причинный граф.
2. `logs`: поиск по message/raw/ID/entity, фильтр severity и service, сортировка по времени. Количество показанных и доступных записей + coverage. Не сообщать «полный датасет», если это sample/partial. Перенос длинных строк и multiline stacktrace без HTML-вставки.
3. `patterns`: список stable templates, count по текущему bounded evidence, сервисы, переменные. Нажатие вызывает onSelectTemplate(id), shell переключает view в logs. Не путать количество записей в snapshot с полным объёмом исходного датасета.

## Inspector и provenance

Показывает exact ID, timestamp, severity, message, raw, parsed fields, template, entity, filename/line, redacted flag. Native details или inline section, без modal focus-trap. Кнопка очистить выбор. Если ID неизвестен, показать «Evidence unavailable» вместо молчаливого выбора другой записи.
Показать metadata investigation.source: dataset, absolute UTC time range, query description, coverage; эти поля должны быть доступны в каждом представлении.
Показывать why relevant/correlationBasis отдельно от raw-данных.

## Состояния и приёмка

- Фильтр без совпадений: «No matching events» и рабочий reset; данные не удаляются.
- Смена выбранного evidence должна раскрыть именно его, даже если локальный поисковый фильтр скрывает строку (inspector может быть независимым от результатов).
- Из шаблона видны только его записи, сброс шаблона и service работают.
- Совместимые управляемые props, без отдельной копии view/selectedEvidenceId в локальном state.
- Native controls, label для поиска и фильтров, aria-pressed для переключателей, aria-live только для результатов. Не использовать огромную live region для всего лога.
- На 375/768/1440px нет переполнения страницы. Все значимые сообщения можно прочитать.
- Typecheck и раздел «Результат» в этом MD.

## Результат

- Реализованы `src/ui/components/investigation/evidence-browser.tsx` и локальные стили `evidence.module.css`: управляемые вкладки, UTC timeline, поиск и фильтры логов, шаблоны, provenance и raw-event inspector. Шаблон передаётся только через `onSelectTemplate`; переход в logs выполняет shell, без дублирующего navigation callback.
- Выбранный evidence отображается в inspector независимо от текущего локального поиска; неизвестный ID показывает `Evidence unavailable`. Active controlled template/service filters are visible in every view and clear together through the shell's single `onSelectTemplate(null)` navigation path.
- Проверки: `npm run typecheck` из `src/ui` — успешно; UTC formatter вынесен в `lib/format-utc.ts`, проверен в Node с `timeZoneName` и явными date/time-полями. Browser uses container queries, so controls and log rows adapt to the panel width (375/415/720px), not only viewport.
- Ограничение: компонент ждёт подключения контролируемых props и callbacks из workspace; реального data adapter или загрузки данных этот UI slice не добавляет.
