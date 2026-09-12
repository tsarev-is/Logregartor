# UI-01: аномалия, ранжированные гипотезы, следующие проверки

## Зачем

Закрывает видимую часть Must have «Detect one anomaly class», «Ranked root-cause hypothesis» и DoD «clear next-step recommendation», «documented limitations».

## Реализация

Создать `src/ui/components/investigation/incident-analysis.tsx` и `analysis.module.css`.
Экспорт `IncidentAnalysis({ investigation, onOpenEvidence })`.
Типы импортировать из `@/lib/investigation-contract`; callback `(evidenceId: string) => void`.
Прочитать `docs/ui/README.md`; только эти два source-файла и этот MD принадлежат исполнителю.

## Компоненты внутри

1. `IncidentSummary`: заголовок, статус, source/dataset, synthetic badge, UTC-интервал, сущности, coverage. Не приравнивать число логов к числу инцидентов/запросов.
2. `AnomalyFinding`: класс, описание, метод/правило, observed vs baseline с единицей и baseline-интервалом, порог, IDs доказательств. Если чисел нет, не рисовать нули и не изобретать график.
3. `HypothesisList`: сортировка по rank без изменения props; первая раскрыта. Раздельно причина-гипотеза, reasoning, supporting и contradicting evidence, missing evidence. Ссылки открывают существующие IDs. Не рисовать процентов confidence: в контракте qualitative `confidence` и объяснение `confidenceReason`.
4. `NextChecks`: конкретная безопасная проверка, её expected result и evidence. Никакой auto-remediation или выдуманного runbook URL.
5. `Limitations`: явно отображать limitations, insufficient evidence/abstained.

## Состояния и поведение

- Пустой список аномалий/гипотез/проверок имеет честное сообщение, а не пустую рамку.
- Статус `insufficient_evidence` не подписывать как установленную причину.
- Evidence callbacks только при наличии записи в investigation.evidence; сломанная ссылка обозначается как unavailable, не переходит к первой записи.
- Интерактивное раскрытие через native details/summary; доступные названия evidence-кнопок содержат ID.
- Не выводить старые checkout-метрики, 87%, 14 evidence items, если их нет в модели данных.

## Приёмка

- Видны все три уровня: факт аномалии, гипотеза причины, проверка для уточнения.
- Две гипотезы имеют понятный порядок и независимые доказательства.
- Ссылка на evidence вызывает callback с точным ID.
- Нет неподтверждённой причинности, процентов и опасных исполняемых действий.
- Панели читаемы при ширине 375px; длинные строки переносятся.
- Запустить typecheck и сообщить результат, не исправляя чужие незавершённые импорты.

## Результат

- Реализованы `src/ui/components/investigation/incident-analysis.tsx` и `analysis.module.css`: summary с source/coverage/synthetic/UTC metadata, findings, ранжированные qualitative hypotheses через native `details`, безопасные next checks и limitations.
- Evidence controls вызывают callback только для IDs, присутствующих в `investigation.evidence`; отсутствующие IDs помечаются unavailable. Пустые списки имеют отдельные честные состояния.
- Проверка: `npm run typecheck` из `src/ui` — успешно.
- Ограничение: компонент ожидает, что интеграционный слой передаст `Investigation` и обработчик `onOpenEvidence`; browser/workspace-переходы находятся в соседних UI-задачах.
