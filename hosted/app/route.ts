import { getChatGPTUser, chatGPTSignInPath } from './chatgpt-auth';
import registerHtml from '../ui/register.html?raw';

export const dynamic = 'force-dynamic';

export async function GET() {
  const user = await getChatGPTUser();
  if (!user) {
    return new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>1930 Helpline Register</title><style>body{margin:0;background:#f5f7fa;color:#193047;font:15px/1.6 "Segoe UI",Arial,sans-serif;display:grid;place-items:center;min-height:100dvh}main{background:white;border:1px solid #e2e8ef;border-radius:14px;padding:36px;max-width:390px;margin:20px;text-align:center}.brand{display:inline-block;background:#112a43;color:white;border-radius:9px;padding:5px 13px;font-size:28px;font-weight:800}h1{font-size:23px;margin:22px 0 10px}p{color:#697a8b;font-size:13px}a{display:block;margin-top:24px;background:#1763d5;border-radius:7px;color:white;padding:12px 20px;font-weight:600;text-decoration:none}a:focus-visible{outline:3px solid #112a43;outline-offset:3px}</style></head><body><main><div class="brand">1930</div><h1>Open your private register</h1><p>Sign in to view your records and record a new call.</p><a href="${chatGPTSignInPath('/')}" target="_top">Sign in to your register</a></main></body></html>`, {headers: {'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'}});
  }
  return new Response(registerHtml, {
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'no-referrer',
    },
  });
}
