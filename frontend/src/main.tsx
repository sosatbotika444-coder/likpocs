import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import uzUZ from 'antd/locale/uz_UZ';
import dayjs from 'dayjs';
import 'dayjs/locale/uz';
import 'antd/dist/reset.css';
import './styles.css';
import App from './App';
import { AuthProvider } from './auth';

dayjs.locale('uz');

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider locale={uzUZ} theme={{ token: { colorPrimary: '#255744', colorInfo: '#255744', borderRadius: 8, fontFamily: "'DM Sans', sans-serif", colorBgLayout: '#f6f7f3', controlHeight: 38 }, components: { Layout: { siderBg: '#183a31', headerBg: '#ffffff' }, Menu: { darkItemBg: '#183a31', darkItemSelectedBg: '#2a5947', darkItemHoverBg: '#234b3d' } } }}>
      <AuthProvider><BrowserRouter><App /></BrowserRouter></AuthProvider>
    </ConfigProvider>
  </StrictMode>,
);
