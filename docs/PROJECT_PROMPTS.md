# Промпты для RS Best Hostel

Перед работой передайте помощнику этот файл и корневой `AGENTS.md`.

## Новая функция

> Сначала изучи существующие шаблоны React, FastAPI, SQLAlchemy и Alembic. Реализуй **[функцию]** целиком: проверку данных, права доступа на API, журнал аудита, миграцию базы, интерфейс на узбекском языке латиницей и изолированные тесты. Не удаляй историю финансовых операций. В конце перечисли изменённые файлы, порядок применения миграции, выполненные проверки и необходимые настройки внешних сервисов.

## Платежи и расчёты

> Проследи весь путь данных для **[изменения]**: схему запроса, транзакцию, ограничения базы, блокировку расчётного периода, отчёты, главную панель и аудит. Используй Decimal и NUMERIC для сумм, календарную дату Ташкента для бизнес-правил. Обязательно требуй безопасный `Idempotency-Key` для каждой записи платежа и расхода; конфликт ключа с другим содержимым верни как 409. Сохрани старые и новые значения и причину. Добавь проверки частичной и полной оплаты, повтора, конфликта, запроса без ключа и отката. Не меняй прошлые начисления без явной записи в истории.

## Проверка безопасности

> Проверь **[раздел]**: права на API, токены и сессии, ограничение частоты запросов, владение данными, доступ к личным файлам, утечку секретов и полноту аудита. Подтверди каждую проблему кодом, исправь её минимальной безопасной миграцией и добавь изолированные регрессионные тесты. Не обращайся к реальным внешним сервисам и не выводи секреты.

## Проверка интерфейса

> Проверь **[экран или сценарий]** на широком и мобильном экранах. Все видимые подписи, подсказки и ошибки должны быть на узбекском языке латиницей. Используй общие функции форматирования, добавь состояния загрузки, пустого списка и ошибки, проверь работу с клавиатуры. Внеси нужные улучшения и собери production-версию сайта.

## Приём заявок, ссылки и AI документов

> For the applicant flow, preserve quick file storage and asynchronous status polling. Keep document bytes on the configured private server and do not log or persist OCR text. Require explicit consent before processing. With local consent only, run Tesseract OCR using Uzbek Latin/Cyrillic, English, and Russian models. With separate `X-External-AI-Consent`, send the original image directly to `dots-studio/dots-3-note-preview:free` through the server-side OpenRouter key; validate its JSON locally and fill blank form fields only. Preserve manual entry and human review; tell the applicant to verify every suggestion. Retry must verify the applicant session, CSRF, file ownership, and fresh consent; late OCR must not restore extracted data after deletion or replacement. Never log provider response bodies, secrets, image bytes, or extracted values. Never promise 100% accuracy or let OCR approve an application.

> The configured Dots3-Note Preview free endpoint supports image inputs and JSON response formatting. Keep its exact model ID as the default OpenRouter route. Do not put `OPENROUTER_API_KEY` in the browser bundle. A user who selects external processing must explicitly consent before the original document leaves the private file store; use the model directly rather than running local OCR first. Do not send restrictive provider-routing parameters that cause the selected free endpoint to be rejected. Request a JSON object and validate provider JSON locally; report provider failures without logging provider bodies, secrets, image bytes, or extracted values.

## Одобрение заявки и восстановление заселения

> Проследи переход заявки от решения персонала до списка жителей: проверь статус заявки, `resident_id`, профиль жителя, период комнаты и первый расчётный период. Все записи обычного одобрения должны сохраняться одной транзакцией. При повторном заселении ранее выбывшего жителя очисти устаревшую дату выезда и сохрани её в audit details. Если заявка уже одобрена, но связь с жителем потеряна, разреши сотруднику безопасно восстановить её через существующий API: повторно проверь доступность комнаты и даты, покажи вероятные совпадения для ручного выбора, не создавай дубликат автоматически, сохрани исходный статус/дату одобрения и запиши восстановление в аудит. Проверь также, что прямая ссылка на карточку жителя остаётся редактируемой, даже если текущий фильтр скрывает его строку. Повторный запрос не должен создавать второй профиль, проживание, расчёт или событие одобрения. Обнови экран персонала на узбекском языке латиницей, индекс проекта и изолированное регрессионное покрытие; не читай личную локальную БД.

## Внешний сервис или устройство

> Спроектируй адаптер для **[провайдера]** по его актуальному официальному протоколу. Храни ключи только на сервере, проверь подписи, защиту от повторных callback и идемпотентность, не записывай секреты в логи. Если интеграция не настроена, она должна безопасно отказывать. Добавь контрактные тесты с имитацией ответов. Во время разработки не отправляй реальные сообщения, не принимай оплату и не управляй устройствами.
