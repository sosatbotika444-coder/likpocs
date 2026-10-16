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
      JWT_SECRET: process.env.DORMFLOW_RAILWAY_JWT_SECRET || preserve(),
      INITIAL_OPERATOR_EMAIL: process.env.DORMFLOW_INITIAL_OPERATOR_EMAIL || preserve(),
      INITIAL_OPERATOR_PASSWORD: process.env.DORMFLOW_INITIAL_OPERATOR_PASSWORD || preserve(),
      INITIAL_OPERATOR_NAME: process.env.DORMFLOW_INITIAL_OPERATOR_NAME || 'Yotoqxona operatori',
    },
  });

  return project('DormFlow', { resources: [api, db] });
});
