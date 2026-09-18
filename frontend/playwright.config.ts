import {defineConfig} from '@playwright/test'
export default defineConfig({testDir:'./e2e',fullyParallel:false,workers:1,timeout:60000,use:{baseURL:'http://127.0.0.1:5173',channel:'msedge',trace:'retain-on-failure'},reporter:[['list'],['html',{open:'never'}]],webServer:[{command:'..\\backend\\.venv\\Scripts\\python.exe ..\\backend\\manage.py runserver 127.0.0.1:8017 --noreload',url:'http://127.0.0.1:8017/api/v1/health/',reuseExistingServer:true},{command:'npm run dev',url:'http://127.0.0.1:5173',reuseExistingServer:true}]})

