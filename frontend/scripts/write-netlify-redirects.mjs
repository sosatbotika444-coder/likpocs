import { writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const configuredUrl = process.env.RAILWAY_API_URL;
if (!configuredUrl) {
  throw new Error('Netlify sozlamalariga RAILWAY_API_URL (masalan, https://dormflow-api.up.railway.app) kiriting.');
}

let apiOrigin;
try {
  const parsed = new URL(configuredUrl);
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.pathname !== '/' || parsed.search || parsed.hash) {
    throw new Error('URL faqat HTTPS origin bo‘lishi kerak, yo‘l yoki maxfiy ma’lumot bo‘lmasin.');
  }
  apiOrigin = parsed.origin;
} catch (error) {
  throw new Error(`RAILWAY_API_URL noto‘g‘ri. HTTPS manzilini kiriting. ${error.message}`);
}

const redirects = [
  `/api/* ${apiOrigin}/api/:splat 200!`,
  '/* /index.html 200',
  '',
].join('\n');

await writeFile(resolve('dist', '_redirects'), redirects, 'utf8');
console.log('Netlify API proxy va SPA yo‘naltirishlari tayyor.');
