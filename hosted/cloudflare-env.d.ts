declare namespace Cloudflare {
  interface Env {
    DB?: D1Database;
    HELPLINE_ADMIN_EMAILS?: string;
    BUCKET?: R2Bucket;
  }
}
