# Индекс проекта RS Best Hostel

Этот файл — карта кода и точка входа для людей и ИИ-агентов. Он описывает проверенное состояние репозитория на 2026-10-30. Для новых изменений обновляйте этот индекс в той же задаче, что и код; правила находятся в корневом AGENTS.md.

## Быстрый старт для агента

1. Прочитайте корневой AGENTS.md: в нём продуктовые, финансовые, авторизационные и приватностные ограничения.
2. Прочитайте нужный раздел этого файла и откройте названные исходники. Индекс помогает найти код, но исходники и миграции — источник истины.
3. Для API сверьте схему в backend/app/schemas.py, маршрут в backend/app/api.py или backend/app/admissions_api.py, модель в backend/app/models.py и соответствующую бизнес-логику/миграцию.
4. Для пользовательского сценария сверьте страницу frontend/src/pages, вызовы frontend/src/api.ts, типы frontend/src/types.ts и подписи frontend/src/locales/uz.ts.
5. Для финансовых, ролевых, файловых и миграционных правил найдите отдельный тест из backend/tests; тестовая БД — изолированная SQLite, не корневой dormflow-local.sqlite3.
6. Не читайте и не копируйте .env, файлы базы, загруженные документы, секреты, ключи, токены, пароли или персональные данные в документацию и логи.

## Карта репозитория

| Путь | Назначение |
| --- | --- |
| AGENTS.md | Обязательные инструкции продукта, финансов, доступа, приватности и изменений. |
| README.md | Установка, конфигурация, потоки продукта, планировщики и развертывание. |
| docs/PROJECT_INDEX.md | Эта карта модулей, API, авторизации, функций, тестов и правила сопровождения. |
| docs/PROJECT_PROMPTS.md | Шаблоны запросов к ИИ для разработки функций и проверок. |
| backend/app/ | FastAPI API, бизнес-правила, ORM-модели, безопасность, файлы и фоновые команды. |
| backend/alembic/versions/ | Версионируемые изменения схемы PostgreSQL/SQLite. |
| backend/tests/ | Изолированные pytest-сценарии с SQLite в памяти. |
| frontend/src/ | React/TypeScript SPA, страницы, авторизация, API-клиент, типы и узбекский текст. |
| scripts/ | PowerShell-сценарии первичной настройки Railway и Netlify. |
| .railway/railway.ts | Railway IaC for PostgreSQL, the API, scheduled jobs, and private OCR environment settings. |
| docker-compose.yml | Локальная/одноузловая сборка PostgreSQL, API и Nginx-фронтенда. |
| netlify.toml | Сборка SPA и прокси API для Netlify. |
| main.py | Удобная точка запуска FastAPI из корня; приложение определено в backend/app/main.py. |
| .env.example | Имена настроек и безопасные примеры; не реальные секреты. |

## Основные потоки

### Персонал и авторизация

1. Оператор создаётся идемпотентной первичной настройкой через backend/app/bootstrap.py и backend/app/seed.py.
2. React AuthProvider загружает пользователя через GET /api/auth/me, вход отправляет email/пароль в POST /api/auth/login.
3. Сервер проверяет пароль через pwdlib, создаёт короткоживущий access JWT и refresh JWT. Клиент хранит их в localStorage и добавляет access токен как Bearer.
4. При 401 клиент однократно обновляет access/refresh через /api/auth/refresh и повторяет исходный запрос; запросы авторизации не запускают рекурсивный refresh.
5. API dependencies.py повторно проверяет подпись, тип access токена, активность пользователя и UUID. Защита роутов в интерфейсе — только навигация, не граница безопасности.
6. OPERATOR управляет учётными записями, аудитом и чувствительными действиями. ADMIN выполняет повседневные операции в рамках разрешённых API.

Точки входа: backend/app/security.py, backend/app/dependencies.py, backend/app/api.py, frontend/src/auth.tsx, frontend/src/api.ts и frontend/src/App.tsx.

### Публичная заявка абитуриента

Staff create campaigns and invitations. Applicants open /apply, save a draft, upload requested files, and submit through a CSRF-protected session. After explicit consent, either local Tesseract runs on the private server, or a separate OpenRouter consent sends normalized image pages to `dots-studio/dots-3-note-preview:free` for structured field suggestions. OpenRouter is never called from the browser. The provider request allows up to 6,000 completion tokens and 120 seconds; the frontend continues polling long enough for that request. The response parser also accepts labelled text or nested labelled JSON, then applies the same local field validation. Validated suggestions fill blank fields only; the frontend shows results asynchronously and tells applicants to verify every value against the original. Retry requires fresh consent; deleting or replacing the file clears extracted values and a late task cannot restore them. Staff review the original and decide the application; OCR does not approve it.

См. backend/app/admissions_api.py, backend/app/file_storage.py, backend/app/ai_extraction.py и frontend/src/pages/Admissions.tsx. Файлы частные. ИИ-подсказки распознавания доступны только при согласии; это не автоматическое одобрение. Настоящие Telegram, антивирус и платёжные callback не подключены.

Одобрение сотрудником одной транзакцией связывает заявку с `Resident`, периодом `ResidencePeriod` и первым расчётным периодом. При повторном заселении ранее выбывшего связанного жителя очищается устаревшая дата `departed_on`, чтобы активный профиль отображался в списке. Если у старой уже одобренной заявки отсутствует `resident_id`, персонал может восстановить связь из карточки: выбрать найденного совпадающего жителя либо создать профиль, заново проверив комнату, даты и тариф. Повторное связывание сохраняет статус и исходную дату одобрения, не добавляет фиктивное событие смены статуса и записывается в аудит как `APPLICATION_RESIDENT_LINKED`; предыдущая дата выезда включается в audit details. После восстановления житель появляется в `GET /residents`.

### Финансы, проживание и планировщики

- Billing cycle — интервал [start_date, end_date). Деньги хранятся как Decimal/Numeric(14,2). Платёж неизменяем; исправление — отдельный PaymentAdjustment. Расход можно void с причиной, запись остаётся.
- Создание платежа и расхода требует Idempotency-Key; запрос без ключа отклоняется до записи. Перед распределением платежа блокируется затронутый период. Баланс строится в backend/app/billing.py.
- Проверка мест и интервалы заселения находятся в backend/app/residency.py. Бизнес-дата вычисляется в Asia/Tashkent, timestamps — UTC.
- GET не создаёт периоды. backend/app/scheduled_jobs.py запускает явный дневной rollover и создаёт адресные напоминания; backend/app/purge_expired_files.py отдельной командой удаляет просроченные закрытые файлы.

## Авторизация API

Обозначения: «Публичный» — без токена, но с проверками сессии/CSRF/ограничения частоты там, где это требуется; «Персонал» — активный OPERATOR или ADMIN через get_current_user; «Оператор» — require_operator; «Настройка тарифа» — require_billing_permission (OPERATOR, либо ADMIN если ADMINS_CAN_ADJUST_BILLING=true). Любая запись аудита должна сохранять автора и безопасные метаданные; не включайте документы или секреты.

### Основной API — backend/app/api.py

Все пути ниже имеют префикс /api.

| Метод и путь | Доступ | Назначение |
| --- | --- | --- |
| GET /health | Публичный | Состояние API и БД для healthcheck. |
| POST /auth/login | Публичный | Вход, access/refresh пара токенов. |
| POST /auth/refresh | Публичный | Проверка refresh JWT и выпуск пары токенов. |
| GET /auth/me | Персонал | Текущая активная учётная запись. |
| GET /users | Оператор | Перечень сотрудников. |
| POST /users | Оператор | Создать ADMIN; роль OPERATOR нельзя выдать через эту схему. |
| PATCH /users/{user_id} | Оператор | Изменить администратора, отключить или сменить пароль. |
| GET /rooms | Персонал | Фильтрованный и постраничный перечень комнат. |
| POST /rooms | Персонал | Создать комнату. |
| PATCH /rooms/{room_id} | Персонал | Изменить комнату с проверкой вместимости/назначений. |
| DELETE /rooms/{room_id} | Оператор | Архивировать комнату, если нет препятствующих связей. |
| GET /residents | Персонал | Поиск и постраничный список жителей с состоянием расчётов. |
| POST /residents | Персонал | Создать жителя и, если задан тариф/период, первый счёт. |
| GET /residents/{resident_id} | Персонал | Карточка, расчётные периоды и журнал изменений. |
| PATCH /residents/{resident_id} | Персонал | Обновить сведения, назначение комнаты и условия биллинга. |
| POST /residents/{resident_id}/archive | Персонал | Архивировать профиль с сохранением истории. |
| POST /residents/{resident_id}/checkout | Персонал | Зафиксировать выезд и закрыть подходящие будущие неоплаченные периоды. |
| POST /residents/{resident_id}/restore | Оператор | Восстановить архивный профиль. |
| POST /residents/{resident_id}/extend | Настройка тарифа | Продлить текущий период, сохранить старые/новые даты, сумму и причину. |
| GET /residents/{resident_id}/payments | Персонал | Платёжная история конкретного жителя. |
| GET /payments | Персонал | Фильтрованный список фактических платежей. |
| POST /payments | Персонал | Записать платёж; обязательный Idempotency-Key, проверка и блокировка затронутого счёта. |
| GET /expenses | Персонал | Фильтрованный перечень расходов. |
| POST /expenses | Персонал | Записать расход с обязательным Idempotency-Key и автором. |
| POST /expenses/{expense_id}/void | Оператор | Отменить проведённый расход по обязательной причине, не удаляя строку. |
| POST /payments/{payment_id}/adjustments | Оператор | Создать аудируемую корректировку платежа с причиной. |
| GET /payments/{payment_id}/adjustments | Оператор | История корректировок. |
| GET /dashboard | Персонал | Агрегаты заселения и финансов, основанные на сохранённых данных. |
| GET /notifications | Персонал | Только уведомления текущего пользователя. |
| POST /notifications/read-all | Персонал | Отметить прочитанными только уведомления текущего пользователя. |
| GET /settings | Персонал | Прочитать настройки общежития. |
| PUT /settings | Оператор | Изменить настройки с аудитом. |
| GET /audit | Оператор | Постраничный журнал действий. |
| GET /reports/{kind}.{file_format} | Персонал | CSV/XLSX/PDF отчёты по доступным видам и диапазону дат. |

Точное поведение валидации, пагинации, транзакций и статус-кодов смотрите в handler-функциях api.py и схемах. Для новой операции обязательно проверяйте роль на сервере.

Имена обработчиков из таблицы, сгруппированные по ресурсу: health; login, refresh, me; list_users, create_user, update_user; list_rooms, create_room, update_room, archive_room; list_residents, create_resident, get_resident, update_resident, archive_resident, checkout_resident, restore_resident, extend_resident, resident_payments; list_payments, create_payment, adjust_payment, list_adjustments; list_expenses, create_expense, void_expense; dashboard; list_notifications, mark_notifications_read; get_settings, update_settings; list_audit; export_report. Все эти функции находятся в backend/app/api.py.

### Приём заявок — backend/app/admissions_api.py

Персональные маршруты имеют префикс /api; публичные — /api/public. Все маршруты staff_router требуют активный аккаунт персонала; дополнительно отмеченные операции требуют оператора.

| Метод и путь | Доступ | Назначение |
| --- | --- | --- |
| GET /dormitories | Персонал | Список корпусов; оператор может запросить неактивные. |
| POST /dormitories | Оператор | Создать корпус. |
| PATCH /dormitories/{dormitory_id} | Оператор | Изменить корпус. |
| GET /admissions/campaigns | Персонал | Кампании. |
| POST /admissions/campaigns | Оператор | Создать кампанию и правила анкеты/согласия. |
| PATCH /admissions/campaigns/{campaign_id}/status | Оператор | Активировать, приостановить или закрыть кампанию. |
| GET /admissions/invitations | Персонал | Список приглашений. |
| POST /admissions/invitations | Персонал | Выпустить приглашение; возвращаемый секрет показывается только при создании. |
| POST /admissions/invitations/{invitation_id}/pause | Персонал | Приостановить приглашение. |
| POST /admissions/invitations/{invitation_id}/resume | Персонал | Возобновить приглашение. |
| POST /admissions/invitations/{invitation_id}/revoke | Персонал | Отозвать приглашение. |
| GET /admissions/applications | Персонал | Очередь заявок и фильтры. |
| GET /admissions/applications/{application_id} | Персонал | Карточка/история статусов заявки. |
| POST /admissions/applications/{application_id}/assign-to-me | Персонал | Назначить заявку текущему сотруднику. |
| PUT /admissions/applications/{application_id}/notes | Персонал | Внутренняя заметка, не видимая заявителю. |
| GET /admissions/applications/{application_id}/duplicates | Персонал | Найти вероятно совпадающих жителей для ручной проверки. |
| POST /admissions/applications/{application_id}/request-info | Персонал | Запросить у заявителя уточнения. |
| POST /admissions/applications/{application_id}/start-review | Персонал | Начать проверку. |
| POST /admissions/applications/{application_id}/reject | Персонал | Отклонить заявку с причиной. |
| POST /admissions/applications/{application_id}/approve | Персонал | Одобрить, назначить комнату и создать/связать жителя и счёт; также восстановить отсутствующую связь у уже одобренной заявки с аудитом `APPLICATION_RESIDENT_LINKED`. |
| POST /admissions/applications/{application_id}/tracking-code | Персонал | Повторно выпустить код доступа после ручной проверки личности. |
| GET /admissions/summary | Персонал | Сводка приёма, начислений и оплат связанных жителей. |
| GET /admissions/settings | Authenticated staff | Reports storage, retention, upload availability, local Tesseract readiness, optional external AI readiness, and a safe configuration issue. |
| GET /admissions/applications/{application_id}/files/{file_id} | Персонал | Авторизованная выдача приватного файла. |
| GET /admissions/applications/{application_id}/files/{file_id}/signed-url | Персонал | Короткая подписанная ссылка для S3, если выбран S3. |
| DELETE /admissions/applications/{application_id}/files/{file_id} | Персонал | Удалить закрытый файл и связанный извлечённый результат по правилам хранения. |
| POST /invitations/exchange | Публичный | Обменять приглашение на сессию заявителя. Ограничение частоты; `campaign` сообщает готовность AI и безопасный код причины, не раскрывая модель или секреты. |
| POST /application/access-code | Публичный | Проверить одноразовый код для статуса и создать сессию. Ограничение частоты. |
| GET /application | Публичный | Получить анкету текущей сессии. |
| PATCH /application | Публичный | Изменить черновик; CSRF. |
| GET /application/files | Публичный | Список только собственных загруженных файлов. |
| POST /application/files | Applicant session | Validates and stores the file, then queues processing after `X-AI-Processing-Consent: true`; `X-External-AI-Consent: true` selects direct Dots3-Note Preview processing, otherwise local Tesseract runs. |
| POST /application/files/{file_id}/extract | Applicant session | Retries processing for a file belonging to the signed-in application; verifies CSRF/session and fresh processing consent. External processing requires its own consent header. |
| POST /application/submit | Публичный | Проверить обязательные сведения/согласие и подать анкету; CSRF. |
| GET /application/status | Публичный | Проверить свой статус. |
| POST /application/respond | Публичный | Ответить на запрос уточнения; CSRF. |

Префиксы задаются в admissions_api.py и подключаются main.py. Не считайте публичную сессию аккаунтом персонала.

Имена обработчиков из таблицы: list_dormitories, create_dormitory, update_dormitory; list_campaigns, create_campaign, change_campaign_status; list_invitations, create_invitation, pause_invitation, resume_invitation, revoke_invitation; list_applications, get_application, assign_application, update_application_notes, find_application_duplicates, request_application_info, start_application_review, reject_application, approve_application (обычное одобрение и восстановление отсутствующей связи профиля), reissue_tracking_code, admission_summary, admission_settings, download_application_file, signed_application_file_url, delete_application_file; exchange_invitation, exchange_access_code, get_public_application, update_public_application, list_public_application_files, upload_public_file, retry_public_file_extraction, submit_public_application, public_application_status, respond_to_request. Все эти функции находятся в backend/app/admissions_api.py.

## Структура backend и символы

### API и схема

- backend/app/api.py: основной router; обработчики перечислены выше. Вспомогательные функции: natural_room_key, page_result, ensure_due_periods, verify_room_capacity, net_payment, get_report_rows, spreadsheet_safe, xlsx_file, pdf_file. Здесь находятся проверки данных/условий операций, расчёты панели и формирование экспортов.
- backend/app/admissions_api.py: staff_router/public_router; route handlers are listed in the route table. Helpers include `_digest`, `_aware`, `_require_staff`, `_rate_limit`, `_invitation_status`, `_invite_out`, `_event`, `_phone`, `_validate_extra`, `_apply_values`, `_public_application`, `_application`, `_student_session`, `_student_write_session`, `_set_student_session`, `_rotate_csrf`, `_public_campaign`, `_application_status`, `_public_file_out`, `_run_file_extraction`, `_schedule_file_extraction`. Extraction background tasks receive `allow_external_ai`; their conditional update cannot restore results after file deletion/replacement. `retry_public_file_extraction` honors a fresh external-provider consent and does not silently fall back to local OCR when external processing was selected.
- backend/app/schemas.py: Pydantic-контракты запросов и ответов для auth, сотрудников, комнат, жителей, billing, платежей, расходов, отчётов, кампаний, приглашений, публичных анкет/статусов и файлов. `PublicCampaignOut` reports `ai_processing_issue`, `local_ocr_available`, and `external_ai_processing_available`. Validators: ResidentFields.validate_billing_range, ResidentUpdate.validate_billing_range, ExtendRequest.require_one_method, ExpenseCreate.normalized_description_required, ExpenseVoid.normalized_reason_required, PaymentAdjustmentCreate.nonzero_amount, CustomFieldDefinition.validate_options, ApplicationDraftIn.ordered_dates, ApplicationApproveIn.ordered_stay.
- backend/app/models.py: SQLAlchemy-модели и ограничения: User, Room, Resident, BillingPeriod, BillingChange, Payment, Expense, PaymentAdjustment, AuditEvent, Notification, SystemSetting, Dormitory, AdmissionCampaign, AdmissionInvitation, StudentApplication, ApplicationStatusEvent, ApplicationAccessSession, ApplicationFile, ApplicationFileBlob, ResidencePeriod, PublicRateLimit. utcnow создаёт UTC timestamp.

### Бизнес-логика и сервисы

- backend/app/billing.py: period_paid, period_balance, current_period, ensure_period, create_initial_period, extend_period, set_period_dates, mark_paid_and_advance, close_unpaid_future_periods_for_departure. Это основной источник правил сумм, периодов и неизменяемой истории корректировок.
- backend/app/residency.py: assert_room_available проверяет пересечения дат и вместимость; record_room_assignment записывает интервал и закрывает заменяемые интервалы; close_open_period завершает проживание.
- backend/app/services.py: today_local, room_out, period_out, resident_out, resident_detail, payment_out, notification_out, expense_out, audit_out. Сериализация API и вычисление отображаемого баланса/статуса.
- backend/app/audit.py: audit добавляет аудиторское событие; notify создаёт уведомление, которое надо адресовать user_id при персональной доставке.
- backend/app/bootstrap.py: bootstrap создаёт начального оператора и базовые настройки/корпус только при отсутствии записей.
- backend/app/scheduled_jobs.py: run_daily_jobs и main — запланированный rollover и персональные ежедневные напоминания; запуск: python -m app.scheduled_jobs.

### Безопасность, конфигурация, файлы и внешние сервисы

- backend/app/security.py: hash_password, verify_password, create_token, create_token_pair. Не хранит refresh-состояние в БД: JWT проверяется криптографически и по типу.
- backend/app/dependencies.py: get_current_user, require_operator, require_billing_permission — обязательные API-зависимости авторизации.
- backend/app/config.py: normalize_database_url, Settings.normalize_openrouter_model, Settings.validate_public_app_url, Settings.public_app_base_url, Settings.public_app_origin, Settings.cors_origin_list, get_settings; Pydantic Settings загружает переменные окружения и корневой .env. `OPENROUTER_MODEL` defaults to `dots-studio/dots-3-note-preview:free` (empty values use this default); `OPENROUTER_API_KEY` remains server-only. public_app_base_url не допускает localhost для ссылок приглашения. `TESSERACT_CMD` optionally overrides the local OCR executable; Docker installs the OCR engine and required language packs.
- backend/app/db.py: SQLAlchemy Base, engine, SessionLocal и get_db dependency. SQLite получает check_same_thread=False; тесты переопределяют get_db.
- backend/app/file_storage.py: sniff_content_type, validate_upload, PrivateFileStorage (configured, _s3, put, local_path, _local_path, signed_download_url, read, delete), singleton storage. Production local storage отключён; поддержаны private PostgreSQL blob, локальная разработка и настраиваемый S3; read используется только после проверки владельца файла для повторного AI-разбора.
- backend/app/ai_extraction.py: AIExtractionResult, _OCRLine, openrouter_configured, openrouter_processing_issue, openrouter_document_processing_available, document_processing_issue, document_processing_available, local_ocr_available, _normalize_content_type, _validate_file, _image_to_jpeg, _pdf_page_images, _image_payload, _prepare_ocr_image, _tesseract_lines, _label_matches, _clean_ocr_value, _scripted_name_field, _fields_from_ocr_lines, _extract_local_ocr, _normalize_date, _parse_labelled_text, _parse_fields, _provider_failure_status, _post_chat_completion, extract_identity_document. Local Tesseract OCR remains the private default; it uses Uzbek Latin/Cyrillic, English, and Russian models, image normalization, TSV word confidence, labeled-field mapping, and conservative validation. With separate external consent, the configured Dots3-Note Preview free vision model receives normalized JPEG image pages; the request allows a 120-second timeout and 6,000 completion tokens. `_parse_fields` accepts the constrained JSON response or falls back through `_parse_labelled_text` to validated labelled text/nested labelled JSON. Other free routes remain blocked. Unexpected HTTP failures preserve only safe categories and status codes, never provider bodies or document contents.
- backend/app/telegram.py: NotificationAdapter и TelegramAdapter — только граница адаптера; реальный провайдер не настроен.
- backend/app/purge_expired_files.py: purge_expired_files, main; пакетная очистка с аудитом, запуск python -m app.purge_expired_files --batch-size 100.
- backend/app/main.py: lifespan проверяет минимальные production-секреты; security_headers, validation_error, database_error и root; подключение роутеров и CORS.
- backend/app/seed.py: main — вызвать bootstrap; опциональный --demo создаёт только комнаты.

## Frontend

- frontend/src/main.tsx: монтирует React, Ant Design Uzbek locale, dayjs locale, CSS и AuthProvider.
- frontend/src/App.tsx: App маршруты; Login, Shell, Protected, Home, OperatorOnly; лениво загружает страницы. Маршруты сотрудников требуют пользователя, вкладки пользователей и аудита скрыты/защищены также проверкой OPERATOR в клиенте. Только маршрут `/app` получает компактную оболочку панели; на ширине от 576 px сохраняется боковая навигация, остальные экраны продолжают использовать обычную адаптивную оболочку.
- frontend/src/auth.tsx: AuthProvider и useAuth (login, logout, reloadUser, начальная проверка сессии).
- frontend/src/api.ts: Axios api с Bearer header, автоматическим однократным refresh, saveSession, clearSession, hasSession, errorMessage. Добавляйте общие HTTP-поведения здесь; никогда не помещайте серверный секрет в VITE_ переменную.
- frontend/src/types.ts: TypeScript-контракты API (Role, User, Room, Resident, BillingPeriod/Change, Payment/Adjustment, Expense, Dashboard, Settings, Audit, admissions и public session types).
- frontend/src/locales/uz.ts: единственное общее место для подписей на узбекском латинском; moneyToMinorUnits, isPositiveMoney, sumMoney, formatMoney, formatDate, todayUzbekistan, statusLabel, auditActionLabel, auditEntityLabel, auditDetailLabel. `APPLICATION_RESIDENT_LINKED`, `StudentApplication`, `previous_departed_on` и `repair_of_approved_application` переведены для журнала аудита.
- frontend/src/pages/Dashboard.tsx: панель состояния; `Dashboard` загружает существующий `GET /api/dashboard` (доступ «Персонал»), `Metric` иконками/значениями показывает жителей, занятость и фактический доход, `moneyAxis` форматирует ось графика, `initials` формирует буквенные аватары. Графики показывают заполненность комнат столбцами, общую занятость мест кольцевой диаграммой и тренд дохода линией; правая колонка показывает недавно заселённых жителей, финансовые показатели и последние платежи из того же ответа API. Новых API, моделей или миграций нет.
- frontend/src/pages/Residents.tsx: список, карточка, фильтры, заселение/выезд, тариф, история оплат; карточку жителя по прямой ссылке можно редактировать и когда профиль скрыт текущим фильтром; cleanDate, statusTag.
- frontend/src/pages/Rooms.tsx: корпуса и комнаты, вместимость, доступные места и цена.
- frontend/src/pages/Admissions.tsx: PublicIntake/PublicApplication poll processing with a gradually increasing interval long enough for provider timeout and fill only blank fields; show the local OCR consent separately from optional external OpenRouter consent; show OCR confidence policy, statuses, and retry instructions. Provider request failures have actionable public labels without exposing response bodies. StaffAdmissions shows local and external processing readiness, displays extracted suggestions for human review, and offers a recovery action when an approved application has no linked resident.
- frontend/src/pages/Payments.tsx: регистрация и просмотр оплат, idempotency key на повтор запроса.
- frontend/src/pages/Expenses.tsx: учёт расходов и операторская отмена с причиной.
- frontend/src/pages/Reports.tsx: экспорт CSV/XLSX/PDF и выбор диапазона/группировки.
- frontend/src/pages/Settings.tsx: общие параметры, operator управление ADMIN-аккаунтами, журнал; auditValue и SettingsPage.
- frontend/src/pages/AdminGuide.tsx: узбекское руководство персоналу.
- frontend/src/pages/Landing.tsx: публичная лендинг-страница; DashboardPreview.
- frontend/src/pages/shared.tsx: переиспользуемые PageHeading, Panel, EmptyBlock, Actions.
- frontend/src/styles.css, landing.css, app-overrides.css: базовые стили SPA и лендинга; `app-overrides.css` содержит стили, ограниченные оболочкой `/app`, для центрированного компактного окна, светлой узкой навигации, сетки панели и мобильной компоновки.

## Именной каталог функций

Ниже приведены именованные функции и методы приложения и тестов. Вложенные анонимные callbacks/лямбды React и Python перечисляются в исходнике вместе с контекстом использования. Поиск по имени удобнее всего выполнять rg -n "имя" backend frontend/src.

- backend/app/api.py: endpoint handlers перечислены выше; helpers natural_room_key, page_result, ensure_due_periods, verify_room_capacity, net_payment, get_report_rows, spreadsheet_safe, xlsx_file, pdf_file.
- backend/app/admissions_api.py: route handlers are listed above; helpers `_digest`, `_aware`, `_require_staff`, `_rate_limit`, `_invitation_status`, `_invite_out`, `_event`, `_phone`, `_validate_extra`, `_apply_values`, `_public_application`, `_application`, `_student_session`, `_student_write_session`, `_set_student_session`, `_rotate_csrf`, `_public_campaign`, `_application_status`, `_public_file_out`, `_run_file_extraction`, `_schedule_file_extraction`.
- backend/app/ai_extraction.py: AIExtractionResult, _OCRLine, openrouter_configured, openrouter_processing_issue, openrouter_document_processing_available, document_processing_issue, document_processing_available, local_ocr_available, _normalize_content_type, _validate_file, _image_to_jpeg, _pdf_page_images, _image_payload, _prepare_ocr_image, _tesseract_lines, _label_matches, _clean_ocr_value, _scripted_name_field, _fields_from_ocr_lines, _extract_local_ocr, _normalize_date, _parse_labelled_text, _parse_fields, _provider_failure_status, _post_chat_completion, extract_identity_document. Local Tesseract OCR remains the private default; it uses Uzbek Latin/Cyrillic, English, and Russian models, image normalization, TSV word confidence, labeled-field mapping, and conservative validation. With separate external consent, the configured Dots3-Note Preview free vision model receives normalized JPEG image pages and returns structured field suggestions. Neither OCR text nor document bytes are logged or persisted as OCR text.
- backend/app/audit.py: audit, notify. backend/app/billing.py: period_paid, period_balance, current_period, ensure_period, create_initial_period, extend_period, set_period_dates, mark_paid_and_advance, close_unpaid_future_periods_for_departure.
- backend/app/bootstrap.py: bootstrap. backend/app/config.py: normalize_database_url, Settings.normalize_openrouter_model, Settings.validate_public_app_url, Settings.public_app_base_url, Settings.public_app_origin, Settings.cors_origin_list, get_settings. backend/app/db.py: get_db.
- backend/app/dependencies.py: get_current_user, require_operator, require_billing_permission. backend/app/file_storage.py: sniff_content_type, validate_upload, PrivateFileStorage.backend, configured, _s3, put, local_path, _local_path, signed_download_url, read, delete.
- backend/app/main.py: lifespan, security_headers, validation_error, database_error, root. backend/app/models.py: utcnow; ORM классы User, Room, Resident, BillingPeriod, BillingChange, Payment, Expense, PaymentAdjustment, AuditEvent, Notification, SystemSetting, Dormitory, AdmissionCampaign, AdmissionInvitation, StudentApplication, ApplicationStatusEvent, ApplicationAccessSession, ApplicationFile, ApplicationFileBlob, ResidencePeriod, PublicRateLimit.
- Корневая main.py: запуск uvicorn с app.main:app; настройки запуска DORMFLOW_HOST, DORMFLOW_PORT, DORMFLOW_RELOAD.
- backend/app/purge_expired_files.py: purge_expired_files, main. backend/app/residency.py: assert_room_available, record_room_assignment, close_open_period. backend/app/scheduled_jobs.py: run_daily_jobs, main.
- backend/app/schemas.py: классы и методы-валидаторы перечислены выше и в разделе контрактов; отдельно смотри validate_billing_range, require_one_method, normalized_description_required, normalized_reason_required, nonzero_amount, validate_options, ordered_dates, ordered_stay.
- backend/app/security.py: hash_password, verify_password, create_token, create_token_pair. backend/app/seed.py: main. backend/app/services.py: today_local, room_out, period_out, resident_out, resident_detail, payment_out, notification_out, expense_out, audit_out.
- backend/app/telegram.py: NotificationAdapter.send, TelegramAdapter.__init__, TelegramAdapter.send.
- backend/tests/conftest.py: database, client, operator_token, admin_token. test_admissions.py: _png_bytes, _headers, _workflow, _fill_application и тесты test_admission_approval_creates_resident_billing_and_updates_statistics, test_invitation_uses_public_domain_when_local_setting_is_stale, test_approval_links_matching_resident_without_duplicate_billing, test_approved_application_without_resident_can_be_repaired, test_openrouter_failure_status_mapping_is_actionable_and_safe, test_document_field_parser_accepts_labelled_plain_text_and_nested_json, test_free_vision_model_is_blocked_for_private_identity_documents, test_openrouter_suggestions_require_consent_and_are_private (фоновые статусы, отказ провайдера, прямая маршрутизация OpenRouter, обязательное согласие и повторная обработка), test_rejects_a_forged_image_instead_of_saving_it, test_invitation_pause_resume_revoke_expiry_and_role_access, test_private_application_files_require_staff_auth_and_audit_metadata_only, test_production_file_storage_uses_postgres_and_supports_staff_download_and_delete, test_room_stay_intervals_reject_overlapping_approvals.
- backend/tests/test_billing.py: tday, room, resident, payment_headers, test_arbitrary_period_partial_payment_then_full_payment_stays_paid_until_due, test_payment_without_a_valid_billing_period_is_rejected, test_billing_can_be_configured_later_without_manual_dates, test_explicit_end_date_applies_to_the_current_cycle_and_period_days_roll_forward, test_overpayment_cannot_be_silently_applied, test_extension_is_separate_from_payment_and_preserves_old_dates, test_invalid_billing_dates_are_rejected, test_price_changes_preserve_old_and_new_cycle_amounts.
- backend/tests/test_expenses.py: auth, test_expenses_are_idempotent_audited_and_voided_without_deletion, test_dashboard_and_expense_report_only_include_active_expenses, test_expense_input_rejects_future_dates_and_nonpositive_amount. test_idempotency.py: test_payment_retries_return_the_original_receipt_without_double_counting, test_financial_writes_require_idempotency_keys, test_get_requests_do_not_create_billing_periods_but_daily_job_does.
- backend/tests/test_migrations.py: load_revision, test_migrations_build_and_drop_the_full_schema_and_backfill_rooms. test_notifications.py: test_notifications_are_created_by_job_and_scoped_per_user. test_permissions.py: tday, test_admin_cannot_read_audit_or_manage_users, test_only_operator_can_adjust_historical_payments, test_admin_cannot_extend_billing_when_not_authorized, test_admin_cannot_assign_operator_role, test_room_capacity_cannot_be_exceeded.
- backend/tests/test_reports.py: tday, test_report_formats_return_exports_with_uzbek_headers, test_spreadsheet_exports_neutralize_formula_like_text_but_keep_numeric_values.
- frontend/src/api.ts: saveSession, clearSession, hasSession, errorMessage. frontend/src/auth.tsx: AuthProvider, useAuth. frontend/src/App.tsx: Login, Shell, Protected, Home, OperatorOnly, App.
- frontend/src/locales/uz.ts: moneyToMinorUnits, isPositiveMoney, sumMoney, formatMoney, formatDate, todayUzbekistan, statusLabel, auditActionLabel, auditEntityLabel, auditDetailLabel.
- frontend/src/pages/Dashboard.tsx: Dashboard, Metric, initials, moneyAxis. Dashboard uses only staff-scoped `/api/dashboard`; it presents current hostel data in a compact responsive layout, with recent residents/payments and finance details still visible. The visuals derive from the existing occupancy and revenue fields.
- frontend/src/pages/Admissions.tsx: PublicIntake/PublicApplication poll processing and fill only blank fields; show the local OCR consent separately from optional external OpenRouter consent; show OCR confidence policy, statuses, and retry instructions. StaffAdmissions shows local and external processing readiness and displays extracted suggestions for human review.
- frontend/src/pages/Residents.tsx: cleanDate, statusTag, Residents. Settings.tsx: auditValue, SettingsPage. Также экспортируются компоненты Expenses, Payments, Reports, Rooms, AdminGuide и общие компоненты PageHeading, Panel, EmptyBlock, Actions.

## Данные и миграции

Актуальные столбцы/связи смотрите в backend/app/models.py; валидируемые DTO — в backend/app/schemas.py. Цепочка Alembic:

1. 0001_initial.py (0001_initial) — исходные сотрудники, комнаты, жители, периоды, платежи, аудит, настройки.
2. 16f28cfa0755_admission_and_residency_workflow.py — корпуса, кампании, приглашения, заявки, сессии, файлы и даты проживания.
3. 20261026_01_financial_controls_and_expenses.py — финансовые ограничения, идемпотентность, корректировки и расходы.
4. 20261026_02_application_file_ocr.py — промежуточные поля OCR.
5. 20261026_03_postgres_application_file_blobs.py — приватные файловые blobs в PostgreSQL.
6. 20261027_01_resident_departures.py — дата выезда.
7. 20261028_01_openrouter_document_extraction.py — согласие на ИИ-обработку и структурированные предложения; удаление полей сохранённого OCR-текста.

Всегда добавляйте новую Alembic-ревизию, проверяйте upgrade/downgrade на поддерживаемых PostgreSQL и SQLite тестовой схеме; не переписывайте применённую миграцию без явного плана восстановления.

Document extraction changes do not require a schema migration. `ApplicationFile.ai_status` (`String(24)`) stores `PROCESSING`, `COMPLETED`, `NO_FIELDS`, `OCR_NOT_CONFIGURED`, `OCR_FAILED`, `OCR_TIMEOUT`, provider categories, and legacy statuses. `PublicCampaignOut` reports local and external readiness. Local OCR requires explicit applicant consent; external processing additionally requires `X-External-AI-Consent` and uses the configured Dots3-Note Preview free vision model. OCR text is transient, only validated field suggestions are stored, and applicants must verify them manually. No OCR engine can guarantee 100% accuracy.

## Тесты и запуск проверок

| Файл | Что покрывает |
| --- | --- |
| backend/tests/conftest.py | SQLite в памяти, TestClient, оператор и ADMIN фикстуры. |
| test_permissions.py | запреты ADMIN для аккаунтов, аудита, корректировки истории, изменение роли и вместимость. |
| test_billing.py | частичная/полная оплата, произвольные интервалы, тариф, продление и ошибки периода. |
| test_idempotency.py | обязательный ключ и безопасный повтор платежа, отсутствие побочных записей в GET; job создаёт rollover явно. |
| test_expenses.py | идемпотентность, аудит, void без удаления, отчётность и валидация суммы/даты. |
| test_admissions.py | одобрение, связи жителя, кампании/приглашения, приватные файлы, хранение, дубли, сессии заявителя, фоновые AI-статусы, безопасная классификация HTTP-ошибок провайдера, согласие и повтор обработки, parsing labelled text/nested JSON extraction responses. |
| test_notifications.py | адресность уведомлений и создание планировщиком. |
| test_reports.py | CSV/XLSX/PDF и защита spreadsheet от formula injection. |
| test_migrations.py | построение и обратное удаление схемы и миграционный backfill. |

Verification for the local OCR changes: Python `py_compile` passed; frontend TypeScript `tsc --noEmit` and Vite production build passed (existing warning: one chunk is over 500 kB). Backend tests were not run. Tesseract and Docker are unavailable in this Windows environment, so the OCR engine and Docker image were not executed here; OCR quality still needs evaluation with synthetic, non-personal samples.

Document extraction reliability update (2026-10-30): the external request now allows 6,000 completion tokens and 120 seconds, `_parse_fields` falls back through `_parse_labelled_text` to locally validated labelled text when the model does not return the expected JSON shape, and the applicant page polls at a gradually increasing interval. `py_compile`, frontend TypeScript, Vite production build, and `backend/tests/test_admissions.py` passed (14 tests; test fixtures use in-memory SQLite); Vite reported the existing large-chunk warning. Two stale status expectations in admission tests were aligned with the existing safe status mapping. No schema or route changes.

Dashboard visual refinement (2026-10-30): frontend TypeScript `tsc --noEmit -p tsconfig.json` and Vite production build passed; Vite reported the existing large-chunk warning. A fresh browser screenshot and reference comparison could not be completed: automatic review rejected launching headless Edge at the local dev URL, so rendered visual verification remains outstanding. The dashboard retains the existing staff-authorized API and data; no backend tests or schema changes apply.

Admission resident-link recovery (2026-10-30): `approve_application` now repairs a legacy/already-approved application whose resident link is missing, retaining its approved status and original terminal date and writing `APPLICATION_RESIDENT_LINKED` audit metadata. StaffAdmissions exposes the action and prompts staff to select a matching resident or create one; a deep-linked resident card remains editable even when the active-list filter hides it. The regression coverage checks departed-resident reactivation and list visibility, plus idempotent orphan-link repair, preserved approval date, room stay, billing, and audit. No schema or migration change. Verification: full backend suite passed (38 tests, including 15 admissions tests); TypeScript typecheck passed; Vite production build passed with the existing large-chunk warning; `git diff --check` and `py_compile` passed. PowerShell blocked the npm launcher, so typecheck/build used the installed Node executable directly.

Local API startup (2026-10-30): corrected root `main.py` default port from 8001 to 8000 to match README and the Vite `/api` proxy; `DORMFLOW_PORT` remains an override.

Financial write retry safety (2026-10-30): `create_payment` and `create_expense` now reject requests without `Idempotency-Key` before writing; the payment concurrency-recovery check also compares an explicitly selected `billing_period_id`. First-party payment and expense forms already send UUID keys. Added `test_financial_writes_require_idempotency_keys` and updated isolated write tests to send keys. No schema or migration change.

## Конфигурация и развёртывание

- Имена переменных и примеры: .env.example; реальные значения — только в частной среде. Не открывайте корневой .env для индексирования.
- backend/app/config.py: ENVIRONMENT, DATABASE_URL, JWT_SECRET, ACCESS_TOKEN_MINUTES, REFRESH_TOKEN_DAYS, TIMEZONE, ADMINS_CAN_ADJUST_BILLING, CORS_ORIGINS, PUBLIC_APP_URL, FILE_*, OPENROUTER_*, S3_*, TESSERACT_CMD. `TESSERACT_CMD` optionally overrides the local OCR executable; Docker installs the OCR engine and required language packs.
- Docker: docker-compose.yml; backend/Dockerfile; frontend/Dockerfile, frontend/nginx.conf.
- Netlify: netlify.toml и frontend/scripts/write-netlify-redirects.mjs; приватный API origin задаётся переменной RAILWAY_API_URL среды сборки.
- Railway: `.railway/railway.ts` provisions PostgreSQL, API, and cleanup jobs, sets the Dots3-Note Preview OpenRouter model, preserves the server-side `OPENROUTER_API_KEY`, and sets `TESSERACT_CMD`; the backend Dockerfile installs Tesseract and its language packs.
- Вспомогательные: backend/requirements.txt, frontend/package.json/package-lock.json, frontend/.nvmrc, frontend/vite.config.ts, frontend/tsconfig*.json, backend/alembic.ini, backend/alembic/env.py, backend/alembic/script.py.mako.
- backend/alembic/env.py: run_migrations_offline, run_migrations_online; в каждой ревизии есть upgrade и downgrade.
- Редактор: .vscode/settings.json. Корневая main.py запускает backend-приложение и читает DORMFLOW_HOST, DORMFLOW_PORT и DORMFLOW_RELOAD; порт по умолчанию — 8000, совпадает с README и proxy frontend/vite.config.ts. Порт можно переопределить через DORMFLOW_PORT.

## Полный список исходников

Ниже перечислены сопровождаемые исходные файлы, а не генерируемые каталоги node_modules, dist, .venv и кэши:

- Корень: AGENTS.md, README.md, amain.txt, docker-compose.yml, netlify.toml, main.py, .env.example, .gitignore.
- Backend app: backend/app/__init__.py, admissions_api.py, ai_extraction.py, api.py, audit.py, billing.py, bootstrap.py, config.py, db.py, dependencies.py, file_storage.py, main.py, models.py, purge_expired_files.py, residency.py, scheduled_jobs.py, schemas.py, security.py, seed.py, services.py, telegram.py.
- Alembic: backend/alembic.ini, backend/alembic/env.py, backend/alembic/script.py.mako и семь ревизий, перечисленных в разделе миграций.
- Backend tests: backend/tests/__init__.py, conftest.py, test_admissions.py, test_billing.py, test_expenses.py, test_idempotency.py, test_migrations.py, test_notifications.py, test_permissions.py, test_reports.py.
- Frontend root: frontend/Dockerfile, .dockerignore, .nvmrc, index.html, nginx.conf, package.json, package-lock.json, tsconfig.json, tsconfig.node.json, vite.config.ts.
- Frontend scripts/source: frontend/scripts/write-netlify-redirects.mjs; frontend/src/App.tsx, api.ts, app-overrides.css, auth.tsx, landing.css, main.tsx, styles.css, types.ts, locales/uz.ts; страницы AdminGuide.tsx, Admissions.tsx, Dashboard.tsx, Expenses.tsx, Landing.tsx, Payments.tsx, Reports.tsx, Residents.tsx, Rooms.tsx, Settings.tsx, shared.tsx.
- Deploy/docs/editor: scripts/deploy-netlify.ps1, scripts/deploy-railway.ps1, .railway/package.json, package-lock.json, railway.ts, docs/PROJECT_INDEX.md, docs/PROJECT_PROMPTS.md, .vscode/settings.json.
- Корневой .env и dormflow-local.sqlite3 игнорируются и намеренно не индексируются; не добавляйте их содержимое сюда.

## Обновление индекса при каждом изменении

По запросу владельца проекта, не пропускайте документацию: вместе с любой новой функцией, фиксой или конфигурацией обновите этот файл в той же задаче. Запишите каждый добавленный/переименованный/удалённый endpoint и функцию (с точкой входа и ролью), изменение схемы/миграции, новый экран или маршрут, изменённый межслойный поток, внешний сервис, переменную конфигурации и соответствующее покрытие проверок. Уточните инвентарь файлов и затронутые разделы. При изменении существующего поведения исправьте описание старого поведения; не оставляйте противоречивые устаревшие заметки. Ничего не копируйте из .env, секретов, персональных данных и документов. В финальном ответе назовите индексированные изменения и проверки.
