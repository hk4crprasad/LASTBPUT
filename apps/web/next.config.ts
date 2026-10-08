import type { NextConfig } from 'next';
const config:NextConfig={experimental:{proxyTimeout:180000},async rewrites(){return [{source:'/api/:path*',destination:`${process.env.API_INTERNAL_URL||'http://localhost:8000'}/api/:path*`}]}};
export default config;
