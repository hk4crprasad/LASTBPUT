import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',timeout:90000,expect:{timeout:15000},fullyParallel:false,workers:1,use:{baseURL:process.env.E2E_BASE_URL||'http://localhost:3000',headless:true,screenshot:'only-on-failure',trace:'retain-on-failure'},reporter:[['list'],['html',{open:'never'}]],projects:[{name:'chromium',use:{browserName:'chromium'}}]});
