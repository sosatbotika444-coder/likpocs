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
      OCR_ENABLED: 'true',
      OCR_LANGUAGES: 'uzb+uzb_cyrl+eng+rus',
      JWT_SECRET: process.env.DORMFLOW_RAILWAY_JWT_SECRET || preserve(),
      INITIAL_OPERATOR_EMAIL: process.env.DORMFLOW_INITIAL_OPERATOR_EMAIL || preserve(),
      INITIAL_OPERATOR_PASSWORD: process.env.DORMFLOW_INITIAL_OPERATOR_PASSWORD || preserve(),
      INITIAL_OPERATOR_NAME: process.env.DORMFLOW_INITIAL_OPERATOR_NAME || 'Yotoqxona operatori',
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

  return project('DormFlow', { resources: [api, dailyJobs, fileCleanup, db] });
});
