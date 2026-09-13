<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="login-logo">SO</div>
      <h1 class="login-title">Sedna Ops</h1>
      <p class="login-sub">L2 VMS Support — Operations Hub</p>

      <div v-if="checking" class="login-msg">Checking…</div>

      <template v-else-if="!authEnabled">
        <!-- Dev mode: no Google credentials configured -->
        <div class="login-dev-banner">Dev mode — auth not configured</div>
        <p class="login-hint">Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to enable Google sign-in.</p>
        <button class="btn login-btn" @click="devBypass">Enter (dev mode)</button>
      </template>

      <template v-else>
        <div v-if="errorMsg" class="login-error">{{ errorMsg }}</div>
        <a class="login-google-btn" href="/api/auth/google">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M17.64 9.2c0-.637-.057-1.25-.164-1.84H9v3.48h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908C16.658 14.145 17.64 11.88 17.64 9.2Z" fill="#4285F4"/>
            <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.859-3.048.859-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18Z" fill="#34A853"/>
            <path d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332Z" fill="#FBBC05"/>
            <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58Z" fill="#EA4335"/>
          </svg>
          Sign in with Google
        </a>
        <p class="login-hint">Only <strong>@sedna.com</strong> accounts are allowed.</p>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { api } from '@/api/client'

const router = useRouter()
const route = useRoute()

const authEnabled = ref(true)
const checking = ref(true)
const errorMsg = ref('')

const ERROR_MESSAGES: Record<string, string> = {
  access_denied:         'You cancelled the sign-in.',
  domain_not_allowed:    'Only @sedna.com accounts can access Sedna Ops.',
  invalid_state:         'Sign-in session expired. Please try again.',
  token_exchange_failed: 'Authentication failed. Please try again.',
  userinfo_failed:       'Could not retrieve account info. Please try again.',
}

onMounted(async () => {
  const err = route.query.error as string
  if (err) errorMsg.value = ERROR_MESSAGES[err] ?? 'Sign-in failed. Please try again.'

  try {
    const res = await api.health()
    authEnabled.value = res.data.auth_enabled ?? true
  } catch { /* leave authEnabled true */ } finally {
    checking.value = false
  }
})

function devBypass() {
  // In dev mode (no Google creds), let the user in without a token.
  // The backend also skips auth checks when GOOGLE_CLIENT_ID is unset.
  localStorage.removeItem('so_token')
  router.push('/')
}
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
}

.login-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px 48px;
  background: var(--surface);
  border: 1px solid var(--border2);
  border-radius: 16px;
  box-shadow: 0 24px 60px rgba(0,0,0,.35);
  width: 340px;
  max-width: 95vw;
}

.login-logo {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--accent);
  color: #fff;
  font-size: 18px;
  font-weight: 900;
  display: flex;
  align-items: center;
  justify-content: center;
  letter-spacing: -.02em;
  margin-bottom: 4px;
}

.login-title {
  font-size: 20px;
  font-weight: 800;
  color: var(--text);
  margin: 0;
}

.login-sub {
  font-size: 11px;
  color: var(--text3);
  margin: 0 0 8px;
  text-align: center;
}

.login-google-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  background: var(--surface2);
  border: 1px solid var(--border2);
  border-radius: 8px;
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  transition: background .15s, border-color .15s;
  width: 100%;
  justify-content: center;
}
.login-google-btn:hover {
  background: var(--border);
  border-color: var(--accent);
}

.login-hint {
  font-size: 10px;
  color: var(--text3);
  text-align: center;
  margin: 0;
}

.login-error {
  width: 100%;
  padding: 9px 12px;
  background: rgba(255,80,80,.1);
  border: 1px solid rgba(255,80,80,.3);
  border-radius: 6px;
  font-size: 11px;
  color: var(--red);
  text-align: center;
}

.login-dev-banner {
  padding: 6px 12px;
  background: rgba(255,180,40,.12);
  border: 1px solid rgba(255,180,40,.3);
  border-radius: 6px;
  font-size: 10px;
  font-weight: 700;
  color: var(--amber);
  letter-spacing: .05em;
  text-transform: uppercase;
}

.login-msg {
  font-size: 11px;
  color: var(--text3);
}

.login-btn {
  width: 100%;
}
</style>
