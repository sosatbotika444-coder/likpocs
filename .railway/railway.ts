import {
  defineRailway,
  github,
  postgres,
  preserve,
  project,
  service,
} from 'railway/iac';

const repo = 'sosatbotika444-coder/likpocs';

export default defineRailway(() => {
  const db = postgres('dormflow-postgres');

  const api = service('dormflow-api', {
    source: github(repo, { branch: 'main', rootDirectory: 'backend' }),
    healthcheck: '/api/health',
    healthcheckTimeout: 300,
    env: {
      DATABASE_URL: db.env.DATABASE_URL,
      ENVIRONMENT: 'production',
      TIMEZONE: 'Asia/Tashkent',
      CORS_ORIGINS: '',
      PUBLIC_APP_URL: 'https://dormflows.netlify.app',
      FILE_STORAGE_BACKEND: 'postgres',
      FILE_RETENTION_DAYS: '365',
      TESSERACT_CMD: 'tesseract',
      OPENROUTER_ENABLED: 'true',
      OPENROUTER_MODEL: 'dots-studio/dots-3-note-preview:free',
      OPENROUTER_API_KEY: preserve(),
      JWT_SECRET: process.env.DORMFLOW_RAILWAY_JWT_SECRET || preserve(),
      INITIAL_OPERATOR_EMAIL: process.env.DORMFLOW_INITIAL_OPERATOR_EMAIL || preserve(),
      INITIAL_OPERATOR_PASSWORD: process.env.DORMFLOW_INITIAL_OPERATOR_PASSWORD || preserve(),
      INITIAL_OPERATOR_NAME: process.env.DORMFLOW_INITIAL_OPERATOR_NAME || 'Yotoqxona operatori',
      // Optional extra accounts, created once at start-up when both email and password are set.
      INITIAL_ADMIN_EMAIL: process.env.DORMFLOW_INITIAL_ADMIN_EMAIL || preserve(),
      INITIAL_ADMIN_PASSWORD: process.env.DORMFLOW_INITIAL_ADMIN_PASSWORD || preserve(),
      INITIAL_INVESTOR_EMAIL: process.env.DORMFLOW_INITIAL_INVESTOR_EMAIL || preserve(),
      INITIAL_INVESTOR_PASSWORD: process.env.DORMFLOW_INITIAL_INVESTOR_PASSWORD || preserve(),
      TELEGRAM_BOT_TOKEN: preserve(),
      TELEGRAM_BOT_USERNAME: preserve(),
    },
  });

  // aiogram long-polling worker: no public port, shares the API image and database.
  const telegramBot = service('dormflow-telegram-bot', {
    source: github(repo, { branch: 'main', rootDirectory: 'backend' }),
    deploy: {
      startCommand: 'python -m app.telegram_bot',
      restartPolicyType: 'ALWAYS',
    },
    env: {
      DATABASE_URL: db.env.DATABASE_URL,
      ENVIRONMENT: 'production',
      TIMEZONE: 'Asia/Tashkent',
      PUBLIC_APP_URL: 'https://dormflows.netlify.app',
      FILE_STORAGE_BACKEND: 'postgres',
      FILE_RETENTION_DAYS: '365',
      JWT_SECRET: process.env.DORMFLOW_RAILWAY_JWT_SECRET || preserve(),
      TELEGRAM_BOT_TOKEN: preserve(),
      TELEGRAM_BOT_USERNAME: preserve(),
    },
  });

  const dailyJobs = service('dormflow-daily-jobs', {
    source: github(repo, { branch: 'main', rootDirectory: 'backend' }),
    deploy: {
      startCommand: 'python -m app.scheduled_jobs',
      cronSchedule: '0 0 * * *',
      restartPolicyType: 'ON_FAILURE',
      restartPolicyMaxRetries: 2,
    },
    env: {
      DATABASE_URL: db.env.DATABASE_URL,
      ENVIRONMENT: 'production',
      TIMEZONE: 'Asia/Tashkent',
      FILE_STORAGE_BACKEND: 'postgres',
      FILE_RETENTION_DAYS: '365',
      TELEGRAM_BOT_TOKEN: preserve(),
    },
  });

  const fileCleanup = service('dormflow-file-cleanup', {
    source: github(repo, { branch: 'main', rootDirectory: 'backend' }),
    deploy: {
      startCommand: 'python -m app.purge_expired_files --batch-size 100',
      cronSchedule: '30 0 * * *',
      restartPolicyType: 'ON_FAILURE',
      restartPolicyMaxRetries: 2,
    },
    env: {
      DATABASE_URL: db.env.DATABASE_URL,
      ENVIRONMENT: 'production',
      TIMEZONE: 'Asia/Tashkent',
      FILE_STORAGE_BACKEND: 'postgres',
      FILE_RETENTION_DAYS: '365',
    },
  });

  return project('DormFlow', { resources: [api, telegramBot, dailyJobs, fileCleanup, db] });
});
