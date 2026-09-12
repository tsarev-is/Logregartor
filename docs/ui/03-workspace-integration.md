# UI-03: интеграция базовых компонентов в текущий workspace

## Зачем

Воспроизводимый сценарий из требований: аномалия → связанные события → вероятная причина → доказательства → следующая проверка. Chat — Should have; демо не должно требовать LLM/ключа.

## Владение

Редактировать `src/ui/components/incident-workspace.tsx`, `src/ui/app/globals.css` (только shell/responsive), создать `src/ui/lib/investigation-navigation.ts`. Можно исправить `src/ui/README.md` по итоговому поведению. Отчёт — этот MD.
Прочитать общий README, исходники чата, общий contract и fixture. Не менять `app/api/*`, `lib/chat-contract.ts`, `lib/mcp-client.ts`, общую фикстуру и файлы соседних исполнителей.

## Обязательное поведение

1. Сохранить исходный light/coral дизайн, sidebar и copilot; вынести статичный checkout detail, Metric и timeline из монолита. Встроить `IncidentAnalysis` и `EvidenceBrowser` из UI-01/02 по их интерфейсам.
2. Главный empty state имеет кнопку `Open demo investigation`, которая напрямую открывает `DEMO_INVESTIGATION`, независимо от AI/MCP readiness. `Open demo incident` в quick prompts также всегда локальный. Не отправлять synthetic сообщения в будущую историю серверного AI (mark localOnly).
3. Демо явно synthetic и snapshot даже при подключённом MCP. Статус MCP отдельно от источника показанных данных; не показывать фиктивные live metrics/counts.
4. Контролируемый state: активное investigation, EvidenceView, selectedEvidenceId, templateId, service. Клик evidence из гипотезы открывает logs + точный inspector. Клик template открывает filtered logs. Назад восстанавливает предыдущий view/filter/selection. Не сбрасывать поиск из-за ответа чата без действия пользователя.
5. Экспортировать pure `resolveInvestigationAction(action, investigation)` из navigation. Возвращает `InvestigationSelection | null`. Известные targets: investigation.id (overview/timeline/logs), evidence.id (logs/timeline), template.id (logs), service exact match (show_service). Строго учитывать kind; неизвестное сочетание kind/target → null. Никаких fallback на первый event или демо для произвольного MCP ID.
6. Typed AI action в демо может разрешаться только по demo IDs при локальном сообщении; live messages не открывают synthetic data даже если ID совпал. Для live без data adapter показать `Data view unavailable`, тип/ID, объяснение отсутствия loader и возврат, не «reference resolved».
7. Рабочие nav Incidents/Log explorer/Patterns ведут к соответствующим views при открытом demo. Topology не имитировать: disabled/объяснение unavailable. Убрать или честно disabled неработающие Settings/Notifications/search. Collapse copilot либо реализовать с доступным reopen, либо убрать неработающую кнопку.
8. Сохранить существующие POST chat/status и обработку ошибок, проверить `isChatReply` на клиенте перед отображением. Различать нет ключа, ошибка chat, неизвестный source. Не менять серверный API и не передавать секреты в browser.

## Интерфейс selection (общий контракт)

`InvestigationSelection = { view: 'overview' | EvidenceView; evidenceId: string | null; templateId: string | null; service: string | null }`.
`resolveInvestigationAction` не мутирует input и не делает сетевых запросов. Импорт UiAction только type.

## Приёмка

- Сценарий выполняется без сети/ключа через прямое открытие demo.
- Chat работает по прежнему API, synthetic/local messages исключены из server history.
- Evidence из гипотезы → точная строка; template → filtered logs; back → прежний view.
- Неизвестный live ID → unavailable; synthetic никогда не маркируется live.
- Нет горизонтального overflow в прежней проблемной зоне 901–1200px и на mobile 375px.
- Не добавлять npm зависимости. Typecheck; интеграционные build/browser проверит координатор.

## Результат

- Реализован shell расследования в `src/ui/components/incident-workspace.tsx`: локальное открытие synthetic snapshot, controlled selection/history, интеграция `IncidentAnalysis` и сохраняемого в DOM `EvidenceBrowser`, а также честный экран unavailable для live action без loader.
- Добавлен pure resolver `src/ui/lib/investigation-navigation.ts`; он сопоставляет только допустимые kind/target IDs текущего investigation и не использует fallback.
- В `src/ui/app/globals.css` добавлены shell/responsive корректировки для 901–1200px и mobile, disabled/focus states и заголовок investigation.
- Проверка: `npm run typecheck` из `src/ui` — успешно. Общий build и browser acceptance остаются за координатором.
- Ограничение: live MCP chat actions намеренно не открывают fixture — для них нужен будущий server-side investigation data adapter.
