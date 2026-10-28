import { env } from 'cloudflare:workers';
import { getChatGPTUser } from '../../chatgpt-auth';
// @ts-expect-error JavaScript core is tested independently against SQLite.
import { handleApi } from '../../../lib/register-core.mjs';

export const dynamic = 'force-dynamic';

async function handle(request: Request) {
  const user = await getChatGPTUser();
  const admins = new Set((env.HELPLINE_ADMIN_EMAILS ?? '').split(',').map(value => value.trim().toLowerCase()).filter(Boolean));
  const isAdmin = Boolean(user && admins.has(user.email.toLowerCase()));
  return handleApi(request, env.DB, user?.email ?? null, user?.displayName ?? null, isAdmin);
}

export { handle as GET, handle as POST, handle as PATCH, handle as PUT, handle as DELETE };
